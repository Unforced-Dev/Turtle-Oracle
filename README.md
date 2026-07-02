# 🐢 The Terrible Turtle Oracle

An AI-powered oracle deck for the Burning Man camp **Terrible Turtle** — *Move Slow & Bite Things.*

**▶ Live site: https://unforced-dev.github.io/Turtle-Oracle/**
Browse the full 48-card deck, read the vision, download the booklet — and **[ask the oracle](https://unforced-dev.github.io/Turtle-Oracle/oracle.html)** (runs entirely in your browser).

Built on a synchronicity: Burning Man 2026's theme is **Axis Mundi** (the World Tree), and in myth the World Tree grows from the back of the **World Turtle**. The camp's mascot is the foundation the whole theme stands on. So the deck is that tree, on that turtle.

**48 cards, four realms of twelve** — Shell (archetypes) · Roots (what to face) · Trunk (where you stand) · Branches (what to reach for). Every card carries universal life-wisdom, a **Turtle Dare** (one real adventure into the burn), and — in the app — this year's real camps/art + where to find them.

## The two forms
- **🃏 Print deck** — timeless, woodcut + gold, ~50 physical copies for the camp. Print-ready files in `print/`.
- **📱 The oracle** — two flavors:
  - **Static (this site):** the reading engine runs client-side in JS. Always on, nothing to break.
  - **Local server (`app/`):** the full experience — fluid **LLM** readings (Ollama), city **map + directions**, and a **58 mm thermal-receipt** "adventure guide." Runs fully offline on a laptop in the shell. `PYTHONPATH=app python3 -m oracle.server`.
  - **🔮 The Séance (`/kiosk`):** the tablet ritual for playa — a speaking Oracle avatar greets the seeker, asks how their burn is going (voice or keyboard), asks one light LLM-crafted follow-up, theatrically pulls three cards shaped by what they shared, reads them, and offers a **quest**: three moves with real places, a proof to bring back from each, and the vow — *return to the shell, tell the tale, receive a gift.* Accept it or say "hear me further" and the quest is re-woven around your words. Printable on receipt paper.
    - **Live on the internet now (served from the camp Mac mini):** https://parachute.taildf9ce2.ts.net:10000/kiosk (Tailscale Funnel → HTTPS, which is also what lets the mic work in browsers).
    - **Voice input is local:** the browser records audio and the mini transcribes it with **whisper.cpp** (`/api/transcribe`, ~0.6 s) — no cloud speech API, works on playa.
    - **LLM:** Ollama `gemma4:e2b` (~50 tok/s on the M4 mini), pinned in memory; template fallback if it's down.

## Repo map
- `index.html` / `oracle.html` / `cards.web.json` — the static Pages site (showcase + client-side oracle).
- `app/` — the offline server + reading engine (`deck`, `select`, `weave`, `geo`, `printer`, `server`).
- `data/` — `cards.json` (canonical deck), `brc_geo.json`, `playa_2026.json`, schema. See `data/README.md`.
- `cards/web/` — web-optimized thumbnails + medium images. `cards/back.png` — the card back.
- `print/` — `booklet.pdf`, `proof.pdf`, print README. (Full-res fronts + `cards/art/` are kept local; too large for git.)
- `docs/` — design docs (deck, app, style guide) + sourced 2026 research.
- `tools/` — build scripts (web images, contact sheet, booklet, print prep, static build).

## The 2026 data (August refresh)
The app overlays real 2026 placements via the Burning Man API — dev GPS unlocks **Aug 9, 2026**. See `data/README.md`.
