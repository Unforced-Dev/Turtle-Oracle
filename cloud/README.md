# The cloud turtle

The Terrible Turtle Oracle séance, as a single Cloudflare Worker, for
`turtle-oracle.unforced.dev`.

The oracle that matters is the one in camp: a DGX Spark running `qwen3:30b-a3b` under
Ollama, on camp power, behind camp wifi, printing thermal receipts. This is the backup —
the same ceremony for anyone with a phone and a signal, and the thing that still answers
when the Spark is off, the generator is out, or someone wants to show a friend at home
what the shell does.

It started as a **port, not a rewrite**: every stage, every spoken line and all five
tuned prompt strings were copied out of `app/oracle/` unchanged, and `cloud/test/parity.mjs`
proves it by building each prompt on both sides and diffing them byte for byte. If you
change a prompt in one place, that test fails until you change it in both.

As of `feat/cloud-seance-v2` the cloud turtle is **ahead of the Spark in three places, on
purpose** — the séance flow, how specific a quest is allowed to be, and (as of
`fix/seance-smooth`) the shape of a quest: the cloud turtle gives ONE bite of 20-40 words
with one bearing and one proof, where the Spark still gives three moves. Every string that
diverged prints as `skip` in the parity test rather than `ok`, each with a note saying what
moved and to port it back to `app/oracle/` when the Spark is reachable, then restore the
byte-diff. Everything else still diffs, and still has to match.

## Run it

```sh
export CLOUDFLARE_API_TOKEN=...        # never in a file in this repo, never in a URL
export CLOUDFLARE_ACCOUNT_ID=<account-id>          # `npx wrangler whoami` prints it

cd cloud
TZ=America/Los_Angeles npm test        # both suites — needs node 22+ and python3, no network
npm run test:seance         # just the state machine (no python3 needed)
npm run test:parity         # just the prompt diff against app/oracle
npx wrangler deploy --env staging      # -> turtle-oracle-staging.unforced.workers.dev
npx wrangler deploy                    # -> turtle-oracle, the custom domain. Review first.
```

`turtle-oracle` is production and owns the `turtle-oracle.unforced.dev` custom domain,
which is attached out of band — `wrangler.toml` declares no routes, so a deploy will not
move or remove it. Staging is the same code with `workers_dev = true` and no domain, and
the two share one KV namespace on purpose: a staging séance and a production séance are
both real séances, and the Tale-Book should remember either.

## Shape

```
cloud/
  wrangler.toml        bindings, models, timeouts — every knob is a [vars] entry
  prepare-assets.sh    wrangler's [build] step: copies cards/web/* into assets/
  assets/index.html    app/web/kiosk.html, with a few marked changes
  src/index.js         the router — app/oracle/server.py
  src/session.js       the séance state machine — app/oracle/session.py
  src/sessiondo.js     one Durable Object per séance — the state KV could not hold
  src/weave.js         reading + quest — app/oracle/weave.py
  src/llm.js           Workers AI — app/oracle/llm.py
  src/ears.js          /api/transcribe — app/oracle/ears.py; its own file so a test
                       can import it without the Workers runtime
  src/guide.js         the city: what is on, where camps and art stand — app/oracle/guide.py
  src/chat.js          Ask the Turtle — app/oracle/chat.py
  src/deck.js  select.js  geo.js  lore.js  printer.js  util.js
  test/all.mjs         all three suites, every one run even when an earlier one fails
  test/seance.mjs      walks both doors of the séance against a fake model
  test/city.mjs        the city, the chat and the routes, on a pinned clock
  test/parity.mjs      builds every prompt on both sides and diffs them
../tools/build_city.py  the Burning Man dump -> assets/city.json, at deploy time
```

Static assets (the kiosk, 52 cards at two sizes, the medallion) are served by the
`[assets]` binding; the Worker script only ever sees `/api/*`. Card art is **not**
duplicated into the repo — `prepare-assets.sh` copies it out of `cards/web/` at build
time and `assets/{med,thumb,tiles,avatar.jpg}` are gitignored.

## Three doors

