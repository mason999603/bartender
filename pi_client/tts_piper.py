"""Piper TTS — local, offline voice for Russell.

Wraps the `piper-tts` Python package. Synthesises text → numpy audio → playback.
Playback uses `aplay` so ALSA handles any sample-rate conversion the on-board
DAC can't do natively (Pi 3.5mm jack wants 44.1/48 kHz, Piper outputs 22.05 kHz).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import wave
from io import BytesIO
from typing import Optional

import numpy as np

logger = logging.getLogger("russell.tts")


class PiperTTS:
    """Lazy-loaded Piper voice. One instance reused across many syntheses."""

    def __init__(self, voice_path: str):
        self.voice_path = voice_path
        self._voice = None

    def _ensure_loaded(self) -> None:
        if self._voice is not None:
            return
        try:
            from piper.voice import PiperVoice
        except ImportError as e:
            raise RuntimeError(
                "piper-tts not installed. `pip install piper-tts` on the Pi."
            ) from e
        logger.info(f"Loading Piper voice: {self.voice_path}")
        self._voice = PiperVoice.load(self.voice_path)

    def synthesize_to_wav(self, text: str, wav_path: str) -> None:
        """Render `text` straight to a wav file on disk."""
        self._ensure_loaded()
        sr = self._voice.config.sample_rate
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            self._voice.synthesize(text, wf)

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Return (samples_int16, sample_rate). Kept for backward compatibility."""
        self._ensure_loaded()
        sr = self._voice.config.sample_rate
        buf = BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16
            wf.setframerate(sr)
            self._voice.synthesize(text, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            n = wf.getnframes()
            raw = wf.readframes(n)
        samples = np.frombuffer(raw, dtype=np.int16)
        return samples, sr


def speak(tts: PiperTTS, text: str, output_device: Optional[int] = None) -> None:
    """Top-level: synth + play. Uses `aplay` for reliable Pi audio routing."""
    text = (text or "").strip()
    if not text:
        return
    # Piper handles punctuation well; strip markdown leftovers Claude sometimes slips in.
    text = text.replace("**", "").replace("*", "").replace("`", "")

    aplay = shutil.which("aplay")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        tts.synthesize_to_wav(text, wav_path)

        if aplay:
            # `plughw:N,0` lets ALSA resample for us — Piper's 22050Hz to whatever the DAC wants.
            # If we don't know the output device, fall back to "default" (sound server / dmix).
            if output_device is not None:
                target = f"plughw:{output_device},0"
            else:
                target = "default"
            cmd = [aplay, "-q", "-D", target, wav_path]
            try:
                subprocess.run(cmd, check=True)
                return
            except subprocess.CalledProcessError as e:
                logger.warning(f"aplay failed ({e}); falling back to sounddevice")

        # Fallback: in-process playback (works if no aplay available, e.g. dev machines)
        from audio_io import play_audio_array
        samples, sr = tts.synthesize(text)
        play_audio_array(samples, sr, output_device=output_device)
    finally:
        try:
            import os
            os.unlink(wav_path)
        except OSError:
            pass
