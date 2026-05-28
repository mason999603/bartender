"""Phase 3 voice tests — POST /api/voice/transcribe (Whisper STT via emergentintegrations)."""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://code-snapshot-23.preview.emergentagent.com").rstrip("/")
URL = f"{BASE_URL}/api/voice/transcribe"


class TestVoiceTranscribe:
    # No file uploaded -> FastAPI validation 422
    def test_no_file_returns_422(self):
        r = requests.post(URL)
        assert r.status_code == 422

    # Tiny blob (<500 bytes) -> graceful {text:""} (no STT call)
    def test_tiny_blob_returns_empty_text(self):
        tiny = io.BytesIO(b"\x00" * 100)
        files = {"audio": ("voice.webm", tiny, "audio/webm")}
        r = requests.post(URL, files=files)
        assert r.status_code == 200
        data = r.json()
        assert data == {"text": ""}

    # Real audio (1s 440Hz sine WAV via ffmpeg) -> 200 with "text" field
    def test_real_audio_returns_text_field(self):
        wav_path = "/tmp/test.wav"
        assert os.path.exists(wav_path), "ffmpeg-generated test WAV missing"
        with open(wav_path, "rb") as f:
            files = {"audio": ("voice.wav", f, "audio/wav")}
            r = requests.post(URL, files=files, timeout=60)
        # 200 from Whisper, or 429 if budget exceeded
        if r.status_code == 429:
            pytest.skip(f"Whisper budget exceeded: {r.text}")
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        data = r.json()
        assert "text" in data
        assert isinstance(data["text"], str)

    # No filename, but content-type audio/webm -> route guards add extension and proceeds
    def test_missing_filename_with_webm_content_type(self):
        # Filename omitted entirely — should be guarded
        buf = io.BytesIO(b"\x00" * 200)  # tiny -> short-circuits to {text:""} without breaking
        files = {"audio": ("", buf, "audio/webm")}
        r = requests.post(URL, files=files)
        # Tiny short-circuits to 200 {text:""}, proves the no-filename branch did not crash
        assert r.status_code == 200
        assert r.json() == {"text": ""}

    # >25MB -> 413
    def test_too_large_returns_413(self):
        # 26MB of zeros
        big = io.BytesIO(b"\x00" * (26 * 1024 * 1024))
        files = {"audio": ("big.webm", big, "audio/webm")}
        r = requests.post(URL, files=files, timeout=120)
        assert r.status_code == 413


# Regression — Phase 1/2 endpoints still alive
class TestRegression:
    def test_chat_endpoint_alive(self):
        r = requests.post(f"{BASE_URL}/api/chat", json={"session_id": "phase3-test", "message": "Ping"}, timeout=60)
        assert r.status_code in (200, 429)

    def test_cocktails_list(self):
        r = requests.get(f"{BASE_URL}/api/cocktails")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) > 0

    def test_substitutions_list(self):
        r = requests.get(f"{BASE_URL}/api/substitutions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_cocktails_by_flavour(self):
        r = requests.post(f"{BASE_URL}/api/cocktails/by-flavour", json={"include": ["smoky"], "exclude": []})
        assert r.status_code == 200
        assert isinstance(r.json(), list)
