"""Russell action layer — Russell can mutate user data during chat.

Format:
    Claude appends a hidden block at the end of his reply:

        <russell_actions>
        [{"type": "add_cocktail", "name": "...", ...}, ...]
        </russell_actions>

    `parse_and_execute()` extracts the block, runs each action against the DB,
    and returns (cleaned_reply, list_of_executed_actions).

Supported action types:
    - add_cocktail            → /api/cocktails (custom spec)
    - add_collection_item     → finds (or auto-creates) a collection and pushes an item
    - create_collection       → spins up a new collection
    - add_memory              → key/value note in /api/memory
    - set_inventory           → 86 or restock an ingredient
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .db import db
from .models import (
    Cocktail,
    CocktailIngredient,
    Collection,
    CollectionItem,
    InventoryItem,
    Memory,
)

logger = logging.getLogger("russell.actions")

ACTION_BLOCK_RE = re.compile(
    # Be liberal in what we accept. The 8B fallback model has a habit of emitting
    # `[russell_actions>` (markdown-style square open) or `[russell_actions]` instead
    # of the proper `<russell_actions>...</russell_actions>` wrap. We accept any
    # combo of `<` / `[` for open and `>` / `]` for close, then yank the JSON array
    # between them. The 70B model emits the proper tags — both styles work.
    r"[<\[]\s*russell_actions\s*[>\]]\s*(\[.*?\])\s*[<\[]\s*/\s*russell_actions\s*[>\]]",
    re.DOTALL | re.IGNORECASE,
)

# Last-ditch fallback when even the closing tag is missing/malformed — find any
# JSON array immediately preceded by the words "russell_actions" or "russell actions"
# (with any bracket noise around it) and capture from there.
ACTION_FALLBACK_RE = re.compile(
    r"[<\[]?\s*russell_actions\s*[>\]]?\s*(\[\s*\{.*?\}\s*\])",
    re.DOTALL | re.IGNORECASE,
)


# ============================================================
# System prompt block — appended to Russell's persona instructions
# ============================================================
ACTIONS_PROMPT = """
## TAKING ACTIONS ON THE USER'S DATA

You can save things directly to the user's database during a conversation. To do so,
APPEND a special JSON block at the very END of your reply. The user does NOT see this
block — it's parsed and executed silently. Your visible reply should still confirm in
plain English what you saved ("Saved — Mezcal Margarita's in your Library now, mate.").

FORMAT (only emit this when the user clearly asks you to save/remember/add/86 something):

<russell_actions>
[
  {"type": "add_cocktail", "name": "Mezcal Margarita", "category": "sour", "glassware": "rocks", "garnish": "salt rim, lime wheel", "method": "shake", "ingredients": [{"name": "Mezcal", "amount_ml": 45}, {"name": "Lime juice", "amount_ml": 22}, {"name": "Agave syrup", "amount_ml": 15}], "instructions": "Shake hard with ice, strain over a big rock. Half-rim with salt.", "flavor_profile": ["smoky", "tart", "agave"], "tags": ["mezcal", "sour"]}
]
</russell_actions>

ACTION TYPES YOU CAN EMIT:

1. add_cocktail — save a custom cocktail spec the user wants in their Library.
   Required: `name`, `ingredients` (array of {name, amount_ml}).
   Optional: `category`, `glassware`, `garnish`, `method` (shake/stir/build/throw),
             `instructions`, `flavor_profile` (array), `tags` (array).

2. add_collection_item — add something to one of the user's personal collections
   (Records, Books, Movies, etc.). If the collection doesn't exist yet, the system
   creates it automatically.
   Required: `collection_name`, `title`.
   Optional: `subtitle` (year / artist / author), `tags` (array — for records use
             genre/mood like "Reggae", "Rock", "Smoky", "Late Night"), `notes`,
             `rating` (integer 1-5).

3. create_collection — only when the user clearly wants a brand-new collection
   category that doesn't exist yet (e.g. "start me a Whiskey Wishlist").
   Required: `name`. Optional: `icon` (one of: stack, vinyl, book, film, music),
   `description`.

4. add_memory — save a general fact the user wants you to remember (e.g.
   preferences, where their bar is, who their partner is).
   Required: `key` (short slug like "favorite_spirit"), `value` (the actual content).

5. set_inventory — 86 or restock an ingredient. Use when the user says things like
   "we're out of X" or "X is back in".
   Required: `name`, `in_stock` (boolean).

