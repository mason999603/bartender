"""YouTube router — OAuth + publish endpoint for Russell's Studio.

Endpoints:
    GET  /api/youtube/login       → returns Google auth URL for the frontend to open
    GET  /api/youtube/callback    → OAuth redirect target (HTML "you can close this")
    GET  /api/youtube/status      → { connected, channel_title, ... }
    POST /api/youtube/disconnect  → forget the refresh token
    POST /api/youtube/publish     → upload a media file (from /studio/media) as a Short
    GET  /api/youtube/publish/{id} → poll a publish job
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from pydantic import BaseModel

from core.db import db
from core.models import now_iso
from core.youtube_client import (
    disconnect as youtube_disconnect,
    exchange_code_for_tokens,
    get_authorize_url,
    get_status,
    get_youtube_client,
    is_connected,
)

router = APIRouter(prefix="/youtube", tags=["youtube"])
logger = logging.getLogger("russell.youtube")

# Studio media dir — mirror studio.py's env variable so both share the same location.
MEDIA_DIR = Path(os.environ.get("STUDIO_MEDIA_DIR", "/app/backend/generated/studio"))


# ── OAuth ────────────────────────────────────────────────────────────────────
@router.get("/login")
async def youtube_login():
    try:
        auth_url, _state = get_authorize_url()
        return {"auth_url": auth_url}
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.get("/callback")
async def youtube_callback(code: str | None = None, error: str | None = None):
    if error:
        return HTMLResponse(_callback_html(False, f"Google said: {error}"))
    if not code:
        raise HTTPException(400, "Missing `code` parameter from Google")
    try:
        await exchange_code_for_tokens(db, code)
    except Exception as e:
        logger.exception("YouTube code exchange failed")
        return HTMLResponse(_callback_html(False, str(e)))
    return HTMLResponse(_callback_html(True))


@router.get("/status")
async def youtube_status():
    return await get_status(db)


@router.post("/disconnect")
async def youtube_disconnect_route():
    await youtube_disconnect(db)
    return {"ok": True}


# ── Publish ──────────────────────────────────────────────────────────────────
class PublishRequest(BaseModel):
    filename: str            # e.g. final_<uuid>.mp4 inside MEDIA_DIR
    title: str               # generated fully-auto by the FE (or user-editable later)
    description: str = ""
    tags: list[str] = []
    privacy: str = "public"  # public | unlisted | private
    category_id: str = "22"  # People & Blogs — safe default for cocktail Shorts


def _safe_filename(name: str) -> Path:
    """Reject traversal, only allow media in MEDIA_DIR."""
    base = os.path.basename(name)
    p = MEDIA_DIR / base
    return p


def _shape_title(title: str) -> str:
    """YouTube caps titles at 100 chars. Add #Shorts hint if missing."""
    t = (title or "").strip()
    if len(t) > 90:
        t = t[:87].rstrip() + "..."
    if "#shorts" not in t.lower():
        t = (t + " #Shorts")[:100]
    return t


def _shape_tags(tags: list[str]) -> list[str]:
    """De-dup, lowercase alphanumeric, cap at ~12 tags (YouTube max is 500 chars total)."""
    seen: list[str] = []
    for raw in tags:
        clean = re.sub(r"[^0-9a-zA-Z ]", "", raw or "").strip().lower()
        if clean and clean not in seen:
            seen.append(clean)
    # Always tack on Shorts
    if "shorts" not in seen:
        seen.append("shorts")
    return seen[:12]


