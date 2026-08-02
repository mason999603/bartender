"""APScheduler wrapper for autopilot's daily cron.

Started on FastAPI lifespan. Reads current config from Mongo and installs a
CronTrigger that fires at `publish_time_local` in `timezone`. If autopilot
is disabled, the job is removed. `reschedule_autopilot(cfg)` is called from
the config router whenever the user tweaks the schedule.
"""
from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.autopilot import load_config, produce_and_publish
from core.db import db

logger = logging.getLogger("russell.scheduler")

_scheduler: AsyncIOScheduler | None = None
JOB_ID = "autopilot_daily"


async def _daily_job():
    logger.info("Autopilot cron firing — producing today's video")
    try:
        await produce_and_publish(db, trigger="cron")
    except Exception:
        logger.exception("Autopilot cron run failed")


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
    scheduler.add_job(_daily_job, trigger=trigger, id=JOB_ID, replace_existing=True, misfire_grace_time=3600)
    logger.info("Autopilot cron installed: %02d:%02d %s", hh, mm, tz)


async def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    cfg = await load_config(db)
    _install_job(_scheduler, cfg)


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
