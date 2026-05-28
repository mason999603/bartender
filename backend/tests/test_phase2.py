"""Sheldon Phase 2 backend tests: flavour search + substitutions + 86'd-aware chat."""
import os
import time
import pytest
import requests

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# --- Phase 2 cocktails seeding regression ---
class TestPhase2Cocktails:
    def test_cocktails_count_44_plus(self, s):
        r = s.get(f"{API}/cocktails", timeout=20)
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        assert len(names) >= 44, f"expected >=44, got {len(names)}"

    def test_phase2_new_specs_present(self, s):
        names = [c["name"] for c in s.get(f"{API}/cocktails", timeout=20).json()]
        expected = [
            "Mai Tai", "Jungle Bird", "Sidecar", "Vieux Carré", "Naked & Famous",
            "Oaxaca Old Fashioned", "Pisco Sour", "Caipirinha", "Corpse Reviver #2",
            "Garibaldi", "Hugo Spritz", "Americano", "White Russian", "Paloma",
            "Moscow Mule", "Mint Julep", "Hanky Panky", "Tom Collins", "Bee's Knees",
            "Hemingway Daiquiri", "Piña Colada",
        ]
        missing = [n for n in expected if n not in names]
        assert not missing, f"missing phase 2 specs: {missing}"


# --- Flavour search ---
class TestFlavourSearch:
    def test_by_flavour_smoky_citrus_exclude_sweet(self, s):
        r = s.post(f"{API}/cocktails/by-flavour",
                   json={"include": ["smoky", "citrus"], "exclude": ["sweet"]}, timeout=20)
        assert r.status_code == 200
        results = r.json()
        names = [m["cocktail"]["name"] for m in results]
        # Naked & Famous and Penicillin should both score 2 include-matches
        assert "Naked & Famous" in names
        assert "Penicillin" in names
        # Find their scores
        for m in results:
            if m["cocktail"]["name"] in ("Naked & Famous", "Penicillin"):
                assert m["include_matches"] == 2, f"{m['cocktail']['name']} include_matches={m['include_matches']}"
        # No result should have 'sweet' in flavor_profile
        for m in results:
            profile = [p.lower() for p in m["cocktail"].get("flavor_profile", [])]
            assert "sweet" not in profile, f"{m['cocktail']['name']} has sweet in profile"

    def test_by_flavour_bitter_5_plus(self, s):
        r = s.post(f"{API}/cocktails/by-flavour",
                   json={"include": ["bitter"], "exclude": []}, timeout=20)
        assert r.status_code == 200
        results = r.json()
        names = [m["cocktail"]["name"] for m in results]
        assert len(results) >= 5, f"expected >=5 bitter, got {len(results)}: {names}"
        # Sample bitter classics
        bitter_classics = {"Negroni", "Boulevardier", "Americano", "Aperol Spritz", "Paper Plane"}
        assert bitter_classics & set(names), f"none of {bitter_classics} in {names}"

    def test_by_flavour_empty_returns_empty(self, s):
        r = s.post(f"{API}/cocktails/by-flavour",
                   json={"include": [], "exclude": []}, timeout=15)
        assert r.status_code == 200
        assert r.json() == []


# --- Substitutions ---
class TestSubstitutions:
    def test_list_substitutions_22_plus_sorted(self, s):
        r = s.get(f"{API}/substitutions", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 22, f"expected >=22 subs, got {len(data)}"
        names = [d["ingredient"] for d in data]
        assert names == sorted(names), "substitutions not sorted by ingredient"

    def test_get_substitutions_cointreau(self, s):
        r = s.get(f"{API}/substitutions/Cointreau", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ingredient"] == "Cointreau"
        sub_names = [x["name"] for x in d["subs"]]
        assert len(sub_names) == 3
        for must in ["Grand Marnier", "Triple Sec", "Orange Curaçao"]:
            assert must in sub_names, f"missing sub {must}"
        for x in d["subs"]:
            assert x.get("notes"), "each sub should have notes"

    def test_get_substitutions_lowercase(self, s):
        r = s.get(f"{API}/substitutions/cointreau", timeout=15)
        assert r.status_code == 200
        assert r.json()["ingredient"] == "Cointreau"

    def test_get_substitutions_404(self, s):
        r = s.get(f"{API}/substitutions/nonexistent_zzz_xxx", timeout=15)
        assert r.status_code == 404
        body = r.json()
        # FastAPI default detail key
        msg = (body.get("detail") or body.get("message") or "").lower()
        assert "no substitutions" in msg or "improvise" in msg


# --- LLM chat: proactive sub when Cointreau 86'd ---
class TestChatProactiveSub:
    def test_chat_proactive_sub_when_cointreau_86(self, s):
        # Ensure a clean state for our test inventory item
        # find existing Cointreau in inventory
        inv = s.get(f"{API}/inventory", timeout=15).json()
        existing = next((i for i in inv if i["name"].lower() == "cointreau"), None)
        if existing:
            # mark 86'd
            s.patch(f"{API}/inventory/{existing['id']}?in_stock=false", timeout=15)
            item_id = existing["id"]
            created = False
        else:
            r = s.post(f"{API}/inventory",
                       json={"name": "Cointreau", "in_stock": False, "notes": "test 86"},
                       timeout=15)
            assert r.status_code == 200
            item_id = r.json()["id"]
            created = True

        try:
            s.delete(f"{API}/chat/history?session_id=phase2-test", timeout=15)
            time.sleep(0.5)
            r = s.post(f"{API}/chat",
                       json={"session_id": "phase2-test",
                             "message": "How do I make a Margarita?"},
                       timeout=120)
            assert r.status_code == 200, r.text
            reply = r.json()["reply"].lower()
            # Should proactively mention a swap from sub list
            swap_hits = ["grand marnier", "triple sec", "orange curaçao", "orange curacao"]
            assert any(h in reply for h in swap_hits), (
                f"reply did not mention any proactive Cointreau swap: {reply[:400]}"
            )
        finally:
            if created:
                s.delete(f"{API}/inventory/{item_id}", timeout=15)
            else:
                # restore in_stock=true
                s.patch(f"{API}/inventory/{item_id}?in_stock=true", timeout=15)
            s.delete(f"{API}/chat/history?session_id=phase2-test", timeout=15)
