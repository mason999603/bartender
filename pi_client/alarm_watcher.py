"""Alarm watcher — background thread on the Pi that fires scheduled alarms.

Every 15 seconds we hit `GET /api/alarms/pending`. If any docs come back,
they're due to fire. For each:
  1. Immediately POST /api/alarms/{id}/fired so a Pi restart mid-alarm doesn't
     replay it.
  2. Duck the wake-word listener via `pause_wake_event` (owned by the main loop).
  3. Play the spoken message through the existing CloudTTS with a short lead-in
     beep so it grabs your attention. Loop up to 3 times with a 4s gap between
     rounds, checking after each round whether a silence phrase came in via
     the backend (Russell also silences via chat, so the loop just polls the
     alarm's `active` field).
  4. Unpause the wake-word listener.

Silencing:
  - Voice channel: user says "that's enough" / "shut up" / etc → chat call →
    Russell's brain calls `silence_alarm` action → backend flips `active=False`.
  - The alarm watcher notices `active=False` on next poll and stops the loop.

This design keeps the Pi client simple: no mid-playback keyword spotting, no
duplicate STT models. The user's existing wake-word + chat pipeline handles
silence via natural language.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import requests

logger = logging.getLogger("russell.alarms")

POLL_SECONDS = 15
MAX_ROUNDS = 3
BEEP_LEAD = "Oi. "  # short attention-grabber prepended to the TTS message


class AlarmWatcher(threading.Thread):
    def __init__(
        self,
        api_base: str,
        speak_fn: Callable[[str], None],
        pause_wake_event: threading.Event,
        stop_flag: dict,
    ):
        """
        api_base: e.g. https://xxx.preview.emergentagent.com (no trailing slash)
        speak_fn: callable that takes text and plays TTS (blocks until done)
        pause_wake_event: when set(), the main wake-word listener MUST idle.
                          The watcher sets it before firing an alarm and clears
                          it once done.
        stop_flag: dict with {"stop": bool} — shared shutdown signal.
        """
        super().__init__(name="RussellAlarmWatcher", daemon=True)
        self.api = api_base.rstrip("/")
        self.speak = speak_fn
        self.pause_wake = pause_wake_event
        self.stop_flag = stop_flag

    def _get_pending(self) -> list[dict]:
        try:
            r = requests.get(f"{self.api}/api/alarms/pending", timeout=8)
            r.raise_for_status()
            return r.json() or []
        except Exception:
            # Silent — backend flap shouldn't spam logs
            return []

    def _is_still_active(self, alarm_id: str) -> bool:
        try:
            r = requests.get(f"{self.api}/api/alarms", timeout=8)
            r.raise_for_status()
            for a in r.json() or []:
                if a.get("id") == alarm_id:
                    return bool(a.get("active"))
        except Exception:
            pass
        return True  # Assume still active on network error — better to keep ringing

    def _mark_fired(self, alarm_id: str) -> None:
        try:
            requests.post(f"{self.api}/api/alarms/{alarm_id}/fired", timeout=8)
        except Exception:
            pass

    def _play_alarm(self, alarm: dict) -> None:
        alarm_id = alarm["id"]
        message = (alarm.get("message") or "Alarm.").strip()
        self._mark_fired(alarm_id)
        self.pause_wake.set()  # tell the main loop to idle
        try:
            for round_idx in range(MAX_ROUNDS):
                if not self._is_still_active(alarm_id) or self.stop_flag.get("stop"):
                    logger.info("Alarm %s silenced mid-play, stopping loop", alarm_id[:8])
                    return
                try:
                    self.speak(BEEP_LEAD + message)
                except Exception:
                    logger.exception("Alarm TTS failed")
                # Between rounds, give the user a moment to say a silence phrase
                # to Russell's wake-listener (which briefly resumes here).
                self.pause_wake.clear()
                time.sleep(4)
                if not self._is_still_active(alarm_id):
                    logger.info("Alarm %s silenced between rounds", alarm_id[:8])
                    return
                self.pause_wake.set()
            logger.info("Alarm %s completed %d rounds without silence", alarm_id[:8], MAX_ROUNDS)
        finally:
            self.pause_wake.clear()

    def run(self) -> None:
        logger.info("AlarmWatcher started — polling %ds", POLL_SECONDS)
        while not self.stop_flag.get("stop"):
            pending = self._get_pending()
            if pending:
                # Only fire one at a time so overlapping alarms don't cause chaos
                self._play_alarm(pending[0])
            time.sleep(POLL_SECONDS)
        logger.info("AlarmWatcher stopped")
