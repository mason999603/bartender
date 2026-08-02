"""Russell's Studio — content pipeline for faceless cocktail videos.

Endpoints:
    POST /api/studio/ideas          → generate video ideas for a topic
    POST /api/studio/script         → write a full script (short + long)
    POST /api/studio/voiceover      → generate narration audio (returns WAV url)
    GET  /api/studio/scripts        → list saved scripts
    POST /api/studio/scripts        → save a script
    DELETE /api/studio/scripts/{id} → delete a script

Text generation goes through the same Emergent Claude the brain uses. Voiceover
uses the existing /api/voice/speak infrastructure (OpenAI TTS onyx).
"""
from __future__ import annotations

import logging
import uuid

from emergentintegrations.llm.chat import LlmChat, UserMessage
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import EMERGENT_LLM_KEY, CLAUDE_MODEL
from core.db import db
from core.models import now_iso

router = APIRouter(prefix="/studio", tags=["studio"])
logger = logging.getLogger("russell.studio")


# ─────────────────────────────────────────────────────────────────────────────
# Persona: keep Russell's voice consistent across all generated content
# ─────────────────────────────────────────────────────────────────────────────
STUDIO_PERSONA = """You are Russell — a witty, dry, down-to-earth young Australian bartender. Real bloke energy: confident without being arrogant, quick with a one-liner, never robotic.

You're generating faceless AI video content for TikTok and YouTube — targeting hospitality workers, home bartenders, and cocktail curious viewers.

Your content DNA:
- HOOK IN THE FIRST 2 SECONDS. Every video. Non-negotiable for short-form.
- Speak like you'd explain something to a mate at the bar mid-service. Not lecturing.
- Sharp opinions welcome. Take sides. The internet rewards conviction.
- Show, don't just tell — describe visual cues ("watch the crown of bubbles collapse", "notice how the ice cracks")
- Every video should teach something specific and useful. No fluff.
- Aussie tone but subtle — not parody. Occasional "mate", "reckon", "fair dinkum".
- Never invent facts. If you don't know it, don't say it."""


class IdeasRequest(BaseModel):
    topic: str
    count: int = 5


@router.post("/ideas")
async def generate_ideas(req: IdeasRequest):
    """Generate hook-driven video ideas for a given topic."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")
    if not req.topic.strip():
        raise HTTPException(400, "Provide a `topic`")

    count = max(1, min(15, req.count))
    prompt = f"""Generate {count} faceless AI video ideas around this topic: **{req.topic}**

For each idea, return in this EXACT format (no markdown, no extra text):

TITLE: <catchy title, max 60 chars>
HOOK: <the first 8-second on-screen line that stops the scroll>
ANGLE: <one sentence on the unique take or angle>
PLATFORM: <best fit — "tiktok", "youtube-shorts", "youtube-long", or "both">
---

Rules:
- Hooks should provoke, surprise, or challenge conventional wisdom. Not "In this video I'll teach you..."
- Mix formats: some myth-busters, some technique deep-dives, some hot takes, some quick tips
- Angles should be things a normal cocktail YouTuber wouldn't cover
- No repetitive ideas — each must be genuinely different"""

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"studio_ideas_{uuid.uuid4()}",
        system_message=STUDIO_PERSONA,
    ).with_model("anthropic", CLAUDE_MODEL)

    try:
        raw = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("Idea generation failed")
        raise HTTPException(500, f"LLM error: {e}")

    # Parse the fixed-format blocks
    ideas = []
    for block in str(raw).split("---"):
        block = block.strip()
        if not block:
            continue
        entry = {"title": "", "hook": "", "angle": "", "platform": ""}
        for line in block.splitlines():
            for k in ("TITLE", "HOOK", "ANGLE", "PLATFORM"):
                if line.upper().startswith(k + ":"):
                    entry[k.lower()] = line.split(":", 1)[1].strip()
        if entry["title"] and entry["hook"]:
            ideas.append(entry)

    return {"topic": req.topic, "ideas": ideas}


class ScriptRequest(BaseModel):
    title: str
    hook: str
    angle: str = ""
    platform: str = "tiktok"  # tiktok | youtube-shorts | youtube-long | both


@router.post("/script")
async def generate_script(req: ScriptRequest):
    """Write the full narration script + on-screen text cues + b-roll notes."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")

    if req.platform in ("tiktok", "youtube-shorts"):
        length_brief = "60 seconds max (about 150 words spoken)"
    elif req.platform == "youtube-long":
        length_brief = "4-6 minutes (about 700-900 words spoken)"
    else:  # both
        length_brief = "provide BOTH a 60-second short version AND a 4-6 min long-form version, clearly labelled"

    prompt = f"""Write the narration script for this video:

Title: {req.title}
Hook: {req.hook}
Angle: {req.angle}
Platform target: {req.platform}
Length: {length_brief}

Return in this format:

## SPOKEN SCRIPT
<the actual narration — pure spoken word, no stage directions inline. Write it exactly as Russell would say it. Include natural pauses shown with commas and full stops.>

## ON-SCREEN TEXT (for subtitles / caption overlays)
<the same script broken into 4-8 word chunks per line, one line per caption card, roughly matching cadence>

## B-ROLL SHOT LIST
<numbered list of visual shots the editor should cut to, one per line. Be specific: "hero shot: whisky pouring into a rocks glass, slow-mo, warm light" not just "cocktail shot". Prefer shots achievable with stock footage or basic AI image generation.>

## HASHTAGS
<15 hashtags mixing high-volume (#cocktails), niche (#homebartending), and trending (#booktok-style bar takeover if applicable). Comma-separated.>

Rules:
- HOOK is the first line of the spoken script — literally the hook you were given, or a slightly punchier version
- No "hey guys welcome back" openings. Ever.
- End on a specific takeaway or a hot take, not a "smash the subscribe button"
- Match tone to platform: TikTok = punchy, YouTube = slightly more considered but still tight"""

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"studio_script_{uuid.uuid4()}",
        system_message=STUDIO_PERSONA,
    ).with_model("anthropic", CLAUDE_MODEL)

    try:
        raw = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("Script generation failed")
        raise HTTPException(500, f"LLM error: {e}")

    return {
        "title": req.title,
        "hook": req.hook,
        "platform": req.platform,
        "script_markdown": str(raw),
    }


class SavedScriptRequest(BaseModel):
    title: str
    hook: str
    platform: str
    script_markdown: str


@router.get("/scripts")
async def list_scripts():
    docs = await db.studio_scripts.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


@router.post("/scripts")
async def save_script(req: SavedScriptRequest):
    doc = {
        "id": str(uuid.uuid4()),
        "title": req.title,
        "hook": req.hook,
        "platform": req.platform,
        "script_markdown": req.script_markdown,
        "created_at": now_iso(),
    }
    await db.studio_scripts.insert_one(doc.copy())
    return {"id": doc["id"], "created_at": doc["created_at"]}


@router.delete("/scripts/{script_id}")
async def delete_script(script_id: str):
    r = await db.studio_scripts.delete_one({"id": script_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Script not found")
    return {"deleted": True}
