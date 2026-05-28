"""Phase 7 — Russell action layer tests.

Covers:
- POST /api/chat triggers add_cocktail / add_collection_item / create_collection / set_inventory / add_memory
- Negative cases (no actions for casual / question prompts)
- Reply cleanliness (no <russell_actions> tag in reply) + chat history cleanliness
- Auto-icon for new collections (Books → book, Movies → film, Records/Vinyl → vinyl)
- Inventory idempotency (same name twice → updated, not duplicated)
- Bad / unknown action JSON safety
- Telegram webhook in-process ASGI test with sendMessage monkey-patched
- Twilio SMS form-post: actions execute but reply XML has no [saved] suffix
- Previous functionality smoke (cocktails/collections/inventory/memory/substitutions/abv/weather/telegram/status)
- Chat history persistence: 2 docs per turn
- Direct unit tests for parse_and_execute on malformed / unknown blocks
"""
import os
import re
import json
import uuid
import time
import asyncio
import pathlib
import sys

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

# Make backend importable for in-process tests + direct module tests
sys.path.insert(0, "/app/backend")

SESSION = f"TEST_ACTIONS_{uuid.uuid4().hex[:8]}"

# Track created entities for cleanup
_created = {
    "cocktail_ids": set(),
    "collection_ids": set(),
    "memory_ids": set(),
    "inventory_ids": set(),
    "chat_sessions": set([SESSION]),
}


def _chat(message: str, session_id: str = SESSION, timeout: int = 90) -> dict:
    r = requests.post(f"{API}/chat", json={"session_id": session_id, "message": message}, timeout=timeout)
    assert r.status_code == 200, f"chat failed: {r.status_code} {r.text[:300]}"
    return r.json()


def _track(data: dict):
    for act in data.get("actions", []) or []:
        if not act.get("ok"):
            continue
        res = act.get("result") or {}
        kind = res.get("kind")
        if kind == "cocktail" and res.get("id"):
            _created["cocktail_ids"].add(res["id"])
        elif kind == "collection" and res.get("id"):
            _created["collection_ids"].add(res["id"])
        elif kind == "memory" and res.get("id"):
            _created["memory_ids"].add(res["id"])


# ============================================================
# 1. Basic shape + negative casual greeting
# ============================================================
def test_chat_casual_greeting_no_actions():
    data = _chat("g'day")
    assert "actions" in data
    assert isinstance(data["actions"], list)
    assert data["actions"] == [], f"Expected no actions for casual greeting, got {data['actions']}"
    assert "<russell_actions>" not in data["reply"]


def test_chat_question_no_actions():
    """'what's a good Manhattan' — answering a question, NOT saving."""
    data = _chat("what's a good Manhattan recipe")
    # Should not save a cocktail
    cocktail_saves = [a for a in data["actions"] if a.get("type") == "add_cocktail"]
    assert cocktail_saves == [], f"Should not save cocktail when just asking: {data['actions']}"
    assert "<russell_actions>" not in data["reply"]


def test_chat_vague_compliment_no_actions():
    data = _chat("this is great")
    saves = [a for a in data["actions"] if a.get("ok") and a.get("type") in ("add_cocktail", "add_memory")]
    assert saves == [], f"Vague compliment should not trigger saves: {data['actions']}"


# ============================================================
# 2. add_cocktail
# ============================================================
def test_chat_add_cocktail():
    unique = f"TEST_ACTIONS_Negroni_{uuid.uuid4().hex[:6]}"
    data = _chat(
        f"Save this as my house cocktail called '{unique}': 30ml gin, 30ml Campari, 30ml sweet vermouth, "
        "stirred over ice, orange peel garnish. Save it to my Library please."
    )
    _track(data)
    assert "<russell_actions>" not in data["reply"], "Action block must be stripped"
    actions = data["actions"]
    cocktail_acts = [a for a in actions if a.get("type") == "add_cocktail"]
    assert len(cocktail_acts) >= 1, f"Expected add_cocktail action, got: {actions}"
    a = cocktail_acts[0]
    assert a["ok"] is True, f"add_cocktail failed: {a}"
    assert a["result"]["kind"] == "cocktail"
    cocktail_id = a["result"]["id"]

    # Verify in DB via GET
    r = requests.get(f"{API}/cocktails", timeout=30)
    assert r.status_code == 200
    cocktails = r.json()
    found = [c for c in cocktails if c["id"] == cocktail_id]
    assert found, f"New cocktail id={cocktail_id} not found in /api/cocktails"
    assert found[0]["is_custom"] is True


