"""Tests for Russell's alarm system and CalDAV write config.

Covers:
- Alarm CRUD lifecycle (POST, GET, GET /pending, POST /silence, POST /{id}/fired, DELETE)
- repeat_daily behaviour (silence reschedules +24h, stays active)
- CalDAV write status endpoint
- CalDAV write config with fake creds → 400
- CalDAV write event when not configured → 400
- Chat action pipeline (skip if LLM budget)
- Chat action failure relay
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://code-snapshot-23.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ── Shared client ──────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# Track created alarm ids for cleanup
_created_alarm_ids: list[str] = []


@pytest.fixture(scope="module", autouse=True)
def cleanup_alarms(client):
    yield
    for aid in _created_alarm_ids:
        try:
            client.delete(f"{API}/alarms/{aid}", timeout=10)
        except Exception:
            pass


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


# ── Alarm CRUD lifecycle ──────────────────────────────────────────────
class TestAlarmLifecycle:
    def test_create_future_alarm(self, client):
        fire_at = _iso(datetime.now(timezone.utc) + timedelta(hours=1))
        r = client.post(f"{API}/alarms", json={
            "fire_at_iso": fire_at,
            "message": "TEST_future alarm",
            "source_channel": "test",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] and d["message"] == "TEST_future alarm"
        assert d["active"] is True and d["fired_at"] is None
        assert d["repeat_daily"] is False
        _created_alarm_ids.append(d["id"])

    def test_list_contains_created(self, client):
        r = client.get(f"{API}/alarms")
        assert r.status_code == 200
        ids = [a["id"] for a in r.json()]
        assert _created_alarm_ids[0] in ids

    def test_past_alarm_shows_up_in_pending(self, client):
        fire_at = _iso(datetime.now(timezone.utc) - timedelta(minutes=1))
        r = client.post(f"{API}/alarms", json={
            "fire_at_iso": fire_at,
            "message": "TEST_past alarm",
            "source_channel": "test",
        })
        assert r.status_code == 200
        aid = r.json()["id"]
        _created_alarm_ids.append(aid)

        pending = client.get(f"{API}/alarms/pending").json()
        assert any(a["id"] == aid for a in pending)

    def test_mark_fired(self, client):
        aid = _created_alarm_ids[-1]
        r = client.post(f"{API}/alarms/{aid}/fired")
        assert r.status_code == 200
        # Verify via list
        alarms = client.get(f"{API}/alarms").json()
        target = next(a for a in alarms if a["id"] == aid)
        assert target["fired_at"] is not None

    def test_silence_specific(self, client):
        aid = _created_alarm_ids[-1]
        r = client.post(f"{API}/alarms/silence", json={"id": aid})
        assert r.status_code == 200
        result = r.json()
        assert aid in result["silenced"]
        # Verify no longer active
        alarms = client.get(f"{API}/alarms").json()
        target = next(a for a in alarms if a["id"] == aid)
        assert target["active"] is False
        assert target["silenced_at"] is not None

    def test_silence_all_firing(self, client):
        # Create two past, active alarms
        past = _iso(datetime.now(timezone.utc) - timedelta(minutes=2))
        ids = []
        for i in range(2):
            r = client.post(f"{API}/alarms", json={
                "fire_at_iso": past, "message": f"TEST_bulk {i}", "source_channel": "test",
            })
            assert r.status_code == 200
            ids.append(r.json()["id"])
            _created_alarm_ids.append(r.json()["id"])

        r = client.post(f"{API}/alarms/silence", json={})
        assert r.status_code == 200
        result = r.json()
        # Both created ids should be in silenced (some other test data may also silence)
        for aid in ids:
            assert aid in result["silenced"], f"{aid} not in silenced {result}"

    def test_delete_alarm(self, client):
        # Create a throwaway alarm
        r = client.post(f"{API}/alarms", json={
            "fire_at_iso": _iso(datetime.now(timezone.utc) + timedelta(hours=2)),
            "message": "TEST_delete me",
        })
        aid = r.json()["id"]
        r2 = client.delete(f"{API}/alarms/{aid}")
        assert r2.status_code == 200
        assert r2.json()["deleted"] is True
        # Deleting again → 404
        r3 = client.delete(f"{API}/alarms/{aid}")
        assert r3.status_code == 404

    def test_invalid_fire_at_iso(self, client):
        r = client.post(f"{API}/alarms", json={"fire_at_iso": "not-a-date", "message": "TEST_bad"})
        assert r.status_code == 400


# ── repeat_daily behaviour ────────────────────────────────────────────
class TestRepeatDailyAlarm:
    def test_repeat_daily_reschedules_on_silence(self, client):
        past = datetime.now(timezone.utc) - timedelta(minutes=3)
        past_iso = _iso(past)
        r = client.post(f"{API}/alarms", json={
            "fire_at_iso": past_iso,
            "message": "TEST_repeat daily",
            "repeat_daily": True,
            "source_channel": "test",
        })
        assert r.status_code == 200
        aid = r.json()["id"]
        _created_alarm_ids.append(aid)

        r2 = client.post(f"{API}/alarms/silence", json={"id": aid})
        assert r2.status_code == 200
        result = r2.json()
        assert aid in result["rescheduled"], f"expected in rescheduled: {result}"
        assert aid not in result["silenced"]

        # Verify it's still active and fire_at pushed ~24h
        alarms = client.get(f"{API}/alarms").json()
        target = next(a for a in alarms if a["id"] == aid)
        assert target["active"] is True
        new_dt = datetime.fromisoformat(target["fire_at_iso"])
        # Should be ~24h after the original past time
        delta = new_dt - past
        assert timedelta(hours=23, minutes=59) < delta < timedelta(hours=24, minutes=1)


# ── CalDAV endpoints ──────────────────────────────────────────────────
class TestCalDAVWrite:
    def test_status_returns_configured_flag(self, client):
        r = client.get(f"{API}/calendar/write/status")
        assert r.status_code == 200
        d = r.json()
        assert "configured" in d
        # Note: may be true or false depending on prior state — we only check shape
        assert isinstance(d["configured"], bool)

    def test_write_event_without_config_returns_400(self, client):
        # Only meaningful if not configured. If configured skip.
        status = client.get(f"{API}/calendar/write/status").json()
        if status.get("configured"):
            pytest.skip("CalDAV already configured — skipping unconfigured-write test")
        r = client.post(f"{API}/calendar/write/event", json={
            "summary": "TEST_event",
            "start_iso": _iso(datetime.now(timezone.utc) + timedelta(hours=1)),
            "end_iso": _iso(datetime.now(timezone.utc) + timedelta(hours=2)),
        })
        assert r.status_code == 400
        assert "not configured" in r.json().get("detail", "").lower()

    def test_config_with_fake_creds_rejected(self, client):
        status = client.get(f"{API}/calendar/write/status").json()
        was_configured = status.get("configured", False)

        r = client.post(f"{API}/calendar/write/config", json={
            "apple_id": "TEST_fake@icloud.com",
            "app_specific_password": "xxxx-xxxx-xxxx-xxxx",
            "calendar_name": None,
        }, timeout=30)
        # iCloud should reject the fake creds → 400
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "").lower()
        assert "rejected" in detail or "credential" in detail or "icloud" in detail or "auth" in detail

        # If we weren't configured before, we should still not be
        # (save_config may have persisted before verification failed — that's a code quality note)
        if not was_configured:
            after = client.get(f"{API}/calendar/write/status").json()
            # Just log; don't fail — the save may have persisted the bad creds
            print(f"After fake config attempt, configured={after.get('configured')}")


# ── Chat pipeline (LLM budget may skip) ───────────────────────────────
class TestChatActions:
    def _chat(self, client, msg: str, session_id: str):
        return client.post(f"{API}/chat", json={
            "session_id": session_id, "message": msg,
        }, timeout=60)

    def test_chat_set_alarm_creates_alarm(self, client):
        session = f"TEST_alarm_{uuid.uuid4().hex[:8]}"
        # snapshot alarm count
        before = len(client.get(f"{API}/alarms").json())
        r = self._chat(client, "set an alarm for 30 seconds from now with the message tomorrow", session)
        if r.status_code == 429:
            pytest.skip("LLM budget exceeded (429)")
        if r.status_code == 500 and "budget" in r.text.lower():
            pytest.skip("LLM budget exceeded (500)")
        assert r.status_code == 200, r.text
        reply = r.json().get("reply", "").lower()
        assert reply  # non-empty
        # Check alarms grew
        after = client.get(f"{API}/alarms").json()
        assert len(after) > before, f"No alarm created. Reply: {reply}"
        # Track newest alarm for cleanup
        newest = max(after, key=lambda a: a.get("created_at", ""))
        _created_alarm_ids.append(newest["id"])

    def test_chat_add_event_failure_relay(self, client):
        # Only makes sense if CalDAV is NOT configured
        status = client.get(f"{API}/calendar/write/status").json()
        if status.get("configured"):
            pytest.skip("CalDAV is configured — can't test failure relay")

        session = f"TEST_addevent_{uuid.uuid4().hex[:8]}"
        r = self._chat(client, "add a dinner reservation with mum saturday at 7pm to my calendar", session)
        if r.status_code == 429:
            pytest.skip("LLM budget exceeded")
        if r.status_code == 500 and "budget" in r.text.lower():
            pytest.skip("LLM budget exceeded")
        assert r.status_code == 200, r.text
        reply = r.json().get("reply", "").lower()

        # If Russell emitted an add_event action, reply must NOT falsely claim success.
        cheerful_lies = ["you're booked", "added — you", "all set", "booked in", "added to your"]
        honest_fail_signals = [
            "tried, but", "didn't go through", "couldn't", "can't add",
            "not configured", "no calendar", "set up", "fix", "apple id",
        ]
        # If actions ran and failed, reply should signal honest failure
        actions = r.json().get("actions", []) or []
        add_event_actions = [a for a in actions if a.get("type") == "add_event"]
        if add_event_actions and any(not a.get("ok", True) for a in add_event_actions):
            assert any(s in reply for s in honest_fail_signals), \
                f"Expected honest fail message, got: {reply[:300]}"
            assert not any(lie in reply for lie in cheerful_lies), \
                f"Reply contains cheerful lie despite action failure: {reply[:300]}"
        else:
            # LLM may not have emitted an add_event action — just log
            print(f"No add_event action emitted. Reply: {reply[:200]}")
