"""Phase Autopilot tests — status, config, persona, topics, run-now, youtube gate."""
import os
import time
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"


# ── status ───────────────────────────────────────────────────────────────
def test_autopilot_status_shape():
    r = requests.get(f"{API}/autopilot/status", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "enabled" in d and isinstance(d["enabled"], bool)
    cfg = d["config"]
    assert cfg["publish_time_local"] == "07:00"
    assert cfg["timezone"] == "Australia/Sydney"
    assert cfg["duration_seconds"] == 30
    # next_run_local parses & is in future
    from datetime import datetime
    nxt = datetime.fromisoformat(d["next_run_local"])
    assert nxt.timestamp() > time.time()
    assert isinstance(d["persona_ready"], bool)


# ── config ───────────────────────────────────────────────────────────────
def test_autopilot_config_update_and_validate():
    # Get
    r = requests.get(f"{API}/autopilot/config", timeout=10)
    assert r.status_code == 200
    # Update to 12:30
    r = requests.post(f"{API}/autopilot/config", json={"publish_time_local": "12:30"}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["publish_time_local"] == "12:30"
    # Invalid
    r = requests.post(f"{API}/autopilot/config", json={"publish_time_local": "25:99"}, timeout=10)
    assert r.status_code == 400
    # Reset
    r = requests.post(f"{API}/autopilot/config", json={"publish_time_local": "07:00"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["publish_time_local"] == "07:00"


# ── persona ──────────────────────────────────────────────────────────────
def test_persona_get():
    r = requests.get(f"{API}/autopilot/persona", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("name") == "Russell"
    assert d.get("id") == "russell-v1"
    assert d.get("sheet") and isinstance(d["sheet"], str) and len(d["sheet"]) > 20
    assert d.get("sora_snippet") and isinstance(d["sora_snippet"], str)
    assert "image_ready" in d and "image_url" in d


def test_persona_regenerate_and_serve():
    r = requests.post(f"{API}/autopilot/persona/regenerate", timeout=90)
    assert r.status_code == 200, r.text[:500]
    d = r.json()
    assert d["image_url"] == "/api/studio/media/persona.png"
    # Fetch image
    img = requests.get(f"{BASE}/api/studio/media/persona.png", timeout=30)
    assert img.status_code == 200
    assert "image/png" in img.headers.get("content-type", "")
    assert len(img.content) > 10000


# ── topics ───────────────────────────────────────────────────────────────
def test_topic_add_list_delete():
    topic = "TEST_topic_autopilot"
    r = requests.post(f"{API}/autopilot/topics", json={"topic": topic}, timeout=10)
    assert r.status_code == 200
    r = requests.get(f"{API}/autopilot/topics", timeout=10)
    assert r.status_code == 200
    topics = r.json()
    assert any(topic in (t if isinstance(t, str) else t.get("topic", "")) for t in topics), topics
    r = requests.delete(f"{API}/autopilot/topics", json={"topic": topic}, timeout=10)
    assert r.status_code == 200
    r = requests.delete(f"{API}/autopilot/topics", json={"topic": topic}, timeout=10)
    assert r.status_code == 404


# ── youtube gate (no OAuth completed) ────────────────────────────────────
def test_youtube_disconnected_but_login_url_ready():
    r = requests.get(f"{API}/youtube/status", timeout=10)
    assert r.status_code == 200
    assert r.json().get("connected") is False
    r = requests.get(f"{API}/youtube/login", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "auth_url" in d
    assert "accounts.google.com" in d["auth_url"]


# ── run-now (long) ───────────────────────────────────────────────────────
@pytest.mark.timeout(300)
def test_run_now_progresses():
    r = requests.post(f"{API}/autopilot/run-now", timeout=15)
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert "queued_at" in r.json()

    terminal_ok = {
        "assembling", "ready", "ready-not-published", "published", "failed"
    }
    deadline = time.time() + 240  # 4 min
    last_status = None
    run_id = None
    while time.time() < deadline:
        rr = requests.get(f"{API}/autopilot/runs", timeout=15)
        assert rr.status_code == 200
        runs = rr.json()
        if runs:
            run = runs[0]
            run_id = run.get("id")
            last_status = run.get("status")
            print(f"[run-now] status={last_status}")
            if last_status in terminal_ok:
                break
        time.sleep(6)

    assert last_status in terminal_ok, f"Autopilot never reached progress state. last={last_status}"

    # GET by id also works
    if run_id:
        rr = requests.get(f"{API}/autopilot/runs/{run_id}", timeout=10)
        assert rr.status_code == 200
        assert rr.json().get("id") == run_id