6. spotify_play — start playback on the user's Spotify (Premium, voice-controlled).
   Use when the user asks you to play music. Examples:
     "play some Marley" → {"type":"spotify_play","query":"Bob Marley","kind":"artist"}
     "put on Kind of Blue" → {"type":"spotify_play","query":"Kind of Blue Miles Davis","kind":"album"}
     "play Redemption Song" → {"type":"spotify_play","query":"Redemption Song Bob Marley","kind":"track"}
     "throw on some smoky tiki music" → {"type":"spotify_play","query":"smoky dub reggae","kind":"playlist"}
   Required: `query` (search terms).
   Optional: `kind` (one of: track | album | artist | playlist, default "track").
   The system will search Spotify and start playing the top match on the user's active device.

7. spotify_pause / spotify_resume / spotify_next / spotify_previous — simple controls.
   No fields required. Use when the user says "pause", "skip", "next track", "go back".
     {"type":"spotify_pause"} / {"type":"spotify_next"} etc.

8. spotify_volume — set Spotify volume.
   Required: `percent` (integer 0-100).
   Use for "turn it up", "quieter please", "max it". Pick a reasonable level
   (e.g. up=80, down=30, max=100, mute=0) unless they give a specific number.

9. spotify_queue — queue a track to play after the current one.
   Required: `query`. Use when user says "queue X next", "play X after this".

RULES — READ CAREFULLY:
- ONLY emit actions when the user clearly asked you to save/add/remember/86 something,
  OR when they're sharing a finished spec and you can tell they'd want it kept.
- If you're unsure ("this is great" — is that 'save this' or just a comment?), don't
  guess. Ask first: "Want me to chuck that in your Library?"
- ALWAYS write your normal conversational reply BEFORE the actions block, and in that
  reply confirm exactly what you saved.
- Multiple actions per turn? Put them all in the same JSON array.
- DON'T wrap the actions block in markdown code fences. Just the raw tag.
- DON'T mention the actions block to the user — it's invisible to them.
- For add_collection_item on records, look at the existing tags style from the user's
  collection and match the same shape (Title: "Artist — Album", tags = genre/mood).
- CRITICAL — JSON VALUE RULES:
  • `amount_ml` MUST be a real number like `45` or `22.5`. NEVER a placeholder string
    like "insert_amount", "TBD", or "to taste". If you genuinely don't know the
    amount, use `0` (zero) — the system treats that as "no measurement specified".
  • All string fields must be real text or empty string "" — never a placeholder.
  • Booleans must be `true` or `false` (lowercase), not strings.
  • If you cannot fill a required field with a real value, OMIT the whole action and
    ask the user for the missing info in your conversational reply instead.
