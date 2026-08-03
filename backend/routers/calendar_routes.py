"""Calendar router — add/list/remove sources, fetch upcoming, refresh."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.calendar_analyzer import briefing_block, rank_upcoming
from core.calendar_client import fetch_and_store
from core.db import db
from core.models import now_iso

router = APIRouter(prefix="/calendar", tags=["calendar"])
logger = logging.getLogger("russell.calendar")


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(min_length=10)
    is_work: bool = False


class SourceUpdate(BaseModel):
    name: str | None = None
    is_work: bool | None = None


# ── Sources CRUD ─────────────────────────────────────────────────────────────
@router.get("/sources")
async def list_sources():
    return await db.calendar_sources.find({}, {"_id": 0}).sort("created_at", 1).to_list(50)


@router.post("/sources")
async def add_source(src: SourceIn):
    doc = {
        "id": str(uuid.uuid4()),
        "name": src.name.strip(),
        "url": src.url.strip(),
        "is_work": src.is_work,
        "created_at": now_iso(),
        "last_fetched": None,
        "last_event_count": None,
        "last_error": None,
    }
    await db.calendar_sources.insert_one(doc)
    doc.pop("_id", None)
    # Kick a fetch immediately so the user sees events right away
    asyncio.create_task(_fetch_one_and_record(doc))
    return doc


@router.patch("/sources/{source_id}")
async def update_source(source_id: str, patch: SourceUpdate):
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "nothing to update")
    r = await db.calendar_sources.update_one({"id": source_id}, {"$set": fields})
    if r.matched_count == 0:
        raise HTTPException(404, "source not found")
    return await db.calendar_sources.find_one({"id": source_id}, {"_id": 0})


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    await db.calendar_sources.delete_one({"id": source_id})
    await db.calendar_events.delete_many({"source_id": source_id})
    return {"deleted": True}


# ── Refresh ──────────────────────────────────────────────────────────────────
async def _fetch_one_and_record(src: dict) -> dict:
    result = await fetch_and_store(db, src)
    await db.calendar_sources.update_one(
        {"id": src["id"]},
        {
            "$set": {
                "last_fetched": now_iso(),
                "last_event_count": result.get("events"),
                "last_error": result.get("error"),
            }
        },
    )
    return result


@router.post("/refresh")
async def refresh_all():
    sources = await db.calendar_sources.find({}, {"_id": 0}).to_list(50)
    results = await asyncio.gather(*(_fetch_one_and_record(s) for s in sources), return_exceptions=True)
    return {
        "sources": len(sources),
        "results": [
            r if not isinstance(r, Exception) else {"ok": False, "error": str(r)} for r in results
        ],
    }


# ── Upcoming (ranked) ────────────────────────────────────────────────────────
@router.get("/upcoming")
async def upcoming(days: int = 7, limit: int = 40):
    sources = await db.calendar_sources.find({}, {"_id": 0}).to_list(50)
    horizon = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    events = await db.calendar_events.find(
        {"start": {"$lte": horizon}},
        {"_id": 0},
    ).to_list(2000)
    ranked = rank_upcoming(events, sources)[:limit]
    return {
        "sources": sources,
        "count": len(ranked),
        "events": ranked,
    }


@router.get("/briefing")
async def briefing(days: int = 7):
    """Plain-text ranked briefing. Used by the brain when the user asks 'what's on'."""
    payload = await upcoming(days=days, limit=25)
    return {"text": briefing_block(payload["events"])}