A tablet on a table at camp is walked up to for a reading. A phone is taken out of a
pocket for three different reasons, and the attract screen answers all three:

| door | what it is | routes |
|---|---|---|
| **Pull the cards** | the séance, unchanged | `POST /api/session/*` |
| **Ask the Turtle** | open talk, grounded in the city and the cards | `POST /api/chat`, `/api/chat/open` |
| **What's happening** | browse the city by window, kind and name | `GET /api/city/happening`, `search`, `item` |

and from a reading or a sealed quest, two more: **What's out there for this**
(`GET /api/city/for?session=`) and **Talk with the Turtle about this**.

### The city file

`tools/build_city.py` slims the 4.3MB Burning Man dump (`data/brc_2026_snapshot.json`,
gitignored) into `assets/city.json` — 1.38MB, 3410 events with 6563 occurrences, 1184
camps, 345 art. Both files stay out of git: the API terms embargo public display of
placements, and a derived copy is the same redistribution wearing a hat.
`prepare-assets.sh` builds it as part of the deploy, and a machine **without** the dump
still deploys — the Worker then knows the 52 cards, says plainly that it has no city in
it, and `/api/health` reports `city: false`.

`/city.json` is **404 on the public path**. It is an asset so `env.ASSETS.fetch` can read
it, and that call does not re-enter the Worker, so the door is on the street and not on
the kitchen. `/api/health` reads the 200-byte `city.meta.json` instead, so an uptime check
on a cold isolate never pays for the parse.

`src/guide.js` holds the city in two lazy per-isolate promises, and the split is the
point: the parse plus the occurrence timeline is ~32ms and is what browsing needs; the
token index over every name and description is ~100ms and is what only search and the
model's retrieval need. Browsing must not pay for an index it does not use. Nothing
re-parses per request — if you find `JSON.parse` on the request path, that is the bug.

### Rate limits

Every route that costs money or bandwidth has its own budget, and none of them spend from
the séance's: a seeker mid-reading who also wants to know where the coffee is must not pay
for it out of their reading.

| binding | route | limit |
|---|---|---|
| `RL` | the séance | 30/min |
| `RL_SPEAK` | `/api/speak` | 120/min |
| `RL_EARS` | `/api/transcribe` | 12/min |
| `RL_CHAT` | `/api/chat`, `/api/chat/open` | 20/min |
| `RL_CITY` | `/api/city/*` | 120/min |

## The voice

**Nothing auto-speaks.** Aaron, 2026-09-05, on the tablets: auto-speaking is very
disturbing. A tablet at camp has a person standing beside it; a phone speaks into a tent
at 3am. So every utterance — the séance's lines, the look, the question, the reading, the
quest offered, the sealed quest, every chat answer — carries its own **Read aloud** button;
tapping it again stops. The chip in the corner is the old always-speak behaviour, kept,
remembered in `localStorage` under `turtle-oracle.voice`, and off by default.

A Read aloud tap gets the server voice or nothing: no browser `speechSynthesis` behind it,
because the seeker asked for the Turtle and a bright system voice reading its lines is
worse than being told the voice is out — which is what *voice unavailable* beside the
button says. The always-speak chip keeps its fallback.

The whole utterance goes to `/api/speak` in as few calls as the server's 600-character
roof allows, not one call per sentence. A reading used to be a dozen round trips; on
Starlink that is a dozen chances to stall between two half-sentences.

The silent pacing is unchanged — `speakOr` and `incant`'s `SILENT_WORD_MS` were already
the path a muted phone took, and they are now the path the ceremony runs on.

## The séance

Twelve stages, and the whole thing turns on the second one. A seeker deep in their burn is
not going to complete the sentence *"I want to keep…"* — the old flow made them, and that
is the stage this version deletes. Every step is a `POST /api/session/say` with the
séance id; the body and the event are what the kiosk speaks.

