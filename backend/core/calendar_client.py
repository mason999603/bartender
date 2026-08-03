"""iCal / webcal calendar fetcher + parser.

Russell reads any number of user-configured .ics subscription URLs (typically
iCloud published calendars). Each source is fetched, parsed, and stored in
`db.calendar_events` with a source_id. We de-dup via VEVENT UID.

Design goals:
- Read-only: never write back to Apple's servers.
- Cheap: fetch every 15 min in a background task, no per-query hits.
- Timezone-aware: iCloud emits floating times for some events; we normalise
  everything to UTC-aware `datetime` objects before storing.
- Recurring events expanded up to the horizon we care about (14 days ahead).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

import requests
from icalendar import Calendar
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.models import now_iso

logger = logging.getLogger("russell.calendar")

FETCH_TIMEOUT = 20
UA = "Russell/1.0 (Aussie AI bartender)"


def _to_https(url: str) -> str:
    """webcal:// → https:// (they're the same server, just a different scheme)."""
    if url.startswith("webcal://"):
        return "https://" + url[len("webcal://"):]
    return url


def _to_aware(dt) -> datetime:
    """Normalise DATE or DATETIME to a UTC-aware datetime."""
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(dt, date):
        return datetime.combine(dt, time.min, tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _clean(s) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def _expand_recurrence(component, horizon_end: datetime) -> Iterable[dict]:
    """Yield concrete occurrences of a VEVENT up to horizon_end.

    Uses python-dateutil's rrulestr for standard RRULE expansion. Non-recurring
    events yield a single occurrence.
    """
    dtstart = component.get("DTSTART")
    if not dtstart:
        return
    start_dt = _to_aware(dtstart.dt)
    end_prop = component.get("DTEND")
    if end_prop:
        end_dt = _to_aware(end_prop.dt)
    else:
        # All-day events with only DTSTART: treat as 1 day
        end_dt = start_dt + timedelta(hours=1)
    duration = end_dt - start_dt

    rrule = component.get("RRULE")
    if not rrule:
        yield {"start": start_dt, "end": end_dt}
        return

    # Recurring — expand
    try:
        from dateutil.rrule import rrulestr

        rrule_str = "RRULE:" + rrule.to_ical().decode("ascii")
        rule = rrulestr(rrule_str, dtstart=start_dt)
        for occ in rule:
            if occ > horizon_end:
                break
            yield {"start": occ, "end": occ + duration}
    except Exception:
        # If we can't parse, just emit the master event once
        yield {"start": start_dt, "end": end_dt}


async def fetch_and_store(db: AsyncIOMotorDatabase, source: dict, horizon_days: int = 14) -> dict:
    """Fetch a single source URL, parse, upsert events into db.calendar_events.
    Returns a summary dict with counts + any error.
    """
    url = _to_https(source["url"])
    try:
        r = requests.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": UA})
        r.raise_for_status()
    except Exception as e:
        logger.exception("Calendar fetch failed: %s", url)
        return {"ok": False, "error": f"fetch: {e}", "events": 0}

    try:
        cal = Calendar.from_ical(r.text)
    except Exception as e:
        return {"ok": False, "error": f"parse: {e}", "events": 0}

    horizon_end = datetime.now(timezone.utc) + timedelta(days=horizon_days)
    horizon_start = datetime.now(timezone.utc) - timedelta(days=1)

    # Purge previous events for this source — cleaner than trying to sync incrementally.
    await db.calendar_events.delete_many({"source_id": source["id"]})

    events: list[dict] = []
    calendar_name = _clean(cal.get("X-WR-CALNAME") or source.get("name") or "Calendar")

    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        uid = _clean(comp.get("UID"))
        summary = _clean(comp.get("SUMMARY"))
        location = _clean(comp.get("LOCATION"))
        description = _clean(comp.get("DESCRIPTION"))
        for occ in _expand_recurrence(comp, horizon_end):
            if occ["end"] < horizon_start:
                continue
            if occ["start"] > horizon_end:
                continue
            events.append(
                {
                    "source_id": source["id"],
                    "source_name": source.get("name") or calendar_name,
                    "uid": f"{uid}@{occ['start'].isoformat()}",  # unique per occurrence
                    "summary": summary,
                    "location": location,
                    "description": description[:500],
                    "start": occ["start"].isoformat(),
                    "end": occ["end"].isoformat(),
                    "all_day": (occ["end"] - occ["start"]) >= timedelta(hours=23),
                    "duration_minutes": int((occ["end"] - occ["start"]).total_seconds() // 60),
                }
            )

    if events:
        await db.calendar_events.insert_many(events)

    return {
        "ok": True,
        "events": len(events),
        "calendar_name": calendar_name,
    }
