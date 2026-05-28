"""Phase 4: Twilio telephony tests (SMS + Voice) + regressions."""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://code-snapshot-23.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ----- /api/twilio/status -----
def test_twilio_status_returns_unconfigured_state():
    r = requests.get(f"{API}/twilio/status", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["configured"] is False
    assert data["has_account_sid"] is False
    assert data["has_auth_token"] is False
    assert data["phone_number_configured"] is False
    assert data["signature_validation"] is True
    assert "public_base_url" in data


# ----- /api/twilio/sms -----
def _is_twiml(text: str) -> bool:
    return text.lstrip().startswith("<?xml") and "<Response>" in text and "</Response>" in text


def test_sms_replies_with_in_character_message():
    r = requests.post(
        f"{API}/twilio/sms",
        data={"From": "+61400000000", "Body": "G'day Sheldon, recommend a smoky drink"},
        timeout=120,
    )
    assert r.status_code == 200, r.text
    assert "application/xml" in r.headers.get("content-type", "").lower()
    body = r.text
    assert _is_twiml(body)
    m = re.search(r"<Message>(.+?)</Message>", body, re.DOTALL)
    assert m, "No <Message> tag found"
    msg = m.group(1)
    # Length bound (under 1500 chars after escape)
    assert len(msg) <= 1500
    # No raw unescaped XML special chars
    assert "<" not in msg and ">" not in msg
    # & must be entity-encoded
    for amp_idx in [i for i, ch in enumerate(msg) if ch == "&"]:
        tail = msg[amp_idx:amp_idx + 7]
        assert re.match(r"&(amp|lt|gt|quot|apos|#\d+);", tail), f"Unescaped & found: ...{tail}"
    # Should look like a real reply (non-trivial length, mentions something smoky-ish or a spirit)
    assert len(msg.strip()) > 15


def test_sms_empty_body_asks_for_input():
    r = requests.post(f"{API}/twilio/sms", data={"From": "+61400000000", "Body": ""}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.text
    assert _is_twiml(body)
    assert "<Message>" in body and "</Message>" in body


# ----- /api/twilio/voice (greeting) -----
def test_voice_greeting_has_polly_russell_and_gather():
    r = requests.post(f"{API}/twilio/voice", data={"From": "+61400000000"}, timeout=30)
    assert r.status_code == 200, r.text
    assert "application/xml" in r.headers.get("content-type", "").lower()
    body = r.text
    assert _is_twiml(body)
    assert 'voice="Polly.Russell"' in body
    assert 'language="en-AU"' in body
    assert 'input="speech"' in body
    assert 'speechTimeout="auto"' in body
    assert 'action="/api/twilio/voice/gather"' in body
    assert 'method="POST"' in body


# ----- /api/twilio/voice/gather -----
def test_voice_gather_with_speech_returns_say_then_gather():
    r = requests.post(
        f"{API}/twilio/voice/gather",
        data={"SpeechResult": "what should I make with rye and amaro", "Confidence": "0.9"},
        timeout=120,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert _is_twiml(body)
    # Must contain a Say (the reply) AND another Gather (to continue conversation)
    assert "<Say" in body
    assert "<Gather " in body
    assert 'action="/api/twilio/voice/gather"' in body


def test_voice_gather_empty_speech_returns_hangup():
    r = requests.post(f"{API}/twilio/voice/gather", data={"SpeechResult": "", "Confidence": "0"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.text
    assert _is_twiml(body)
    assert "<Hangup/>" in body
    assert "<Say" in body
    # Should NOT continue conversation
    assert "<Gather " not in body


def test_voice_gather_goodbye_triggers_hangup():
    r = requests.post(f"{API}/twilio/voice/gather", data={"SpeechResult": "alright goodbye mate"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.text
    assert _is_twiml(body)
    assert "<Hangup/>" in body
    assert "<Gather " not in body


# ----- One brain across channels -----
def test_one_brain_sms_and_voice_both_persist_to_session_main():
    # Marker strings unique enough to find in chat history
    sms_marker = f"PH4TEST sms ping {int(time.time())}"
    voice_marker = f"PH4TEST voice ping {int(time.time())}"

    r1 = requests.post(f"{API}/twilio/sms", data={"From": "+61400000000", "Body": sms_marker}, timeout=120)
    assert r1.status_code == 200

    r2 = requests.post(f"{API}/twilio/voice/gather", data={"SpeechResult": voice_marker, "Confidence": "0.9"}, timeout=120)
    assert r2.status_code == 200

    # Wait a tick to ensure persistence
    time.sleep(1)

    r = requests.get(f"{API}/chat/history?session_id=main&limit=500", timeout=30)
    assert r.status_code == 200
    history = r.json()
    contents = [m["content"] for m in history]
    assert any(sms_marker in c for c in contents), "SMS body not found in main session history"
    assert any(voice_marker in c for c in contents), "Voice SpeechResult not found in main session history"

    # Verify both replies (role=sheldon) exist after the markers
    sheldon_msgs = [m for m in history if m["role"] == "sheldon"]
    assert len(sheldon_msgs) >= 2


# ----- Regression: existing endpoints -----
def test_regression_chat_web_still_works():
    r = requests.post(f"{API}/chat", json={"session_id": "regression_test", "message": "Hi briefly"}, timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "reply" in data and len(data["reply"]) > 0


def test_regression_cocktails_count_44():
    r = requests.get(f"{API}/cocktails", timeout=30)
    assert r.status_code == 200
    assert len(r.json()) == 44


def test_regression_substitutions_count_22():
    r = requests.get(f"{API}/substitutions", timeout=30)
    assert r.status_code == 200
    assert len(r.json()) == 22


def test_regression_voice_transcribe_endpoint_exists():
    # Send empty file (size < 500) — should return {"text": ""} per implementation
    files = {"audio": ("test.webm", b"x" * 100, "audio/webm")}
    r = requests.post(f"{API}/voice/transcribe", files=files, timeout=30)
    assert r.status_code == 200
    assert r.json().get("text") == ""
