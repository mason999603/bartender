"""Event importance analyzer.

Assigns each event a `priority` from 1 (background noise) to 10 (must-know),
plus a `category` label. The heuristic combines:
  - Keyword matches in the summary/description/location
  - Duration
  - Location type (venue-like names imply paid events)
  - Whether it's all-day (holidays / vacations)
  - Whether the calendar source is the user's "work" calendar (via a flag)

Categories (in priority order):
  shift             — work shift on the roster (10)
  travel_vacation   — flights, hotels, multi-day trips (10)
  ceremony          — weddings, funerals (10)
  paid_ticket       — concert, movie, show, sports w/ tickets (9)
  medical           — doctor, dentist, hospital, therapy (8)
  birthday          — birthday of a person (8)
  appointment       — haircut, gym trainer, mechanic, contractor (7)
  meeting           — meeting, call, video conf, 1:1 (6)
  personal          — dinner reservation, catch-up, date (7)
  routine           — regular gym/yoga/school (3)
  reminder          — task-like, all-day non-holiday (2)
  ordinary          — anything else (2)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# Keyword taxonomies. Everything is case-insensitive against summary+description+location.
CATEGORY_KEYWORDS: dict[str, tuple[tuple[str, ...], int]] = {
    "shift":            (("shift", "roster", "work:", "opening", "closing", "double", "bar shift"), 10),
    "travel_vacation":  (("flight", "boarding", "vacation", "holiday trip", "vaca", "cruise", "airport", "hotel", "airbnb", "check-in", "check in", "check-out", "departure", "arrival"), 10),
    "ceremony":         (("wedding", "funeral", "memorial", "baptism", "confirmation", "graduation"), 10),
    "paid_ticket":      (("concert", "gig", "festival", "movie", "cinema", "film", "premiere", "show", "musical", "theatre", "theater", "matinee", "match", "game", "grand final", "test match", "event ticket", "opera", "ballet", "comedy", "stand-up", "stand up", "sports"), 9),
    "medical":          (("doctor", "dr ", "dentist", "orthodontist", "gp", "hospital", "specialist", "therapy", "therapist", "physio", "psych", "clinic", "checkup", "check-up", "check up", "surgery", "scan", "mri", "x-ray", "blood test", "consultation"), 8),
    "birthday":         (("birthday", "b-day", "bday", "'s bday", "'s birthday"), 8),
    "appointment":      (("haircut", "barber", "salon", "mechanic", "car service", "vet", "contractor", "plumber", "electrician", "inspection", "quote", "delivery", "pickup", "pick up", "collect", "trainer", "pt session"), 7),
    "personal":         (("dinner", "lunch", "brunch", "date night", "date with", "drinks with", "catch-up", "catch up", "meet ", "meetup", "coffee with", "with mum", "with dad", "family dinner", "reservation", "booking"), 7),
    "meeting":          (("meeting", "1:1", "1-on-1", "standup", "stand-up", "call with", "call w/", "zoom", "google meet", "teams", "sync", "review", "planning", "kickoff", "kick-off", "retro", "briefing", "workshop"), 6),
    "routine":          (("gym", "yoga", "pilates", "run", "training", "school", "class", "lesson", "practice", "rehearsal"), 3),
}

# Words that STRONGLY suggest a paid event / venue in the location field
VENUE_HINTS = (
    "arena", "stadium", "theatre", "theater", "cinema", "opera", "hall",
    "amphitheater", "amphitheatre", "coliseum", "colosseum", "pavilion",
    "concert hall", "playhouse",
)


def _lc(v: Any) -> str:
    return (v or "").lower() if isinstance(v, str) else ""


def _text_blob(ev: dict) -> str:
    return " ".join([_lc(ev.get("summary", "")), _lc(ev.get("location", "")), _lc(ev.get("description", ""))])


def _duration_hours(ev: dict) -> float:
    return (ev.get("duration_minutes") or 0) / 60.0


def analyze(ev: dict, source_is_work: bool = False) -> dict:
    """Return the event dict with 'priority' + 'category' fields added."""
    blob = _text_blob(ev)
    summary_l = _lc(ev.get("summary", ""))
    location_l = _lc(ev.get("location", ""))
    priority = 2
    category = "ordinary"

    # 1) Match against category taxonomies (first hit wins by priority order in dict)
    for cat, (keywords, cat_priority) in CATEGORY_KEYWORDS.items():
        if any(kw in blob for kw in keywords):
            category = cat
            priority = cat_priority
            break

    # 2) Venue hints boost paid_ticket unless already tagged higher
    if any(v in location_l for v in VENUE_HINTS) and priority < 9:
        category = "paid_ticket"
        priority = 9

    # 3) All-day multi-day events → likely vacation
    if ev.get("all_day") and _duration_hours(ev) > 26 and category == "ordinary":
        category = "travel_vacation"
        priority = 10

    # 4) Boost if the calendar is the "work" source AND we couldn't classify it at all.
    # We only promote *ordinary* events (no keyword hits). Routine/medical/personal
    # keyword hits already correctly classified the event — don't override.
    if source_is_work and category == "ordinary":
        if summary_l.strip() and _duration_hours(ev) >= 3:
            category = "shift"
            priority = 10

    # 5) Short (< 20 min) all-day-esque non-holiday items are usually reminders
    if _duration_hours(ev) < 0.35 and category == "ordinary":
        category = "reminder"
        priority = 2

    return {**ev, "priority": priority, "category": category}


def rank_upcoming(events: list[dict], sources: list[dict]) -> list[dict]:
    """Analyse every event, sort by (priority desc, start time asc), return list."""
    work_ids = {s["id"] for s in sources if s.get("is_work")}
    now = datetime.now(timezone.utc)
    scored = []
    for ev in events:
        try:
            start = datetime.fromisoformat(ev["start"])
        except Exception:
            continue
        if start < now:
            continue  # already past
        scored.append(analyze(ev, source_is_work=(ev.get("source_id") in work_ids)))
    scored.sort(key=lambda e: (-e["priority"], e["start"]))
    return scored


def briefing_block(ranked: list[dict], max_items: int = 20) -> str:
    """Compact plaintext block Russell can drop into a chat reply or system prompt."""
    if not ranked:
        return ""
    lines = ["## UPCOMING EVENTS (ranked by importance, high → low)"]
    for ev in ranked[:max_items]:
        try:
            start = datetime.fromisoformat(ev["start"]).astimezone()
            when = start.strftime("%a %d %b %I:%M%p")
        except Exception:
            when = ev.get("start", "?")
        loc = f" @ {ev['location']}" if ev.get("location") else ""
        pri = ev.get("priority", 0)
        cat = ev.get("category", "")
        title = re.sub(r"\s+", " ", ev.get("summary") or "(no title)")
        lines.append(f"[{pri}/10 {cat}] {when} — {title}{loc}")
    return "\n".join(lines)
