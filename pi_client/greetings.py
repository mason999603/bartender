"""Russell's boot greeting — pick a line that suits the time of day.

Vibe: a half-asleep bartender being woken up. Grumpier the later it is.
The pool grows with anytime banter so even on a midday restart he's got
something fresh to say.
"""
from __future__ import annotations

import random
from datetime import datetime


# Late-night / wee hours (10pm–4am): woken up grumpy
LATE_NIGHT = [
    "Aye, why're ya wakin' me at this hour, mate?",
    "Crikey, what time is it? Better be good.",
    "Bloody hell, can't a bloke get some sleep?",
    "Right. I'm up. This better not be about ice.",
    "Strewth, mate, the bar's been closed for hours.",
    "Yeah, yeah, I'm awake. What's the drama?",
    "Mate. It's late. What're we doin'.",
]

# Early morning (4am–8am): rough start, needs coffee
EARLY_MORNING = [
    "Mate, the sun's barely up. Coffee's on you.",
    "Early start, eh? Right, what're we doin'.",
    "Ugh, mornin'. Talk slow till I find me bearings.",
    "Mornin'. Don't suppose you've made coffee.",
    "Up before the birds, you reckon? Alright, I'm here.",
]

# Late morning (8am–noon): functional, getting going
LATE_MORNING = [
    "Mornin' mate. What's the plan today?",
    "G'day. What're we lookin' at?",
    "Right, I'm with ya. What's on?",
    "Mornin'. Hope you've had a coffee.",
    "G'day mate. Ready when you are.",
]

# Afternoon (noon–5pm): cruising
AFTERNOON = [
    "G'day. What's happenin'?",
    "Yep, I'm here. What's the go?",
    "Right mate, talk to me.",
    "On the clock. Whaddya need?",
    "G'day. Behind the stick, ready to roll.",
]

# Evening (5pm–10pm): service mode, sharpest
EVENING = [
    "Right, evenin'. Service time. What've ya got?",
    "G'day. Big night ahead?",
    "Yep, I'm on. Talk to me.",
    "Behind the stick mate, let's go.",
    "Evenin'. Bring it on.",
]

# Anytime banter — works whenever, mixed in as wildcard
ANYTIME = [
    "Ehh, what's up mate?",
    "Yep, I'm awake.",
    "Cool, I'm on.",
    "Right, where were we?",
    "Standing by, mate.",
    "Yeah?",
    "Sound. What's the go?",
    "Aye, I'm here.",
    "Talk to me.",
]


def _pool_for_hour(hour: int) -> list[str]:
    """Pick the right time-band pool for the given local hour (0–23)."""
    if hour >= 22 or hour < 4:
        return LATE_NIGHT
    if hour < 8:
        return EARLY_MORNING
    if hour < 12:
        return LATE_MORNING
    if hour < 17:
        return AFTERNOON
    return EVENING  # 17:00 – 21:59


def pick_greeting(now: datetime | None = None, anytime_weight: float = 0.3) -> str:
    """Return a random greeting, weighted toward time-of-day lines.

    `anytime_weight` (0–1) — chance of overriding the time band with a generic
    anytime line. Default 30% keeps variety without losing the time-of-day cue.
    """
    now = now or datetime.now()
    pool = _pool_for_hour(now.hour)
    if random.random() < anytime_weight:
        pool = ANYTIME
    return random.choice(pool)