# ============================================================
# 3. add_collection_item — Records
# ============================================================
def test_chat_add_collection_item_records():
    # Snapshot Records count
    r0 = requests.get(f"{API}/collections", timeout=30).json()
    rec_before = next(
        (c for c in r0 if "record" in c["name"].lower()), None
    )
    before_count = len(rec_before["items"]) if rec_before else 0

    unique = f"TEST_ACTIONS_AjaSteelyDan_{uuid.uuid4().hex[:6]}"
    data = _chat(
        f"Add Steely Dan — {unique} to my Records collection. Jazz-rock vibes, smooth, late-night."
    )
    _track(data)
    assert "<russell_actions>" not in data["reply"]
    coll_acts = [a for a in data["actions"] if a.get("type") == "add_collection_item" and a.get("ok")]
    assert coll_acts, f"Expected add_collection_item, got: {data['actions']}"
    a = coll_acts[0]
    assert a["result"]["kind"] == "collection_item"

    # Verify item added
    r1 = requests.get(f"{API}/collections", timeout=30).json()
    rec_after = next((c for c in r1 if "record" in c["name"].lower()), None)
    assert rec_after, "Records collection should exist after action"
    after_count = len(rec_after["items"])
    assert after_count >= before_count + 1, f"Records grew {before_count}→{after_count}"
    # Find our item and check it has tags
    new_items = [it for it in rec_after["items"] if unique in (it.get("title") or "")]
    assert new_items, f"New item not found by unique tag {unique}"
    assert new_items[0].get("tags"), f"Expected tags on new record item, got: {new_items[0]}"


# ============================================================
# 4. create_collection + add_collection_item in same turn
# ============================================================
def test_chat_create_collection_and_item():
    unique_col = f"TEST_ACTIONS_WhiskeyWishlist_{uuid.uuid4().hex[:6]}"
    data = _chat(
        f"Start me a new collection called '{unique_col}' and add 'Eagle Rare 17' to it."
    )
    _track(data)
    types = [a.get("type") for a in data["actions"] if a.get("ok")]
    # Either explicit create_collection + add_collection_item, OR a single add_collection_item that auto-creates.
    has_item = "add_collection_item" in types
    assert has_item, f"Expected at least add_collection_item, got: {types}"

    # Verify collection exists
    r = requests.get(f"{API}/collections", timeout=30).json()
    match = [c for c in r if c["name"].lower() == unique_col.lower() or unique_col.lower() in c["name"].lower()]
    assert match, f"New collection '{unique_col}' not found in /api/collections"
    col = match[0]
    _created["collection_ids"].add(col["id"])
    titles = [it.get("title", "") for it in col.get("items", [])]
    assert any("eagle rare" in t.lower() for t in titles), f"Eagle Rare not in collection items: {titles}"


# ============================================================
# 5. set_inventory — 86 (auto-create)
# ============================================================
def test_chat_set_inventory_86():
    unique_ing = f"TEST_ACTIONS_Cointreau_{uuid.uuid4().hex[:6]}"
    data = _chat(f"We're out of {unique_ing}, 86 it.")
    _track(data)
    inv_acts = [a for a in data["actions"] if a.get("type") == "set_inventory" and a.get("ok")]
    assert inv_acts, f"Expected set_inventory action, got: {data['actions']}"
    res = inv_acts[0]["result"]
    assert res["in_stock"] is False
    assert res["kind"] == "inventory"

    r = requests.get(f"{API}/inventory", timeout=30).json()
    matches = [i for i in r if unique_ing.lower() in i["name"].lower()]
    assert matches, f"Inventory entry for {unique_ing} not found"
    assert matches[0]["in_stock"] is False
    _created["inventory_ids"].add(matches[0]["id"])


