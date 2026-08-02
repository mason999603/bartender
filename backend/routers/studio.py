"""Russell's Studio — content pipeline for faceless cocktail videos.

Endpoints:
    Phase 1 — text
    POST /api/studio/ideas          → generate video ideas for a topic
    POST /api/studio/script         → write a full script (short + long)
    GET  /api/studio/scripts        → list saved scripts
    POST /api/studio/scripts        → save a script
    DELETE /api/studio/scripts/{id} → delete a script

    Phase 2 — media
    POST /api/studio/jobs/hero-clip  → kick off Sora 2 background render (4-12s portrait)
    POST /api/studio/jobs/image-card → generate a still image via GPT-Image-1 (sync)
    POST /api/studio/jobs/voiceover  → render narration to a saved MP3 (sync)
    POST /api/studio/jobs/assemble   → stitch hero + voiceover into a captioned MP4
    GET  /api/studio/jobs/{id}       → poll job status
    GET  /api/studio/jobs            → list recent jobs
    GET  /api/studio/media/{name}    → download generated media
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import textwrap
import uuid
from pathlib import Path

from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import (
    OpenAITextToSpeech,
    OpenAIVideoGeneration,
)
from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.config import EMERGENT_LLM_KEY, CLAUDE_MODEL
from core.db import db
from core.models import now_iso

router = APIRouter(prefix="/studio", tags=["studio"])
logger = logging.getLogger("russell.studio")

# ─────────────────────────────────────────────────────────────────────────────
# Media storage
# ─────────────────────────────────────────────────────────────────────────────
MEDIA_DIR = Path(os.environ.get("STUDIO_MEDIA_DIR", "/app/backend/generated/studio"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _media_path(name: str) -> Path:
    # Sanitise: no directory traversal
    safe = os.path.basename(name)
    return MEDIA_DIR / safe


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



# ═════════════════════════════════════════════════════════════════════════════
# PHASE 2 — Media pipeline (Sora 2 hero clips, GPT-Image-1 stills, ffmpeg assembly)
# ═════════════════════════════════════════════════════════════════════════════


async def _create_job(job_type: str, params: dict) -> str:
    """Insert a job doc; return its id."""
    job_id = str(uuid.uuid4())
    await db.studio_jobs.insert_one(
        {
            "id": job_id,
            "type": job_type,
            "status": "queued",
            "params": params,
            "output": None,
            "error": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    return job_id


async def _update_job(job_id: str, **fields) -> None:
    fields["updated_at"] = now_iso()
    await db.studio_jobs.update_one({"id": job_id}, {"$set": fields})


# ── Hero clip via Sora 2 (async background) ──────────────────────────────────
# Sora 2 (fast) only supports 720x1280 / 1280x720. Sora 2 Pro adds the bigger sizes.
SORA_SIZES = {"portrait": "720x1280", "landscape": "1280x720"}
SORA_SIZES_PRO = {"portrait": "1024x1792", "landscape": "1792x1024", "square": "1024x1024"}
SORA_DURATIONS = {4, 8, 12}


class HeroClipRequest(BaseModel):
    prompt: str
    aspect: str = "portrait"  # portrait | square | landscape
    duration: int = 4  # 4 | 8 | 12
    model: str = "sora-2"  # sora-2 | sora-2-pro
    image_filename: str | None = None  # optional reference image already in MEDIA_DIR


async def _run_sora_job(job_id: str, prompt: str, size: str, duration: int, model: str, image_path: str | None = None) -> None:
    """Blocking Sora call executed in a worker thread. Saves MP4 to MEDIA_DIR."""
    try:
        await _update_job(job_id, status="rendering")
        # SDK's SIZES whitelist misses the true Sora 2 fast sizes (720x1280/1280x720).
        # Extend it in-place before calling so validation passes.
        for extra in ("720x1280", "1280x720"):
            OpenAIVideoGeneration.SIZES.setdefault(extra, {"width": int(extra.split("x")[0]), "height": int(extra.split("x")[1])})
        client = OpenAIVideoGeneration(api_key=EMERGENT_LLM_KEY)

        # SDK is synchronous — run in the default executor so we don't block the loop.
        video_bytes = await asyncio.to_thread(
            client.text_to_video,
            prompt=prompt,
            model=model,
            size=size,
            duration=duration,
            max_wait_time=600,
            image_path=image_path,
            mime_type="image/png" if (image_path or "").lower().endswith(".png") else "image/jpeg",
        )

        if not video_bytes:
            await _update_job(job_id, status="failed", error="Sora returned no bytes (timeout or safety filter)")
            return

        fname = f"hero_{job_id}.mp4"
        (MEDIA_DIR / fname).write_bytes(video_bytes)
        await _update_job(
            job_id,
            status="done",
            output={"filename": fname, "url": f"/api/studio/media/{fname}", "bytes": len(video_bytes)},
        )
    except Exception as e:  # pragma: no cover — network paths
        logger.exception("Sora job failed")
        await _update_job(job_id, status="failed", error=str(e))


@router.post("/jobs/hero-clip")
async def create_hero_clip(req: HeroClipRequest):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")
    if req.duration not in SORA_DURATIONS:
        raise HTTPException(400, f"duration must be one of {sorted(SORA_DURATIONS)}")
    if req.model not in ("sora-2", "sora-2-pro"):
        raise HTTPException(400, "model must be sora-2 or sora-2-pro")
    size_table = SORA_SIZES_PRO if req.model == "sora-2-pro" else SORA_SIZES
    if req.aspect not in size_table:
        raise HTTPException(
            400,
            f"aspect must be one of {list(size_table.keys())} for {req.model}",
        )
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(400, "Provide a prompt")

    size = size_table[req.aspect]
    image_path: str | None = None
    if req.image_filename:
        p = _media_path(req.image_filename)
        if not p.exists():
            raise HTTPException(404, f"reference image not found: {req.image_filename}")
        image_path = str(p)

    job_id = await _create_job(
        "hero-clip",
        {"prompt": prompt, "aspect": req.aspect, "size": size, "duration": req.duration, "model": req.model, "image_filename": req.image_filename},
    )
    # Fire and forget
    asyncio.create_task(_run_sora_job(job_id, prompt, size, req.duration, req.model, image_path))
    return {"id": job_id, "status": "queued"}


# ── Image card via OpenAI GPT-Image-1 (sync, ~10s) ──────────────────────────
class ImageCardRequest(BaseModel):
    prompt: str
    quality: str = "medium"  # low | medium | high


@router.post("/jobs/image-card")
async def create_image_card(req: ImageCardRequest):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(400, "Provide a prompt")
    if req.quality not in ("low", "medium", "high"):
        raise HTTPException(400, "quality must be low/medium/high")

    job_id = await _create_job("image-card", {"prompt": prompt, "quality": req.quality})
    await _update_job(job_id, status="rendering")
    try:
        client = OpenAIImageGeneration(api_key=EMERGENT_LLM_KEY)
        images = await client.generate_images(
            prompt=prompt, model="gpt-image-1", number_of_images=1, quality=req.quality
        )
        if not images:
            await _update_job(job_id, status="failed", error="No image returned")
            raise HTTPException(500, "No image returned")
        fname = f"card_{job_id}.png"
        (MEDIA_DIR / fname).write_bytes(images[0])
        output = {"filename": fname, "url": f"/api/studio/media/{fname}", "bytes": len(images[0])}
        await _update_job(job_id, status="done", output=output)
        return {"id": job_id, "status": "done", **output}
    except Exception as e:
        logger.exception("Image card failed")
        await _update_job(job_id, status="failed", error=str(e))
        raise HTTPException(500, f"Image generation failed: {e}")


# ── Voiceover to saved MP3 ───────────────────────────────────────────────────
class VoiceoverRequest(BaseModel):
    text: str
    voice: str = "onyx"


@router.post("/jobs/voiceover")
async def create_voiceover(req: VoiceoverRequest):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")
    text = (req.text or "").strip().replace("**", "").replace("*", "").replace("`", "")
    if not text:
        raise HTTPException(400, "Empty text")
    if len(text) > 4000:
        text = text[:3996] + "..."

    job_id = await _create_job("voiceover", {"chars": len(text), "voice": req.voice})
    await _update_job(job_id, status="rendering")
    try:
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        audio_bytes = await tts.generate_speech(text=text, model="tts-1", voice=req.voice, response_format="mp3")
        fname = f"voice_{job_id}.mp3"
        (MEDIA_DIR / fname).write_bytes(audio_bytes)
        output = {"filename": fname, "url": f"/api/studio/media/{fname}", "bytes": len(audio_bytes)}
        await _update_job(job_id, status="done", output=output)
        return {"id": job_id, "status": "done", **output}
    except Exception as e:
        logger.exception("Voiceover failed")
        await _update_job(job_id, status="failed", error=str(e))
        raise HTTPException(500, f"Voiceover failed: {e}")


# ── Assembly (ffmpeg) ────────────────────────────────────────────────────────
class AssembleRequest(BaseModel):
    hero_filename: str
    voice_filename: str
    caption: str = ""  # optional big on-screen text overlay
    outro_image_filename: str | None = None  # optional still image tail


def _srt_from_caption(text: str, total_seconds: float) -> str:
    """Split caption into 4-word chunks evenly spaced over the clip duration."""
    words = text.split()
    if not words:
        return ""
    chunks = [" ".join(words[i : i + 4]) for i in range(0, len(words), 4)]
    per = max(1.0, total_seconds / max(1, len(chunks)))

    def _ts(sec: float) -> str:
        h, r = divmod(int(sec), 3600)
        m, s = divmod(r, 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    out = []
    for i, chunk in enumerate(chunks):
        out.append(str(i + 1))
        out.append(f"{_ts(i * per)} --> {_ts(min(total_seconds, (i + 1) * per))}")
        out.append(chunk)
        out.append("")
    return "\n".join(out)


def _run_ffmpeg(hero_path: Path, voice_path: Path, out_path: Path, caption: str, outro_path: Path | None) -> None:
    """Combine hero clip + voiceover + optional captions + optional outro card into an MP4."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        # 1) Get voice duration (this is the total output duration)
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(voice_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        voice_dur = float(probe.stdout.strip() or 0)
        if voice_dur <= 0:
            raise RuntimeError("Could not determine voiceover duration")

        # 2) Loop the hero clip to cover the voiceover; optionally append outro still.
        # Portrait 720x1280 is the Sora 2 native. We keep the whole pipeline at 720x1280.
        inputs = ["-stream_loop", "-1", "-i", str(hero_path)]
        filter_complex_parts = []
        if outro_path and outro_path.exists():
            inputs += ["-loop", "1", "-t", str(voice_dur), "-i", str(outro_path)]
            filter_complex_parts.append(
                "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1[hero]"
            )
            filter_complex_parts.append(
                "[1:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1[outro]"
            )
            # Show hero for voice_dur - 2s, then outro for last 2s
            hero_secs = max(1.0, voice_dur - 2.0)
            filter_complex_parts.append(
                f"[hero]trim=duration={hero_secs:.2f},setpts=PTS-STARTPTS[herov]"
            )
            filter_complex_parts.append(
                "[outro]trim=duration=2.0,setpts=PTS-STARTPTS[outrov]"
            )
            filter_complex_parts.append("[herov][outrov]concat=n=2:v=1:a=0[vout]")
            vmap = "[vout]"
        else:
            filter_complex_parts.append(
                "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,"
                f"trim=duration={voice_dur:.2f},setpts=PTS-STARTPTS[vout]"
            )
            vmap = "[vout]"

        # Optional captions overlay via SRT
        if caption.strip():
            srt = _srt_from_caption(caption.strip(), voice_dur)
            srt_path = tdp / "caps.srt"
            srt_path.write_text(srt, encoding="utf-8")
            filter_complex_parts.append(
                f"{vmap}subtitles={srt_path}:force_style='Alignment=2,FontSize=20,PrimaryColour=&H00FFFFFF,"
                "BackColour=&H80000000,BorderStyle=3,Outline=2,Shadow=0,MarginV=100'[final]"
            )
            vmap = "[final]"

        # Voice as audio track
        inputs += ["-i", str(voice_path)]
        audio_idx = 2 if (outro_path and outro_path.exists()) else 1

        cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filter_complex_parts),
            "-map",
            vmap,
            "-map",
            f"{audio_idx}:a",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(out_path),
        ]
        logger.info("ffmpeg cmd: %s", " ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")


