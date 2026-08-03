"""CalDAV write client — Russell adds events to your iCloud calendar.

Uses your Apple ID + an app-specific password (generated at
appleid.apple.com → Sign-In & Security → App-Specific Passwords). Credentials
are stored in `db.caldav_config` (single doc `_id=primary`) — the password is
stored as-is because we need to send it on every request; the whole database
is local-only in this deployment.

Discovers your default calendar automatically. To use a specific calendar
instead of the default, set the `calendar_name` field in the config.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import caldav
from icalendar import Calendar as ICal, Event as IEvent
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("russell.caldav")

# Apple iCloud CalDAV endpoint (works for all users)
ICLOUD_URL = "https://caldav.icloud.com/"


async def load_config(db: AsyncIOMotorDatabase) -> Optional[dict]:
    doc = await db.caldav_config.find_one({"_id": "primary"}, {"_id": 0})
    return doc


async def save_config(
    db: AsyncIOMotorDatabase,
    apple_id: str,
    app_specific_password: str,
    calendar_name: Optional[str] = None,
) -> dict:
    doc = {
        "_id": "primary",
        "apple_id": apple_id.strip(),
        "password": app_specific_password.strip(),
        "calendar_name": (calendar_name or "").strip() or None,
    }
    await db.caldav_config.replace_one({"_id": "primary"}, doc, upsert=True)
    doc.pop("_id", None)
    return doc


async def is_configured(db: AsyncIOMotorDatabase) -> bool:
    doc = await load_config(db)
    return bool(doc and doc.get("apple_id") and doc.get("password"))


def _open_client(cfg: dict) -> caldav.DAVClient:
    return caldav.DAVClient(url=ICLOUD_URL, username=cfg["apple_id"], password=cfg["password"])


def _pick_calendar(client: caldav.DAVClient, calendar_name: Optional[str]):
    principal = client.principal()
    cals = principal.calendars()
    if not cals:
        raise RuntimeError("No calendars found on this Apple ID")
    if calendar_name:
        for c in cals:
            if (c.name or "").strip().lower() == calendar_name.strip().lower():
                return c
        raise RuntimeError(f"Calendar '{calendar_name}' not found. Available: {[c.name for c in cals]}")
    return cals[0]  # default


async def list_calendar_names(db: AsyncIOMotorDatabase) -> list[str]:
    cfg = await load_config(db)
    if not cfg:
        return []
    import asyncio
    def _sync() -> list[str]:
        client = _open_client(cfg)
        return [c.name for c in client.principal().calendars()]
    return await asyncio.to_thread(_sync)


async def create_event(
    db: AsyncIOMotorDatabase,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    location: str = "",
) -> dict:
    cfg = await load_config(db)
    if not cfg:
        raise RuntimeError("CalDAV not configured — set Apple ID + app-specific password first")

    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    # Build the VEVENT
    cal = ICal()
    cal.add("prodid", "-//Russell AI Bartender//EN")
    cal.add("version", "2.0")
    ev = IEvent()
    uid = f"russell-{uuid.uuid4()}@russellpi.local"
    ev.add("uid", uid)
    ev.add("summary", summary.strip() or "Untitled")
    ev.add("dtstart", start_dt)
    ev.add("dtend", end_dt)
    ev.add("dtstamp", datetime.now(timezone.utc))
    if description:
        ev.add("description", description.strip())
    if location:
        ev.add("location", location.strip())
    cal.add_component(ev)
    ics_str = cal.to_ical().decode("utf-8")

    import asyncio
    def _sync() -> str:
        client = _open_client(cfg)
        calendar = _pick_calendar(client, cfg.get("calendar_name"))
        calendar.save_event(ics_str)
        return calendar.name

    calendar_name = await asyncio.to_thread(_sync)
    logger.info("CalDAV event created: '%s' in calendar '%s'", summary, calendar_name)
    return {
        "uid": uid,
        "summary": summary,
        "start_iso": start_dt.isoformat(),
        "end_iso": end_dt.isoformat(),
        "calendar_name": calendar_name,
    }
