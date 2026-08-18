# The Terrible Turtle Oracle — App Design

An interactive oracle that runs **fully offline in the shell** (no internet on playa). Someone asks a question aloud; the Turtle draws three cards along the World Tree and weaves them into one reading plus one real adventure into the burn.

## Flow
```
voice (or typed) question
   → transcribe (local Whisper; text-input fallback)
   → SELECT: pick 1 Root + 1 Trunk + 1 Branch card resonant to the question
   → WEAVE: one reading across the three (face / stand / reach) + ONE adventure tonight
   → reveal the three cards (woodcut art) + text
   → (optional) speak it back in the Turtle's slow voice (local TTS)
```

## Hard constraint: offline on playa
Everything self-contained on one machine in the camp. No network calls at read-time. Live 2026 event data (if used) is a static snapshot loaded before leaving.

## Intelligence: graceful degradation (3 tiers)
1. **A real LLM** (best) — either backend, same interface, chosen by `ORACLE_LLM_BACKEND=ollama|cloud|auto` (default `auto`: cloud if an API key is in the environment, else Ollama). Does the woven reading, the echoes, the refine and the seal. The reading is the magic; a real model makes it sing.
   - **Ollama** on localhost — the playa instance. Model set by `ORACLE_MODEL` (e.g. `qwen2.5`, `gemma4:e2b`), host by `OLLAMA_HOST`. No internet, no bill.
   - **Cloud** — any OpenAI-compatible `/chat/completions` host, for the public instance where there is no GPU to lean on. Key from `ORACLE_CLOUD_KEY` (or `GROQ_API_KEY` / `OPENAI_API_KEY`); `ORACLE_CLOUD_BASE` and `ORACLE_CLOUD_MODEL` default to Groq `openai/gpt-oss-20b`. **No key → `available()` is False and the séance runs on templates**, exactly as a dead Ollama does; the key is only ever read from the environment, never committed.
2. **Deterministic fallback** (always works) — if no LLM: keyword-resonance card selection + a templated weave stitched from each card's own Reading and Turtle Dare. Less fluid, never fails, no dependencies.
3. Transcription: local Whisper (`faster-whisper` / `whisper.cpp`) if present; otherwise the UI takes typed input.

## Modules (`app/oracle/`)
- `deck.py` — load `data/cards.json`; group by realm; the Tree spread (1 Root / 1 Trunk / 1 Branch; a Shell card may substitute into any slot as "the axis speaks").
- `select.py` — choose the resonant three (LLM pick → keyword score → random).
- `weave.py` — build the reading + adventure (LLM → template fallback).
- `llm.py` — both adapters over stdlib `urllib`, one interface (`available()` / `generate()` / `model`); `make_llm()` picks. `LLM` probes Ollama's `/api/tags`; `CloudLLM` POSTs OpenAI-shaped `/chat/completions`, probes `/models`, strips `<think>` blocks and ``` fences before the caller's `json.loads`, and retries once on 429/5xx (or bare, on a 400 from a reasoning knob the provider doesn't know). Any failure → `None` → fallback.
- `cli.py` — `python3 app/oracle/cli.py "your question"` → prints the three cards + woven reading + adventure. Testable with zero dependencies.

## Maps & wayfinding (built)
- `data/brc_geo.json` — BRC clock+street address system, 2026 street rings, fixed landmarks + placement zones.
- `data/playa_2026.json` — `live_hook` → real 2026 instances + location (honest status: fixed / zone / citywide / roaming / pending_api).
- `app/oracle/geo.py` — `locate(card)` resolves a card to a place; `COMPASS_ROSE` (≤32-col city compass); `directions_lines()`. `/api/reading` returns per-card `location`, a `map`, and `directions`. Refresh with GPS via the Burning Man API in August (see `data/README.md`).

## Thermal receipt printer (built)
- Target: the camp's **Epson TM-m30III (80mm)** units. `app/oracle/printer.py` formats a 48-col receipt (header, question, the three cards, the reading, the quest with directions, the compass, footer) and prints via `python-escpos`: network first (`ESCPOS_HOST`, port 9100 — one ethernet cable to the camp router), USB fallback (`ESCPOS_VENDOR_ID`/`ESCPOS_PRODUCT_ID`); with neither set it saves a preview to `app/receipts/`. `ORACLE_PRINT_WIDTH=32` retargets a 58mm printer. Endpoint: `POST /api/print` (prints the last reading). UI: "🧾 Print my quest" button.
- Playa setup: `pip install python-escpos pyusb`; find IDs via `system_profiler SPUSBDataType` (macOS) / `lsusb`; export the two env vars before launching the server.

## Server + UI (built)
- Stdlib HTTP server (`app/oracle/server.py`): serves the page, card art, `/api/reading`, `/api/print`, `/api/deck`. Bound to `0.0.0.0` (Tailscale-reachable).
- Single static page (`app/web/index.html`, no build step): "Ask the Turtle", mic (browser SpeechRecognition for now), slow card-flip reveal with woodcut art + locations, the reading, the quest, the compass map, and print.

## Later
- True offline voice: local Whisper transcription + Piper TTS (the Turtle's slow voice).
- Offline map tiles (iBurn `.mbtiles`) once the 2026 data lands in late August.

## The voice (system persona)
The Turtle Oracle: slow, grounded, warm, wry, a little bite. Honest, never saccharine. Speaks *to* the seeker. Weaves the three cards into a single arc — what to face, how to stand, what to reach for — landing on one concrete, doable adventure that references the real 2026 playa.
