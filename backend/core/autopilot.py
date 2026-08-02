"""Autopilot — end-to-end daily video pipeline for Russell.

One function (`produce_and_publish`) that runs from topic → idea → script →
voiceover → Sora hero clip (with persona reference) → ffmpeg assembly →
optional YouTube upload → daily-run record in Mongo.

Called by:
  • APScheduler cron job every day (started in server.py on lifespan)
  • Manual `POST /api/autopilot/run-now` from the UI
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import OpenAITextToSpeech, OpenAIVideoGeneration
from googleapiclient.http import MediaFileUpload
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.config import CLAUDE_MODEL, EMERGENT_LLM_KEY
from core.models import now_iso
from core.persona import ensure_persona_image, load_persona, persona_sora_snippet
from core.topic_rotator import next_topic
from core.youtube_client import get_youtube_client, is_connected as youtube_connected

logger = logging.getLogger("russell.autopilot")

MEDIA_DIR = Path(os.environ.get("STUDIO_MEDIA_DIR", "/app/backend/generated/studio"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Idea + script generation (Claude)
# ─────────────────────────────────────────────────────────────────────────────
_IDEA_PROMPT = """You're writing a single ~30 second faceless AI video for TikTok / YouTube Shorts, on this topic:

**{topic}**

Return in this EXACT format (no markdown, no explanations):

TITLE: <catchy title, max 60 chars>
HOOK: <the first 8-second on-screen line that stops the scroll — provocative, opinionated>
ANGLE: <one sentence on the unique take>

Rules:
- No "hey guys welcome back" style openings
- Hook must challenge conventional wisdom OR make a bold claim
- Angle should be specific and useful — a home bartender learns one concrete thing
"""


_SCRIPT_PROMPT = """Write the narration script for a ~30 second (about 75 spoken words) faceless TikTok/YouTube Shorts video:

Title: {title}
Hook: {hook}
Angle: {angle}

Return in this format:

## SPOKEN SCRIPT
<the actual narration — exactly what Russell speaks. Pure spoken word, no stage directions. Under 80 words total. First line IS the hook.>

## ON-SCREEN TEXT
<the same script broken into 4-6 word caption chunks, one line each>

## B-ROLL SHOT LIST
<3-5 numbered visual cues the video should show, achievable with a slow-mo bar/pour visual — one per line>

