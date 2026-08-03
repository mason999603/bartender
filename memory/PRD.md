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
- **Pi systemd unit fixed**: `/app/pi_client/systemd/russell.service` paths corrected — `WorkingDirectory=/opt/russell/pi_client`, venv path inside that dir, ExecStart uses the correct script location. Verified on hardware — Russell now auto-starts on Pi boot.
- **Custom wake-word infra**: new `/app/pi_client/keywords/` folder with a `.gitignore` keeping `.onnx` out of git, and a `README.md` walking through openWakeWord's Google Colab training notebook for a free custom "Hey Russell" model.
- **Tested**: iteration 8 — 8/8 backend pytest, 100% frontend Playwright.

### Phase 8 (2026-05-31) — Multi-provider LLM rotation + action parser hardening
- **OpenRouter was primary brain** with a multi-model rotation chain (deepseek-v4-flash → nvidia-nemotron-3-super-120b → moonshot-kimi-k2.6 → llama-3.3-70b → qwen3-next-80b → gemma-4-31b → gpt-oss-120b → glm-4.5-air). Each `:free` model has its own daily quota, so rotating across 8 effectively multiplies headroom. Groq 70B → 8B kept as deeper fallback when *all* OpenRouter models are throttled. Friendly 429 surfaced only when literally everything is exhausted.
- **System prompt slimmed** (saves ~3K tokens per request): substitutions only injected for currently 86'd ingredients (was injecting all 22 every time); memories/regulars capped at 15; chat history trimmed 20 → 12 messages.
- **Action parser hardened against dumber fallback models**:
  - Regex now tolerates `[russell_actions>` (square-open Markdown corruption) in addition to proper `<russell_actions>` tags — the 8B-class models routinely emit the malformed version, every save was silently failing.
  - `amount_ml` coercion handles placeholders (`"insert_amount"` → 0), strings with units (`"22.5 ml"` → 22.5), and nulls (→ 0) instead of throwing.
  - `set_inventory.in_stock` accepts `"true"`/`"yes"`/`1` as truthy strings.
  - Added explicit JSON-value rules to the actions system prompt forbidding placeholder strings.
- **Live on user's Pi (2026-05-31)** — Pi voice loop now hits OpenRouter via the cloud `/api/chat` endpoint, full pipeline still on the free stack.

