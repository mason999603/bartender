"""Autopilot router — status, config, manual run, persona controls, topic queue.

Endpoints:
    GET  /api/autopilot/status         — enabled, next_run, last_run summary
    GET  /api/autopilot/config
    POST /api/autopilot/config         — toggle enabled, publish_time_local, timezone
    POST /api/autopilot/run-now        — trigger a full pipeline right now (async)
    GET  /api/autopilot/runs           — list recent runs
    GET  /api/autopilot/runs/{id}
    GET  /api/autopilot/persona        — current persona sheet + image URL
    POST /api/autopilot/persona/regenerate  — force a new persona render
    GET  /api/autopilot/topics         — list user-added topics
    POST /api/autopilot/topics         — add a topic to the front of the queue
    DELETE /api/autopilot/topics       — remove a topic
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.autopilot import (
    latest_run,
    list_runs,
    load_config,
    produce_and_publish,
    save_config,
)
from core.db import db
from core.models import now_iso
from core.persona import ensure_persona_image, load_persona, persona_image_exists, save_persona
from core.topic_rotator import add_user_topic, list_user_topics, remove_user_topic

router = APIRouter(prefix="/autopilot", tags=["autopilot"])
logger = logging.getLogger("russell.autopilot")


# ─────────────────────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────────────────────
def _next_run_iso(cfg: dict) -> str | None:
    """Best-effort human-readable next-run timestamp based on cfg + tz."""
    try:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(cfg.get("timezone") or "UTC")
        hh, mm = [int(x) for x in (cfg.get("publish_time_local") or "07:00").split(":")]
        now_local = datetime.now(tz)
        target = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now_local:
            target = target + timedelta(days=1)
        return target.isoformat()
    except Exception:
        return None


@router.get("/status")
async def autopilot_status():
    cfg = await load_config(db)
    last = await latest_run(db)
    return {
        "enabled": bool(cfg.get("enabled")),
        "config": cfg,
        "next_run_local": _next_run_iso(cfg),
        "last_run": last,
        "persona_ready": persona_image_exists(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
class ConfigPatch(BaseModel):
    enabled: bool | None = None
    publish_time_local: str | None = None  # "HH:MM"
    timezone: str | None = None
    duration_seconds: int | None = None


@router.get("/config")
async def get_config():
    return await load_config(db)


@router.post("/config")
async def update_config(patch: ConfigPatch):
    body = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "publish_time_local" in body:
        # sanity-check
        try:
            hh, mm = [int(x) for x in body["publish_time_local"].split(":")]
            assert 0 <= hh < 24 and 0 <= mm < 60
        except Exception:
            raise HTTPException(400, "publish_time_local must be 'HH:MM' 24h")
    cfg = await save_config(db, body)

    # Reschedule the cron if the scheduler is up
    try:
        from core.scheduler import reschedule_autopilot
        reschedule_autopilot(cfg)
    except Exception:  # scheduler optional
        logger.exception("Couldn't reschedule cron (scheduler not initialised)")
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Manual run
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/run-now")
async def run_now():
    # Return immediately, run in the background
    async def _bg():
        try:
            await produce_and_publish(db, trigger="manual")
        except Exception:
            logger.exception("Manual autopilot run failed")

    asyncio.create_task(_bg())
    return {"ok": True, "queued_at": now_iso()}


@router.get("/runs")
async def get_runs():
    return await list_runs(db, 30)


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    doc = await db.autopilot_runs.find_one({"id": run_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Run not found")
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# Persona
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/persona")
async def get_persona():
    p = await load_persona(db)
    return {
        **p,
        "image_ready": persona_image_exists(),
        "image_url": "/api/studio/media/persona.png" if persona_image_exists() else None,
    }


@router.post("/persona/regenerate")
async def regen_persona():
    try:
        path = await ensure_persona_image(db, force=True)
        return {"ok": True, "image_url": "/api/studio/media/persona.png", "bytes": path.stat().st_size}
    except Exception as e:
        raise HTTPException(500, f"Persona render failed: {e}")


class PersonaUpdate(BaseModel):
    name: str | None = None
    sheet: str | None = None
    sora_snippet: str | None = None


@router.post("/persona")
async def update_persona(patch: PersonaUpdate):
    current = await load_persona(db)
    merged = {**current}
    for k, v in patch.model_dump().items():
        if v:
            merged[k] = v
    await save_persona(db, merged)
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Topics
# ─────────────────────────────────────────────────────────────────────────────
class TopicIn(BaseModel):
    topic: str


@router.get("/topics")
async def get_topics():
    return await list_user_topics(db)


@router.post("/topics")
async def post_topic(req: TopicIn):
    t = req.topic.strip()
    if not t:
        raise HTTPException(400, "empty topic")
    await add_user_topic(db, t, now_iso())
    return {"ok": True}


@router.delete("/topics")
async def del_topic(req: TopicIn):
    n = await remove_user_topic(db, req.topic.strip())
    if n == 0:
        raise HTTPException(404, "not found")
    return {"ok": True}
