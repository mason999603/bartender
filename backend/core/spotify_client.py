"""Spotify Web API client — single-user, server-side token storage in Mongo.

Auth flow:
  1. Frontend hits GET /api/spotify/login → backend returns Spotify's authorise URL.
  2. User logs in, Spotify redirects to /api/spotify/callback?code=...
  3. Backend exchanges the code for an access+refresh token, stores in
     `spotify_auth` collection (single document, `_id="primary"`).
  4. Every subsequent API call calls `get_spotify_client()` which lazily refreshes
     the access token if it's near expiry, then hands back a ready spotipy client.

We persist tokens in Mongo rather than spotipy's default file cache because the
container filesystem doesn't survive restarts.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger("russell.spotify")

# All the scopes we need for the use cases: voice playback control + currently-playing
# + queue + search + library reads (for personal-taste flavour).
SPOTIFY_SCOPES = " ".join([
    "user-read-playback-state",       # currently playing, devices, volume
    "user-modify-playback-state",     # play / pause / next / previous / queue / volume
    "user-read-currently-playing",
    "user-read-private",              # confirm premium
    "user-library-read",              # saved albums/tracks (taste context)
    "user-top-read",                  # top tracks/artists (taste context)
    "playlist-read-private",
])

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "").strip()

# Buffer (seconds) before we proactively refresh the access token.
TOKEN_REFRESH_BUFFER = 120


def _oauth() -> SpotifyOAuth:
    """Build a SpotifyOAuth without spotipy's file cache (we manage storage ourselves)."""
    if not (SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_REDIRECT_URI):
        raise RuntimeError(
            "Spotify not configured — set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI in .env"
        )
    # cache_handler=None and open_browser=False so spotipy doesn't try to touch
    # disk or launch a browser; we drive the flow ourselves.
    return SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SPOTIFY_SCOPES,
        cache_handler=None,
        open_browser=False,
    )


def get_authorize_url() -> str:
    return _oauth().get_authorize_url()


async def exchange_code_for_tokens(db: AsyncIOMotorDatabase, code: str) -> dict:
    """Exchange the OAuth code for tokens and persist them. Returns the token info dict."""
    oauth = _oauth()
    token_info = oauth.get_access_token(code, as_dict=True, check_cache=False)
    if not token_info:
        raise RuntimeError("Spotify rejected the auth code")
    await _persist_tokens(db, token_info)
    return token_info


async def _persist_tokens(db: AsyncIOMotorDatabase, token_info: dict) -> None:
    """Upsert the single-user token doc."""
    doc = {
        "_id": "primary",
        "access_token": token_info["access_token"],
        "refresh_token": token_info.get("refresh_token"),
        "expires_at": token_info.get("expires_at", int(time.time()) + 3600),
        "scope": token_info.get("scope", SPOTIFY_SCOPES),
        "token_type": token_info.get("token_type", "Bearer"),
    }
    # Spotify only returns a new refresh_token sometimes — preserve the old one if missing.
    if not doc["refresh_token"]:
        existing = await db.spotify_auth.find_one({"_id": "primary"})
        if existing and existing.get("refresh_token"):
            doc["refresh_token"] = existing["refresh_token"]
    await db.spotify_auth.replace_one({"_id": "primary"}, doc, upsert=True)


async def _load_tokens(db: AsyncIOMotorDatabase) -> Optional[dict]:
    return await db.spotify_auth.find_one({"_id": "primary"})


async def is_connected(db: AsyncIOMotorDatabase) -> bool:
    doc = await _load_tokens(db)
    return bool(doc and doc.get("refresh_token"))


async def disconnect(db: AsyncIOMotorDatabase) -> None:
    await db.spotify_auth.delete_one({"_id": "primary"})


