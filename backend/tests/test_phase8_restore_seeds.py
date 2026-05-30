"""Phase 8 — Tombstone & restore endpoints for seeded cocktails.

Covers:
- GET /api/cocktails/admin/deleted-seeds
- POST /api/cocktails/admin/restore-seeds (single name, ["*"], empty, unknown)
- DELETE /api/cocktails/{id} creates a tombstone for seeded recipes
- Existing /api/cocktails CRUD regression
- /api/chat regression (Groq-powered)
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://code-snapshot-23.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module", autouse=True)
def cleanup_after_tests(client):
    """After the run, restore everything and remove any TEST_ cocktails."""
    yield
    try:
        client.post(f"{API}/cocktails/admin/restore-seeds", json={"names": ["*"]}, timeout=30)
    except Exception:
        pass
    try:
        r = client.get(f"{API}/cocktails", timeout=30)
        if r.ok:
            for c in r.json():
                if c.get("name", "").startswith("TEST_"):
                    client.delete(f"{API}/cocktails/{c['id']}", timeout=15)
    except Exception:
        pass


def _get_seed_named(client, name):
    r = client.get(f"{API}/cocktails", params={"search": name}, timeout=30)
    assert r.status_code == 200
    matches = [c for c in r.json() if c.get("name") == name and not c.get("is_custom")]
    return matches[0] if matches else None


# ---------- Health / regression -----------------------------------------------

def test_list_cocktails_ok(client):
    r = client.get(f"{API}/cocktails", timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) > 0


def test_chat_endpoint_regression(client):
    """Groq-powered /api/chat should respond with a 'reply' field."""
    sid = f"TEST_RESTORE_{uuid.uuid4().hex[:8]}"
    r = client.post(
        f"{API}/chat",
        json={"session_id": sid, "message": "Just say hi in one word."},
        timeout=90,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "reply" in data
    assert isinstance(data["reply"], str) and len(data["reply"]) > 0


# ---------- /admin/deleted-seeds & restore-seeds ------------------------------

def test_deleted_seeds_initially_empty_or_list(client):
    """Endpoint must respond 200 with a list, even when nothing is deleted."""
    # Ensure clean state first
    client.post(f"{API}/cocktails/admin/restore-seeds", json={"names": ["*"]}, timeout=30)
    r = client.get(f"{API}/cocktails/admin/deleted-seeds", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert body == []


def test_restore_seeds_rejects_empty_body(client):
    r = client.post(f"{API}/cocktails/admin/restore-seeds", json={}, timeout=30)
    assert r.status_code == 400


def test_restore_seeds_unknown_name_silently_skips(client):
    r = client.post(
        f"{API}/cocktails/admin/restore-seeds",
        json={"names": ["DefinitelyNotACocktail_XYZ"]},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 0
    assert data["restored"] == []


def test_delete_seeded_creates_tombstone_and_single_restore(client):
    # Pick a seeded cocktail (try Margarita first, else first seeded found)
    target = _get_seed_named(client, "Margarita")
    if target is None:
        r = client.get(f"{API}/cocktails", timeout=30)
        seeded = [c for c in r.json() if not c.get("is_custom")]
        assert seeded, "no seeded cocktails to test against"
        target = seeded[0]

    target_name = target["name"]
    target_id = target["id"]

    # DELETE
    r = client.delete(f"{API}/cocktails/{target_id}", timeout=30)
    assert r.status_code == 200
    assert r.json().get("deleted") is True

    # Tombstone should be visible
    r = client.get(f"{API}/cocktails/admin/deleted-seeds", timeout=30)
    assert r.status_code == 200
    names = [d["name"] for d in r.json()]
    assert target_name in names

    # Restore by exact name
    r = client.post(
        f"{API}/cocktails/admin/restore-seeds",
        json={"names": [target_name]},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert target_name in data["restored"]

    # Tombstone gone
    r = client.get(f"{API}/cocktails/admin/deleted-seeds", timeout=30)
    assert target_name not in [d["name"] for d in r.json()]

    # Cocktail back in list
    restored = _get_seed_named(client, target_name)
    assert restored is not None, f"{target_name} not restored to library"


def test_restore_all_with_star(client):
    # Delete two different seeded cocktails
    r = client.get(f"{API}/cocktails", timeout=30)
    seeded = [c for c in r.json() if not c.get("is_custom")]
    assert len(seeded) >= 2
    picks = []
    seen = set()
    for c in seeded:
        if c["name"] in seen:
            continue
        seen.add(c["name"])
        picks.append(c)
        if len(picks) == 2:
            break
    assert len(picks) == 2

    for c in picks:
        r = client.delete(f"{API}/cocktails/{c['id']}", timeout=30)
        assert r.status_code == 200

    r = client.get(f"{API}/cocktails/admin/deleted-seeds", timeout=30)
    tomb_names = {d["name"] for d in r.json()}
    for c in picks:
        assert c["name"] in tomb_names

    # Restore everything
    r = client.post(
        f"{API}/cocktails/admin/restore-seeds",
        json={"names": ["*"]},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 2
    for c in picks:
        assert c["name"] in data["restored"]

    # Tombstones cleared
    r = client.get(f"{API}/cocktails/admin/deleted-seeds", timeout=30)
    assert r.json() == []


# ---------- CRUD regression on /api/cocktails ---------------------------------

def test_custom_cocktail_crud_flow(client):
    name = f"TEST_RESTORE_{uuid.uuid4().hex[:8]}"
    payload = {
        "name": name,
        "category": "custom",
        "glassware": "rocks",
        "garnish": "lime",
        "method": "shake",
        "ingredients": [{"name": "Gin", "amount_ml": 60, "notes": ""}],
        "instructions": "shake hard",
        "flavor_profile": ["herbal"],
        "abv_estimate": 30,
        "tags": ["custom"],
    }
    r = client.post(f"{API}/cocktails", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["name"] == name
    assert created["is_custom"] is True
    cid = created["id"]

    # GET
    r = client.get(f"{API}/cocktails/{cid}", timeout=30)
    assert r.status_code == 200
    assert r.json()["name"] == name

    # DELETE custom (should NOT add a tombstone)
    r = client.delete(f"{API}/cocktails/{cid}", timeout=30)
    assert r.status_code == 200

    # Verify no tombstone created for custom delete
    r = client.get(f"{API}/cocktails/admin/deleted-seeds", timeout=30)
    assert name not in [d["name"] for d in r.json()]

    # GET again -> 404
    r = client.get(f"{API}/cocktails/{cid}", timeout=30)
    assert r.status_code == 404
