# The cloud turtle

The Terrible Turtle Oracle séance, as a single Cloudflare Worker, for
`turtle-oracle.unforced.dev`.

The oracle that matters is the one in camp: a DGX Spark running `qwen3:30b-a3b` under
Ollama, on camp power, behind camp wifi, printing thermal receipts. This is the backup —
the same ceremony for anyone with a phone and a signal, and the thing that still answers
when the Spark is off, the generator is out, or someone wants to show a friend at home
what the shell does.

It is a **port, not a rewrite**. Every stage, every spoken line, and all five tuned
prompt strings are copied out of `app/oracle/` unchanged, and `cloud/test/parity.mjs`
proves it by building each prompt on both sides of the port and diffing them byte for
byte. If you change a prompt in one place, that test fails until you change it in both.

## Run it

```sh
export CLOUDFLARE_API_TOKEN=...        # never in a file in this repo, never in a URL
export CLOUDFLARE_ACCOUNT_ID=<account-id>          # `npx wrangler whoami` prints it

cd cloud
npm test                    # port parity — needs node 22+ and python3, no network
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
  src/weave.js         reading + quest — app/oracle/weave.py
  src/llm.js           Workers AI — app/oracle/llm.py
  src/deck.js  select.js  geo.js  lore.js  printer.js  util.js
  test/parity.mjs      builds every prompt on both sides and diffs them
```

Static assets (the kiosk, 52 cards at two sizes, the medallion) are served by the
`[assets]` binding; the Worker script only ever sees `/api/*`. Card art is **not**
duplicated into the repo — `prepare-assets.sh` copies it out of `cards/web/` at build
time and `assets/{med,thumb,tiles,avatar.jpg}` are gitignored.

## What changed from the playa app, and why

| | playa (`app/`) | cloud (`cloud/`) |
|---|---|---|
| séance state | module-level `SESSIONS` dict + `_gc()` | KV `sess:<id>`, 2h TTL |
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

- **30 POST `/api/*` a minute per IP** (the `RL` ratelimit binding in `wrangler.toml`).
  A whole séance is about a dozen calls. Over the limit the shell says so, with a 429.
  A missing binding means no limit, not no séance — deleting the block is safe.
- **1.5MB of audio** per `/api/transcribe`. The kiosk's own recorder caps at 60s, which
  is ~240KB of webm/opus or ~1MB of iOS mp4/aac.
- **1000 characters a share, 12 shares a séance, 3 refinements a quest.** Past the third
  the Turtle says the Tree has settled and spends nothing more.
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
and `esc()` around everything the model or the seeker puts on the quest parchment.
Everything else — the mic, the browser-TTS fallback, the localStorage session restore,
the `?kiosk=1` station param — is untouched. **The playa kiosk is the original.** Real UI
work belongs in `app/web/kiosk.html` first, then gets copied down.
