# Sheldon — AI Bartender (PRD)

## Original Problem Statement
User started asking "can you give me your source code so I can build an offline version of the software" — conversation evolved into building a personal AI assistant named **Sheldon** for a bartender/mixologist. Long-term vision: deploy to a Raspberry Pi with mic + speaker + internet, accept voice + SMS + phone calls, one continuous brain.

## Persona
- Single user: a working bartender / mixologist.
- Voice/style requested: "witty, dry young Australian bartender, an up and commer but down to earth."

## Architecture (current — Phase 1)
- **Backend**: FastAPI + MongoDB + emergentintegrations (Claude Sonnet 4.5 via Emergent Universal Key).
- **Frontend**: React 19 + TailwindCSS + Phosphor Icons + Sonner (toasts). Dark "speakeasy" theme (charcoal #0A0A0C + amber #E09132 + Cormorant Garamond/Manrope).
- **Routes**: `/` (Chat), `/cocktails` (Library), `/tools` (5 tools), `/inventory`, `/regulars`, `/memory`.

## Core Requirements (locked)
1. Claude Sonnet 4.5 brain.
2. Persistent memory across sessions (MongoDB).
3. Full bartender toolkit: clash check, what-can-I-make, ABV, batching, cost, library, regulars, custom specs, inventory.
4. Sheldon embeds live context (memories + regulars + inventory + custom specs) in every system prompt.
5. Aussie personality, tight responses (bartender-style).

## What's Been Implemented
### Phase 1 (2026-01) — MVP
- Chat with Claude Sonnet 4.5, transcript-prefix history, persisted in Mongo (`chat_messages`).
- Seeded knowledge: 22 cocktails, 61 ingredients, 14 clash rules.
- Tools API: `/api/tools/compatibility`, `/api/tools/abv`, `/api/tools/batch`, `/api/tools/cost`, `/api/cocktails/search-by-ingredients`.
- CRUD for cocktails (custom specs), regulars, memory, inventory.
- Frontend: 6 pages, dark speakeasy theme, full `data-testid` coverage.
- Graceful 429 message when Emergent LLM budget exceeded.
- Tested (iteration_1): backend 17/19, frontend 100%.

### Phase 2 (2026-01) — Cocktail Superpowers
- **+22 cocktails** (now 44 total): Mai Tai, Jungle Bird, Sidecar, Vieux Carré, Naked & Famous, Oaxaca Old Fashioned, Pisco Sour, Caipirinha, Corpse Reviver #2, Garibaldi, Hugo Spritz, Americano, White Russian, Paloma, Moscow Mule, Mint Julep, Hanky Panky, Tom Collins, Bee's Knees, Hemingway Daiquiri, Piña Colada, Bramble.
- **+16 ingredients** (Lillet Blanc, Cachaça, Crème de Violette, Amaro Nonino, Suze, etc.).
- **Substitutions engine**: 22 ingredients with curated swap notes. New endpoints `/api/substitutions` and `/api/substitutions/{name}`.
- **Flavour-profile search**: `/api/cocktails/by-flavour` with include/exclude lists; ranked by include-match count.
- **Sheldon's brain upgraded**: system prompt now embeds the full substitutions cheat-sheet AND a separate "currently 86'd" inventory block. Sheldon proactively suggests swaps when a recipe needs something out of stock (verified: Cointreau-86 → Margarita reply mentions Grand Marnier / Triple Sec swap automatically).
- **Seed strategy**: switched to **upsert-by-name** so new data lands cleanly without wiping custom specs across restarts.
- **Library UI**: 18-chip flavour filter with 3-state cycle (off → include → exclude). Name search auto-disables while flavour filter is active.
- **Cocktail modal UI**: when an in-recipe ingredient is 86'd, it renders with strikethrough + "86'd" badge + an inline "Sheldon suggests" panel listing alternatives from the substitutions table.
- **Tools page**: new **Subs** tab — type or click any of 22 quick-browse tags to see swaps with notes.
- Tested (iteration_2): backend 29/29 (100%), frontend 100%.

### Phase 3 (2026-01) — Voice on Web
- **STT**: `/api/voice/transcribe` endpoint using `OpenAISpeechToText` (whisper-1) via Emergent Universal Key. Accepts multipart audio (webm/mp4/wav/ogg), handles missing filename via content-type detection, graceful for silence (<500B) and oversize (>25MB).
- **TTS**: free browser `speechSynthesis` (no API costs). Auto-picks `en-AU` voice when available. Voice picker with live preview in settings.
- **Two input modes** (toggle in settings, persisted in localStorage):
  - Push-to-talk: hold mic button OR press spacebar (when not in a text field).
  - Hands-free / continuous: amplitude-based VAD; stops on ~1.2s silence, auto-restarts.
- Live amplitude ring, transcribing spinner, stop-speaking button.
- Transcribed text auto-sends. LocalStorage keys: `sheldon-mode`, `sheldon-tts`, `sheldon-voice`.
- Tested (iteration_3): backend 9/9, frontend 11/11 — 100%.

### Phase 4 (2026-01) — Telephony (Twilio SMS + Voice)
- Refactored chat into `chat_with_sheldon(session_id, text, channel)` helper. SMS replies capped ~320 chars (no markdown); voice replies capped ~35 words.
- `POST /api/twilio/sms` — inbound SMS webhook returning TwiML `<Message>`.
- `POST /api/twilio/voice` — inbound voice greeting with `<Say voice="Polly.Russell" language="en-AU">` + `<Gather input="speech" speechTimeout="auto" language="en-AU">`.
- `POST /api/twilio/voice/gather` — continuation; speaks reply + opens next Gather. Hang-up triggers on "bye/goodbye/cheers mate".
- `GET /api/twilio/status` — config check.
- **One brain everywhere**: all channels share `session_id="main"` — web, SMS, and voice memory flow together.
- New Phone page (`/phone`) — status card, copyable webhook URLs, 4-step setup walkthrough with `.env` snippet.
- X-Twilio-Signature validation gated on TWILIO_AUTH_TOKEN being set (auto-skipped during dev setup).
- Tested (iteration_4): 12/12 backend, all frontend checks — 100%.

### Phase 4.5 (2026-01) — Companion + Rename + Collections
- **Rename Sheldon → Russell** across all 12 source files (system prompts, UI strings, voice greetings, TwiML messages, localStorage keys). DB migration rewrites both `role` field AND inline mentions of "Sheldon" in chat_messages.content for clean history.
- **Companion grounding (`/app/backend/companion.py`)**: every chat turn now silently includes a real-time context block: current local time + day + time-of-day phase (morning/midday/etc.) + user's location + live weather (when relevant).
- **Free weather**: Open-Meteo (primary) + **wttr.in fallback** (no API key, free, no quota fights). 10-minute in-memory cache to be polite to the providers.
- **Persona upgrade**: Russell is now "mate first, bartender second" — he engages with random non-cocktail questions naturally (existentialism, weather, life advice, music recs).
- **New `/api/companion/weather` and `/api/companion/context` endpoints** for direct UI access and debugging.
- **Collections feature**: Russell can now remember the user's record collection, books, movies, playlists, or any list-style data.
  - Models: `Collection` with `items` array (title, subtitle, tags, notes, 1-5 star rating).
  - CRUD: `/api/collections`, `/api/collections/{id}/items`.
  - Collections are injected into Russell's system prompt — verified that asking "what should I play tonight" surfaces titles by name from the saved Records collection with personal commentary ("Side three into four is an absolute journey…").
  - New `/collections` page (nav label: **Crates**) with preset starters (Records/Books/Movies/Playlists), custom icon picker, item detail modal with star ratings.
- Tested (iteration_5): backend 21/21, frontend full coverage — 100%. One data-hygiene issue (legacy "Sheldon" in historical message content) was caught and patched same iteration via the extended migration.

### Phase 6 (2026-02) — Backend Refactor + Reverse Mood Pairing
- **Refactor `server.py`**: was a 1100-line monolith — now a 153-line shell. Feature code split into:
  - `core/config.py`, `core/db.py`, `core/models.py`, `core/brain.py` (chat orchestration, system prompt, clash + record-mention detection)
  - `routers/{chat,voice,companion,twilio_routes,cocktails,substitutions,ingredients,tools,regulars,memory,inventory,collections}.py`
  - All endpoints under `/api` preserved exactly. Zero behavioural change verified.
- **Reverse mood pairing (record → cocktail)**: new `_detect_record_mention()` in `core/brain.py` scans the user's message for (a) a music-intent keyword (play/spin/put on/listening to/throw on/queue up/vinyl/record/lp/album/needle/turntable) AND (b) any record title (or its artist or album half) literally present in the user's Records collection. On a hit, injects a "REVERSE MOOD PAIRING TRIGGER" block into the system prompt with the record's tags, prompting Russell to suggest a cocktail matching that record's vibe in one casual line.
- **Record context enrichment**: system prompt now embeds the per-record mood/genre tags in brackets so Russell has them as pairing cues.
- **Chat persistence fix carried over**: messages persisted atomically AFTER successful LLM call — no orphan user msgs on errors.
- Tested (iteration_6): backend 26/26 (100%). Verified pairing fires for "spun up Rastaman Vibrations" (reggae match) and stays quiet for non-music input or records not in the collection (no fabrication).

### Phase 6.5 (2026-02) — Telegram Bot integration
- **Channel #4**: Russell is now reachable via Telegram in addition to Web, SMS, and Voice. Free forever, no card, no phone number.
- New `/app/backend/routers/telegram_routes.py`:
  - `POST /api/telegram/webhook` — receives updates from Telegram, verifies `X-Telegram-Bot-Api-Secret-Token` header, routes text → `chat_with_russell(channel="telegram")` → `sendMessage`.
  - `GET /api/telegram/status` — live bot info + webhook status (no secrets exposed).
  - `POST /api/telegram/setup` — registers the webhook with Telegram (auto-generates a secret if missing) using the public app URL.
  - `POST /api/telegram/teardown` — unregisters the webhook.
  - Commands handled: `/start`, `/help`, `/whoami` (returns chat_id for lockdown).
  - Optional allowlist via `TELEGRAM_ALLOWED_CHAT_IDS` env var so the bot can be locked to specific personal chats.
- **Brain channel**: new `channel="telegram"` instructs Russell to output plain text (no markdown asterisks/headers) — Telegram's MarkdownV2 escaping is painful, plain text is reliable.
- **Frontend**: Phone page renamed to "Channels", new Telegram card + 3-step setup wizard (Create with BotFather → Drop token in .env → Register webhook button). One-click register copies the auto-generated webhook secret to clipboard.
- Verified end-to-end via in-process ASGI test: `/start` → friendly intro; "Negroni spec" → Russell returns clean plain-text spec; bad secret → 403; `/whoami` → echoes chat_id.

### Phase 5 (2026-02) — Raspberry Pi voice client
- **Wake-word triggered Pi client** living at `/app/pi_client/`. Always-on, voice in the room.
- **Files**:
  - `russell_pi_client.py` — main loop (wake → record → STT → chat → TTS → repeat). Uses `pvporcupine` (custom "Hey Russell" .ppn from Picovoice console), `sounddevice` for mic/speaker I/O, the existing cloud `/api/voice/transcribe` for Whisper STT, `/api/chat` for the Claude brain, and local Piper for TTS (Aussie southern english male voice, offline).
  - `audio_io.py` — VAD-bounded recording + WAV packaging + playback helpers.
  - `tts_piper.py` — Piper voice wrapper (lazy-loaded; reused across syntheses).
  - `requirements_pi.txt` — Pi-specific deps (requests, sounddevice, pvporcupine, piper-tts, numpy, soundfile, python-dotenv).
  - `.env.example` — config template with all knobs (backend URL, Porcupine key + .ppn path, audio device indices, VAD thresholds, voice path).
  - `systemd/russell.service` — autostart unit so Russell boots with the Pi.
  - `run.sh` — convenience launcher (assumes ./venv).
  - `README.md` — full setup walkthrough: Picovoice account → wake-word training → voice download → apt deps → venv → .env → run + systemd. Includes BT speaker pairing tips, VAD tuning, and a "going fully offline" roadmap.
- **Channels page UI** updated with a new "Raspberry Pi — voice in the room" section with the 4-step setup distilled (links to Picovoice + HuggingFace, code blocks for venv setup and systemd install).
- **One brain across all channels**: session_id="main" — Russell remembers what you told him on Telegram while you're standing in the kitchen.
- Files compile cleanly; runtime test must happen on the Pi hardware itself (server doesn't have audio devices or wake-word libs).

### Phase 6 (2026-02) — Free stack migration + Pi hardware validated
- **Cloud brain switched from Claude (Emergent key) to Groq Llama 3.3 70B Versatile.** Same `/api/chat` contract — no frontend changes needed.
- **STT switched from OpenAI Whisper to Groq Whisper Large V3.** Same `/api/voice/transcribe` contract.
- **Pi-side TTS reverted from cloud OpenAI TTS back to local Piper** (Aussie male voice, `en_GB-alan-medium.onnx`) piped through `aplay` to bypass ALSA channel-count quirks. Zero per-request cost.
- **Picovoice Porcupine replaced with openWakeWord** (fully free, ONNX, on-device). Currently using pre-trained `hey_jarvis` model — custom "Hey Russell" .onnx training instructions live at `/app/pi_client/keywords/README.md`.
- **Blue Yeti / ALSA robustness**: `find_working_input_device()` in `audio_io.py` auto-scans every input device on startup. Survives the USB mic re-enumerating to a different ALSA index between reboots.
- **Verified live on hardware (2026-05-31)**: Full pipeline working end-to-end — wake fires on "Hey Jarvis", Groq STT transcribes accurately, Llama 3.3 70B replies in-character, Piper speaks the reply through the speaker. Russell is officially alive on free infra.

### Phase 7 (2026-05-31) — Service Mode + Restore Seeds + Pi infra polish
- **Service Mode UI toggle**: new `ServiceModeContext` provider + pill button in Topbar. Toggles `service-mode` class on `<html>`, persisted to localStorage. Bumps base font-size to 19px and scales nav/inputs/buttons/cards/badges for behind-the-bar glance-ability. Subtle amber stripe on the topbar reminds you it's on.
- **Restore deleted seeded recipes**: two new admin endpoints — `GET /api/cocktails/admin/deleted-seeds` and `POST /api/cocktails/admin/restore-seeds` (accepts `{"names": ["Margarita"]}` or `{"names": ["*"]}` for everything). Library page shows a "Restore (N)" badge only when tombstones exist; modal lists each one with per-row + restore-all buttons.
- **Pi systemd unit fixed**: `/app/pi_client/systemd/russell.service` paths corrected — `WorkingDirectory=/opt/russell/pi_client`, venv path inside that dir, ExecStart uses the correct script location. Ready to copy into `/etc/systemd/system/` for boot-time autostart.
- **Custom wake-word infra**: new `/app/pi_client/keywords/` folder with a `.gitignore` keeping `.onnx` out of git, and a `README.md` walking through openWakeWord's Google Colab training notebook for a free custom "Hey Russell" model.
- **Tested**: iteration 8 — 8/8 backend pytest, 100% frontend Playwright (toggle persistence, restore modal end-to-end, regressions on /api/chat and /api/cocktails CRUD).

## Prioritized Backlog
### P1 — Next up
- [ ] **Train custom "Hey Russell" wake word** via openWakeWord Colab (instructions in `/app/pi_client/keywords/README.md`) — fully on user.
- [ ] **Install systemd autostart on the Pi**: `sudo cp /opt/russell/pi_client/systemd/russell.service /etc/systemd/system/ && sudo systemctl enable --now russell` — fully on user.

### P2 — Polish
- [ ] Strip test-time deps from `/app/backend/requirements.txt` (deferred — pip resolver conflict between emergentintegrations and litellm needs untangling first).
- [ ] Dedupe duplicate seeded cocktails in the DB (pre-existing data quirk: "Margarita" and "Apple Pie Martini" appear twice).
- [ ] Refactor `/admin/*` cocktail routes onto a sub-`APIRouter(prefix="/admin")` for tidier routing (currently relies on declaration order).

### Notes from chat
- User's hardware on hand: Blue Yeti USB mic, Bluetooth speaker (AUX-capable), NVMe SSD.
- Recommended Pi 4 8GB build (cheaper, works fine as cloud-thin-client): ~A$165 total with USB 3.0 NVMe enclosure.
- Recommended Pi 5 build (future-proof for offline mode + Hailo AI HAT path): ~A$225-260.

## Known Constraints
- Emergent Universal Key has a per-request budget cap; long chats can hit it. Topping up balance or using a personal Anthropic key removes the cap.

## File Map (current — post Phase 6 refactor)
- `/app/backend/server.py` — thin app shell (lifecycle + CORS + router mounting)
- `/app/backend/core/{config,db,models,brain}.py` — shared infra
- `/app/backend/routers/*.py` — one file per feature area
- `/app/backend/companion.py` — weather/time grounding helpers
- `/app/backend/seed_data.py` — initial cocktails/ingredients/clash rules
- `/app/frontend/src/App.js` — routes
- `/app/frontend/src/pages/*` — Chat, Cocktails, Tools, Inventory, Regulars, Memory, Phone, Collections
- `/app/frontend/src/components/Topbar.jsx`, `PageHeader.jsx`, `VoiceControls.jsx`
- `/app/frontend/src/lib/api.js`
