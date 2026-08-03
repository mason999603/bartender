"""Cloud TTS with streaming MP3 playback.

The backend `/api/voice/speak` endpoint returns audio bytes. For a 30s reply
a WAV is ~5MB, an MP3 is ~500KB — 10x less to shove over the Pi's Wi-Fi. We
request MP3 and pipe the bytes straight into `mpg123 -` (stdin decoder), which
starts playing the moment enough data has arrived to decode a frame. Perceived
latency drops from "wait for full download + aplay" to "first sound ~200ms
after the network response starts".

Fallback: if `mpg123` isn't installed on the Pi, we degrade to buffer-to-disk +
ffplay / aplay so nothing breaks — but install mpg123 to unlock the streaming
win:  `sudo apt install -y mpg123`
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

import requests

logger = logging.getLogger("russell.tts")


class CloudTTS:
    """Thin wrapper around POST /api/voice/speak."""

    def __init__(self, base_url: str, voice: str = "onyx", model: str = "tts-1", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.voice = voice
        self.model = model
        self.timeout = timeout

    def open_stream(self, text: str, fmt: str = "mp3") -> requests.Response:
        """Return a raw streaming HTTP response. Caller must close it."""
        r = requests.post(
            f"{self.base_url}/api/voice/speak",
            json={"text": text, "voice": self.voice, "model": self.model, "format": fmt},
            timeout=self.timeout,
            stream=True,
        )
        r.raise_for_status()
        return r


def _play_streaming_mp3(tts: CloudTTS, text: str, output_device: Optional[int]) -> bool:
    """Best path: pipe MP3 bytes from the backend straight into mpg123's stdin.

    mpg123 decodes-and-plays as bytes arrive, so playback starts within a few
    hundred milliseconds of the response first-byte. Returns True on success.
    """
    mpg123 = shutil.which("mpg123")
    if not mpg123:
        return False

    # `-a plughw:X,0` targets a specific ALSA device; omit for system default.
    cmd = [mpg123, "-q"]
    if output_device is not None:
        cmd += ["-a", f"plughw:{output_device},0"]
    cmd += ["-"]  # read from stdin

    resp = tts.open_stream(text, fmt="mp3")
    try:
        # bufsize=0 = unbuffered writes so audio starts fast
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, bufsize=0)
    except Exception as e:
        logger.warning(f"mpg123 launch failed ({e}) — falling back to buffered aplay")
        resp.close()
        return False

    try:
        # 8KB chunks — small enough for fast first-frame, big enough to be efficient
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            try:
                proc.stdin.write(chunk)
            except BrokenPipeError:
                # mpg123 exited early (bad device? SIGINT?). Bail cleanly.
                break
        try:
            proc.stdin.close()
        except Exception:
            pass
        rc = proc.wait(timeout=60)
        if rc != 0:
            logger.debug(f"mpg123 exited {rc}")
        return True
    except Exception as e:
        logger.warning(f"Streaming playback error: {e}")
        try:
            proc.kill()
        except Exception:
            pass
        return False
    finally:
        resp.close()


def _play_buffered_wav(tts: CloudTTS, text: str, output_device: Optional[int]) -> bool:
    """Fallback: download WAV → save → aplay. Slower but bulletproof."""
    aplay = shutil.which("aplay")
    if not aplay:
        logger.error("aplay not found — install with: sudo apt install -y alsa-utils")
        return False

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        r = requests.post(
            f"{tts.base_url}/api/voice/speak",
            json={"text": text, "voice": tts.voice, "model": tts.model, "format": "wav"},
            timeout=tts.timeout,
        )
        r.raise_for_status()
        with open(wav_path, "wb") as f:
            f.write(r.content)

        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 200:
            logger.warning("Cloud TTS produced empty/tiny audio — skipping playback")
            return False

        target = f"plughw:{output_device},0" if output_device is not None else "default"
        try:
            subprocess.run([aplay, "-q", "-D", target, wav_path], check=True)
        except subprocess.CalledProcessError as e:
            logger.warning(f"aplay -D {target} failed ({e}) — trying default device")
            subprocess.run([aplay, "-q", wav_path], check=True)
        return True
    except Exception as e:
        logger.warning(f"Buffered playback failed: {e}")
        return False
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


def speak(tts: CloudTTS, text: str, output_device: Optional[int] = None) -> None:
    """Top-level: cloud-synth + play. Streams via mpg123 when available."""
    text = (text or "").strip()
    if not text:
        return
    # Strip markdown leftovers the model might slip in — TTS reads them literally.
    text = text.replace("**", "").replace("*", "").replace("`", "")

    # Try streaming MP3 first, fall back to buffered WAV.
    if _play_streaming_mp3(tts, text, output_device):
        return
    _play_buffered_wav(tts, text, output_device)
