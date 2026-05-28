"""Sheldon — AI bartender backend API tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://code-snapshot-23.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# --- Root ---
def test_root(s):
    r = s.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["app"] == "Sheldon"
    assert "status" in j


# --- Cocktails (library) ---
class TestCocktails:
    def test_list_seeded(self, s):
        r = s.get(f"{API}/cocktails", timeout=15)
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        assert len(names) >= 22
        for must in ["Old Fashioned", "Negroni", "Margarita", "Daiquiri", "Manhattan"]:
            assert must in names, f"missing {must}"

    def test_search_filter(self, s):
        r = s.get(f"{API}/cocktails?search=negroni", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert all("negroni" in c["name"].lower() for c in data)

    def test_get_single(self, s):
        all_c = s.get(f"{API}/cocktails", timeout=15).json()
        cid = all_c[0]["id"]
        r = s.get(f"{API}/cocktails/{cid}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "ingredients" in d and len(d["ingredients"]) > 0
        assert "method" in d

    def test_create_custom(self, s):
        payload = {
            "name": "TEST_Sheldon_Special",
            "category": "custom",
            "glassware": "Coupe",
            "method": "Stir",
            "ingredients": [{"name": "Gin", "amount_ml": 60}],
            "instructions": "Stir hard",
            "flavor_profile": ["dry"],
            "abv_estimate": 30,
            "tags": ["test"],
        }
        r = s.post(f"{API}/cocktails", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_custom"] is True
        assert d["name"] == "TEST_Sheldon_Special"
        # verify GET
        g = s.get(f"{API}/cocktails/{d['id']}", timeout=15)
        assert g.status_code == 200
        # cleanup
        s.delete(f"{API}/cocktails/{d['id']}", timeout=15)

    def test_search_by_ingredients(self, s):
        payload = {"ingredients": ["gin", "lime juice", "simple syrup"]}
        r = s.post(f"{API}/cocktails/search-by-ingredients", json=payload, timeout=20)
        assert r.status_code == 200
        results = r.json()
        assert len(results) >= 1
        # gimlet should match (gin + lime + simple)
        names = [m["cocktail"]["name"] for m in results]
        assert "Gimlet" in names
        for m in results:
            assert "match_ratio" in m and 0 < m["match_ratio"] <= 1


# --- Tools ---
class TestTools:
    def test_compat_fatal_baileys_lime(self, s):
        r = s.post(f"{API}/tools/compatibility", json={"ingredients": ["Baileys Irish Cream", "Lime Juice"]}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["verdict"] == "fatal"
        assert len(d["warnings"]) >= 1
        reason_txt = " ".join(w["reason"].lower() for w in d["warnings"])
        assert "curdl" in reason_txt or "acid" in reason_txt

    def test_compat_ok_vodka_cranberry(self, s):
        r = s.post(f"{API}/tools/compatibility", json={"ingredients": ["Vodka", "Cranberry Juice"]}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["verdict"] == "ok"
        assert d["warnings"] == []

    def test_abv(self, s):
        payload = {
            "ingredients": [
                {"name": "Bourbon", "amount_ml": 60, "abv": 45},
                {"name": "Sweet Vermouth", "amount_ml": 30, "abv": 16},
            ],
            "dilution_ml": 25,
        }
        r = s.post(f"{API}/tools/abv", json=payload, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # alc = 60*0.45 + 30*0.16 = 27 + 4.8 = 31.8; total=115; abv=27.65
        assert 27.0 <= d["abv"] <= 28.0
        assert "standard_drinks_au" in d
        assert d["total_volume_ml"] == 115

    def test_batch_by_cocktail_id(self, s):
        cs = s.get(f"{API}/cocktails?search=negroni", timeout=15).json()
        cid = cs[0]["id"]
        r = s.post(f"{API}/tools/batch", json={"cocktail_id": cid, "servings": 10}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["servings"] == 10
        assert len(d["scaled_ingredients"]) >= 3
        assert d["total_volume_ml"] > 0
        # Negroni 30+30+30 = 90 single; 900 total
        assert d["total_volume_ml"] == 900

    def test_cost(self, s):
        payload = {
            "ingredients": [
                {"name": "Gin", "amount_ml": 60, "price_per_litre": 40},
                {"name": "Tonic", "amount_ml": 120, "price_per_litre": 5},
            ],
            "extra_cost": 0.5,
        }
        r = s.post(f"{API}/tools/cost", json=payload, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # 0.06*40 + 0.12*5 + 0.5 = 2.4 + 0.6 + 0.5 = 3.5
        assert abs(d["total_cost"] - 3.5) < 0.05
        assert "suggested_menu_price_4x" in d
        assert "suggested_menu_price_5x" in d


# --- Memory CRUD ---
class TestMemory:
    def test_memory_crud(self, s):
        mr = s.post(f"{API}/memory", json={"key": "TEST_house_style", "value": "dry low-sugar"}, timeout=15)
        assert mr.status_code == 200
        mid = mr.json()["id"]
        lst = s.get(f"{API}/memory", timeout=15).json()
        assert any(m["id"] == mid for m in lst)
        d = s.delete(f"{API}/memory/{mid}", timeout=15)
        assert d.status_code == 200


# --- Regulars CRUD ---
class TestRegulars:
    def test_regulars_crud(self, s):
        r = s.post(f"{API}/regulars", json={
            "name": "TEST_Dave", "likes": ["smoky"], "dislikes": ["sweet"],
            "favourite_cocktails": ["Penicillin"], "notes": "no ice"
        }, timeout=15)
        assert r.status_code == 200
        rid = r.json()["id"]
        lst = s.get(f"{API}/regulars", timeout=15).json()
        assert any(x["id"] == rid for x in lst)
        s.delete(f"{API}/regulars/{rid}", timeout=15)


# --- Inventory CRUD ---
class TestInventory:
    def test_inventory_crud(self, s):
        r = s.post(f"{API}/inventory", json={"name": "TEST_Bottle", "in_stock": True, "notes": ""}, timeout=15)
        assert r.status_code == 200
        iid = r.json()["id"]
        # patch toggle
        p = s.patch(f"{API}/inventory/{iid}?in_stock=false", timeout=15)
        assert p.status_code == 200
        # delete
        d = s.delete(f"{API}/inventory/{iid}", timeout=15)
        assert d.status_code == 200


# --- Chat (LLM live) ---
class TestChat:
    def test_chat_aussie_personality(self, s):
        # clear first
        s.delete(f"{API}/chat/history?session_id=test_pytest", timeout=15)
        r = s.post(f"{API}/chat", json={
            "session_id": "test_pytest",
            "message": "What's a good gin cocktail for a hot day?"
        }, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["reply"]) > 20
        assert d["session_id"] == "test_pytest"

    def test_chat_warns_baileys_lime(self, s):
        r = s.post(f"{API}/chat", json={
            "session_id": "test_pytest",
            "message": "Quick check — can I shake Baileys with fresh lime juice?"
        }, timeout=90)
        assert r.status_code == 200
        reply = r.json()["reply"].lower()
        assert ("curdl" in reply or "curdle" in reply or "split" in reply or "won't work" in reply
                or "no" in reply), f"reply did not mention curdle: {reply[:200]}"

    def test_chat_history_persisted(self, s):
        h = s.get(f"{API}/chat/history?session_id=test_pytest", timeout=15)
        assert h.status_code == 200
        msgs = h.json()
        assert len(msgs) >= 2
        roles = {m["role"] for m in msgs}
        assert "user" in roles and "sheldon" in roles

    def test_chat_uses_memory(self, s):
        # save a memory
        mr = s.post(f"{API}/memory", json={"key": "house style", "value": "dry, low-sugar, citrus-forward"}, timeout=15)
        mid = mr.json()["id"]
        # ask sheldon to reference it
        s.delete(f"{API}/chat/history?session_id=test_mem", timeout=15)
        time.sleep(0.5)
        r = s.post(f"{API}/chat", json={
            "session_id": "test_mem",
            "message": "Remind me — what's my house style?"
        }, timeout=90)
        assert r.status_code == 200
        reply = r.json()["reply"].lower()
        # cleanup
        s.delete(f"{API}/memory/{mid}", timeout=15)
        s.delete(f"{API}/chat/history?session_id=test_mem", timeout=15)
        assert ("dry" in reply and ("low" in reply or "sugar" in reply)) or "citrus" in reply, \
            f"reply did not reference memory: {reply[:300]}"

    def test_chat_clear(self, s):
        d = s.delete(f"{API}/chat/history?session_id=test_pytest", timeout=15)
        assert d.status_code == 200
