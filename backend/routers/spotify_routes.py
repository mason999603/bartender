"""Spotify Web API router — OAuth + voice-driven playback control.

Endpoints:
    GET  /api/spotify/login         → returns the Spotify authorise URL
    GET  /api/spotify/callback      → OAuth redirect target; exchanges code for tokens
    GET  /api/spotify/status        → connection state + currently playing
    POST /api/spotify/play          → search-and-play; body: {query, kind?}
    POST /api/spotify/pause
    POST /api/spotify/resume
    POST /api/spotify/next
    POST /api/spotify/previous
    POST /api/spotify/volume        → body: {percent}
    POST /api/spotify/queue         → body: {query}    (queues a track for after current)
    POST /api/spotify/disconnect

The frontend hits /login → redirects user to Spotify → Spotify redirects back to
/callback → we store tokens. All subsequent calls require nothing from the frontend
beyond hitting the backend.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from core.db import db
from core.spotify_client import (
    disconnect as spotify_disconnect,
    exchange_code_for_tokens,
    get_authorize_url,
    get_currently_playing,
    get_spotify_client,
    is_connected,
    search_and_play,
)

router = APIRouter(prefix="/spotify", tags=["spotify"])
logger = logging.getLogger("russell.spotify")


@router.get("/login")
async def spotify_login():
    """Return the Spotify authorise URL — frontend redirects the browser to it."""
    try:
        return {"auth_url": get_authorize_url()}
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.get("/callback")
async def spotify_callback(code: str | None = None, error: str | None = None):
    """OAuth redirect target. After exchanging the code, sends user back to the web UI."""
    if error:
        return HTMLResponse(_callback_html(success=False, message=f"Spotify said: {error}"))
    if not code:
        raise HTTPException(400, "Missing `code` parameter from Spotify")
    try:
        await exchange_code_for_tokens(db, code)
    except Exception as e:
        logger.exception("Spotify code exchange failed")
        return HTMLResponse(_callback_html(success=False, message=str(e)))
    return HTMLResponse(_callback_html(success=True))


@router.get("/status")
async def spotify_status():
    """Connection state + what's playing right now (if connected)."""
    connected = await is_connected(db)
    out: dict = {"connected": connected, "currently_playing": None, "profile": None}
    if not connected:
        return out
    try:
        sp = await get_spotify_client(db)
        me = sp.me()
        out["profile"] = {
            "id": me.get("id"),
            "display_name": me.get("display_name"),
            "product": me.get("product"),
            "is_premium": me.get("product") == "premium",
        }
    except Exception:
        logger.exception("Couldn't fetch Spotify profile")
    out["currently_playing"] = await get_currently_playing(db)
    return out


class PlayRequest(BaseModel):
    query: str
    kind: str = "track"  # track | album | artist | playlist


@router.post("/play")
async def spotify_play(req: PlayRequest):
    if req.kind not in {"track", "album", "artist", "playlist"}:
        raise HTTPException(400, "kind must be one of: track, album, artist, playlist")
    try:
        result = await search_and_play(db, req.query, req.kind)
        return {"ok": True, "playing": result}
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@router.post("/pause")
async def spotify_pause():
    sp = await get_spotify_client(db)
    try:
        sp.pause_playback()
    except Exception as e:
        msg = str(e)
        if "Player command failed" in msg or "NO_ACTIVE_DEVICE" in msg:
            raise HTTPException(409, "No active Spotify device to pause.")
        raise HTTPException(502, msg)
    return {"ok": True}


@router.post("/resume")
async def spotify_resume():
    sp = await get_spotify_client(db)
    try:
        sp.start_playback()
    except Exception as e:
        msg = str(e)
        if "NO_ACTIVE_DEVICE" in msg:
            raise HTTPException(409, "No active Spotify device — open the app on a device first.")
        raise HTTPException(502, msg)
    return {"ok": True}


@router.post("/next")
async def spotify_next():
    sp = await get_spotify_client(db)
    try:
        sp.next_track()
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


@router.post("/previous")
async def spotify_previous():
    sp = await get_spotify_client(db)
    try:
        sp.previous_track()
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


class VolumeRequest(BaseModel):
    percent: int  # 0-100


@router.post("/volume")
async def spotify_volume(req: VolumeRequest):
    pct = max(0, min(100, int(req.percent)))
    sp = await get_spotify_client(db)
    try:
        sp.volume(pct)
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "volume": pct}


class QueueRequest(BaseModel):
    query: str


@router.post("/queue")
async def spotify_queue(req: QueueRequest):
    sp = await get_spotify_client(db)
    results = sp.search(q=req.query, type="track", limit=1)
    items = ((results.get("tracks") or {}).get("items")) or []
    if not items:
        raise HTTPException(404, f"No track matched '{req.query}'")
    track = items[0]
    try:
        sp.add_to_queue(track["uri"])
    except Exception as e:
        msg = str(e)
        if "NO_ACTIVE_DEVICE" in msg:
            raise HTTPException(409, "No active Spotify device — open the app on a device first.")
        raise HTTPException(502, msg)
    return {
        "ok": True,
        "queued": {
            "name": track["name"],
            "artist": ", ".join(a["name"] for a in track.get("artists", [])),
            "uri": track["uri"],
        },
    }


@router.post("/disconnect")
async def disconnect():
    await spotify_disconnect(db)
    return {"ok": True}


def _callback_html(success: bool, message: str = "") -> str:
    """Tiny self-closing page so the OAuth redirect feels seamless."""
    body = (
        "<h1 style='color:#e09132'>Russell is now on Spotify.</h1>"
        "<p>You can close this tab and head back to Russell.</p>"
        if success else
        f"<h1 style='color:#c14b4b'>Couldn't connect Spotify</h1><p>{message}</p>"
    )
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Russell × Spotify</title>
<style>
body {{ background:#0d0a08; color:#f7e8d4; font-family:Georgia, serif;
       display:flex; align-items:center; justify-content:center;
       min-height:100vh; margin:0; padding:2rem; text-align:center; }}
a {{ color:#e09132; text-decoration:none; }}
</style></head>
<body><div>{body}<p><a href='/phone'>← Back to Russell</a></p></div>
<script>setTimeout(() => {{ try {{ window.opener && window.opener.postMessage({{type:'spotify_connected'}}, '*'); }} catch(e) {{}} }}, 300);</script>
</body></html>"""
