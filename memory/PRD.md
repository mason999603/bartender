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

## Prioritized Backlog
### P0 (Phase 5 — Raspberry Pi)
- [ ] Pi client: wake word (Porcupine "Hey Sheldon") → record → hit cloud Brain API → audio playback
- [ ] systemd service for autostart
- [ ] User has Yeti mic + Bluetooth speaker (via AUX) + NVMe SSD already; needs Pi 4 or Pi 5
- [ ] Optional later: fully local mode (Llama 3.2 3B via Ollama, faster-whisper, Piper TTS en-AU)

### Notes from chat
- User's hardware on hand: Blue Yeti USB mic, Bluetooth speaker (AUX-capable), NVMe SSD.
- Recommended Pi 4 8GB build (cheaper, works fine as cloud-thin-client): ~A$165 total with USB 3.0 NVMe enclosure.
- Recommended Pi 5 build (future-proof for offline mode + Hailo AI HAT path): ~A$225-260.

## Known Constraints
- Emergent Universal Key has a per-request budget cap; long chats can hit it. Topping up balance or using a personal Anthropic key removes the cap.

## File Map
- `/app/backend/server.py` — all API routes
- `/app/backend/seed_data.py` — initial cocktails/ingredients/clash rules
- `/app/frontend/src/App.js` — routes
- `/app/frontend/src/pages/*` — Chat, Cocktails, Tools, Inventory, Regulars, Memory
- `/app/frontend/src/components/Topbar.jsx`, `PageHeader.jsx`
- `/app/frontend/src/lib/api.js`
ib/api.js`
