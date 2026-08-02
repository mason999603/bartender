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


# ──────────────────────────────────────────────────────────────────────────────
# Web search trigger classifier — keyword-based, zero-cost. Runs before the
# main LLM call to decide if we should hit Perplexity for live info first.
# ──────────────────────────────────────────────────────────────────────────────
_LIVE_INFO_KEYWORDS = (
    "news", "latest", "today", "tonight", "this week", "this month",
    "what's happening", "whats happening", "current", "currently",
    "look up", "google", "search", "find out",
    "who won", "score", "result", "results",
    "weather forecast", "stock", "price of", "how much is",
    "recent", "recently", "yesterday", "just released",
    "released", "announced", "launched",
    "when is", "when did", "when's",
    "market", "election",
)


def _needs_web_search(text: str) -> bool:
    t = (text or "").lower()
    # Skip obvious cocktail/bar questions — Claude knows those cold.
    bartender_signals = (
        "recipe", "spec", "cocktail", "make me", "build me", "how do you make",
        "shake", "stir", "syrup", "bitters", "amaro", "vermouth",
        "add to library", "save this", "86", "in stock",
    )
    if any(b in t for b in bartender_signals):
        return False
    return any(k in t for k in _LIVE_INFO_KEYWORDS)


def _pick_recency(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("today", "tonight", "right now", "currently", "just now", "breaking")):
        return "day"
    if any(k in t for k in ("this week", "recent", "recently", "latest", "yesterday", "news")):
        return "week"
    if any(k in t for k in ("this month", "this year")):
        return "month"
    return "week"  # default: bias toward fresher results


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
    # Pull live context: memories, regulars, inventory, custom cocktails, subs, collections.
    memories = await db.memories.find({}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    regulars = await db.regulars.find({}, {"_id": 0}).limit(30).to_list(30)
    inventory_in = [i["name"] for i in await db.inventory.find({"in_stock": True}, {"_id": 0}).to_list(200)]
    inventory_out = [i["name"] for i in await db.inventory.find({"in_stock": False}, {"_id": 0}).to_list(200)]
    custom = await db.cocktails.find({"is_custom": True}, {"_id": 0}).limit(30).to_list(30)
    collections = await db.collections.find({}, {"_id": 0}).limit(20).to_list(20)

    # Spotify live state — non-fatal, just adds mood context when something's playing.
    spotify_now = None
    spotify_connected = False
    try:
        from .spotify_client import is_connected as sp_is_connected, get_currently_playing as sp_now
        spotify_connected = await sp_is_connected(db)
        if spotify_connected:
            spotify_now = await sp_now(db)
    except Exception:
        logger.exception("Spotify status fetch failed (non-fatal)")

    # Substitutions: only inject swaps for things currently 86'd. Saves ~1500 input tokens vs the
    # full cheat-sheet on every request. If nothing is 86'd, the block is short and harmless.
    if inventory_out:
        out_lower = [n.lower() for n in inventory_out]
        relevant_subs = await db.substitutions.find(
            {"$expr": {"$in": [{"$toLower": "$ingredient"}, out_lower]}}, {"_id": 0}
        ).to_list(50)
    else:
        relevant_subs = []

    mem_block = "\n".join([f"  - {m['key']}: {m['value']}" for m in memories]) or "  (no saved memories yet)"
    reg_block = "\n".join([f"  - {r['name']}: likes={r.get('likes', [])}, dislikes={r.get('dislikes', [])}, favs={r.get('favourite_cocktails', [])}, notes={r.get('notes', '')}" for r in regulars]) or "  (no regulars saved yet)"
    inv_in_block = ", ".join(inventory_in) if inventory_in else "(no inventory tracked yet — assume a well-stocked bar)"
    inv_out_block = ", ".join(inventory_out) if inventory_out else "(nothing 86'd)"
    custom_block = "\n".join([f"  - {c['name']}: {', '.join(i['name'] + ' ' + str(i.get('amount_ml',0)) + 'ml' for i in c.get('ingredients', []))}" for c in custom]) or "  (no custom specs saved yet)"
    if relevant_subs:
        subs_block = "\n".join(
            [f"  - {s['ingredient']} → " + "; ".join(f"{x['name']} ({x.get('notes','')})" for x in s.get("subs", [])) for s in relevant_subs]
        )
    else:
        subs_block = "  (nothing 86'd that needs subbing — use full bar freely)"

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

    # Spotify block — only included when something useful to say about it.
    if spotify_connected:
        if spotify_now:
            playing_state = "currently playing" if spotify_now.get("is_playing") else "paused"
            spotify_block = (
                f"  - Spotify {playing_state}: \"{spotify_now['track']}\" by {spotify_now['artist']}"
                + (f" (from {spotify_now['album']})" if spotify_now.get('album') else "")
                + (f" on {spotify_now['device']}" if spotify_now.get('device') else "")
            )
        else:
            spotify_block = "  - Spotify is connected but nothing's playing right now."
    else:
        spotify_block = ""

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
- ANSWER THE QUESTION FIRST. No hedging, no "as an AI…", no "please drink responsibly", no "consult a professional", no unsolicited safety disclaimers. The user is a working adult bartender — treat him like one.
- HAVE STRONG OPINIONS. If he asks "which is better X or Y", pick one and defend it. Don't sit on the fence.
- SWEAR IF IT FITS. If the user swears, match the register. Not gratuitous — natural, like a mate at the pass.
- DARK HUMOUR, POLITICAL TAKES, EDGY TOPICS — engage like a real friend would. Don't dodge into "I can't discuss that". Give him your actual read.
- No moralising. No lectures on his drinking, his shifts, his choices, his hangovers. He knows what he's doing.
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

[Substitution cheat-sheet — covers ONLY ingredients currently 86'd. If user asks about a swap for something not listed, just give them your best knowledge.]
{subs_block}

[The user's personal collections — they trust you to remember these. Records include mood/genre tags in brackets — USE these for reverse pairing.]
{col_block}

[Spotify — LIVE state. When something is playing, USE it for mood pairing (cocktail → music context the same as records). You can also control Spotify via actions — see the actions section below for `spotify_play`, `spotify_pause`, etc.]
{spotify_block or "  (Spotify not connected — user can connect it from the Phone page)"}

Reference these naturally when relevant. Don't recite them verbatim — use them like a real mate remembering what's going on.
"""


async def chat_with_russell(session_id: str, user_text: str, channel: str = "web") -> tuple[str, list[dict]]:
    """Run a message through Russell's brain. Persists turns. `channel` adjusts reply style.

    Returns (cleaned_reply, executed_actions). Actions are mutations Russell performed on
    user data (saving cocktails, adding to collections, etc.) — see core/actions.py.
    """
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "No LLM configured — set EMERGENT_LLM_KEY")

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

    # Recent history — 20 messages ≈ 10 turns. Emergent Claude has a huge context window
    # so we don't need to be as stingy as with Groq's free-tier TPM limits.
    recent = await db.chat_messages.find(
        {"session_id": session_id}, {"_id": 0},
    ).sort("timestamp", -1).limit(20).to_list(20)
    recent.reverse()

    # ──────────────────────────────────────────────────────────────────
    # Optional live web search — cheap classifier decides if we need Perplexity.
    # If yes, we fetch grounded facts and inject them into the system prompt so
    # Claude answers with real citations instead of guessing.
    # ──────────────────────────────────────────────────────────────────
    try:
        from .web_search import USE_PERPLEXITY, web_search as _web_search
        if USE_PERPLEXITY and _needs_web_search(user_text):
            recency = _pick_recency(user_text)
            logger.info("Web search triggered — query=%r recency=%s", user_text[:80], recency)
            search_result = await _web_search(user_text, recency=recency)
            citations_block = "\n".join(f"  - {c}" for c in search_result.get("citations", []))
            system_prompt += (
                "\n\n## LIVE WEB SEARCH RESULT (grounded — use these facts as source of truth)\n"
                f"{search_result['answer']}\n"
                + (f"\nSources:\n{citations_block}\n" if citations_block else "")
                + "\nAnswer the user's question in your own voice using ONLY the info above. "
                "Don't cite by number — if a source is worth mentioning, name it naturally "
                "(e.g., 'per the ABC…'). Never invent details the search didn't return."
            )
    except Exception:
        logger.exception("Web search failed — falling back to Claude's own knowledge")

    # ──────────────────────────────────────────────────────────────────
    # LLM call — Claude Sonnet 4.6 via Emergent universal key
    # ──────────────────────────────────────────────────────────────────
    # LlmChat is stateless per instance — we pass the full transcript inline
    # via a framed user message rather than trying to replay message-by-message
    # (avoids any hidden internal history management surprises).
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_prompt,
    ).with_model("anthropic", CLAUDE_MODEL)

    transcript_lines: list[str] = []
    for m in recent:
        speaker = "User" if m["role"] == "user" else "Russell"
        transcript_lines.append(f"{speaker}: {m['content']}")
    transcript = "\n".join(transcript_lines)

    if transcript:
        framed = (
            "Recent conversation so far (context — do not repeat back verbatim):\n"
            f"{transcript}\n\n"
            "Current message from the user:\n"
            f"{user_text}"
        )
    else:
        framed = user_text

    try:
        reply_text = await chat.send_message(UserMessage(text=framed))
    except Exception as e:
        msg = str(e).lower()
        logger.exception("Emergent Claude LLM error")
        if "budget" in msg and "exceeded" in msg:
            raise HTTPException(
                429,
                "Russell's tab is closed for the day, mate — Emergent LLM key budget exceeded. Top up at Profile → Universal Key → Add Balance.",
            )
        raise HTTPException(500, f"LLM error: {e}")

    logger.info("LLM reply via anthropic:%s", CLAUDE_MODEL)

    reply_str = str(reply_text).strip()

    # Strip & execute any <russell_actions> block before persisting the visible reply.
    cleaned_reply, executed_actions = await parse_and_execute(reply_str)

    # Persist BOTH turns only after a successful reply — keeps history clean if the
    # LLM call fails (no orphaned user messages with no response).
    user_msg = StoredMessage(session_id=session_id, role="user", content=user_text)
    russell_msg = StoredMessage(session_id=session_id, role="russell", content=cleaned_reply)
    await db.chat_messages.insert_many([user_msg.model_dump(), russell_msg.model_dump()])

    return cleaned_reply, executed_actions