# ============================================================
# 6. add_memory
# ============================================================
def test_chat_add_memory():
    unique_marker = f"TEST_ACTIONS_dryshake_{uuid.uuid4().hex[:6]}"
    data = _chat(
        f"Remember this for me: I always dry shake egg-white sours first. Marker={unique_marker}"
    )
    _track(data)
    mem_acts = [a for a in data["actions"] if a.get("type") == "add_memory" and a.get("ok")]
    assert mem_acts, f"Expected add_memory action, got: {data['actions']}"
    assert mem_acts[0]["result"]["kind"] == "memory"
    assert mem_acts[0]["result"].get("key")


# ============================================================
# 7. Chat history cleanliness
# ============================================================
def test_chat_history_no_action_block():
    """After action-triggering messages, history must contain CLEANED reply only."""
    r = requests.get(f"{API}/chat/history", params={"session_id": SESSION, "limit": 200}, timeout=30)
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) >= 2, f"Expected at least one full turn, got {len(msgs)}"
    for m in msgs:
        assert "<russell_actions>" not in m["content"], f"History row has raw action block: {m['content'][:120]}"


def test_chat_history_two_docs_per_turn():
    """One fresh chat call should produce exactly 2 new docs."""
    sid = f"TEST_ACTIONS_persist_{uuid.uuid4().hex[:6]}"
    _created["chat_sessions"].add(sid)
    before = requests.get(f"{API}/chat/history", params={"session_id": sid}, timeout=30).json()
    _chat("just a quick hello", session_id=sid)
    after = requests.get(f"{API}/chat/history", params={"session_id": sid}, timeout=30).json()
    assert len(after) - len(before) == 2, f"Expected +2 docs, got {len(after) - len(before)}"
    # order: user first, then russell
    assert after[-2]["role"] == "user"
    assert after[-1]["role"] == "russell"


# ============================================================
# 8. Direct unit tests on actions.parse_and_execute
# ============================================================
@pytest.mark.asyncio
async def test_parse_execute_malformed_block():
    from core.actions import parse_and_execute
    # Brackets present so the regex matches, but inner content is malformed JSON.
    reply = 'Saved it mate.\n<russell_actions>\n[{"type": "add_cocktail", "name": "Broken}]\n</russell_actions>'
    cleaned, executed = await parse_and_execute(reply)
    assert "<russell_actions>" not in cleaned, f"action tag should be stripped, got: {cleaned!r}"
    assert executed == []  # malformed → silently dropped, reply still returned


@pytest.mark.asyncio
async def test_parse_execute_unknown_type():
    from core.actions import parse_and_execute
    reply = 'Done.\n<russell_actions>\n[{"type":"do_a_barrel_roll","x":1}]\n</russell_actions>'
    cleaned, executed = await parse_and_execute(reply)
    assert "<russell_actions>" not in cleaned
    assert len(executed) == 1
    assert executed[0]["ok"] is False
    assert "unknown action type" in executed[0]["error"]


@pytest.mark.asyncio
async def test_parse_execute_auto_icon_for_collection():
    """add_collection_item to a brand new 'Books' collection should pick icon=book; Movies→film; Vinyl/Records→vinyl."""
    from core.actions import parse_and_execute
    from core.db import db
    cases = [("Books", "book"), ("Movies", "film"), ("Vinyl", "vinyl"), ("Records", "vinyl")]
    for cname_base, expected_icon in cases:
        cname = f"TEST_ACTIONS_{cname_base}_{uuid.uuid4().hex[:6]}"
        reply = (
            f"Done.\n<russell_actions>\n"
            f'[{{"type":"add_collection_item","collection_name":"{cname}","title":"TEST_item"}}]\n'
            f"</russell_actions>"
        )
        cleaned, executed = await parse_and_execute(reply)
        assert executed and executed[0]["ok"], f"action failed for {cname}: {executed}"
        col = await db.collections.find_one({"name": cname}, {"_id": 0})
        assert col, f"Collection {cname} was not auto-created"
        assert col["icon"] == expected_icon, f"For {cname_base} expected icon={expected_icon}, got {col['icon']}"
        _created["collection_ids"].add(col["id"])


