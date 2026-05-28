"""Russell — Companion grounding.

Adds real-world awareness to Russell's brain:
 - current local time/date
 - live weather via Open-Meteo (free, no API key)
 - user's saved location

The output of `build_companion_context()` is injected into Russell's system prompt
on every conversation turn so he can speak naturally about today, the weather,
greetings appropriate to the time of day, etc.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("russell.companion")

DEFAULT_LOCATION = "Sydney, Australia"
DEFAULT_TZ = "Australia/Sydney"

# Simple in-memory weather cache: {location_lower: (timestamp, payload)}
# Note: process-local — fine for single-worker. If we go multi-worker, move to Redis or Mongo.
_weather_cache: dict = {}


def _to_float(v):
    """Coerce a value to float, returning None on failure or if v is None."""
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


# WMO weather codes → human description
# (Open-Meteo uses WMO codes; this is the canonical mapping.)
WMO_CODES = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "light freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "rain showers",
    81: "heavy showers",
    82: "violent showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "severe thunderstorm",
}

# Tokens in the user message that should trigger a weather lookup.
WEATHER_TRIGGERS = (
    "weather", "rain", "raining", "rainy", "sunny", "sun ", "cold", "hot", "warm",
    "freezing", "forecast", "today", "tomorrow", "outside", "windy",
    "good morning", "g'day", "morning russell", "good night", "evening russell",
    "what's the day", "what day", "how's the day",
)


async def get_user_location_and_tz(db) -> tuple[str, str]:
    """Read user's saved location + timezone from memories collection.
    Falls back to Sydney/Australia."""
    loc_doc = await db.memories.find_one(
        {"key": {"$regex": "^location$", "$options": "i"}}
    )
    location = (loc_doc or {}).get("value") or DEFAULT_LOCATION

    tz_doc = await db.memories.find_one(
        {"key": {"$regex": "^timezone$", "$options": "i"}}
    )
    tz_value = (tz_doc or {}).get("value") or DEFAULT_TZ
    return location, tz_value


async def fetch_weather(location: str) -> Optional[dict]:
    """Geocode `location` and fetch current weather.

    Strategy: 10-minute in-memory cache → Open-Meteo (primary) → wttr.in (fallback).
    Both services are free with no API key.
    """
    query = location.split(",")[0].strip() if location else DEFAULT_LOCATION
    cache_key = query.lower()
    cached = _weather_cache.get(cache_key)
    if cached and (datetime.utcnow().timestamp() - cached[0]) < 600:
        return cached[1]

    async with httpx.AsyncClient(timeout=8) as client:
        # --- Primary: Open-Meteo ---
        try:
            geo = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": query, "count": 1, "format": "json"},
            )
            if geo.status_code != 200:
                logger.warning(f"Open-Meteo geocode HTTP {geo.status_code} for {query!r}: {geo.text[:200]}")
            results = (geo.json() or {}).get("results") or []
            if results:
                r = results[0]
                lat = r["latitude"]
                lon = r["longitude"]
                tz = r.get("timezone", "auto")
                place_bits = [r.get("name"), r.get("admin1"), r.get("country")]
                place = ", ".join([b for b in place_bits if b])
                fc = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": (
                            "temperature_2m,apparent_temperature,relative_humidity_2m,"
                            "weather_code,wind_speed_10m,is_day"
                        ),
                        "daily": (
                            "temperature_2m_max,temperature_2m_min,"
                            "precipitation_probability_max,sunrise,sunset"
                        ),
                        "timezone": tz,
                        "forecast_days": 1,
                    },
                )
                if fc.status_code != 200:
                    logger.warning(f"Open-Meteo forecast HTTP {fc.status_code} for {place}: {fc.text[:200]}")
                data = fc.json() if fc.status_code == 200 else {}
                if not data.get("error") and data.get("current", {}).get("temperature_2m") is not None:
                    cur = data["current"]
                    daily = data.get("daily", {}) or {}
                    code = cur.get("weather_code")
                    result = {
                        "place": place,
                        "source": "open-meteo",
                        "timezone": tz,
                        "temp_c": cur.get("temperature_2m"),
                        "feels_c": cur.get("apparent_temperature"),
                        "humidity": cur.get("relative_humidity_2m"),
                        "wind_kmh": cur.get("wind_speed_10m"),
                        "is_day": cur.get("is_day") == 1,
                        "code": code,
                        "condition": WMO_CODES.get(code, "—") if code is not None else "—",
                        "high_c": (daily.get("temperature_2m_max") or [None])[0],
                        "low_c": (daily.get("temperature_2m_min") or [None])[0],
                        "rain_chance": (daily.get("precipitation_probability_max") or [None])[0],
                        "sunrise": (daily.get("sunrise") or [None])[0],
                        "sunset": (daily.get("sunset") or [None])[0],
                    }
                    _weather_cache[cache_key] = (datetime.utcnow().timestamp(), result)
                    return result
        except Exception as e:
            logger.warning(f"Open-Meteo failed for {query!r}: {e}")

        # --- Fallback: wttr.in (text-mode 'format=j1' returns JSON) ---
        try:
            r = await client.get(
                f"https://wttr.in/{query}",
                params={"format": "j1"},
                headers={"User-Agent": "Russell-Bartender/1.0"},
            )
            if r.status_code != 200:
                logger.warning(f"wttr.in HTTP {r.status_code} for {query!r}: {r.text[:200]}")
                return None
            j = r.json()
            cur = (j.get("current_condition") or [{}])[0]
            today = (j.get("weather") or [{}])[0]
            area = ((j.get("nearest_area") or [{}])[0]) or {}
            place = ", ".join(filter(None, [
                (area.get("areaName") or [{}])[0].get("value"),
                (area.get("region") or [{}])[0].get("value"),
                (area.get("country") or [{}])[0].get("value"),
            ]))
            desc = (cur.get("weatherDesc") or [{}])[0].get("value", "—").lower()
            result = {
                "place": place or query.title(),
                "source": "wttr.in",
                "timezone": None,
                "temp_c": _to_float(cur.get("temp_C")),
                "feels_c": _to_float(cur.get("FeelsLikeC")),
                "humidity": _to_float(cur.get("humidity")),
                "wind_kmh": _to_float(cur.get("windspeedKmph")),
                "is_day": None,
                "code": None,
                "condition": desc,
                "high_c": _to_float(today.get("maxtempC")),
                "low_c": _to_float(today.get("mintempC")),
                "rain_chance": None,
                "sunrise": (today.get("astronomy") or [{}])[0].get("sunrise"),
                "sunset": (today.get("astronomy") or [{}])[0].get("sunset"),
            }
            _weather_cache[cache_key] = (datetime.utcnow().timestamp(), result)
            return result
        except Exception as e:
            logger.warning(f"wttr.in failed for {query!r}: {e}")

    return None


def _now_in_tz(tz_name: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz_name))
    except ZoneInfoNotFoundError:
        return datetime.now(ZoneInfo(DEFAULT_TZ))


def _time_of_day(now: datetime) -> str:
    h = now.hour
    if 4 <= h < 11:
        return "morning"
    if 11 <= h < 14:
        return "midday"
    if 14 <= h < 17:
        return "afternoon"
    if 17 <= h < 21:
        return "evening"
    return "late night"


async def build_companion_context(db, user_text: str) -> str:
    """Build a real-time grounding block to inject into Russell's system prompt.

    Always includes time + location. Weather is added on relevant trigger words
    (or when the message is short and conversational — like a greeting)."""
    location, tz_name = await get_user_location_and_tz(db)
    now = _now_in_tz(tz_name)

    parts: list[str] = []
    parts.append(
        f"- Now: {now.strftime('%A %d %B %Y, %I:%M %p')} ({tz_name}) — time-of-day: {_time_of_day(now)}"
    )
    parts.append(f"- User's location: {location}")

    t = (user_text or "").lower().strip()
    short_greeting = len(t.split()) <= 5 and any(
        g in t for g in ("morning", "g'day", "gday", "hey russell", "hi russell", "russell")
    )
    weather_wanted = short_greeting or any(k in t for k in WEATHER_TRIGGERS)

    if weather_wanted:
        w = await fetch_weather(location)
        if w and w.get("temp_c") is not None:
            parts.append(
                f"- Weather right now in {w['place']}: {w['temp_c']}°C "
                f"(feels {w['feels_c']}°C), {w['condition']}. "
                f"Today high {w['high_c']}°C / low {w['low_c']}°C, "
                f"rain chance {w['rain_chance']}%, wind {w['wind_kmh']} km/h."
            )
            if w.get("sunrise") and w.get("sunset"):
                # Sunrise/sunset are ISO datetimes in local timezone
                try:
                    sr = datetime.fromisoformat(w["sunrise"]).strftime("%I:%M %p").lstrip("0")
                    ss = datetime.fromisoformat(w["sunset"]).strftime("%I:%M %p").lstrip("0")
                    parts.append(f"- Sunrise {sr}, sunset {ss}.")
                except Exception:
                    pass

    return "\n".join(parts)