| stage | the Turtle | body the phone posts | what comes back |
|---|---|---|---|
| `naming` | asks for a name | `{text}` | → `door` |
| `door` | *talk to the Turtle, or touch?* | `{door:"talk"\|"touch"}` | `doors[]`, → `listening` or `weather` |
| `listening` | *tell the Turtle about your burn* | `{text}` (voice, transcribed, or typed) | → `asking` |
| `weather` | the six skies | `{weather:id}` | `weathers[]`, → `stones` |
| `stones` | *touch what you are carrying* | `{stones:[id]}` | `stones[]`, → `wanting` |
| `wanting` | *what did you come out here for?* | `{wanting:id}` | `wantings[]`, → `asking` |
| `asking` | **draws and reveals the three cards**, then asks one open question | `{text}` or `{chip}` or `{pass:true}` | `cards`, `question`, `chips[]`, → `proposed` |
| `proposed` | the echoes, the reading, the quest, the decision | `{text}` to refine (≤3) | `echoes`, `reading`, `adventure`, → `accepted` |
| `accepted` | seals it | `POST .../accept` | `quest` |

**Every event at `asking`, `proposed` and `accepted` is complete, including the retries.**
Those are the three stages whose renderer reaches into the event — the kiosk deals
`e.cards[slot].id` and walks `e.quest.moves` — and it persists the last step it was handed,
so a `proposed` event with no cards on it is not a missing screen but a blank one that
comes back on every reload. A body with no text at `proposed` (a stale `{pass:true}`, a
chip from the screen before, an empty retry from a phone whose reply died on LTE) re-offers
the standing decision whole, `modes.refine: "standing"`; at `accepted` it replays the
sealed quest; the `asking` retry carries the spread and is marked `retry: true` so a phone
already looking at those cards redraws only the answer row. The kiosk checks the same
contract on its own side (`renderable()`), refuses to save or route an event that fails it,
and `cloud/test/seance.mjs` walks all twelve stages against every body shape.

Plus the tale side, unchanged: `tale_naming` → `tale_listening` → `tale_told`.

Two things about that shape are the point:

- **Nobody has to type to be read.** The touch door is three tap screens and no text box
  anywhere. Each tile becomes a short share phrase so the weave and the keyword scoring
  have words to work with — but those phrases carry a marker, and `seekerWords()` drops
  them, so a tile is never quoted back as something the seeker *said*. That is the rule
  `"I am carrying:"` already enforced for the stones, extended to every tap.
- **The cards come before the question.** An oracle turns the cards and then asks you
  something; a form asks you first and then computes. So the draw happens at `asking`, the
  spread is dealt face up, and the question the Turtle asks about it is shaped by what it
  drew and what it has heard. `{pass:true}` is a real answer — the séance completes on it,
  and the fallback echoes name the cards rather than inventing a quotation.
- **An echo quotes a clause, not a word count.** The line each card turns over on quotes
  3-8 words the seeker actually said, and `validEcho` throws away any the model invented.
  The candidates are cut at the seeker's own punctuation and trimmed back to words with
  weight in them, because a fixed-width window over two minutes of voice lands mid-clause
  — *You said “out to the trash fence alone and”*. The `proposed` event reports
  `modes.echoes: "llm" | "fallback"`, where `"llm"` means at least one of the model's
  three lines survived that check.

## The quest, and how specific it is

Three street addresses is an errand list, and half of what the guide places has moved,
burned, or was never there. So the quest prompt asks for exactly **one** move pinned to a
real 2026 placement and **two** open ones — a direction, a kind of place, a kind of
person, a time of day. The pinned one is chosen from the located cards: the one whose
`live_hook` actually resolved to a placed thing, preferring one the gates data gives an
address or a clock for. `weaveFallback` follows the same rule offline.

The **seal** (`POST /api/session/accept`) obeys the same split, so the parchment says what
the quest said out loud. The anchor realm is decided once when the cards are drawn and
carried on the session (`sess.anchor`); the placed move seals with its card's real
directions, and the other two seal with a bearing — the card's own citywide line when that
line is a kind of place ("Anywhere the playa is open under you"), otherwise the realm's
`OPEN_WHERE` from `weave.js`. The seal prompt marks which move is the placed one and
forbids an address on the other two; `accept()` drops the model's own `where` on those two
anyway, because told to give a bearing it still names a camp, and a camp is an address with
the numbers filed off.

