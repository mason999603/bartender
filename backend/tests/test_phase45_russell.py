"""Phase 4.5 — Russell (formerly Sheldon) rename + Companion + Collections tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://code-snapshot-23.preview.emergentagent.com"
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- Migration / Rename ----------
class TestRenameMigration:
    def test_no_sheldon_role_remains(self, s):
        """After startup migration, no chat_messages should have role='sheldon'."""
        r = s.get(f"{API}/chat/history", params={"session_id": "main"})
        assert r.status_code == 200
        msgs = r.json()
        roles = {m.get("role") for m in msgs}
        assert "sheldon" not in roles, f"Found leftover 'sheldon' role messages: {roles}"

    def test_root_endpoint(self, s):
        r = s.get(f"{API}/")
        assert r.status_code == 200


# ---------- Companion ----------
class TestCompanion:
    def test_companion_context(self, s):
        r = s.get(f"{API}/companion/context")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "location" in d and d["location"]
        assert "timezone" in d and d["timezone"]
        assert "context_block" in d and isinstance(d["context_block"], str)
        block = d["context_block"]
        # Must contain day/date/time-of-day info
        assert "Now:" in block, f"Missing 'Now:' in context block: {block}"
        # day-of-week present (one of these will appear)
        assert any(day in block for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])

    def test_companion_weather_default(self, s):
        r = s.get(f"{API}/companion/weather")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "temp_c" in d
        assert isinstance(d["temp_c"], (int, float)), f"temp_c not a number: {d.get('temp_c')!r}"
        assert d.get("source") in ("open-meteo", "wttr.in"), f"Unexpected source: {d.get('source')!r}"
        assert "place" in d and d["place"]
        assert "condition" in d

    def test_companion_weather_specific_location(self, s):
        r = s.get(f"{API}/companion/weather", params={"location": "Melbourne"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("temp_c"), (int, float))
        # place should reference Melbourne (not Sydney)
        place = (d.get("place") or "").lower()
        assert "melbourne" in place, f"Expected Melbourne in place, got: {place!r}"


# ---------- Chat (Companion mode + time awareness) ----------
class TestRussellChat:
    def test_chat_good_morning_uses_time(self, s):
        r = s.post(f"{API}/chat", json={"session_id": "TEST_phase45_morning", "message": "Russell good morning"})
        assert r.status_code == 200, r.text
        reply = (r.json().get("reply") or "").lower()
        assert reply, "Empty reply"
        # Should not claim it doesn't know the time
        bad_phrases = ["don't know what time", "don't know the time", "no idea what time", "i can't tell what time"]
        for bp in bad_phrases:
            assert bp not in reply, f"Russell denied knowing the time: {reply[:200]}"

    def test_chat_random_question_companion_mode(self, s):
        """Russell should engage with non-cocktail questions, not refuse/redirect."""
        r = s.post(f"{API}/chat", json={"session_id": "TEST_phase45_random", "message": "what's the meaning of life"})
        assert r.status_code == 200, r.text
        reply = (r.json().get("reply") or "").lower()
        assert reply
        # Refusal heuristics
        refusals = [
            "i can only help with cocktails",
            "i only do cocktails",
            "stick to bartending",
            "i'm just a bartender",
            "let's stick to drinks",
        ]
        for ref in refusals:
            assert ref not in reply, f"Russell refused companion mode: {reply[:200]}"

    def teardown_method(self, method):
        # Cleanup test chat sessions
        try:
            requests.delete(f"{API}/chat/history", params={"session_id": "TEST_phase45_morning"})
            requests.delete(f"{API}/chat/history", params={"session_id": "TEST_phase45_random"})
            requests.delete(f"{API}/chat/history", params={"session_id": "TEST_phase45_collections"})
        except Exception:
            pass


# ---------- Collections CRUD ----------
class TestCollections:
    collection_id = None
    item_ids = []

    def test_01_create_collection(self, s):
        r = s.post(f"{API}/collections", json={
            "name": "TEST_Records_Phase45",
            "icon": "vinyl",
            "description": "Test vinyl collection",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == "TEST_Records_Phase45"
        assert d["icon"] == "vinyl"
        assert "id" in d
        assert d.get("items") == []
        TestCollections.collection_id = d["id"]

    def test_02_list_collections(self, s):
        r = s.get(f"{API}/collections")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        ids = [c["id"] for c in data]
        assert TestCollections.collection_id in ids

    def test_03_add_items(self, s):
        cid = TestCollections.collection_id
        assert cid
        items = [
            {"title": "Pink Floyd — Dark Side of the Moon", "subtitle": "1973", "tags": ["rock", "prog"], "rating": 5},
            {"title": "Miles Davis — Kind of Blue", "subtitle": "1959", "tags": ["jazz"], "rating": 5},
            {"title": "Daft Punk — Random Access Memories", "subtitle": "2013", "tags": ["electronic"], "rating": 4},
        ]
        for item in items:
            r = s.post(f"{API}/collections/{cid}/items", json=item)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["title"] == item["title"]
            assert "id" in d
            TestCollections.item_ids.append(d["id"])

        # Verify via GET
        r = s.get(f"{API}/collections/{cid}")
        assert r.status_code == 200
        col = r.json()
        assert len(col["items"]) == 3
        titles = [i["title"] for i in col["items"]]
        assert "Pink Floyd — Dark Side of the Moon" in titles

    def test_04_russell_references_collection(self, s):
        """Ask Russell what to play tonight — should reference one of OUR records."""
        # Give backend a moment in case caching
        time.sleep(0.5)
        r = s.post(f"{API}/chat", json={
            "session_id": "TEST_phase45_collections",
            "message": "what should I play tonight",
        })
        assert r.status_code == 200, r.text
        reply = (r.json().get("reply") or "")
        assert reply
        candidates = ["pink floyd", "dark side", "miles davis", "kind of blue", "daft punk", "random access"]
        hit = any(c in reply.lower() for c in candidates)
        if not hit:
            # Soft flag — log content
            pytest.fail(f"Russell did not reference any of the user's records. Reply: {reply[:400]}")

    def test_05_delete_item(self, s):
        cid = TestCollections.collection_id
        iid = TestCollections.item_ids[0]
        r = s.delete(f"{API}/collections/{cid}/items/{iid}")
        assert r.status_code == 200
        assert r.json().get("deleted") is True
        # Verify item gone
        r2 = s.get(f"{API}/collections/{cid}")
        assert r2.status_code == 200
        ids = [i["id"] for i in r2.json()["items"]]
        assert iid not in ids

    def test_06_delete_collection(self, s):
        cid = TestCollections.collection_id
        r = s.delete(f"{API}/collections/{cid}")
        assert r.status_code == 200
        # Verify gone
        r2 = s.get(f"{API}/collections/{cid}")
        assert r2.status_code == 404


# ---------- Regression: existing endpoints ----------
class TestRegression:
    def test_cocktails_count(self, s):
        r = s.get(f"{API}/cocktails")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 44, f"Expected >=44 cocktails, got {len(data)}"

    def test_substitutions_count(self, s):
        r = s.get(f"{API}/substitutions")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 22, f"Expected >=22 substitutions, got {len(data)}"

    def test_regulars(self, s):
        r = s.get(f"{API}/regulars")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_memory(self, s):
        r = s.get(f"{API}/memory")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_inventory(self, s):
        r = s.get(f"{API}/inventory")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_twilio_voice_returns_twiml(self, s):
        r = requests.post(f"{API}/twilio/voice", data={"From": "+61400000000"})
        assert r.status_code == 200
        assert "<Response>" in r.text
        assert "application/xml" in r.headers.get("content-type", "")

    def test_twilio_sms_returns_twiml(self, s):
        r = requests.post(f"{API}/twilio/sms", data={"From": "+61400000000", "Body": "G'day Russell"})
        assert r.status_code == 200
        assert "<Message>" in r.text

    def test_chat_endpoint_basic(self, s):
        r = s.post(f"{API}/chat", json={"session_id": "TEST_phase45_regression", "message": "hello"})
        assert r.status_code == 200
        assert "reply" in r.json()
        # Cleanup
        s.delete(f"{API}/chat/history", params={"session_id": "TEST_phase45_regression"})