async def get_spotify_client(db: AsyncIOMotorDatabase) -> Spotify:
    """Return a ready-to-use spotipy client with a fresh access token.

    Raises RuntimeError if Spotify isn't connected yet.
    """
    doc = await _load_tokens(db)
    if not doc:
        raise RuntimeError("Spotify not connected — visit /api/spotify/login first")

    now = int(time.time())
    if doc["expires_at"] - now <= TOKEN_REFRESH_BUFFER:
        logger.info("Spotify access token near expiry — refreshing")
        oauth = _oauth()
        try:
            new_info = oauth.refresh_access_token(doc["refresh_token"])
        except Exception as e:
            logger.exception("Spotify refresh failed")
            raise RuntimeError(f"Spotify token refresh failed: {e}")
        await _persist_tokens(db, new_info)
        access_token = new_info["access_token"]
    else:
        access_token = doc["access_token"]

    return Spotify(auth=access_token, requests_timeout=10, retries=2)


# ──────────────────────────────────────────────────────────────────────────────
# Convenience helpers used by routers and the brain
# ──────────────────────────────────────────────────────────────────────────────

async def get_currently_playing(db: AsyncIOMotorDatabase) -> Optional[dict]:
    """Return a slimmed `{track, artist, album, is_playing, ...}` dict, or None."""
    if not await is_connected(db):
        return None
    try:
        sp = await get_spotify_client(db)
    except Exception:
        return None
    try:
        state = sp.current_playback()
    except Exception:
        logger.exception("current_playback failed")
        return None
    if not state or not state.get("item"):
        return None
    item = state["item"]
    return {
        "track": item.get("name"),
        "artist": ", ".join(a["name"] for a in item.get("artists", [])),
        "album": item.get("album", {}).get("name"),
        "is_playing": state.get("is_playing", False),
        "progress_ms": state.get("progress_ms"),
        "duration_ms": item.get("duration_ms"),
        "device": (state.get("device") or {}).get("name"),
        "uri": item.get("uri"),
    }


async def search_and_play(
    db: AsyncIOMotorDatabase,
    query: str,
    kind: str = "track",
) -> dict:
    """Search Spotify for `query` (track/artist/album/playlist) and start playback.

    Strategy:
      • kind="track" → play that single track
      • kind="album" → play the whole album
      • kind="artist" → start a context play on the artist (Spotify's "play this artist" radio-ish)
      • kind="playlist" → play the playlist
    Returns the chosen Spotify item dict for caller to surface.

    Raises RuntimeError if no device is active (common gotcha when you haven't
    opened Spotify on any device recently).
    """
    sp = await get_spotify_client(db)
    results = sp.search(q=query, type=kind, limit=5)
    items = (results.get(f"{kind}s") or {}).get("items") or []
    if not items:
        raise RuntimeError(f"No Spotify {kind} matched '{query}'")
    chosen = items[0]

    # Find an active device. If none active, fall back to the first available.
    device_id = None
    try:
        devices = (sp.devices() or {}).get("devices", [])
        active = [d for d in devices if d.get("is_active")]
        if active:
            device_id = active[0]["id"]
        elif devices:
            device_id = devices[0]["id"]
    except Exception:
        logger.exception("Couldn't list devices — letting Spotify auto-pick")

    try:
        if kind == "track":
            sp.start_playback(device_id=device_id, uris=[chosen["uri"]])
        else:
            sp.start_playback(device_id=device_id, context_uri=chosen["uri"])
    except Exception as e:
        # 404 NO_ACTIVE_DEVICE is the classic Spotify gotcha.
        msg = str(e)
        if "NO_ACTIVE_DEVICE" in msg or "Player command failed" in msg:
            raise RuntimeError(
                "No active Spotify device — open Spotify on your phone or laptop and hit play once, then try again."
            )
        raise

    return {
        "kind": kind,
        "name": chosen.get("name"),
        "artist": ", ".join(a["name"] for a in chosen.get("artists", []) or []) if kind != "playlist" else (chosen.get("owner") or {}).get("display_name", ""),
        "uri": chosen.get("uri"),
    }