async def _run_publish_job(
    job_id: str, path: Path, title: str, description: str, tags: list[str], privacy: str, category_id: str
) -> None:
    """Blocking YouTube upload run in a worker thread."""
    try:
        await db.youtube_publish_jobs.update_one(
            {"id": job_id}, {"$set": {"status": "uploading", "updated_at": now_iso()}}
        )
        youtube = await get_youtube_client(db)

        def _do_upload():
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "categoryId": category_id,
                },
                "status": {
                    "privacyStatus": privacy,
                    "selfDeclaredMadeForKids": False,
                },
            }
            req = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(
                    str(path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True
                ),
            )
            response = None
            last_progress = 0
            while response is None:
                status, response = req.next_chunk()
                if status and status.progress() * 100 - last_progress >= 10:
                    last_progress = status.progress() * 100
                    logger.info("YouTube upload %s progress: %d%%", job_id, int(last_progress))
            return response

        response = await asyncio.to_thread(_do_upload)
        video_id = response["id"]

        await db.youtube_publish_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "done",
                    "video_id": video_id,
                    "video_url": f"https://youtu.be/{video_id}",
                    "updated_at": now_iso(),
                }
            },
        )
    except HttpError as e:
        logger.exception("YouTube upload HttpError")
        # Google returns forced-private on unverified projects. Surface a clear hint.
        detail = str(e)
        if "youtubeSignupRequired" in detail:
            detail = "The connected Google account has no YouTube channel. Create one and reconnect."
        elif "quotaExceeded" in detail:
            detail = "YouTube upload quota exceeded for today. Try again tomorrow or request more quota."
        await db.youtube_publish_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error": detail, "updated_at": now_iso()}},
        )
    except Exception as e:
        logger.exception("YouTube upload failed")
        await db.youtube_publish_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error": str(e), "updated_at": now_iso()}},
        )


@router.post("/publish")
async def publish(req: PublishRequest):
    if not await is_connected(db):
        raise HTTPException(401, "YouTube not connected — hit /api/youtube/login first")
    if req.privacy not in ("public", "unlisted", "private"):
        raise HTTPException(400, "privacy must be public | unlisted | private")

    path = _safe_filename(req.filename)
    if not path.exists():
        raise HTTPException(404, f"File not found in studio media: {req.filename}")
    if path.suffix.lower() != ".mp4":
        raise HTTPException(400, "Only .mp4 files can be published")
    if path.stat().st_size < 1000:
        raise HTTPException(400, "File is too small — probably an incomplete render")

    title = _shape_title(req.title)
    tags = _shape_tags(req.tags)
    description = (req.description or "").strip()[:5000]

    job_id = str(uuid.uuid4())
    await db.youtube_publish_jobs.insert_one(
        {
            "id": job_id,
            "status": "queued",
            "filename": path.name,
            "title": title,
            "description": description,
            "tags": tags,
            "privacy": req.privacy,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    asyncio.create_task(
        _run_publish_job(job_id, path, title, description, tags, req.privacy, req.category_id)
    )
    return {"id": job_id, "status": "queued", "title": title, "tags": tags}


@router.get("/publish/{job_id}")
async def get_publish_job(job_id: str):
    doc = await db.youtube_publish_jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Publish job not found")
    return doc


@router.get("/publish")
async def list_publish_jobs():
    docs = await db.youtube_publish_jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return docs


# ── Callback page ────────────────────────────────────────────────────────────
def _callback_html(success: bool, message: str = "") -> str:
    body = (
        "<h1 style='color:#e09132'>Russell is now on YouTube.</h1>"
        "<p>You can close this tab and head back to the app.</p>"
        if success else
        f"<h1 style='color:#c14b4b'>Couldn't connect YouTube</h1><p>{message}</p>"
    )
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Russell × YouTube</title>
<style>
body {{ background:#0d0a08; color:#f7e8d4; font-family:Georgia, serif;
       display:flex; align-items:center; justify-content:center;
       min-height:100vh; margin:0; padding:2rem; text-align:center; }}
a {{ color:#e09132; text-decoration:none; }}
</style></head>
<body><div>{body}<p><a href='/studio'>← Back to Studio</a></p></div>
<script>setTimeout(() => {{ try {{ window.opener && window.opener.postMessage({{type:'youtube_connected'}}, '*'); }} catch(e) {{}} }}, 300);</script>
</body></html>"""
