# Russell on the Raspberry Pi 🍸

A standalone Python client that turns a Raspberry Pi 4 (or 5) into Russell — your
voice-activated AI bartender. Wake-word triggered. Cloud brain. Local Aussie voice.

```
You: "Hey Russell."
Russell: "Yeah?"
You: "What's a good drink for a rainy Friday?"
Russell: "Reckon a Hot Toddy — bourbon, honey, lemon, hot water. Warming as anything. Want the spec?"
```

---

## What runs where

| Component | Location | Why |
|---|---|---|
| Wake word detection | **Local (Pi)** | Always-on, low-power, no internet needed |
| Voice activity / recording | **Local (Pi)** | Streams mic input directly |
| Speech-to-text (Whisper) | **Cloud (your Emergent backend)** | Quality + no need for a beefy Pi |
| LLM brain (Claude 4.5) | **Cloud (your Emergent backend)** | Same one as web/SMS/Telegram — one memory |
| Text-to-speech (Piper) | **Local (Pi)** | Free, offline, low-latency, Aussie voice |

Session id is hard-coded to `main` so all four channels (Web / SMS / Telegram / Pi) share Russell's memory + chat history.

---

## Hardware

You'll need:
- **Raspberry Pi 4 (4GB+) or Pi 5** with Raspberry Pi OS Lite 64-bit (Bookworm)
- **USB microphone** — you've got the Blue Yeti, which is great
- **Speaker** — any 3.5mm or Bluetooth speaker works
- A wired ethernet or solid wifi connection (the brain lives in the cloud)

---

## One-time setup

### 1. Get a Picovoice Access Key (free)
1. Sign up at https://console.picovoice.ai/ (free personal tier)
2. Copy your **Access Key** from the dashboard

### 2. Train a custom "Hey Russell" wake word (free)
1. In the Picovoice console → **Porcupine → Train a Wake Word**
2. Phrase: `Hey Russell`
3. Platform: **Raspberry Pi (arm64)** — important!
4. Click **Train** and wait ~30 seconds
5. Download the `.ppn` file → save it to `pi_client/keywords/hey_russell_raspberry-pi.ppn`

*If you skip this step, the client falls back to the built-in word "computer" for testing.*

### 3. Download a Piper voice
Piper doesn't ship a true Aussie voice (yet), so we use **`en_GB/northern_english_male`** — gruff working-class English bloke, closest fit to Russell's vibe and miles better than any American option. Two files, ~63MB:

```bash
mkdir -p voices
cd voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json
cd ..
```

### 4. Install system audio deps on the Pi
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip libportaudio2 portaudio19-dev libsndfile1
```

### 5. Set up the Python environment
```bash
cd /opt/russell    # or wherever you cloned the pi_client folder
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements_pi.txt
```

### 6. Configure your .env
```bash
cp .env.example .env
nano .env
```

Fill in (at minimum):
- `RUSSELL_BACKEND_URL` — your Emergent backend URL (no trailing slash). Already pre-filled.
- `PORCUPINE_ACCESS_KEY` — from step 1.
- `PORCUPINE_KEYWORD_PATH` — path to the .ppn file from step 2.
- `PIPER_VOICE_PATH` — path to the .onnx file from step 3.

### 7. Pick your audio devices (optional but recommended)
List devices to find your Yeti's index and your speaker's:
```bash
python russell_pi_client.py --list-audio
```

Set the indices in `.env`:
```
INPUT_DEVICE_INDEX=2
OUTPUT_DEVICE_INDEX=1
```

---

## Run it

```bash
./run.sh
```

You should hear: **"G'day. Russell standing by."**

Now say **"Hey Russell"** — wait for the (silent) ack — then ask anything.

---

## Autostart on boot (systemd)

```bash
sudo cp systemd/russell.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable russell.service
sudo systemctl start russell.service
```

Logs:
```bash
sudo journalctl -u russell -f
```

---

## Bluetooth speaker pairing (quick reference)

```bash
bluetoothctl
scan on
# wait for your speaker
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
```

Then test playback:
```bash
speaker-test -t wav -c 2
```

If Russell goes silent after the BT speaker disconnects, the systemd unit will restart automatically.

---

## Tuning tips

- **Wake word fires too easily / not enough?** Open the Picovoice console and lower/raise the sensitivity, retrain, re-download the .ppn.
- **Russell cuts you off mid-sentence?** Increase `VAD_SILENCE_SECONDS` (try 2.0).
- **Russell records ambient noise as if you spoke?** Raise `VAD_SILENCE_THRESHOLD` (try 0.025).
- **First reply takes 5+ seconds?** Normal on cold start — Claude + Piper warm up. Subsequent replies are fast.

---

## Going fully offline (future work — Phase 6+)

To take Russell off the grid entirely, you'd swap:
- **Whisper STT** → local `faster-whisper` (small.en model, runs on Pi 5 acceptably)
- **Claude brain** → local `Ollama` with `llama3.2:3b` or `gemma2:2b`

Persona prompt and cocktail/collection context can be ported directly. The Piper TTS is already local. We can wire this up when you've got the hardware in front of you.

---

## Architecture diagram

```
                  ┌────────────────────────────────────────────────────────┐
                  │ Cloud (this Emergent app)                              │
                  │                                                        │
                  │  POST /api/voice/transcribe ──┐                        │
                  │                                ↓                       │
                  │  POST /api/chat ── Claude 4.5 + memory + collections   │
                  │                                                        │
                  └────────────┬───────────────────────────────────────────┘
                               ↑↓ HTTPS
┌──────────────────────────────┴─────────────────────────────────────────────┐
│ Raspberry Pi                                                               │
│                                                                            │
│  Blue Yeti ─→ sounddevice ─→ Porcupine (wake word) ─→ VAD recorder ────┐  │
│                                                                          │  │
│  Speaker  ←─ sounddevice ←─ Piper TTS (en_AU) ←─── reply text ←─────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```
