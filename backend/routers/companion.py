"""Companion endpoints — weather + real-time context preview."""
from typing import Optional

from fastapi import APIRouter, HTTPException

from companion import build_companion_context, fetch_weather, get_user_location_and_tz
from core.db import db

router = APIRouter(prefix="/companion", tags=["companion"])


@router.get("/weather")
async def companion_weather(location: Optional[str] = None):
    """Return live weather. If no location given, uses the user's saved location."""
    if location is None:
        location, _ = await get_user_location_and_tz(db)
    w = await fetch_weather(location)
    if not w:
        raise HTTPException(404, f"Couldn't find weather for {location!r}")
    return w


@router.get("/context")
async def companion_context():
    """Preview the real-time grounding block Russell receives.

    For debugging / a 'today' card on the UI. Forces weather inclusion by passing
    "good morning" as the trigger phrase.
    """
    location, tz_name = await get_user_location_and_tz(db)
    block = await build_companion_context(db, "good morning")
    return {"location": location, "timezone": tz_name, "context_block": block}