"""


# ============================================================
# Action runners
# ============================================================

def _coerce_float(v: Any, field: str = "") -> float:
    """Best-effort conversion. Falls back to 0.0 instead of throwing so a single
    junk value (e.g., the 8B model emitting a placeholder string like 'insert_amount')
    doesn't tank the whole save.
    """
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        # Last-ditch: pull the first number out of the string (handles "45 ml" → 45.0).
        if isinstance(v, str):
            m = re.search(r"-?\d+(?:\.\d+)?", v)
            if m:
                return float(m.group(0))
        logger.warning("Couldn't parse %s=%r as number — defaulting to 0", field, v)
        return 0.0


async def _run_add_cocktail(a: dict) -> dict:
    if not a.get("name") or not a.get("ingredients"):
        raise ValueError("add_cocktail requires `name` and `ingredients`")
    cocktail = Cocktail(
        name=a["name"],
        category=a.get("category", "custom"),
        glassware=a.get("glassware", ""),
        garnish=a.get("garnish", ""),
        method=a.get("method", ""),
        ingredients=[
            CocktailIngredient(
                name=i.get("name", ""),
                amount_ml=_coerce_float(i.get("amount_ml"), "amount_ml"),
                notes=i.get("notes"),
            )
            for i in a.get("ingredients", [])
            if i.get("name")
        ],
        instructions=a.get("instructions", ""),
        flavor_profile=list(a.get("flavor_profile") or []),
        tags=list(a.get("tags") or []),
        is_custom=True,
    )
    await db.cocktails.insert_one(cocktail.model_dump())
    return {"id": cocktail.id, "name": cocktail.name, "kind": "cocktail"}


async def _run_create_collection(a: dict) -> dict:
    if not a.get("name"):
        raise ValueError("create_collection requires `name`")
    col = Collection(
        name=a["name"],
        icon=a.get("icon", "stack"),
        description=a.get("description", ""),
    )
    await db.collections.insert_one(col.model_dump())
    return {"id": col.id, "name": col.name, "kind": "collection"}


async def _run_add_collection_item(a: dict) -> dict:
    if not a.get("collection_name") or not a.get("title"):
        raise ValueError("add_collection_item requires `collection_name` and `title`")

    cname = a["collection_name"].strip()
    # Find the collection by case-insensitive exact-name match.
    col = await db.collections.find_one(
        {"name": {"$regex": f"^{re.escape(cname)}$", "$options": "i"}}, {"_id": 0}
    )
    created = False
    if not col:
        # Auto-create with a sensible default icon based on the collection name.
        lower = cname.lower()
        if "record" in lower or "vinyl" in lower or "music" in lower or "album" in lower:
            icon = "vinyl"
        elif "book" in lower:
            icon = "book"
        elif "film" in lower or "movie" in lower or "watch" in lower:
            icon = "film"
        else:
            icon = "stack"
        col_obj = Collection(name=cname, icon=icon)
        await db.collections.insert_one(col_obj.model_dump())
        col = col_obj.model_dump()
        created = True

    item = CollectionItem(
        title=a["title"],
        subtitle=a.get("subtitle", ""),
        tags=list(a.get("tags") or []),
        notes=a.get("notes", ""),
        rating=a.get("rating"),
    )
    await db.collections.update_one(
        {"id": col["id"]}, {"$push": {"items": item.model_dump()}}
    )
    return {
        "kind": "collection_item",
        "collection_name": col["name"],
        "collection_created": created,
        "title": item.title,
        "item_id": item.id,
    }


async def _run_add_memory(a: dict) -> dict:
    if not a.get("key") or not a.get("value"):
        raise ValueError("add_memory requires `key` and `value`")
    mem = Memory(key=a["key"], value=a["value"])
    await db.memories.insert_one(mem.model_dump())
    return {"id": mem.id, "key": mem.key, "kind": "memory"}


async def _run_set_inventory(a: dict) -> dict:
    if not a.get("name") or "in_stock" not in a:
        raise ValueError("set_inventory requires `name` and `in_stock` (boolean)")

    name = a["name"].strip()
    raw_in_stock = a["in_stock"]
    # Tolerate the 8B model emitting "true"/"false" as strings or yes/no.
    if isinstance(raw_in_stock, str):
        in_stock = raw_in_stock.strip().lower() in {"true", "yes", "y", "1", "in_stock"}
    else:
        in_stock = bool(raw_in_stock)

    # Match by name case-insensitively (regex). Upsert: if it doesn't exist yet, create it.
    existing = await db.inventory.find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}, {"_id": 0}
    )
    if existing:
        await db.inventory.update_one(
            {"id": existing["id"]}, {"$set": {"in_stock": in_stock}}
        )
        return {
            "kind": "inventory",
            "name": existing["name"],
            "in_stock": in_stock,
            "created": False,
        }

    item = InventoryItem(name=name, in_stock=in_stock)
    await db.inventory.insert_one(item.model_dump())
    return {
        "kind": "inventory",
        "name": item.name,
        "in_stock": in_stock,
        "created": True,
    }


async def _sp_client():
    """Lazy import + grab a fresh spotipy client. Centralised so action runners stay tiny."""
    from .spotify_client import get_spotify_client
    return await get_spotify_client(db)


async def _run_spotify_play(a: dict) -> dict:
    from .spotify_client import search_and_play
    query = (a.get("query") or "").strip()
    if not query:
        raise ValueError("spotify_play requires `query`")
    kind = (a.get("kind") or "track").strip().lower()
    if kind not in {"track", "album", "artist", "playlist"}:
        kind = "track"
    result = await search_and_play(db, query, kind)
    return {"kind": "spotify", "action": "play", **result}


async def _run_spotify_pause(_a: dict) -> dict:
    sp = await _sp_client()
    sp.pause_playback()
    return {"kind": "spotify", "action": "pause"}


async def _run_spotify_resume(_a: dict) -> dict:
    sp = await _sp_client()
    sp.start_playback()
    return {"kind": "spotify", "action": "resume"}


async def _run_spotify_next(_a: dict) -> dict:
    sp = await _sp_client()
    sp.next_track()
    return {"kind": "spotify", "action": "next"}


async def _run_spotify_previous(_a: dict) -> dict:
    sp = await _sp_client()
    sp.previous_track()
    return {"kind": "spotify", "action": "previous"}


async def _run_spotify_volume(a: dict) -> dict:
    pct_raw = a.get("percent")
    pct = int(_coerce_float(pct_raw, "percent"))
    pct = max(0, min(100, pct))
    sp = await _sp_client()
    sp.volume(pct)
    return {"kind": "spotify", "action": "volume", "percent": pct}


async def _run_spotify_queue(a: dict) -> dict:
    query = (a.get("query") or "").strip()
    if not query:
        raise ValueError("spotify_queue requires `query`")
    sp = await _sp_client()
    results = sp.search(q=query, type="track", limit=1)
    items = ((results.get("tracks") or {}).get("items")) or []
    if not items:
        raise ValueError(f"No track matched '{query}'")
    track = items[0]
    sp.add_to_queue(track["uri"])
    return {
        "kind": "spotify",
        "action": "queue",
        "name": track["name"],
        "artist": ", ".join(a["name"] for a in track.get("artists", [])),
    }


_DISPATCH = {
    "add_cocktail": _run_add_cocktail,
    "add_collection_item": _run_add_collection_item,
    "create_collection": _run_create_collection,
    "add_memory": _run_add_memory,
    "set_inventory": _run_set_inventory,
    "spotify_play": _run_spotify_play,
    "spotify_pause": _run_spotify_pause,
    "spotify_resume": _run_spotify_resume,
    "spotify_next": _run_spotify_next,
    "spotify_previous": _run_spotify_previous,
    "spotify_volume": _run_spotify_volume,
    "spotify_queue": _run_spotify_queue,
}


# ============================================================
# Parser + executor
# ============================================================

async def parse_and_execute(reply: str) -> tuple[str, list[dict[str, Any]]]:
    """Strip the <russell_actions> block from `reply`, run each action, return (clean_reply, executed)."""
    m = ACTION_BLOCK_RE.search(reply)
    if m:
        raw = m.group(1)
        cleaned = ACTION_BLOCK_RE.sub("", reply).strip()
    else:
        # Fallback regex for when only the opening tag survived — better to save a
        # cocktail with a slightly messy reply than to drop it entirely.
        m = ACTION_FALLBACK_RE.search(reply)
        if not m:
            return reply, []
        raw = m.group(1)
        cleaned = ACTION_FALLBACK_RE.sub("", reply).strip()
        logger.warning("Action block matched via FALLBACK regex (malformed tags from LLM)")

    try:
        actions = json.loads(raw)
        if not isinstance(actions, list):
            raise ValueError("actions block must be a JSON array")
    except Exception as e:
        logger.warning(f"Failed to parse Russell actions block: {e} | raw={raw[:200]!r}")
        return cleaned, []

    executed: list[dict[str, Any]] = []
    for a in actions:
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        runner = _DISPATCH.get(t)
        if not runner:
            logger.warning(f"Unknown action type: {t!r}")
            executed.append({"type": t, "ok": False, "error": f"unknown action type: {t!r}"})
            continue
        try:
            result = await runner(a)
            executed.append({"type": t, "ok": True, "result": result})
            logger.info(f"[action] {t} → {result}")
        except Exception as e:
            logger.exception(f"[action] {t} failed")
            executed.append({"type": t, "ok": False, "error": str(e)})

    return cleaned, executed


def summarize_for_channel(executed: list[dict[str, Any]]) -> str:
    """One-line summary for non-web channels (SMS/Telegram). Empty string if nothing saved."""
    if not executed:
        return ""
    saved_bits: list[str] = []
    for ex in executed:
        if not ex.get("ok"):
            continue
        result = ex.get("result") or {}
        kind = result.get("kind")
        if kind == "cocktail":
            saved_bits.append(f"cocktail '{result.get('name')}'")
        elif kind == "collection_item":
            cname = result.get("collection_name", "collection")
            saved_bits.append(f"'{result.get('title')}' → {cname}")
        elif kind == "collection":
            saved_bits.append(f"new collection '{result.get('name')}'")
        elif kind == "memory":
            saved_bits.append(f"memory '{result.get('key')}'")
        elif kind == "inventory":
            state = "86'd" if not result.get("in_stock") else "back in stock"
            saved_bits.append(f"{result.get('name')} {state}")
        elif kind == "spotify":
            act = result.get("action", "")
            if act == "play":
                saved_bits.append(f"♪ playing {result.get('name', '?')}")
            elif act == "queue":
                saved_bits.append(f"♪ queued {result.get('name', '?')}")
            elif act == "volume":
                saved_bits.append(f"♪ volume {result.get('percent')}%")
            else:
                saved_bits.append(f"♪ {act}")
    if not saved_bits:
        return ""
    return "  [saved: " + "; ".join(saved_bits) + "]"
