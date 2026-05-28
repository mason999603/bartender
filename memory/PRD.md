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

## What's Been Implemented (2026-01)
- Chat with Claude Sonnet 4.5, transcript-prefix history, persisted in Mongo (`chat_messages`).
- Seeded knowledge: **22 classic cocktails**, **61 ingredients with flavour profiles**, **14 clash rules** (including the Baileys + citrus curdle warning).
- Tools API: `/api/tools/compatibility`, `/api/tools/abv`, `/api/tools/batch`, `/api/tools/cost`, `/api/cocktails/search-by-ingredients`.
- CRUD for cocktails (custom specs), regulars, memory, inventory.
- Frontend: 6 pages with full data-testid coverage; dark speakeasy theme; phosphor icons; toast notifications.
- Graceful 429 message when Emergent LLM budget exceeded.
- Tested by testing_agent_v3 (iteration_1): backend 17/19 pass (2 LLM-budget infra), frontend 100%.

## Prioritized Backlog
### P0 (Phase 2 — Cocktail superpowers polish)
- [ ] Add 30+ more classics & modern classics to the library
- [ ] Flavour-profile search ("smoky + citrus, not too sweet")
- [ ] Sheldon proactive substitution suggestions when an ingredient is 86'd

### P1 (Phase 3 — Voice on Web)
- [ ] OpenAI Whisper STT for push-to-talk in browser
- [ ] OpenAI TTS or ElevenLabs for Sheldon's voice reply
- [ ] Web Audio activity indicators

### P2 (Phase 4 — Telephony)
- [ ] Twilio number → SMS chat with Sheldon
- [ ] Twilio Voice → realtime call (Media Streams + STT + TTS)

### P3 (Phase 5 — Raspberry Pi)
- [ ] Export to GitHub
- [ ] Pi client: wake word (Porcupine "Hey Sheldon") → record → hit cloud Brain API → TTS playback
- [ ] Optional: fully local mode via Ollama + Llama 3 for offline ops

## Known Constraints
- Emergent Universal Key has a per-request budget cap; long chats can hit it. Topping up balance or using a personal Anthropic key removes the cap.

## File Map
- `/app/backend/server.py` — all API routes
- `/app/backend/seed_data.py` — initial cocktails/ingredients/clash rules
- `/app/frontend/src/App.js` — routes
- `/app/frontend/src/pages/*` — Chat, Cocktails, Tools, Inventory, Regulars, Memory
- `/app/frontend/src/components/Topbar.jsx`, `PageHeader.jsx`
- `/app/frontend/src/lib/api.js`