### Phase 9 (2026-02) — Emergent AI migration + Perplexity + iOS PWA + Spotify
- **LLM/STT/TTS unified on Emergent Universal Key.** Claude Sonnet 4.6 (brain), Whisper-1 (STT), OpenAI TTS `onyx` (Russell's voice). OpenRouter/Groq rotation and Piper removed from active path.
- **Unhedged personality**: guardrails scrubbed from system prompt — blunt bartender voice.
- **Perplexity Sonar-Pro** wired in for live news / real-time facts. Lightweight classifier in `core/brain.py` routes news-y queries to `core/web_search.py`.
- **Spotify OAuth + playback control**: `core/spotify_client.py`, `routers/spotify_routes.py`. Currently-playing context injected into every chat prompt.
- **iOS PWA**: manifest + service-worker + Apple touch icons; installable to home screen.
- **Mobile keyboard UX**: `lib/keyboardViewport.js` + 100dvh layout — bottom nav auto-hides on keyboard open, horizontal scroll locked.
- **Telegram webhook**: cache/404 issue resolved; still active.

### Phase 10 (2026-02) — Russell's Studio (faceless AI video pipeline)
- **New page `/studio`** in the top nav.
- **Backend** at `/app/backend/routers/studio.py`:
  - Phase 10a — text: `POST /studio/ideas`, `POST /studio/script`, `GET/POST/DELETE /studio/scripts`.
  - Phase 10b — media: `POST /studio/jobs/hero-clip` (Sora 2 async), `POST /studio/jobs/image-card` (GPT-Image-1 sync), `POST /studio/jobs/voiceover` (OpenAI TTS onyx MP3), `POST /studio/jobs/assemble` (ffmpeg async), `GET /studio/jobs/{id}`, `GET /studio/jobs`, `GET /studio/media/{name}`.
- **Studio persona**: hook-first, opinion-forward. Sharp Aussie voice, no "hey guys welcome back" openings.
- **Video pipeline**: Sora 2 720x1280 hero clip → OpenAI onyx voiceover → optional GPT-Image-1 outro card → ffmpeg stitches into a 720x1280 H.264 MP4 with SRT-based caption overlay and a 2s outro tail. Voice duration drives final length.
- **SDK compatibility patch**: `OpenAIVideoGeneration.SIZES` in-memory whitelist extended to include the actual Sora 2 fast sizes (720x1280 / 1280x720) which the SDK version 0.1.2 missed.
- **Storage**: `/app/backend/generated/studio/` (env `STUDIO_MEDIA_DIR`). Jobs tracked in `db.studio_jobs`, scripts in `db.studio_scripts`.
- **ffmpeg installed system-wide** (5.1.9).
- **Frontend `/app/frontend/src/pages/StudioPage.jsx`**: 4-step flow — Topic → Ideas → Script (per platform, with vault save/load/delete) → Voiceover playback (Step 3) → Video Production (Step 4: Sora hero, save voiceover, optional outro card, assemble MP4 with caption).
- **Tested (iteration_9 + iteration_10)**: 100% backend + 100% frontend. Sora 4s portrait render ~60s; ffmpeg assembly ~5-10s.

### Phase 11 (2026-02) — YouTube auto-publish
- **New router `/app/backend/routers/youtube_routes.py`** + **client `/app/backend/core/youtube_client.py`** (mirrors the Spotify OAuth pattern used elsewhere).
- **Endpoints**: `GET /api/youtube/login`, `GET /api/youtube/callback`, `GET /api/youtube/status`, `POST /api/youtube/disconnect`, `POST /api/youtube/publish` (async job), `GET /api/youtube/publish/{id}`, `GET /api/youtube/publish` (list).
- **Auth**: Google OAuth 2.0 web-app flow, `youtube.upload` scope only. Refresh token persisted in Mongo `youtube_auth` (`_id="primary"`).
- **Publish flow**: takes a `final_*.mp4` filename from the studio media dir, streams via `MediaFileUpload` in 8MB resumable chunks, sets `snippet.title` (with auto `#Shorts` suffix if missing), `description`, `tags` (deduped, ≤12), `categoryId=22` (People & Blogs), `privacyStatus=public`. Progress logged every ~10%.
- **Frontend `YouTubePublisher` in `/app/frontend/src/pages/StudioPage.jsx`** appears after a final MP4 exists. Auto-generates title from idea title/hook, description from the SPOKEN SCRIPT + HASHTAGS sections + `#Shorts`, tags from HASHTAGS section. Shows connect state / channel avatar. Includes an inline 7-step Google Cloud setup helper for first-time users.
- **Env**: new `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REDIRECT_URI` in `backend/.env` (currently empty — user completes Google Cloud setup on their end).
- **Tested (iteration_11)**: 100% backend (7/7) + 100% frontend graceful-degradation without Google creds configured.

### Phase 12 (2026-02) — Autopilot (fully autonomous daily video pipeline)
- **User goal**: "make videos and release them automatically every day" with an Aussie bartender persona as a face. Zero-touch.
- **Locked-in defaults** (from user Q&A): 07:00 Sydney publish, 1 × 30-second Short per day, rugged Aussie bartender persona (mid-30s, black henley, dark tattoo sleeve, moody speakeasy).
- **New files**:
  - `/app/backend/core/persona.py` — persona character sheet + reference PNG rendered once via GPT-Image-1, cached at `MEDIA_DIR/persona.png`.
  - `/app/backend/core/topic_rotator.py` — 60-topic evergreen queue with cursor + user-added topics collection.
  - `/app/backend/core/autopilot.py` — `produce_and_publish()` — the full chain: topic → idea (Claude) → script (Claude) → voiceover (OpenAI TTS onyx) → Sora 2 hero (720×1280, 8s, with persona reference + neutral-prompt safety-retry) → ffmpeg assembly (looped hero + captions + voice) → YouTube upload if connected.
  - `/app/backend/core/scheduler.py` — APScheduler AsyncIOScheduler installing a daily CronTrigger from Mongo config. Reconfigures live when the user tweaks the schedule.
  - `/app/backend/routers/autopilot_routes.py` — status / config / run-now / runs / persona / topics endpoints.
- **Studio.py extension**: `hero-clip` job now accepts optional `image_filename` reference (Sora `image_path`) so any hero clip can use the persona for character consistency.
- **YouTube creds configured** in `backend/.env` — user has completed step 1-5 of Google Cloud setup. OAuth handshake (`/api/youtube/login`) not yet completed by user.
- **Frontend `AutopilotPanel`** at the top of Studio: giant ON/OFF toggle, next-post time in Sydney tz, run-now button, persona render card, YouTube connect card, latest-run + history grid.
- **End-to-end verified (iteration_12 + live test)**: Autopilot run produced a full 720×1280 H.264 24.8s MP4 (4.8MB) autonomously in ~2 minutes. Runs land at `ready-not-published` (queueing MP4s locally until user completes YouTube OAuth) or `published` once YouTube is connected.

### Phase 13 (2026-02) — Reliability + Speed + Calendar
- **Pi 24/7 hardening**: systemd `Restart=always`, watchdog `WatchdogSec=120` with `sd_notify` pings from the wake loop every 30s, 6-hour cron misfire grace, exponential backoff on network drops (2s→60s), silent 429 handling, USB mic auto re-scan on stream error, `mpg123` streaming MP3 playback, systemd Type=notify integration via `systemd-python`.
- **Autopilot startup catchup**: `db.autopilot_state.last_run_date` (Sydney tz) as idempotency key; on backend restart, if today's slot passed and no run happened, fire a catchup. Fixed the "07:00 didn't post because container recycled" bug from real usage.
- **Auto-install ffmpeg on backend startup** — Emergent preview containers cycle and wipe apt packages; startup hook re-installs so Studio+Autopilot MP4 assembly always works.
- **Voice-mode speedup**: `voice_mode: true` on chat POSTs (Pi always sends this) swaps Claude Sonnet → Claude Haiku (~3× lower latency), injects a strict brevity hint at END of prompt (spoken 1-2 sentences, no markdown), MP3 format on the wire (10× smaller than WAV), streamed via `mpg123` stdin for ~200ms first-sound. VAD silence 1.4s → 0.7s. End-to-end Pi latency ~9s → ~2s. `/api/voice/speak` now uses `StreamingResponse`.
- **News classifier broadened** (20+ conversational triggers) + system-prompt rule so Russell never claims he can't access the internet.

### Phase 14 (2026-02) — iCal / iCloud calendar integration
- **New files**:
  - `/app/backend/core/calendar_client.py` — fetches iCloud published subscription URLs (webcal:// or https://), parses via `icalendar`, expands RRULE recurrences up to 14 days, stores in `db.calendar_events`.
  - `/app/backend/core/calendar_analyzer.py` — importance ranker (1-10) with categories: shift, travel_vacation, ceremony, paid_ticket, medical, birthday, appointment, personal, meeting, routine, reminder, ordinary. Combines keyword taxonomy, duration heuristics, venue hints, and `is_work` calendar flag.
  - `/app/backend/routers/calendar_routes.py` — sources CRUD, `POST /refresh`, `GET /upcoming?days=N`, `GET /briefing`.
- **Brain integration**: `_needs_calendar_context()` classifier fires on schedule/roster/day-of-week keywords; when triggered, injects the ranked briefing block into the system prompt.
- **Background refresh**: APScheduler `IntervalTrigger(minutes=15)` job re-fetches all sources.
- **Frontend `/calendar` page** (new tab): sources list with work/home icons + status, add-calendar form with inline setup help, horizon tabs (Today/This week/2 weeks/This month), grouped-by-day event list with priority badges + colour bars.
- **Live test**: User's two iCloud calendars connected. Hapkido training correctly categorized as `3/10 routine`. Voice-mode chat "run down my week" returned two spoken sentences with the events.


### Phase 8 (2026-02) — Voice-Controlled Alarms + CalDAV Write
- **Alarm system** (`/app/backend/core/alarms.py` + `/app/backend/routers/alarm_routes.py`): Russell schedules audio alarms that fire on the Pi speaker. Full CRUD (`POST /api/alarms`, `GET /api/alarms`, `GET /api/alarms/pending`, `POST /api/alarms/{id}/fired`, `POST /api/alarms/silence`, `DELETE /api/alarms/{id}`). Supports single-shot AND `repeat_daily=true` (silence pushes fire_at +24h instead of deactivating).
- **Pi-side alarm watcher** (`/app/pi_client/alarm_watcher.py`): background thread polls `/api/alarms/pending` every 15s, plays the spoken message via CloudTTS, ducks the wake-word listener, and stops when the alarm's `active` flips false (via voice-triggered `silence_alarm` chat action).
- **LLM actions** (`brain.py` + `actions.py`): `set_alarm` (Russell computes UTC ISO from natural-language time using injected NOW block for Australia/Sydney tz), `silence_alarm` (triggered by "that's enough" / "shut up" / "quiet russell" etc.), and `add_event` (writes to iCloud CalDAV).
- **CalDAV write client** (`/app/backend/core/caldav_write.py`): Apple iCloud CalDAV via `caldav` + `icalendar` libs. `verify_credentials()` validates against iCloud BEFORE persisting, so a bad app-specific password never leaves the app in a broken configured state. `clear_config()` supports full disconnect.
- **Calendar routes**: `GET/POST/DELETE /api/calendar/write/config`, `GET /api/calendar/write/calendars`, `POST /api/calendar/write/event`.
- **Frontend `/calendar` page**: new "Russell can add events" section at top with Set up/Update/Disconnect controls, verify-then-save flow, inline appleid.apple.com help link.
- **Action failure relay in `brain.py`**: if any action fails (e.g. add_event when CalDAV unconfigured), Russell's reply is rewritten to speak the honest error instead of hallucinating a success. Voice mode gets a terse one-liner; web mode gets full detail.
- **Tested** (iteration_13): backend 13/13 pass, frontend 100%. One bug found + fixed: config was persisted before verification (fixed to verify-first, plus added DELETE /write/config + Disconnect button).

## Prioritized Backlog
### P1 — Next up
- [ ] Complete YouTube OAuth handshake (open `/api/youtube/login` from the app, log in, authorise) so Autopilot lands `published` instead of `ready-not-published`.
- [ ] Multi-clip storyboard (2-3 Sora clips per video, chained by ffmpeg).
- [ ] TikTok publish (requires TikTok Developer app + Content Posting API approval — user needs to apply first).
- [ ] Verify Spotify OAuth completed by the user (was authorised in-session but no confirmation).
- [ ] ElevenLabs Aussie voice option (currently OpenAI 'onyx' American).
- [ ] Train custom "Hey Russell" wake word via openWakeWord Colab (instructions in `/app/pi_client/keywords/README.md`) — fully on user.

### P2 — Polish
- [ ] Strip test-time deps from `/app/backend/requirements.txt` (deferred — pip resolver conflict between emergentintegrations and litellm needs untangling first).
- [ ] Dedupe duplicate seeded cocktails in the DB (pre-existing data quirk: "Margarita" and "Apple Pie Martini" appear twice).
- [ ] Refactor `/admin/*` cocktail routes onto a sub-`APIRouter(prefix="/admin")` for tidier routing (currently relies on declaration order).
- [ ] Add visible "Russell saved this for you" toast on the web Chat page when an action lands (closes the loop on action transparency).
- [ ] Show currently-active LLM provider/model in a status pill (so user knows when Russell's degraded to a smaller model).

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
