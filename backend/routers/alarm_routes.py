"""Alarm API — Pi polls, web can create/list/silence/delete."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.alarms import (
    create_alarm,
    delete_alarm,
    list_alarms,
    mark_fired,
    pending_alarms,
    silence_alarm,
)
from core.db import db

router = APIRouter(prefix="/alarms", tags=["alarms"])


class AlarmIn(BaseModel):
    fire_at_iso: str = Field(min_length=10)
    message: str = "Alarm."
    repeat_daily: bool = False
    source_channel: str = "web"


class SilenceRequest(BaseModel):
    id: str | None = None  # if None, silence all currently-firing alarms


@router.post("")
async def create(req: AlarmIn):
    # Validate the timestamp
    try:
        dt = datetime.fromisoformat(req.fire_at_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(400, "fire_at_iso must be a valid ISO 8601 timestamp")
    return await create_alarm(
        db,
        fire_at_iso=dt.astimezone(timezone.utc).isoformat(),
        message=req.message,
        repeat_daily=req.repeat_daily,
        source_channel=req.source_channel,
    )


@router.get("")
async def list_all(active_only: bool = False):
    return await list_alarms(db, active_only=active_only)


@router.get("/pending")
async def pending():
    """Called by the Pi client every 15s. Returns alarms whose fire_at is in the past
    and are still active."""
    return await pending_alarms(db)


@router.post("/silence")
async def silence(req: SilenceRequest):
    return await silence_alarm(db, alarm_id=req.id)


@router.post("/{alarm_id}/fired")
async def fired(alarm_id: str):
    """Pi calls this the moment it starts playing the alarm, to prevent re-fire
    on Pi restart mid-alarm."""
    await mark_fired(db, alarm_id)
    return {"ok": True}


@router.delete("/{alarm_id}")
async def delete_one(alarm_id: str):
    n = await delete_alarm(db, alarm_id)
    if n == 0:
        raise HTTPException(404, "alarm not found")
    return {"deleted": True}
