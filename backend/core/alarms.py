"""Alarms — Russell can schedule alarms that fire on the Pi speaker.

Design:
- User (via voice or web chat) says something like "wake me at 6:30" or "set an
  alarm for 30 minutes with the message 'stock the bar'".
- Russell parses the intent and emits a `set_alarm` action containing an
  absolute UTC ISO timestamp + a spoken message.
- The alarm doc is stored in `db.alarms` with `active=true`.
- The Pi client polls `GET /api/alarms/pending` every 15s and, when a doc's
  `fire_at` <= now, fetches the spoken audio and plays it, listening for a
  silence phrase. Once silenced (or after N cycles), the alarm is marked
  `active=false`.
- By default alarms are single-shot. Pass `repeat_daily=true` to have them
  reschedule +24h on silence.

Storage:
    {
        id, fire_at_iso (UTC ISO string),
        message,
        repeat_daily,
        active,             # False once silenced/dismissed
        source_channel,     # "voice" | "web" | ...
        created_at, silenced_at, fired_at
    }
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from core.models import now_iso

logger = logging.getLogger("russell.alarms")


def _iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


async def create_alarm(
    db: AsyncIOMotorDatabase,
    fire_at_iso: str,
    message: str = "Alarm.",
    repeat_daily: bool = False,
    source_channel: str = "voice",
) -> dict:
    """Insert a new alarm doc; returns the doc."""
    doc = {
        "id": str(uuid.uuid4()),
        "fire_at_iso": fire_at_iso,
        "message": (message or "Alarm.").strip(),
        "repeat_daily": bool(repeat_daily),
        "active": True,
        "source_channel": source_channel,
        "created_at": now_iso(),
        "fired_at": None,
        "silenced_at": None,
    }
    await db.alarms.insert_one(doc)
    doc.pop("_id", None)
    logger.info("Alarm scheduled: %s at %s (repeat_daily=%s)", doc["message"][:60], fire_at_iso, doc["repeat_daily"])
    return doc


async def list_alarms(db: AsyncIOMotorDatabase, active_only: bool = False) -> list[dict]:
    q = {"active": True} if active_only else {}
    return await db.alarms.find(q, {"_id": 0}).sort("fire_at_iso", 1).to_list(100)


async def pending_alarms(db: AsyncIOMotorDatabase) -> list[dict]:
    """Alarms that should fire NOW — active, past fire_at, not silenced.

    Called by the Pi client every ~15s.
    """
    now = _iso_utc(datetime.now(timezone.utc))
    return await db.alarms.find(
        {"active": True, "fire_at_iso": {"$lte": now}},
        {"_id": 0},
    ).to_list(20)


async def silence_alarm(db: AsyncIOMotorDatabase, alarm_id: str | None = None) -> dict:
    """Silence a specific alarm, or all currently-firing alarms if `alarm_id` is None.

    If the alarm has `repeat_daily=true`, we don't disable it — we reschedule
    fire_at forward by 24h so it fires again tomorrow at the same clock time.
    """
    now = _iso_utc(datetime.now(timezone.utc))
    q = {"active": True}
    if alarm_id:
        q["id"] = alarm_id
    else:
        q["fire_at_iso"] = {"$lte": now}

    docs = await db.alarms.find(q, {"_id": 0}).to_list(20)
    silenced_ids: list[str] = []
    rescheduled_ids: list[str] = []

    for d in docs:
        if d.get("repeat_daily"):
            # Reschedule +24h
            fa = datetime.fromisoformat(d["fire_at_iso"]) + timedelta(days=1)
            await db.alarms.update_one(
                {"id": d["id"]},
                {"$set": {
                    "fire_at_iso": _iso_utc(fa),
                    "silenced_at": now_iso(),
                }},
            )
            rescheduled_ids.append(d["id"])
        else:
            await db.alarms.update_one(
                {"id": d["id"]},
                {"$set": {
                    "active": False,
                    "silenced_at": now_iso(),
                }},
            )
            silenced_ids.append(d["id"])

    return {
        "silenced": silenced_ids,
        "rescheduled": rescheduled_ids,
        "total": len(docs),
    }


async def mark_fired(db: AsyncIOMotorDatabase, alarm_id: str) -> None:
    """Called by the Pi client when it starts playing an alarm — so if the Pi
    restarts mid-alarm, we don't re-fire it immediately on next boot for
    single-shot alarms.
    """
    await db.alarms.update_one({"id": alarm_id}, {"$set": {"fired_at": now_iso()}})


async def delete_alarm(db: AsyncIOMotorDatabase, alarm_id: str) -> int:
    r = await db.alarms.delete_one({"id": alarm_id})
    return r.deleted_count
