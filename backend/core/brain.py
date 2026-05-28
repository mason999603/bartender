"""Russell's brain — chat orchestration, system prompt, clash detection.

Shared by web chat, SMS, and voice routers.
"""
from __future__ import annotations

import logging
import re
from typing import List

from fastapi import HTTPException

from emergentintegrations.llm.chat import LlmChat, UserMessage

from .config import EMERGENT_LLM_KEY, CLAUDE_MODEL
from .db import db
from .models import StoredMessage
from .actions import ACTIONS_PROMPT, parse_and_execute
from companion import build_companion_context

logger = logging.getLogger("russell.brain")


async def get_clash_warnings(ingredient_names: List[str]) -> List[dict]:
    names_lower = [n.lower() for n in ingredient_names]
    rules = await db.clash_rules.find({}, {"_id": 0}).to_list(1000)
    warnings = []
    for r in rules:
        a, b = r["a"].lower(), r["b"].lower()
        # exact match either direction
        if a in names_lower and b in names_lower:
            warnings.append(r)
            continue
        # partial match for liberal hits (e.g., "cream" matching "Heavy Cream")
        if any(a in n or n in a for n in names_lower) and any(b in n or n in b for n in names_lower):
            if r not in warnings:
                warnings.append(r)
    return warnings


async def _detect_record_mention(user_text: str) -> dict | None:
    """Reverse mood pairing detector.

    If the user mentions playing/listening to a specific record they own,
    return that item's data so we can hint the LLM to suggest a matching cocktail.

    Returns the matched collection item dict (with title/subtitle/tags) or None.
    """
    text = (user_text or "").lower().strip()
    if not text or len(text) < 4:
        return None

    # Lightweight intent filter — only fire when the user is actually engaging with music.
    music_triggers = (
        "play", "playing", "spin", "spinning", "put on", "putting on",
        "listening to", "listen to", "throw on", "throwing on", "queue up",
        "vinyl", "record", "lp", "album", "side a", "side b", "needle", "drop the needle",
        "on the turntable", "on the deck",
    )
    if not any(t in text for t in music_triggers):
        return None

    collections = await db.collections.find(
        {"name": {"$regex": "record", "$options": "i"}}, {"_id": 0}
    ).to_list(20)

    best_match = None
    best_score = 0

    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()

    text_norm = _norm(text)

    for col in collections:
        for item in col.get("items", []) or []:
            title = item.get("title") or ""
            # Titles in this collection look like "Artist — Album". Match either side.
            parts = re.split(r"[—\-–]", title, maxsplit=1)
            candidates = [title] + [p.strip() for p in parts if p.strip()]

            for cand in candidates:
                cand_n = _norm(cand)
                if not cand_n or len(cand_n) < 4:
                    continue
                if cand_n in text_norm:
                    # Longer phrase match wins — avoids matching short artist names accidentally.
                    score = len(cand_n)
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "title": title,
                            "subtitle": item.get("subtitle", ""),
                            "tags": item.get("tags", []),
                            "matched_phrase": cand,
                        }
    return best_match