## HASHTAGS
<12 hashtags comma-separated: mix high-volume (#cocktails), niche (#homebartending), trend-ready. No spaces inside a tag.>

Rules:
- Hook is the first line, delivered in under 3 seconds
- End on a specific takeaway, no "smash subscribe"
- Aussie voice — dry, confident, a little cheeky. Real bloke energy.
"""

STUDIO_PERSONA_MSG = (
    "You are Russell — a witty, dry Australian bartender. Real bloke energy. "
    "Sharp opinions, teaching something specific in every video."
)


def _llm() -> LlmChat:
    return LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"autopilot_{uuid.uuid4()}",
        system_message=STUDIO_PERSONA_MSG,
    ).with_model("anthropic", CLAUDE_MODEL)


async def _gen_idea(topic: str) -> dict:
    raw = str(await _llm().send_message(UserMessage(text=_IDEA_PROMPT.format(topic=topic))))
    entry = {"title": "", "hook": "", "angle": ""}
    for line in raw.splitlines():
        for k in ("TITLE", "HOOK", "ANGLE"):
            if line.upper().startswith(k + ":"):
                entry[k.lower()] = line.split(":", 1)[1].strip()
    if not entry["title"] or not entry["hook"]:
        raise RuntimeError(f"Idea generation didn't parse: {raw[:400]}")
    return entry


async def _gen_script(idea: dict) -> str:
    raw = str(
        await _llm().send_message(
            UserMessage(text=_SCRIPT_PROMPT.format(**idea))
        )
    )
    return raw


def _extract_spoken(script: str) -> str:
    m = re.search(r"##\s*SPOKEN SCRIPT\s*\n([\s\S]*?)(?=\n##\s|$)", script, re.IGNORECASE)
    body = (m.group(1) if m else script).strip()
    return body.replace("**", "").replace("*", "").replace("`", "")


def _extract_hashtags(script: str) -> list[str]:
    m = re.search(r"##\s*HASHTAGS\s*\n([\s\S]*?)(?=\n##\s|$)", script, re.IGNORECASE)
    if not m:
        return []
    return [
        re.sub(r"[^0-9a-zA-Z]", "", t).lower()
        for t in m.group(1).replace("#", "").split(",")
        if t.strip()
    ][:12]


# ─────────────────────────────────────────────────────────────────────────────
# Media steps (voiceover, Sora, ffmpeg)
# ─────────────────────────────────────────────────────────────────────────────
async def _tts_to_disk(run_id: str, text: str) -> Path:
    tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
    audio_bytes = await tts.generate_speech(text=text, model="tts-1", voice="onyx", response_format="mp3")
    p = MEDIA_DIR / f"auto_voice_{run_id}.mp3"
    p.write_bytes(audio_bytes)
    return p


async def _sora_hero(run_id: str, prompt: str, reference: Path) -> Path:
    # Patch SDK size whitelist so 720x1280 is accepted (see studio.py)
    for extra in ("720x1280", "1280x720"):
        OpenAIVideoGeneration.SIZES.setdefault(
            extra,
            {"width": int(extra.split("x")[0]), "height": int(extra.split("x")[1])},
        )
    client = OpenAIVideoGeneration(api_key=EMERGENT_LLM_KEY)
    video_bytes = await asyncio.to_thread(
        client.text_to_video,
        prompt=prompt,
        model="sora-2",
        size="720x1280",
        duration=8,  # 8s hero looped over ~30s voiceover — sweet spot for perceived variety
        max_wait_time=600,
        image_path=str(reference) if reference.exists() else None,
        mime_type="image/png",
    )
    if not video_bytes:
        raise RuntimeError("Sora returned no bytes (safety filter or timeout)")
    p = MEDIA_DIR / f"auto_hero_{run_id}.mp4"
    p.write_bytes(video_bytes)
    return p


def _run_ffmpeg_assemble(hero: Path, voice: Path, out: Path, caption: str) -> None:
    """Loop the hero clip to cover the voiceover, burn captions, mux voice as audio."""
    import subprocess
    import tempfile

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(voice)],
        capture_output=True, text=True, check=True,
    )
    voice_dur = float(probe.stdout.strip() or 0)
    if voice_dur <= 0:
        raise RuntimeError("Can't determine voiceover duration")

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        filters = [
            "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,"
            f"trim=duration={voice_dur:.2f},setpts=PTS-STARTPTS[vout]"
        ]
        vmap = "[vout]"

        if caption.strip():
            # Split caption into 4-word chunks over the voice duration
            words = caption.split()
            chunks = [" ".join(words[i:i + 4]) for i in range(0, len(words), 4)] or [caption]
            per = max(1.0, voice_dur / len(chunks))

            def _ts(sec: float) -> str:
                h, r = divmod(int(sec), 3600)
                m, s = divmod(r, 60)
                ms = int((sec - int(sec)) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

            lines = []
            for i, c in enumerate(chunks):
                lines += [str(i + 1), f"{_ts(i * per)} --> {_ts(min(voice_dur, (i + 1) * per))}", c, ""]
            srt = tdp / "caps.srt"
            srt.write_text("\n".join(lines), encoding="utf-8")
            filters.append(
                f"{vmap}subtitles={srt}:force_style='Alignment=2,FontSize=20,"
                "PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=3,Outline=2,"
                "Shadow=0,MarginV=100'[final]"
            )
            vmap = "[final]"

        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(hero),
            "-i", str(voice),
            "-filter_complex", ";".join(filters),
            "-map", vmap, "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")


# ─────────────────────────────────────────────────────────────────────────────
# YouTube upload
# ─────────────────────────────────────────────────────────────────────────────
def _shape_title(t: str) -> str:
    t = (t or "").strip()
    if len(t) > 90:
        t = t[:87].rstrip() + "..."
    if "#shorts" not in t.lower():
        t = (t + " #Shorts")[:100]
    return t


async def _publish_to_youtube(db: AsyncIOMotorDatabase, mp4: Path, idea: dict, script: str, tags: list[str]) -> dict:
    youtube = await get_youtube_client(db)
    hashtags_line = " ".join(f"#{t}" for t in tags)
    description = f'"{idea["hook"]}"\n\n{idea["angle"]}\n\n{hashtags_line}\n\n#Shorts'.strip()[:5000]
    body = {
        "snippet": {
            "title": _shape_title(idea["title"]),
            "description": description,
            "tags": (tags[:12] + ["shorts"])[:12],
            "categoryId": "22",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }

    def _upload() -> str:
        req = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=MediaFileUpload(str(mp4), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True),
        )
        resp = None
        while resp is None:
            _status, resp = req.next_chunk()
        return resp["id"]

    video_id = await asyncio.to_thread(_upload)
    return {"video_id": video_id, "video_url": f"https://youtu.be/{video_id}"}


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline
# ─────────────────────────────────────────────────────────────────────────────
async def produce_and_publish(db: AsyncIOMotorDatabase, trigger: str = "cron") -> dict:
    """End-to-end run. Returns the run doc. Records progress in db.autopilot_runs.

    trigger: 'cron' | 'manual' — recorded for the UI.
    """
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY not configured — autopilot needs it for LLM+Sora+TTS")

    run_id = str(uuid.uuid4())
    doc = {
        "id": run_id,
        "trigger": trigger,
        "status": "starting",
        "steps": {},
        "error": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.autopilot_runs.insert_one(doc.copy())

    async def _mark(**patch) -> None:
        patch["updated_at"] = now_iso()
        # Steps dict is merged, everything else replaced
        if "step" in patch and "step_status" in patch:
            step, ss = patch.pop("step"), patch.pop("step_status")
            patch[f"steps.{step}"] = ss
        await db.autopilot_runs.update_one({"id": run_id}, {"$set": patch})

    try:
        # 1) Pick topic
        topic = await next_topic(db)
        await _mark(step="topic", step_status={"topic": topic, "ok": True}, status="ideating")

        # 2) Idea
        idea = await _gen_idea(topic)
        await _mark(step="idea", step_status={"ok": True, **idea}, status="scripting")

        # 3) Script
        script = await _gen_script(idea)
        spoken = _extract_spoken(script)
        tags = _extract_hashtags(script)
        await _mark(step="script", step_status={"ok": True, "chars": len(script), "spoken_words": len(spoken.split()), "tags": tags}, status="voicing", script_markdown=script)

        # 4) Voiceover
        voice_path = await _tts_to_disk(run_id, spoken)
        await _mark(step="voice", step_status={"ok": True, "url": f"/api/studio/media/{voice_path.name}", "bytes": voice_path.stat().st_size}, status="persona")

        # 5) Ensure persona image (cached)
        persona = await load_persona(db)
        persona_ref = await ensure_persona_image(db)
        await _mark(step="persona", step_status={"ok": True, "url": "/api/studio/media/persona.png"}, status="rendering-hero")

        # 6) Sora hero — 8s, portrait, with persona reference
        sora_prompt = f"{persona_sora_snippet(persona)} {idea['hook']} — cinematic slow-motion, warm amber tungsten light, shallow depth of field, film grain."
        hero_path = await _sora_hero(run_id, sora_prompt, persona_ref)
        await _mark(step="hero", step_status={"ok": True, "url": f"/api/studio/media/{hero_path.name}", "bytes": hero_path.stat().st_size}, status="assembling")

        # 7) Assemble
        final_path = MEDIA_DIR / f"auto_final_{run_id}.mp4"
        await asyncio.to_thread(_run_ffmpeg_assemble, hero_path, voice_path, final_path, idea["hook"])
        await _mark(
            step="assemble",
            step_status={"ok": True, "url": f"/api/studio/media/{final_path.name}", "bytes": final_path.stat().st_size},
            status="ready",
            final_filename=final_path.name,
            final_url=f"/api/studio/media/{final_path.name}",
            idea=idea,
            tags=tags,
        )

        # 8) Publish (best-effort)
        if await youtube_connected(db):
            try:
                pub = await _publish_to_youtube(db, final_path, idea, script, tags)
                await _mark(step="publish", step_status={"ok": True, **pub}, status="published", video_url=pub["video_url"], video_id=pub["video_id"])
            except Exception as e:
                logger.exception("Autopilot: publish failed but MP4 is safe")
                await _mark(step="publish", step_status={"ok": False, "error": str(e)}, status="ready-not-published", error=f"publish: {e}")
        else:
            await _mark(step="publish", step_status={"ok": False, "skipped": "YouTube not connected"}, status="ready-not-published")

        final_doc = await db.autopilot_runs.find_one({"id": run_id}, {"_id": 0})
        return final_doc or doc
    except Exception as e:
        logger.exception("Autopilot run failed")
        await _mark(status="failed", error=str(e))
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers used by scheduler + router
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "_id": "primary",
    "enabled": False,
    "publish_time_local": "07:00",  # user picked Sydney 7am
    "timezone": "Australia/Sydney",
    "duration_seconds": 30,          # target voiceover length
}


async def load_config(db: AsyncIOMotorDatabase) -> dict:
    doc = await db.autopilot_config.find_one({"_id": "primary"})
    if not doc:
        await db.autopilot_config.insert_one(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()
    # Fill in any missing keys from defaults (forward compat)
    merged = {**DEFAULT_CONFIG, **doc}
    return merged


async def save_config(db: AsyncIOMotorDatabase, patch: dict) -> dict:
    await db.autopilot_config.update_one({"_id": "primary"}, {"$set": patch}, upsert=True)
    return await load_config(db)


async def list_runs(db: AsyncIOMotorDatabase, limit: int = 30) -> list[dict]:
    return await db.autopilot_runs.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)


async def latest_run(db: AsyncIOMotorDatabase) -> Optional[dict]:
    return await db.autopilot_runs.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