## What changed from the playa app, and why

| | playa (`app/`) | cloud (`cloud/`) |
|---|---|---|
| séance state | module-level `SESSIONS` dict + `_gc()` | a Durable Object per séance, 2h expiry |
| Tale-Book | `app/state/talebook.jsonl`, rescanned per lookup | KV `lore:name:<norm>` (30d TTL) + `lore:counts` |
| model | Ollama `qwen3:30b-a3b` on the LAN | Workers AI `@cf/qwen/qwen3-30b-a3b-fp8` |
| ears | whisper.cpp + ffmpeg | `@cf/openai/whisper-large-v3-turbo`, no transcode |
| voice | Kokoro `bm_george` @ 0.86 speed, WAV | `@cf/deepgram/aura-1`, MP3 |
| printer | ESC/POS over the camp LAN | none — `/api/print` returns the formatted receipt |
| `/` | `app/web/site.html`, kiosk at `/kiosk` | the kiosk, because that is the whole product |
| legacy `/api/reading` | present | dropped; the kiosk never called it |
| warm-keeper thread | keeps the model resident | not needed |

Deliberate additions, both in `src/session.js` and both worth back-porting:

- **`isSameQuest`** rejects a "rewritten" quest that is the old quest handed back. Asked
  to rewrite a short quest, the model returned it verbatim in 2 of 5 staging runs; it
  passes the 60-140 word gate, so the seeker heard *"That changes the shape of it"* and
  then their unchanged quest. The prompt already demands one move be **replaced**; this
  enforces it, the way `_valid_echo` enforces the quoted phrase. A rejected rewrite falls
  to `refineFallback`, which genuinely re-scores the cards.
- **per-stage thinking** (`THINK_STAGES`). `llm.py` turns qwen3's scratchpad off for
  every call because one playa GPU cannot afford 700 reasoning tokens a stage. The cloud
  can, on the calls that need it. See the measurements at the top of `src/llm.js`: with
  `/no_think`, **4 of 8 readings were the SYSTEM prompt's own example handed to the
  seeker as their reading**, and the tale honour line lost the half that tells the human
  turtle to hand over the gift. With thinking, neither happens. Refine, echoes and seal
  are better or identical without it, and 3-11x faster, so they skip it.

## Knobs

All of it is `[vars]`, so a change is a redeploy, not a code edit.

| var | default | note |
|---|---|---|
| `MODEL` | `@cf/qwen/qwen3-30b-a3b-fp8` | same family as the Spark |
| `MODEL_FALLBACK` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | tried once if the primary errors or hangs |
| `THINK_STAGES` | `weave,tale` | `""` = never think, `weave,refine,echoes,seal,tale` = always |
| `MAX_TOKENS` | `4096` | a ceiling, not a target; too low truncates a reasoning model mid-JSON |
| `T_SHORT` / `T_LONG` | `20` / `38` | seconds before a stage gives up and uses the template; the fallback model gets half as long again, and the draw chains two stages, so the worst case is 87s of a ~100s edge timeout |
| `SHELL_CHANCE` | `0.10` | how often the Tree's own spine speaks into a Tree slot |
| `WHISPER_MODEL` | `@cf/openai/whisper-large-v3-turbo` | takes webm/opus and mp4/aac straight from MediaRecorder |
| `TTS_MODEL` | `@cf/deepgram/aura-1` | **`"off"` drops the kiosk to its browser voice** |
| `TTS_SPEAKER` | `angus` | `zeus` is slower and deeper |

`GET /api/health` reports which of these is live, plus `fallback_pct` — the number to
watch. If it climbs, the Turtle has gone dumb and is hiding it behind a very convincing
template.

## A public URL, not a tent

The playa server trusts everyone who can reach it, because reaching it means standing in
camp. This one is on the open internet with Workers AI billing behind it, so:

