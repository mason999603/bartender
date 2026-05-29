"""Russell on the Pi — wake-word-triggered voice loop.

Usage on the Pi:
    cd /opt/russell/pi_client && ./venv/bin/python russell_pi_client.py

Flow:
    Mic → openWakeWord ("Hey Jarvis" by default) → record until silence →
    POST audio to /api/voice/transcribe (Whisper) → POST text to /api/chat →
    Piper TTS → play Russell's reply → back to wake-word listening.

One brain across web, SMS, Telegram, and now the Pi (session_id="main").
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import requests
import sounddevice as sd
from dotenv import load_dotenv

# Load env from this script's dir
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from audio_io import record_until_silence, play_wav_file  # noqa: E402
from tts_piper import PiperTTS, speak  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("russell.pi")


# ============================================================
# Config
# ============================================================
class Config:
    backend_url: str
    session_id: str
    wake_model: str
    wake_threshold: float
    input_device: Optional[int]
    output_device: Optional[int]
    vad_threshold: float
    vad_silence_seconds: float
    vad_max_seconds: float
    piper_voice_path: str
    wake_ack_sound: Optional[str]


def _int_or_none(v: str | None) -> Optional[int]:
    if not v or not str(v).strip():
        return None
    try:
        return int(v)
    except ValueError:
        return None


def load_config() -> Config:
    c = Config()
    c.backend_url = (os.environ.get("RUSSELL_BACKEND_URL") or "").rstrip("/")
    c.session_id = os.environ.get("RUSSELL_SESSION_ID") or "main"
    c.wake_model = (os.environ.get("WAKE_WORD_MODEL") or "hey_jarvis").strip()
    c.wake_threshold = float(os.environ.get("WAKE_WORD_THRESHOLD") or 0.5)
    c.input_device = _int_or_none(os.environ.get("INPUT_DEVICE_INDEX"))
    c.output_device = _int_or_none(os.environ.get("OUTPUT_DEVICE_INDEX"))
    c.vad_threshold = float(os.environ.get("VAD_SILENCE_THRESHOLD") or 0.015)
    c.vad_silence_seconds = float(os.environ.get("VAD_SILENCE_SECONDS") or 1.4)
    c.vad_max_seconds = float(os.environ.get("VAD_MAX_RECORD_SECONDS") or 30.0)
    c.piper_voice_path = os.environ.get("PIPER_VOICE_PATH") or "./voices/en_GB-northern_english_male-medium.onnx"
    c.wake_ack_sound = (os.environ.get("WAKE_ACK_SOUND") or "").strip() or None

    # Validate the bare essentials early — fail fast with a clear message.
    missing: list[str] = []
    if not c.backend_url:
        missing.append("RUSSELL_BACKEND_URL")
    if not Path(c.piper_voice_path).expanduser().exists():
        missing.append(f"PIPER_VOICE_PATH (file not found: {c.piper_voice_path})")
    if missing:
        logger.error("Config problems — fix /app/pi_client/.env then restart:")
        for m in missing:
            logger.error(f"  • {m}")
        sys.exit(2)
    return c


# ============================================================
# Cloud brain client
# ============================================================
class RussellAPI:
    def __init__(self, base_url: str, session_id: str):
        self.base = base_url
        self.session_id = session_id

    def transcribe(self, wav_bytes: bytes) -> str:
        files = {"audio": ("voice.wav", wav_bytes, "audio/wav")}
        r = requests.post(f"{self.base}/api/voice/transcribe", files=files, timeout=30)
        r.raise_for_status()
        return (r.json().get("text") or "").strip()

    def chat(self, text: str) -> str:
        payload = {"session_id": self.session_id, "message": text}
        r = requests.post(f"{self.base}/api/chat", json=payload, timeout=60)
        r.raise_for_status()
        return (r.json().get("reply") or "").strip()


# ============================================================
# Wake-word loop
# ============================================================
class WakeWordListener:
    """Streams mic frames into openWakeWord until a wake-word fires.

    openWakeWord is fully open-source, runs on-device, and ships pre-trained models
    like "hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy". You can also pass a path
    to a custom .onnx model you trained yourself.

    Audio format expected by the models: 16 kHz, mono, int16, 80ms chunks (1280 samples).
    """

    SAMPLE_RATE = 16000
    FRAME_LEN = 1280  # 80ms at 16kHz

    def __init__(self, wake_model: str, threshold: float, input_device: Optional[int]):
        # Lazy import — openWakeWord pulls in onnxruntime, slow to import on Pi.
        from openwakeword.model import Model as OWWModel
        from openwakeword.utils import download_models

        # Ensure the bundled models are on disk. No-op after first run.
        download_models()

        # Either a bundled model name or a path to a custom .onnx file.
        kwargs: dict = {"inference_framework": "onnx"}
        if wake_model.endswith(".onnx") or wake_model.endswith(".tflite"):
            kwargs["wakeword_models"] = [wake_model]
        else:
            kwargs["wakeword_models"] = [wake_model]

        self.model = OWWModel(**kwargs)
        self.threshold = threshold
        self.wake_model_name = wake_model
        self.input_device = input_device
        self.stream: Optional[sd.RawInputStream] = None

    def __enter__(self):
        self.stream = sd.RawInputStream(
            samplerate=self.SAMPLE_RATE,
            blocksize=self.FRAME_LEN,
            dtype="int16",
            channels=1,
            device=self.input_device,
        )
        self.stream.start()
        logger.info(
            f"Listening for wake word '{self.wake_model_name}'… "
            f"(threshold={self.threshold}, device={self.input_device})"
        )
        return self

    def __exit__(self, *exc):
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def wait_for_wake(self) -> None:
        """Blocks until any loaded wake-word's score crosses the threshold."""
        while True:
            data, _ = self.stream.read(self.FRAME_LEN)
            audio = np.frombuffer(bytes(data), dtype=np.int16)
            predictions = self.model.predict(audio)
            for _name, score in predictions.items():
                if score >= self.threshold:
                    logger.debug(f"wake fired: {_name}={score:.3f}")
                    return


