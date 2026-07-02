# The Terrible Turtle Oracle — App

An offline, kiosk-style oracle. Ask a question → the Turtle draws one Root, one Trunk, one Branch → weaves them into one reading + one real adventure into the burn. Runs fully self-contained (no internet) — essential on playa.

## Run it (zero dependencies)
```bash
# from the repo root
PYTHONPATH=app python3 -m oracle.server
# open http://localhost:8777
```
Or the text CLI:
```bash
PYTHONPATH=app python3 -m oracle.cli "what should I do about the thing I keep avoiding?"
```

## Two intelligence tiers (automatic)
- **With a local LLM** (best readings): run [Ollama](https://ollama.com) and pull a model, then start the server. It's detected automatically.
  ```bash
  ollama serve &                 # usually already running
  ollama pull qwen2.5            # or llama3.1, etc.
  ORACLE_MODEL=qwen2.5 PYTHONPATH=app python3 -m oracle.server
  ```
- **Without any LLM** (always works): the offline template weave stitches each drawn card's own Reading and Turtle Dare. No installs, never fails.

## Environment
- `ORACLE_MODEL` — Ollama model name (default `qwen2.5`).
- `OLLAMA_HOST` — default `http://localhost:11434`.
- `ORACLE_PORT` — server port (default `8777`).

## How it's built (`app/oracle/`)
- `deck.py` — loads `data/cards.json`, groups by realm, models the Tree spread.
- `select.py` — picks the resonant three (LLM → keyword score → random).
- `weave.py` — the reading + adventure (LLM → template fallback). Holds the Turtle's voice.
- `llm.py` — Ollama adapter (stdlib only); any failure → fallback.
- `server.py` — stdlib HTTP server; serves the page + card art + `/api/reading`.
- `web/index.html` — the offline single-page kiosk (woodcut/gold), text-first with an optional voice button.

## Playa checklist
- One machine (laptop/mini-PC) in the shell, charged / on camp power.
- Ollama + a pulled model installed **before** leaving (no downloads on playa).
- Card art present in `cards/art/` (bundled).
- Start the server; point a tablet/browser at it. Text input always works; local-Whisper voice is a planned addition.

## Ears (local voice input)
`brew install whisper-cpp ffmpeg`, then fetch the model (not in git — 148 MB):
```
curl -L -o app/models/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
```
The kiosk records in the browser and POSTs to `/api/transcribe` (whisper.cpp, ~0.6 s warm).