- **30 POST `/api/*` a minute per IP** (the `RL` ratelimit binding in `wrangler.toml`),
  and **120 a minute for `/api/speak`** on its own `RL_SPEAK` binding. A minimal séance
  is ~7 séance POSTs, but with the Turtle's voice on it is ~41 more, because `/api/speak`
  is one POST per *sentence* — about 48 in all. On one shared counter that meant two
  phones behind a single carrier NAT could 429 each other out of a reading, so the voice
  spends from its own budget. Over the limit the shell says so, with a 429. A missing
  binding means no limit, not no séance — deleting either block is safe.
- **`/api/transcribe` needs a séance.** The séance id goes in an `x-seance-session`
  header (or `?session=` for a hand-run curl) and has to resolve to a live Durable Object
  session in a stage that is actually listening — `naming`, `listening`, `asking`,
  `proposed`, and the two tale stages. Anything else gets a séance-shaped 200 with an
  `error` the kiosk toasts. Without that gate this was a free Whisper endpoint: an IP, a
  4MB body, ~120MB of billed audio a minute. It also has **its own ratelimit binding,
  `RL_EARS` (12/min)**, so one seeker tapping the mic cannot eat their own séance budget
  and a scraper cannot have thirty of them.
- **4MB of audio** per `/api/transcribe`. The talk door gives a seeker two minutes, which
  is ~480KB of webm/opus or ~2MB of iOS mp4/aac (iOS records AAC at ~128kbps and will not
  be talked down). The kiosk's own recorder still stops itself at 120s. **The old
  60s/1.5MB numbers were measured; these are not** — verify a real two-minute share on
  staging and read the TAIL of the transcript, because a truncated answer looks like a
  quiet seeker rather than like an error.
- **1000 characters a share** — except at `listening`, which takes 2000, because that is
  where two minutes of transcribed voice lands in one piece. **12 shares a séance, 3
  refinements a quest.** Past the third the Turtle says the Tree has settled and spends
  nothing more.
- **`/api/print` needs a sealed quest.** The receipt is the paper the shell would have
  cut, and `app/oracle/printer.py` opens it with `YOU TOLD THE TURTLE` and the seeker's own
  shares — which is right on paper handed to the person who said them, and wrong over the
  open internet to anyone holding a session id. The shares stay in the receipt (removing
  them would leave the playa's own format with a heading and nothing under it); what is
  gated is when it can be fetched: `sess.stage === "accepted"`, and nothing before.
- **A thrown séance says so in the Turtle's voice.** `/api/session/*` answers an internal
  failure with a 200 and one line — never `String(err.message)`, which used to go straight
  onto a stranger's screen — and the stack goes to `console.error`. The session is saved on
  that path too when the stage both moved and finished arriving (`session.replayable()`),
  so a retry replays the draw instead of paying for a second one; a stage that was entered
  but never filled in is deliberately not saved, because redoing it costs a draw and saving
  it strands the seeker in a stage whose reveal never reached them.
- **`accept` is a replay, not a reseal** — the sealed quest and its spoken line are stored
  on the session, so a double-tap or a retried POST cannot bill a second sealing.
- **The Tale-Book forgets.** Per-name records expire after 30 days and hold the quest
  title, the three card ids and a timestamp — never what the seeker said.
- The kiosk is served with `nosniff` and a CSP (`src/index.js`); it needs `unsafe-inline`
  for its one inline script and style, `data:` for the grain texture and `blob:` for the
  Turtle's voice.

## The kiosk copy

`assets/index.html` is `app/web/kiosk.html` with a handful of changes, each marked
`cloud:`: a `noindex` meta tag, the Print button hidden (there is no printer out here),
`esc()` around everything the model or the seeker puts on the page (the parchment, the
weather tiles, the stones, the card art), the `renderable()` contract above, a restore that
re-renders without re-buying the voice, and a recorder that asks for 48kbps and checks
`blob.size` against the shell's roof before posting rather than after.
Everything else — the mic, the browser-TTS fallback, the localStorage session restore,
the `?kiosk=1` station param — is untouched. **The playa kiosk is the original.** Real UI
work belongs in `app/web/kiosk.html` first, then gets copied down.