# ============================================================
# Main loop
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="Russell — Raspberry Pi voice client")
    parser.add_argument("--list-audio", action="store_true", help="List audio devices and exit")
    args = parser.parse_args()

    if args.list_audio:
        print(sd.query_devices())
        return 0

    cfg = load_config()
    logger.info(f"Russell Pi client starting — backend={cfg.backend_url}")

    tts = PiperTTS(cfg.piper_voice_path)
    api = RussellAPI(cfg.backend_url, cfg.session_id)

    # Graceful shutdown
    stop_flag = {"stop": False}

    def _handle_sigint(_signum, _frame):
        logger.info("SIGINT received — finishing current cycle then exiting.")
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGTERM, _handle_sigint)

    # Warm Piper up front so the first reply isn't slow.
    try:
        speak(tts, "G'day. Russell standing by.", output_device=cfg.output_device)
    except Exception:
        logger.exception("Piper warm-up failed — continuing anyway")

    while not stop_flag["stop"]:
        try:
            with WakeWordListener(cfg.wake_model, cfg.wake_threshold, cfg.input_device) as listener:
                listener.wait_for_wake()
            logger.info("Wake word fired.")
            if cfg.wake_ack_sound:
                try:
                    play_wav_file(cfg.wake_ack_sound, output_device=cfg.output_device)
                except Exception:
                    logger.exception("Ack sound failed")

            # Record until they stop talking
            wav = record_until_silence(
                silence_threshold=cfg.vad_threshold,
                silence_seconds=cfg.vad_silence_seconds,
                max_seconds=cfg.vad_max_seconds,
                input_device=cfg.input_device,
            )
            logger.info(f"Captured {len(wav)} bytes of audio")

            # Cloud: STT → chat
            text = api.transcribe(wav)
            if not text:
                logger.info("Empty transcription — ignoring.")
                continue
            logger.info(f"You said: {text!r}")
            reply = api.chat(text)
            logger.info(f"Russell: {reply[:140]!r}{'…' if len(reply) > 140 else ''}")

            # Speak it
            speak(tts, reply, output_device=cfg.output_device)

        except requests.HTTPError:
            logger.exception("Backend HTTP error")
            try:
                speak(tts, "Bit of trouble reaching the brain, mate. Try me again.", output_device=cfg.output_device)
            except Exception:
                pass
        except requests.RequestException:
            logger.exception("Network error")
            try:
                speak(tts, "I'm offline at the moment. Check the wi-fi.", output_device=cfg.output_device)
            except Exception:
                pass
        except KeyboardInterrupt:
            stop_flag["stop"] = True
        except Exception:
            logger.exception("Unexpected error — pausing 2s before resuming")
            time.sleep(2)

    logger.info("Russell Pi client stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
