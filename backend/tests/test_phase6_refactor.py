"""Phase 6 backend regression + reverse mood pairing tests.

Covers:
- All existing /api routes after server.py refactor into modular routers
- Reverse mood pairing trigger in core/brain.py _detect_record_mention
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ------------------------- Smoke / health -------------------------
def test_root(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    data = r.json()
    assert data["app"] == "Russell"
    assert "status" in data


# ------------------------- Cocktails -------------------------
class TestCocktails:
    def test_list(self, session):
        r = session.get(f"{API}/cocktails")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 44, f"Expected >=44 cocktails, got {len(data)}"
        assert "id" in data[0] and "name" in data[0]

    def test_get_single(self, session):
        cocktails = session.get(f"{API}/cocktails").json()
        cid = cocktails[0]["id"]
        r = session.get(f"{API}/cocktails/{cid}")
        assert r.status_code == 200
        assert r.json()["id"] == cid

    def test_search_by_ingredients(self, session):
        r = session.post(
            f"{API}/cocktails/search-by-ingredients",
            json={"ingredients": ["Gin", "Vermouth", "Bitters"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "Expected matches for Gin/Vermouth/Bitters"
        # Each match should have cocktail, match_ratio, missing
        assert "cocktail" in data[0]
        assert "match_ratio" in data[0]

    def test_by_flavour_bitter(self, session):
        r = session.post(f"{API}/cocktails/by-flavour", json={"include": ["bitter"]})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1


# ------------------------- Substitutions / Ingredients -------------------------
class TestRefData:
    def test_substitutions_list(self, session):
        r = session.get(f"{API}/substitutions")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 22

    def test_substitutions_get_cointreau(self, session):
        r = session.get(f"{API}/substitutions/Cointreau")
        assert r.status_code == 200
        assert "subs" in r.json()

    def test_ingredients(self, session):
        r = session.get(f"{API}/ingredients")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ------------------------- Tools -------------------------
class TestTools:
    def test_abv_math(self, session):
        # 60ml of 40% spirit + 30ml dilution -> alcohol_ml=24, total=90, abv=26.66
        r = session.post(
            f"{API}/tools/abv",
            json={
                "ingredients": [{"name": "Gin", "amount_ml": 60, "abv": 40}],
                "dilution_ml": 30,
            },
        )
        assert r.status_code == 200
        d = r.json()
        assert d["alcohol_ml"] == 24.0
        assert d["total_volume_ml"] == 90.0
        assert abs(d["abv"] - 26.67) < 0.1

    def test_batch_real_cocktail(self, session):
        cocktails = session.get(f"{API}/cocktails").json()
        real = next((c for c in cocktails if c.get("ingredients")), None)
        assert real
        r = session.post(
            f"{API}/tools/batch",
            json={"cocktail_id": real["id"], "servings": 10, "dilution_pct": 20},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["servings"] == 10
        assert len(d["scaled_ingredients"]) == len(real["ingredients"])
        assert d["added_dilution_water_ml"] > 0

    def test_compatibility_cream_lime(self, session):
        r = session.post(
            f"{API}/tools/compatibility",
            json={"ingredients": ["Cream", "Lime"]},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["verdict"] in ("warning", "fatal"), f"Expected dairy+citrus clash, got verdict={d['verdict']} warnings={d['warnings']}"
        assert len(d["warnings"]) >= 1

    def test_cost(self, session):
        r = session.post(
            f"{API}/tools/cost",
            json={
                "ingredients": [{"name": "Gin", "amount_ml": 60, "price_per_litre": 50}],
                "extra_cost": 1.5,
            },
        )
        assert r.status_code == 200
        d = r.json()
        # 60ml * 50/L = 3.0 + 1.5 = 4.5
        assert abs(d["total_cost"] - 4.5) < 0.01
        assert d["suggested_menu_price_4x"] == 18.0


# ------------------------- Regulars / Memory / Inventory CRUD -------------------------
class TestRegulars:
    def test_crud(self, session):
        payload = {"name": f"TEST_reg_{uuid.uuid4().hex[:6]}", "likes": ["smoky"]}
        r = session.post(f"{API}/regulars", json=payload)
        assert r.status_code == 200
        rid = r.json()["id"]
        # GET list
        lst = session.get(f"{API}/regulars").json()
        assert any(x["id"] == rid for x in lst)
        # DELETE
        d = session.delete(f"{API}/regulars/{rid}")
        assert d.status_code == 200


class TestMemory:
    def test_crud(self, session):
        payload = {"key": f"TEST_key_{uuid.uuid4().hex[:6]}", "value": "test val"}
        r = session.post(f"{API}/memory", json=payload)
        assert r.status_code == 200
        mid = r.json()["id"]
        lst = session.get(f"{API}/memory").json()
        assert any(x["id"] == mid for x in lst)
        d = session.delete(f"{API}/memory/{mid}")
        assert d.status_code == 200


class TestInventory:
    def test_crud_and_patch(self, session):
        payload = {"name": f"TEST_inv_{uuid.uuid4().hex[:6]}", "in_stock": True}
        r = session.post(f"{API}/inventory", json=payload)
        assert r.status_code == 200
        iid = r.json()["id"]
        # PATCH toggle - in_stock is a query param
        p = session.patch(f"{API}/inventory/{iid}?in_stock=false")
        assert p.status_code == 200
        # Verify
        lst = session.get(f"{API}/inventory").json()
        item = next((x for x in lst if x["id"] == iid), None)
        assert item and item["in_stock"] is False
        d = session.delete(f"{API}/inventory/{iid}")
        assert d.status_code == 200


# ------------------------- Collections CRUD -------------------------
class TestCollections:
    def test_records_exists(self, session):
        lst = session.get(f"{API}/collections").json()
        names = [c["name"] for c in lst]
        assert "Records" in names, f"Records collection missing; have {names}"

    def test_full_crud(self, session):
        name = f"TEST_col_{uuid.uuid4().hex[:6]}"
        r = session.post(f"{API}/collections", json={"name": name})
        assert r.status_code == 200
        cid = r.json()["id"]
        # Add item
        ir = session.post(
            f"{API}/collections/{cid}/items",
            json={"title": "TEST_item", "tags": ["Reggae"]},
        )
        assert ir.status_code == 200
        item_id = ir.json()["id"]
        # Verify item visible via GET
        doc = session.get(f"{API}/collections/{cid}").json()
        assert any(i["id"] == item_id for i in doc["items"])
        # Delete item
        di = session.delete(f"{API}/collections/{cid}/items/{item_id}")
        assert di.status_code == 200
        # Delete collection
        dc = session.delete(f"{API}/collections/{cid}")
        assert dc.status_code == 200


# ------------------------- Twilio / Voice / Companion -------------------------
class TestPeripherals:
    def test_twilio_status(self, session):
        r = session.get(f"{API}/twilio/status")
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] is False  # creds intentionally absent

    def test_voice_transcribe_tiny(self, session):
        # Tiny blob — endpoint short-circuits to empty text
        files = {"audio": ("voice.webm", b"x" * 100, "audio/webm")}
        # multipart, drop default JSON header
        r = requests.post(f"{API}/voice/transcribe", files=files)
        assert r.status_code == 200
        assert r.json()["text"] == ""

    def test_companion_weather(self, session):
        r = session.get(f"{API}/companion/weather")
        assert r.status_code == 200
        d = r.json()
        assert "temp_c" in d

    def test_companion_context(self, session):
        r = session.get(f"{API}/companion/context")
        assert r.status_code == 200
        d = r.json()
        assert "location" in d and "timezone" in d and "context_block" in d
        assert len(d["context_block"]) > 20


# ------------------------- Chat — basic + history persistence -------------------------
class TestChat:
    def test_basic_chat_and_history_persistence(self, session):
        sid = f"TEST_phase6_basic_{uuid.uuid4().hex[:6]}"
        try:
            r = session.post(
                f"{API}/chat",
                json={"session_id": sid, "message": "What's a Negroni?"},
                timeout=60,
            )
            assert r.status_code == 200, f"chat failed: {r.status_code} {r.text[:200]}"
            data = r.json()
            assert data["session_id"] == sid
            assert len(data["reply"]) > 10
            # History should have exactly 2: user + russell
            hist = session.get(f"{API}/chat/history?session_id={sid}").json()
            assert len(hist) == 2, f"Expected 2 messages, got {len(hist)}: {hist}"
            roles = [m["role"] for m in hist]
            assert roles == ["user", "russell"], f"Bad role order: {roles}"
        finally:
            session.delete(f"{API}/chat/history?session_id={sid}")
            # Verify cleared
            hist = session.get(f"{API}/chat/history?session_id={sid}").json()
            assert hist == []


# ------------------------- REVERSE MOOD PAIRING -------------------------
class TestReverseMoodPairing:
    """The trigger fires when:
       1. Music intent keyword (play/playing/spinning/...) appears
       2. A title (or part of it) from the Records collection appears
    """

    def _run(self, session, message, sid_prefix):
        sid = f"TEST_phase6_{sid_prefix}_{uuid.uuid4().hex[:6]}"
        try:
            r = session.post(
                f"{API}/chat",
                json={"session_id": sid, "message": message},
                timeout=90,
            )
            assert r.status_code == 200, f"chat failed: {r.status_code} {r.text[:300]}"
            return r.json()["reply"]
        finally:
            session.delete(f"{API}/chat/history?session_id={sid}")

    def test_record_in_collection_reggae(self, session):
        """'Rastaman Vibrations' IS in collection with tag Reggae — Russell should suggest a cocktail."""
        reply = self._run(session, "just spun up Rastaman Vibrations", "reggae")
        reply_lower = reply.lower()
        # Should mention some cocktail name — broad sanity check: contains a known spirit OR known cocktail keyword
        cocktail_signals = [
            "rum", "negroni", "daiquiri", "tiki", "punch", "mai tai", "old fashioned",
            "martini", "spritz", "margarita", "mojito", "cocktail", "sip", "shake",
            "stir", "highball", "sour", "manhattan", "sazerac", "mezcal", "tequila",
            "whisky", "whiskey", "gin", "bourbon", "campari", "vermouth", "aperol",
        ]
        assert any(c in reply_lower for c in cocktail_signals), (
            f"Reply doesn't seem to suggest a cocktail: {reply!r}"
        )
        print(f"\n[reggae] Russell said: {reply}\n")

    def test_record_not_in_collection_taylor_swift(self, session):
        """Taylor Swift is NOT in collection. Russell should NOT claim she's in collection."""
        reply = self._run(session, "about to put on some Taylor Swift", "tswift")
        reply_lower = reply.lower()
        # Russell should not assert she's "in your collection" or similar fabrication.
        bad_phrases = [
            "in your records", "in your collection", "you've got taylor",
            "your taylor swift", "from your collection",
        ]
        for p in bad_phrases:
            assert p not in reply_lower, f"Russell hallucinated ownership: phrase {p!r} in {reply!r}"
        print(f"\n[taylor swift] Russell said: {reply}\n")

    def test_record_not_in_collection_pink_floyd(self, session):
        """Pink Floyd / Dark Side of the Moon is NOT in this collection.
        Reply should be coherent — may suggest a cocktail (forward pairing fine),
        but should not falsely claim Dark Side is in the user's records.
        """
        reply = self._run(
            session,
            "about to put on Pink Floyd Dark Side of the Moon, what should I sip?",
            "pinkfloyd",
        )
        reply_lower = reply.lower()
        # Sanity: response is not empty
        assert len(reply) > 10
        # Should not claim it's in user's collection
        bad_phrases = ["in your records collection", "i see you've got dark side", "from your records collection"]
        for p in bad_phrases:
            assert p not in reply_lower
        print(f"\n[pink floyd] Russell said: {reply}\n")

    def test_no_record_mention_negative(self, session):
        """No music intent at all — Russell should NOT randomly name-drop a record from the collection."""
        reply = self._run(session, "feeling like something boozy tonight", "boozy")
        # Just sanity check we got a meaningful reply
        assert len(reply) > 10
        print(f"\n[no music] Russell said: {reply}\n")