async def _run_assemble_job(
    job_id: str, hero_path: Path, voice_path: Path, caption: str, outro_path: Path | None
) -> None:
    try:
        await _update_job(job_id, status="rendering")
        out_name = f"final_{job_id}.mp4"
        out_path = MEDIA_DIR / out_name
        await asyncio.to_thread(_run_ffmpeg, hero_path, voice_path, out_path, caption, outro_path)
        await _update_job(
            job_id,
            status="done",
            output={
                "filename": out_name,
                "url": f"/api/studio/media/{out_name}",
                "bytes": out_path.stat().st_size,
            },
        )
    except Exception as e:
        logger.exception("Assemble failed")
        await _update_job(job_id, status="failed", error=str(e))


@router.post("/jobs/assemble")
async def assemble(req: AssembleRequest):
    hero = _media_path(req.hero_filename)
    voice = _media_path(req.voice_filename)
    outro = _media_path(req.outro_image_filename) if req.outro_image_filename else None
    if not hero.exists():
        raise HTTPException(404, f"hero not found: {req.hero_filename}")
    if not voice.exists():
        raise HTTPException(404, f"voiceover not found: {req.voice_filename}")
    if outro and not outro.exists():
        raise HTTPException(404, f"outro image not found: {req.outro_image_filename}")

    job_id = await _create_job(
        "assemble",
        {
            "hero_filename": req.hero_filename,
            "voice_filename": req.voice_filename,
            "outro_image_filename": req.outro_image_filename,
            "caption_len": len(req.caption or ""),
        },
    )
    asyncio.create_task(_run_assemble_job(job_id, hero, voice, textwrap.dedent(req.caption or ""), outro))
    return {"id": job_id, "status": "queued"}


# ── Job listing + polling + media serving ────────────────────────────────────
@router.get("/jobs")
async def list_jobs():
    docs = await db.studio_jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return docs


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    doc = await db.studio_jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Job not found")
    return doc


@router.get("/media/{filename}")
async def serve_media(filename: str):
    p = _media_path(filename)
    if not p.exists():
        raise HTTPException(404, "Media not found")
    ext = p.suffix.lower()
    media_type = {
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "application/octet-stream")
    return FileResponse(str(p), media_type=media_type, filename=filename)