@pytest.mark.asyncio
async def test_parse_execute_inventory_idempotency():
    """set_inventory called twice with same name → only one inventory doc, value updated."""
    from core.actions import parse_and_execute
    from core.db import db
    name = f"TEST_ACTIONS_Idempo_{uuid.uuid4().hex[:6]}"
    r1 = f'Done.\n<russell_actions>\n[{{"type":"set_inventory","name":"{name}","in_stock":false}}]\n</russell_actions>'
    _, ex1 = await parse_and_execute(r1)
    assert ex1[0]["ok"] and ex1[0]["result"]["created"] is True
    r2 = f'Done.\n<russell_actions>\n[{{"type":"set_inventory","name":"{name}","in_stock":true}}]\n</russell_actions>'
    _, ex2 = await parse_and_execute(r2)
    assert ex2[0]["ok"] and ex2[0]["result"]["created"] is False
    docs = await db.inventory.find({"name": name}, {"_id": 0}).to_list(10)
    assert len(docs) == 1, f"Expected 1 inventory doc for {name}, got {len(docs)}"
    assert docs[0]["in_stock"] is True
    _created["inventory_ids"].add(docs[0]["id"])


# ============================================================
# 9. Telegram webhook in-process ASGI
# ============================================================
@pytest.mark.asyncio
async def test_telegram_webhook_saves_and_appends_suffix(monkeypatch):
    from httpx import AsyncClient, ASGITransport
    import server as srv  # /app/backend/server.py
    from routers import telegram_routes as tg

    sent = []

    async def fake_tg_call(method, payload=None):
        sent.append({"method": method, "payload": payload or {}})
        return {}

    monkeypatch.setattr(tg, "_tg_call", fake_tg_call)
    # Ensure secrets are present (they are in current env)
    from core import config as cfg
    assert cfg.TELEGRAM_BOT_TOKEN and cfg.TELEGRAM_WEBHOOK_SECRET, "Telegram not configured"

    unique = f"TEST_ACTIONS_TGNegroni_{uuid.uuid4().hex[:6]}"
    update = {
        "update_id": 1,
        "message": {
            "message_id": 99,
            "chat": {"id": 123456789, "type": "private"},
            "from": {"id": 123456789, "first_name": "Tester"},
            "text": f"save this as my house cocktail '{unique}': 30ml gin, 30ml campari, 30ml sweet vermouth, stirred",
        },
    }

    transport = ASGITransport(app=srv.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/api/telegram/webhook",
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": cfg.TELEGRAM_WEBHOOK_SECRET},
            timeout=120,
        )
    assert r.status_code == 200, r.text

    send_msgs = [s for s in sent if s["method"] == "sendMessage"]
    assert send_msgs, f"No sendMessage was called. All calls: {sent}"
    final_text = send_msgs[-1]["payload"].get("text", "")
    # Suffix '[saved: ...' should be appended if cocktail saved
    # (Claude may have only saved a cocktail OR collection item — both produce [saved: ...]).
    assert "[saved:" in final_text, f"Expected [saved: ...] suffix in Telegram reply, got: {final_text[:300]}"

    # Cleanup: find & delete the saved cocktail
    cocktails = requests.get(f"{API}/cocktails", timeout=30).json()
    for c in cocktails:
        if unique in c["name"]:
            _created["cocktail_ids"].add(c["id"])


