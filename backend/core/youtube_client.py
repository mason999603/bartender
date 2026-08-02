"""YouTube Data API v3 client — single-user server-side OAuth.

Mirrors the Spotify pattern used elsewhere in this codebase:
  1. Frontend hits GET /api/youtube/login → backend returns the Google auth URL.
  2. User approves → Google redirects to /api/youtube/callback?code=...
  3. Backend exchanges the code for a refresh token, stores in
     `youtube_auth` collection (single doc `_id="primary"`).
  4. Every upload call builds a fresh access token from the refresh token.

Refresh tokens are long-lived; access tokens are auto-refreshed by
`google-auth`. If the user revokes access, the token doc is deleted on
first 401.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("russell.youtube")

# We only ever upload videos on the user's behalf. This scope is the tightest
# possible for that job (no read, no delete, no comment).
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
YOUTUBE_REDIRECT_URI = os.environ.get("YOUTUBE_REDIRECT_URI", "").strip()


def _client_config() -> dict:
    if not (YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET and YOUTUBE_REDIRECT_URI):
        raise RuntimeError(
            "YouTube not configured — set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, "
            "YOUTUBE_REDIRECT_URI in backend/.env"
        )
    return {
        "web": {
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [YOUTUBE_REDIRECT_URI],
        }
    }


def _flow(state: Optional[str] = None) -> Flow:
    flow = Flow.from_client_config(_client_config(), scopes=YOUTUBE_SCOPES, state=state)
    flow.redirect_uri = YOUTUBE_REDIRECT_URI
    return flow


def get_authorize_url() -> tuple[str, str]:
    """Return (auth_url, state). Caller doesn't need to keep state — Google echoes it back."""
    flow = _flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        # `consent` guarantees a refresh_token even if the user has authorised before.
        prompt="consent",
    )
    return auth_url, state


async def exchange_code_for_tokens(db: AsyncIOMotorDatabase, code: str) -> dict:
    """Exchange the OAuth code for a refresh token + channel info, persist it."""
    flow = _flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    if not creds.refresh_token:
        raise RuntimeError(
            "Google didn't return a refresh_token. Revoke Russell in your Google account "
            "at https://myaccount.google.com/permissions and try again."
        )

    # Get channel identity so we can show which channel is connected.
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = youtube.channels().list(part="id,snippet", mine=True).execute()
    items = resp.get("items") or []
    if not items:
        raise RuntimeError("The Google account you authorised has no YouTube channel.")
    ch = items[0]
    doc = {
        "_id": "primary",
        "refresh_token": creds.refresh_token,
        "scope": " ".join(YOUTUBE_SCOPES),
        "channel_id": ch["id"],
        "channel_title": ch["snippet"]["title"],
        "channel_thumbnail": ((ch["snippet"].get("thumbnails") or {}).get("default") or {}).get("url"),
    }
    await db.youtube_auth.replace_one({"_id": "primary"}, doc, upsert=True)
    return doc


async def _load_tokens(db: AsyncIOMotorDatabase) -> Optional[dict]:
    return await db.youtube_auth.find_one({"_id": "primary"})


async def is_connected(db: AsyncIOMotorDatabase) -> bool:
    doc = await _load_tokens(db)
    return bool(doc and doc.get("refresh_token"))


async def get_status(db: AsyncIOMotorDatabase) -> dict:
    doc = await _load_tokens(db)
    if not doc:
        return {"connected": False}
    return {
        "connected": True,
        "channel_id": doc.get("channel_id"),
        "channel_title": doc.get("channel_title"),
        "channel_thumbnail": doc.get("channel_thumbnail"),
    }


async def disconnect(db: AsyncIOMotorDatabase) -> None:
    await db.youtube_auth.delete_one({"_id": "primary"})


async def get_youtube_client(db: AsyncIOMotorDatabase):
    """Return an authenticated googleapiclient YouTube service instance.

    google-auth handles the access-token refresh from the stored refresh_token.
    """
    doc = await _load_tokens(db)
    if not doc:
        raise RuntimeError("YouTube not connected — visit /api/youtube/login first")

    creds = Credentials(
        token=None,
        refresh_token=doc["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        scopes=YOUTUBE_SCOPES,
    )
    if not creds.valid:
        creds.refresh(GoogleRequest())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)
