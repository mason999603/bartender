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

## Prioritized Backlog
### P0 (Phase 3 — Voice on Web)
- [ ] OpenAI Whisper STT for push-to-talk in browser
- [ ] OpenAI TTS or ElevenLabs for Sheldon's voice reply
- [ ] Web Audio activity indicators

### P1 (Phase 4 — Telephony)
- [ ] Twilio number → SMS chat with Sheldon
- [ ] Twilio Voice → realtime call (Media Streams + STT + TTS)

### P2 (Phase 5 — Raspberry Pi)
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
