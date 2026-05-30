"""Piper TTS — local, offline voice for Russell.

Uses the `piper` CLI (more stable across versions than the Python API) to
synthesize text → WAV, plays back via `aplay` which handles sample-rate
conversion the Pi's on-board DAC needs.

Fully offline / free — no cloud TTS calls.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

logger = logging.getLogger("russell.tts")


class PiperTTS:
    """Local Piper voice via CLI. One instance reused across many syntheses."""

    def __init__(self, voice_path: str):
        self.voice_path = voice_path
        self._cmd = self._find_piper()
        self._warned_missing = False

    @staticmethod
    def _find_piper() -> list[str] | None:
        """Locate the piper executable. Prefer the standalone binary, fall back to `python -m piper`."""
        exe = shutil.which("piper")
        if exe:
            return [exe]
        # piper-tts can be invoked as `python -m piper`
        return [sys.executable, "-m", "piper"]

    def synthesize_to_wav(self, text: str, wav_path: str) -> None:
        """Render `text` straight to a wav file on disk via the piper CLI."""
        text = (text or "").strip()
        if not text:
            return
        if not self._cmd:
            if not self._warned_missing:
                logger.error("piper CLI not found — `pip install piper-tts`")
                self._warned_missing = True
            return
        cmd = self._cmd + ["--model", self.voice_path, "--output_file", wav_path]
        # Pipe text via Popen+communicate so stdin is properly closed (signals EOF to piper).
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, stderr = proc.communicate(input=text.encode("utf-8"), timeout=60)
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="ignore")[:400]
                logger.warning(f"piper exit {proc.returncode}: {err}")
                raise subprocess.CalledProcessError(proc.returncode, cmd, output=err)
        except subprocess.TimeoutExpired:
            proc.kill()
            logger.warning("piper timed out after 60s")
            raise


def speak(tts: PiperTTS, text: str, output_device: Optional[int] = None) -> None:
    """Top-level: synth + play. Uses `aplay` for reliable Pi audio routing."""
    text = (text or "").strip()
    if not text:
        return
    # Strip markdown leftovers Claude/Llama sometimes slip in — Piper reads them literally.
    text = text.replace("**", "").replace("*", "").replace("`", "")

    aplay = shutil.which("aplay")
    if not aplay:
        logger.error("aplay not found — install with: sudo apt install -y alsa-utils")
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        try:
            tts.synthesize_to_wav(text, wav_path)
        except Exception as e:
            logger.warning(f"Piper synthesis failed: {e}")
            return

        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
            logger.warning("Piper produced empty/tiny audio — skipping playback")
            return

        # plughw lets ALSA resample Piper's 22050Hz to whatever the DAC wants.
        target = f"plughw:{output_device},0" if output_device is not None else "default"
        try:
            subprocess.run([aplay, "-q", "-D", target, wav_path], check=True)
        except subprocess.CalledProcessError as e:
            logger.warning(f"aplay -D {target} failed ({e}) — trying default device")
            try:
                subprocess.run([aplay, "-q", wav_path], check=True)
            except subprocess.CalledProcessError as e2:
                logger.error(f"aplay failed entirely: {e2}")
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