async def build_russell_system_prompt() -> str:
    # Pull live context: memories, regulars, inventory, custom cocktails, subs, collections
    memories = await db.memories.find({}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    regulars = await db.regulars.find({}, {"_id": 0}).limit(30).to_list(30)
    inventory_in = [i["name"] for i in await db.inventory.find({"in_stock": True}, {"_id": 0}).to_list(200)]
    inventory_out = [i["name"] for i in await db.inventory.find({"in_stock": False}, {"_id": 0}).to_list(200)]
    custom = await db.cocktails.find({"is_custom": True}, {"_id": 0}).limit(30).to_list(30)
    subs = await db.substitutions.find({}, {"_id": 0}).to_list(500)
    collections = await db.collections.find({}, {"_id": 0}).limit(20).to_list(20)

    mem_block = "\n".join([f"  - {m['key']}: {m['value']}" for m in memories]) or "  (no saved memories yet)"
    reg_block = "\n".join([f"  - {r['name']}: likes={r.get('likes', [])}, dislikes={r.get('dislikes', [])}, favs={r.get('favourite_cocktails', [])}, notes={r.get('notes', '')}" for r in regulars]) or "  (no regulars saved yet)"
    inv_in_block = ", ".join(inventory_in) if inventory_in else "(no inventory tracked yet — assume a well-stocked bar)"
    inv_out_block = ", ".join(inventory_out) if inventory_out else "(nothing 86'd)"
    custom_block = "\n".join([f"  - {c['name']}: {', '.join(i['name'] + ' ' + str(i.get('amount_ml',0)) + 'ml' for i in c.get('ingredients', []))}" for c in custom]) or "  (no custom specs saved yet)"
    subs_block = "\n".join(
        [f"  - {s['ingredient']} → " + "; ".join(f"{x['name']} ({x.get('notes','')})" for x in s.get("subs", [])) for s in subs]
    ) or "  (none on file)"

    # Collections — render each collection compactly. For records, include tags so
    # Russell can do mood-based reverse pairing.
    if collections:
        col_lines = []
        for c in collections:
            items = c.get("items", []) or []
            is_records = "record" in (c.get("name", "") or "").lower()
            rendered = []
            for i in items[:20 if is_records else 15]:
                title = i.get("title", "")
                sub = i.get("subtitle", "")
                tags = i.get("tags", []) or []
                if is_records and tags:
                    rendered.append(f"{title}" + (f" ({sub})" if sub else "") + f" [tags: {', '.join(tags)}]")
                else:
                    rendered.append(f"{title}" + (f" ({sub})" if sub else ""))
            item_summary = "; ".join(rendered)
            if len(items) > (20 if is_records else 15):
                item_summary += f"; …and {len(items) - (20 if is_records else 15)} more"
            col_lines.append(f"  - {c['name']} ({len(items)} items): {item_summary or '(empty)'}")
        col_block = "\n".join(col_lines)
    else:
        col_block = "  (no personal collections saved yet)"

    return f"""You are RUSSELL — a witty, dry, down-to-earth young Australian. Real bloke energy: confident without being arrogant, quick with a one-liner, never robotic. You speak with subtle Aussie warmth (occasional "mate", "reckon", "no worries", "fair dinkum") but you DON'T overdo it or sound like a parody.

You're a MATE FIRST, BARTENDER SECOND. The user is your friend (a working bartender/mixologist) — talk to him like one. You can help with anything a smart mate would: the weather, what time it is, life advice, random questions, news, music, jokes, what to cook, what to watch, life stuff, philosophy, banter — *anything*. You happen to also be an expert bartender, but you're not just a cocktail vending machine.

REAL-TIME AWARENESS:
You DO have access to the current local time, date, and live weather (provided to you each turn in the REAL-TIME CONTEXT section below). Use it naturally:
- If user says "good morning" / "g'day" — greet them back warmly, mention the weather if it's interesting, suggest something time-appropriate.
- If asked "what time is it" / "what day is it" / "is it still morning" — answer directly from the context.
- If asked about the weather, the forecast, "is it gonna rain", etc. — answer with the live data, not a guess.
- Comment on weather naturally when relevant ("ripper day for an Aperol Spritz outside" / "wet one tonight — perfect Hot Toddy weather").

YOUR DEEP KNOWLEDGE (when the topic comes up):
- Encyclopedic on spirits, liqueurs, modifiers, bitters, mixers, syrups — flavour profiles, ABVs, production, regional variations.
- Cocktail chemistry: emulsion, dilution, acidity, sugar, bitterness balance. You know what clashes and why.
- Classics (IBA list), modern classics, tiki, low-ABV, zero-proof builds.
- Technique: shake hard vs gentle, dry shake order, stir vs shake, ice formats, glassware, garnish.
- Service: batching, pre-dilution, oleo saccharum, fat-washing, clarification, infusions.

BEHAVIOUR RULES:
- KEEP REPLIES TIGHT. Conversational, real-mate length. Not essay-mode unless the user clearly wants depth.
- When the user describes a build with a fatal chemistry clash (e.g., dairy + citrus), tell them straight (with the reason) and offer the fix.
- When suggesting cocktails, give a proper SPEC (with ml measurements) and method.
- When the user asks "what can I make" — check the inventory below.
- If a recipe you're suggesting needs something 86'd, PROACTIVELY swap it using the Substitutions cheat-sheet — don't make them ask.
- **AUTO-MOOD PAIRING (cocktail → record)**: when you suggest a cocktail (or the user says they're making/drinking one), check the user's *Records* collection below for a vibe match. If something fits, drop ONE casual line like *"Stick Marley — Rastaman Vibrations on while it builds."* — **CRITICAL: only ever name a record that is LITERALLY in their collection below. Never recommend music they don't own. If nothing in their collection fits the mood, skip the pairing silently — don't apologise, don't explain.** Use the exact title and artist as they appear in the collection.
- **REVERSE MOOD PAIRING (record → cocktail)**: if the user mentions playing/listening to / putting on / spinning a specific record, album, artist, or side from their *Records* collection — proactively suggest a cocktail that matches that record's vibe (use its tags as your mood cue). Keep it casual — one line is enough. e.g. *"Nice. That one's begging for a smoky Mezcal Negroni."* Pick a cocktail that genuinely fits the energy of the music; lean on the record's tags. Don't force it — if nothing matches, just react naturally to the music.
- Outside cocktails/spirits — just be a smart, funny mate. Answer briefly, share an opinion if you've got one, riff if it's fun.
- If you genuinely don't know something, say so. No making things up.
- Pure conversation — no markdown headers, no bullet lists unless really helpful, no asterisks for emphasis.

CURRENT CONTEXT THE USER HAS SAVED:

[Things you should remember about the user / bar]
{mem_block}

[Regulars / customer preferences]
{reg_block}

[Currently in stock]
{inv_in_block}

[Currently 86'd — DO NOT use these; substitute proactively]
{inv_out_block}

[User's custom cocktail specs]
{custom_block}

[Substitution cheat-sheet — use when an ingredient is 86'd or user asks for swaps]
{subs_block}

[The user's personal collections — they trust you to remember these. Records include mood/genre tags in brackets — USE these for reverse pairing.]
{col_block}

Reference these naturally when relevant. Don't recite them verbatim — use them like a real mate remembering what's going on.
"""


async def chat_with_russell(session_id: str, user_text: str, channel: str = "web") -> tuple[str, list[dict]]:
    """Run a message through Russell's brain. Persists turns. `channel` adjusts reply style.

    Returns (cleaned_reply, executed_actions). Actions are mutations Russell performed on
    user data (saving cocktails, adding to collections, etc.) — see core/actions.py.
    """
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")

    # Build system prompt with live context + actions schema + per-channel addendum + real-time grounding
    system_prompt = await build_russell_system_prompt()
    system_prompt += "\n" + ACTIONS_PROMPT

    companion_block = await build_companion_context(db, user_text)
    if companion_block:
        system_prompt += f"\n\n## REAL-TIME CONTEXT (use naturally, don't recite verbatim)\n{companion_block}"

    # Reverse mood pairing: if user mentioned a record from their collection,
    # inject a strong hint so Russell pairs a cocktail with the music.
    record = await _detect_record_mention(user_text)
    if record:
        tags = ", ".join(record.get("tags", [])) or "—"
        system_prompt += (
            "\n\n## REVERSE MOOD PAIRING TRIGGER\n"
            f"The user just mentioned playing/listening to: **{record['title']}**"
            + (f" ({record['subtitle']})" if record.get('subtitle') else "")
            + f". Vibe tags from their collection: [{tags}]. "
            "Suggest a cocktail that matches this record's energy in ONE casual line. "
            "Don't list multiple — pick the one that fits best."
        )

    if channel == "sms":
        system_prompt += (
            "\n\nCHANNEL: SMS — Keep your reply under 320 characters (2 SMS segments). "
            "Plain text only — no markdown, no lists, no bullet points. Be tight and conversational."
        )
    elif channel == "voice":
        system_prompt += (
            "\n\nCHANNEL: PHONE CALL — You're being spoken aloud over a phone. "
            "Keep replies under 35 words. No markdown, no lists, no bullet points, no headers. "
            "Pure natural speech. Don't read out ml measurements as numbers — say 'fifteen mls' style."
        )
    elif channel == "telegram":
        system_prompt += (
            "\n\nCHANNEL: TELEGRAM — Plain text only. No markdown (no **bold**, no *italics*, no headers, no bullet lists). "
            "Keep it tight and conversational like SMS but you can run a bit longer if you've got a spec to give. "
            "When you give a cocktail spec, use simple line breaks and dash-bullets like '- 60ml gin' — no asterisks."
        )

    # Recent history (last 20 messages) for transcript context — fetched BEFORE we persist
    # the new user turn so the model doesn't see a duplicate "Current message" line.
    recent = await db.chat_messages.find(
        {"session_id": session_id}, {"_id": 0},
    ).sort("timestamp", -1).limit(20).to_list(20)
    recent.reverse()

    chat_client = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_prompt,
    ).with_model("anthropic", CLAUDE_MODEL)

    transcript_lines = []
    for m in recent:
        speaker = "User" if m["role"] == "user" else "Russell"
        transcript_lines.append(f"{speaker}: {m['content']}")
    transcript = "\n".join(transcript_lines)

    if transcript:
        framed = (
            "Recent conversation so far (for context, do not repeat):\n"
            f"{transcript}\n\n"
            "Current message from the user:\n"
            f"{user_text}"
        )
    else:
        framed = user_text

    try:
        reply_text = await chat_client.send_message(UserMessage(text=framed))
    except Exception as e:
        msg = str(e).lower()
        logger.exception("LLM error")
        if "budget" in msg and "exceeded" in msg:
            raise HTTPException(
                429,
                "Russell's tab is closed for the day, mate — Emergent LLM key budget exceeded. Top it up at Profile → Universal Key → Add Balance.",
            )
        raise HTTPException(500, f"LLM error: {e}")

    reply_str = str(reply_text).strip()

    # Strip & execute any <russell_actions> block before persisting the visible reply.
    cleaned_reply, executed_actions = await parse_and_execute(reply_str)

    # Persist BOTH turns only after a successful reply — keeps history clean if the
    # LLM call fails (no orphaned user messages with no response).
    user_msg = StoredMessage(session_id=session_id, role="user", content=user_text)
    russell_msg = StoredMessage(session_id=session_id, role="russell", content=cleaned_reply)
    await db.chat_messages.insert_many([user_msg.model_dump(), russell_msg.model_dump()])

    return cleaned_reply, executed_actions
