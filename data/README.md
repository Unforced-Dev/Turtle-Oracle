# Data

| File | What it is |
|---|---|
| `cards.json` | **The 48 cards** — canonical source of truth (Reading, shadow, Turtle Dare, keywords, `real_2026`, `live_hook`, `image_file`). Drives both the print deck and the app. Validated against `card.schema.json`. |
| `card.schema.json` | JSON Schema for one card. |
| `brc_geo.json` | Black Rock City geography: the clock+street address system, 2026 street rings (Ararat…Kundalini), fixed landmarks (Man, Temple, Center Camp, Trash Fence…) and placement zones. Powers the app's map + directions. |
| `playa_2026.json` | **App-only 2026 overlay.** Maps each card's `live_hook` → real 2026 instances + a location/status. The print deck stays timeless; this layer makes the app 2026-specific. |
| `brc_2026_snapshot.json` | **Local only — gitignored.** The raw Burning Man API pull (camps, art, events). Rebuild with `python3 tools/fetch_brc.py`; see the embargo below. |

## The `live_hook` seam
Every card carries a `live_hook` tag (e.g. `sunrise_soundcamp`, `temple`, `art:titanic`, `camp:terrible-turtle`). The print deck ignores it. The app uses it to look up `playa_2026.json` → the real thing(s) + where they are → wayfinding in the reading and on the receipt.

## Location status honesty
`playa_2026.json` marks each hook: `fixed` (known now), `zone` (typical area), `citywide` / `roaming` (not a fixed place), or **`pending_api`** (exact GPS drops via the Burning Man API in August).

## The August refresh (get GPS + placements)
Burning Man releases location data on a schedule; pre-wire now, refresh then:
- ✅ **Registered** at `api.burningman.org` — key in `~/.config/burningman/token` (or `$BRC_API_KEY`). Never commit it, never put it on a command line.
- ✅ **The pull is tooled.** `python3 tools/fetch_brc.py` writes one snapshot, `data/brc_2026_snapshot.json` — every camp, all 331 art pieces (with `gps_latitude`/`gps_longitude`), every registered event. Only `year` filters server-side; everything else is filtered locally.
- ✅ **The flip is tooled.** `python3 tools/refresh_playa.py` matches each `camp:` / `art:` hook against the snapshot by name and rewrites the unambiguous ones: `status: "fixed"`, the real `address`, `gps` for art, a `source` stamp, this year's `events` for camps, and the address in front of the directions. Ambiguous and missing ones are left alone and reported. `--dry-run` reports without writing.
- **On the playa, before departure** — re-run both tools. Placements move right up to the event, and camps that hadn't registered yet (the Zendo Project, as of this writing) will have.
- **Late August** — mirror iBurn `data/2026/` for ready-made **GeoJSON + offline `.mbtiles`** map tiles (cheapest path to an offline map). Poll its `update.json`. The iBurn geocoder (`github.com/iBurnApp/iBurn-Data`, MIT) turns a clock address into lat/lng for the camps the API gives no GPS for.

### The embargo — why the snapshot is not in git
Burning Man's API terms embargo **public display** of placement data: art until gates open, camps until the Sunday before the event. This repo is public, so:
- `data/brc_*_snapshot.json` is **gitignored**. It lives only on the camp laptop.
- A full `refresh_playa.py` run writes third-party placements into `playa_2026.json` — **that result is not committed either.** Run it locally, keep it locally.
- `python3 tools/refresh_playa.py --only-own-camp` applies just the hooks that resolve to Terrible Turtle's own record. Our own address is ours to publish, so that result *is* committable — it is how `camp:terrible-turtle` became `E & 6:15`.

Sources: `https://api.burningman.org` · `https://playaevents.burningman.org` · `https://github.com/iBurnApp/iBurn-Data` · `https://innovate.burningman.org/apis-page/`
