"""APScheduler wrapper for autopilot's daily cron.

Started on FastAPI lifespan. Reads current config from Mongo and installs a
CronTrigger that fires at `publish_time_local` in `timezone`. If autopilot
is disabled, the job is removed. `reschedule_autopilot(cfg)` is called from
the config router whenever the user tweaks the schedule.

**Catchup on startup**: because APScheduler is in-memory (Emergent preview
containers cycle periodically), on every startup we check whether today's
scheduled slot has already passed AND autopilot hasn't run today — if so we
fire a catchup run immediately. `db.autopilot_state.last_run_date` (Sydney
YYYY-MM-DD) is the idempotency key.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.autopilot import load_config, produce_and_publish
from core.db import db
from core.models import now_iso

logger = logging.getLogger("russell.scheduler")

_scheduler: AsyncIOScheduler | None = None
JOB_ID = "autopilot_daily"


def _today_local_date(cfg: dict) -> str:
    tz = ZoneInfo(cfg.get("timezone") or "UTC")
    return datetime.now(tz).strftime("%Y-%m-%d")


def _slot_already_passed_today(cfg: dict) -> bool:
    """Has today's publish_time already gone by, in the config timezone?"""
    tz = ZoneInfo(cfg.get("timezone") or "UTC")
    hh, mm = [int(x) for x in (cfg.get("publish_time_local") or "07:00").split(":")]
    now_local = datetime.now(tz)
    slot = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return now_local >= slot


async def _daily_job():
    logger.info("Autopilot cron firing — producing today's video")
    try:
        cfg = await load_config(db)
        today = _today_local_date(cfg)
        # Idempotency: only mark last_run_date on cron path so manual runs
        # via /run-now don't block the actual cron.
        await produce_and_publish(db, trigger="cron")
        await db.autopilot_state.update_one(
            {"_id": "primary"}, {"$set": {"last_run_date": today}}, upsert=True
        )
    except Exception:
        logger.exception("Autopilot cron run failed")


async def _catchup_if_missed() -> None:
    """Backend just started — if we skipped today's slot because we were down, fire now."""
    cfg = await load_config(db)
    if not cfg.get("enabled"):
        return
    if not _slot_already_passed_today(cfg):
        return  # Nothing to catch up — today's slot is still in the future
    today = _today_local_date(cfg)
    state = await db.autopilot_state.find_one({"_id": "primary"}) or {}
    if state.get("last_run_date") == today:
        logger.info("Catchup skipped — Russell already posted for %s", today)
        return

    logger.warning("Catchup RUN — backend was down during today's %s slot", cfg.get("publish_time_local"))
    # Mark BEFORE the (long) run starts so a concurrent restart won't double-fire
    await db.autopilot_state.update_one(
        {"_id": "primary"}, {"$set": {"last_run_date": today, "catchup": True}}, upsert=True
    )
    try:
        await produce_and_publish(db, trigger="catchup")
    except Exception:
        logger.exception("Catchup run failed — will retry on next restart or manual run")
        # Clear the marker so a manual /run-now attempts again
        await db.autopilot_state.update_one(
            {"_id": "primary"}, {"$unset": {"last_run_date": ""}}
        )


def _install_job(scheduler: AsyncIOScheduler, cfg: dict) -> None:
    # Remove existing if any
    try:
        scheduler.remove_job(JOB_ID)
    except Exception:
        pass

    if not cfg.get("enabled"):
        logger.info("Autopilot disabled — no cron job installed")
        return

    hh, mm = [int(x) for x in (cfg.get("publish_time_local") or "07:00").split(":")]
    tz = ZoneInfo(cfg.get("timezone") or "UTC")
    trigger = CronTrigger(hour=hh, minute=mm, timezone=tz)
    scheduler.add_job(
        _daily_job,
        trigger=trigger,
        id=JOB_ID,
        replace_existing=True,
        # If backend was down at trigger time, still fire if we come back within 6 hours.
        # Beyond that, `_catchup_if_missed` handles it on startup.
        misfire_grace_time=6 * 3600,
        coalesce=True,
    )
    logger.info("Autopilot cron installed: %02d:%02d %s", hh, mm, tz)


async def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    cfg = await load_config(db)
    _install_job(_scheduler, cfg)

    # Calendar refresh: every 15 min, pull all iCal sources.
    async def _refresh_calendars():
        try:
            from core.calendar_client import fetch_and_store
            sources = await db.calendar_sources.find({}, {"_id": 0}).to_list(50)
            for s in sources:
                result = await fetch_and_store(db, s)
                await db.calendar_sources.update_one(
                    {"id": s["id"]},
                    {"$set": {
                        "last_fetched": now_iso(),
                        "last_event_count": result.get("events"),
                        "last_error": result.get("error"),
                    }},
                )
        except Exception:
            logger.exception("Calendar refresh failed")

    _scheduler.add_job(
        _refresh_calendars,
        trigger=IntervalTrigger(minutes=15),
        id="calendar_refresh",
        replace_existing=True,
        # Fire once ~30s after startup so Russell has fresh events without a wait.
        next_run_time=datetime.now() + timedelta(seconds=30),
    )
    logger.info("Calendar refresh scheduled every 15 minutes")

    # Fire catchup in the background so startup isn't blocked by a 2-min pipeline run
    asyncio.create_task(_catchup_if_missed())


def reschedule_autopilot(cfg: dict) -> None:
    """Called from the router when the user changes config."""
    if _scheduler is None:
        return
    _install_job(_scheduler, cfg)


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


# Convenience: allow synchronous callers to schedule the startup
def start_scheduler_sync():
    loop = asyncio.get_event_loop()
    loop.create_task(start_scheduler())
