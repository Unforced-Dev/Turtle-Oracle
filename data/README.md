# Data

| File | What it is |
|---|---|
| `cards.json` | **The 48 cards** — canonical source of truth (Reading, shadow, Turtle Dare, keywords, `real_2026`, `live_hook`, `image_file`). Drives both the print deck and the app. Validated against `card.schema.json`. |
| `card.schema.json` | JSON Schema for one card. |
| `brc_geo.json` | Black Rock City geography: the clock+street address system, 2026 street rings (Ararat…Kundalini), fixed landmarks (Man, Temple, Center Camp, Trash Fence…) and placement zones. Powers the app's map + directions. |
| `playa_2026.json` | **App-only 2026 overlay.** Maps each card's `live_hook` → real 2026 instances + a location/status. The print deck stays timeless; this layer makes the app 2026-specific. |

## The `live_hook` seam
Every card carries a `live_hook` tag (e.g. `sunrise_soundcamp`, `temple`, `art:titanic`, `camp:terrible-turtle`). The print deck ignores it. The app uses it to look up `playa_2026.json` → the real thing(s) + where they are → wayfinding in the reading and on the receipt.

## Location status honesty
`playa_2026.json` marks each hook: `fixed` (known now), `zone` (typical area), `citywide` / `roaming` (not a fixed place), or **`pending_api`** (exact GPS drops via the Burning Man API in August).

## The August refresh (get GPS + placements)
Burning Man releases location data on a schedule; pre-wire now, refresh then:
- **Before Aug 9, 2026** — register at `api.burningman.org` and `playaevents.burningman.org` for a key.
- **Aug 9 (dev unlock)** — pull camp + art **GPS** via the API (honor the ToS embargo: art hidden until gates, camps until the Sunday prior). Geocode BRC clock addresses ("D & 3:15" → lat/lng) with the **iBurn geocoder** (`github.com/iBurnApp/iBurn-Data`, MIT).
- **Late August** — mirror iBurn `data/2026/` for ready-made **GeoJSON + offline `.mbtiles`** map tiles (cheapest path to an offline map). Poll its `update.json`.
- Then flip each `pending_api` hook in `playa_2026.json` from a zone/description to a real address.

Sources: `https://api.burningman.org` · `https://playaevents.burningman.org` · `https://github.com/iBurnApp/iBurn-Data` · `https://innovate.burningman.org/apis-page/`