# ============================================================
# 10. Twilio SMS — actions run, but no suffix in reply
# ============================================================
@pytest.mark.asyncio
async def test_twilio_sms_actions_run_but_no_suffix():
    from httpx import AsyncClient, ASGITransport
    import server as srv

    unique = f"TEST_ACTIONS_SMSNegroni_{uuid.uuid4().hex[:6]}"
    form = {
        "Body": f"save this as my house cocktail '{unique}': 30ml gin, 30ml campari, 30ml sweet vermouth, stirred",
        "From": "+15555550000",
    }
    transport = ASGITransport(app=srv.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/twilio/sms", data=form, timeout=120)
    assert r.status_code == 200, r.text
    xml = r.text
    assert "<Message>" in xml
    assert "[saved:" not in xml, f"SMS reply must NOT include [saved:] suffix. xml={xml[:300]}"

    # Verify cocktail actually got saved (server-side action executed)
    cocktails = requests.get(f"{API}/cocktails", timeout=30).json()
    matches = [c for c in cocktails if unique in c["name"]]
    assert matches, f"SMS-triggered cocktail '{unique}' was not persisted. Action layer must run for SMS too."
    _created["cocktail_ids"].add(matches[0]["id"])


# ============================================================
# 11. Previous functionality smoke
# ============================================================
def test_smoke_previous_endpoints():
    endpoints = [
        ("/cocktails", list),
        ("/collections", list),
        ("/inventory", list),
        ("/memory", list),
        ("/substitutions", list),
        ("/telegram/status", dict),
    ]
    for path, t in endpoints:
        r = requests.get(f"{API}{path}", timeout=30)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
        assert isinstance(r.json(), t), f"{path} wrong shape"


def test_smoke_abv_tool():
    payload = {
        "ingredients": [
            {"name": "Gin", "amount_ml": 60, "abv": 40},
            {"name": "Vermouth", "amount_ml": 10, "abv": 17},
        ],
        "dilution_ml": 30,
    }
    r = requests.post(f"{API}/tools/abv", json=payload, timeout=30)
    assert r.status_code == 200
    out = r.json()
    assert "abv_pct" in out or "final_abv" in out or "abv" in out


def test_smoke_weather():
    r = requests.get(f"{API}/companion/weather", timeout=30)
    assert r.status_code == 200
    data = r.json()
    # tolerant: source may be open-meteo or wttr fallback
    assert "temp_c" in data or "temperature" in data, f"weather payload missing temp: {data}"


# ============================================================
# Cleanup (runs once at end of session)
# ============================================================
@pytest.fixture(scope="session", autouse=True)
def _cleanup_at_end():
    yield
    # Delete cocktails
    for cid in list(_created["cocktail_ids"]):
        try:
            requests.delete(f"{API}/cocktails/{cid}", timeout=15)
        except Exception:
            pass
    # Delete collections (and their items)
    for col_id in list(_created["collection_ids"]):
        try:
            requests.delete(f"{API}/collections/{col_id}", timeout=15)
        except Exception:
            pass
    # Delete TEST_ACTIONS_ collections by name sweep (catches LLM-auto-created ones)
    try:
        cols = requests.get(f"{API}/collections", timeout=15).json()
        for c in cols:
            if "TEST_ACTIONS_" in c.get("name", ""):
                requests.delete(f"{API}/collections/{c['id']}", timeout=15)
    except Exception:
        pass
    # Delete cocktails sweep
    try:
        cks = requests.get(f"{API}/cocktails", timeout=15).json()
        for c in cks:
            if "TEST_ACTIONS_" in c.get("name", ""):
                requests.delete(f"{API}/cocktails/{c['id']}", timeout=15)
    except Exception:
        pass
    # Inventory sweep
    try:
        inv = requests.get(f"{API}/inventory", timeout=15).json()
        for i in inv:
            if "TEST_ACTIONS_" in i.get("name", ""):
                requests.delete(f"{API}/inventory/{i['id']}", timeout=15)
    except Exception:
        pass
    # Memory sweep — look for TEST_ACTIONS marker in value
    try:
        mems = requests.get(f"{API}/memory", timeout=15).json()
        for m in mems:
            if "TEST_ACTIONS_" in (m.get("value") or "") or "TEST_ACTIONS_" in (m.get("key") or ""):
                requests.delete(f"{API}/memory/{m['id']}", timeout=15)
    except Exception:
        pass
    # Chat history sweep
    for sid in list(_created["chat_sessions"]):
        try:
            requests.delete(f"{API}/chat/history", params={"session_id": sid}, timeout=15)
        except Exception:
            pass
