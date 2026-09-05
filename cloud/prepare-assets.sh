#!/usr/bin/env bash
# Stage the card art for Workers Static Assets.
#
# The deck's web images already live in cards/web/ and are committed there. Copying
# 25MB of JPEG into cloud/assets/ and committing it a second time would double the
# repo for nothing, so this runs as wrangler's [build] step and the copies are
# gitignored. Nothing here is generated — it is all `cp`.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/.." && pwd)"
src="$repo/cards/web"

if [ ! -d "$src/med" ]; then
  echo "prepare-assets: $src/med is missing — run tools/webimg.py first" >&2
  exit 1
fi

rm -rf "$here/assets/med" "$here/assets/thumb" "$here/assets/tiles"
mkdir -p "$here/assets/med" "$here/assets/thumb"

cp "$src"/med/*.jpg "$here/assets/med/"
cp "$src"/thumb/*.jpg "$here/assets/thumb/"

# The kiosk's medallion. The playa server falls back to cards/back.png when the avatar
# is missing; here the avatar has always been built, so a missing one is a real error.
cp "$src/med/avatar.jpg" "$here/assets/avatar.jpg"

# Weather tiles are optional: the repo has never built cards/web/tiles, and the kiosk's
# <img onerror> hides a tile that 404s, showing the weather's name alone. If they are
# ever generated, they ship automatically.
if [ -d "$src/tiles" ]; then
  mkdir -p "$here/assets/tiles"
  cp "$src"/tiles/*.jpg "$here/assets/tiles/" 2>/dev/null || true
fi

# The city — camps, art and what is on. tools/build_city.py slims the 4.3MB Burning Man
# dump into cloud/assets/city.json (~1.4MB), which src/guide.js reads through the ASSETS
# binding. Both the dump and the built file are gitignored: the API terms embargo public
# display of placements, and a derived copy in git is the same redistribution wearing a
# hat. A machine WITHOUT the dump still deploys — the Worker then knows the 52 cards and
# says plainly that it has no city in it, and /api/health reports city:false.
rm -f "$here/assets/city.json" "$here/assets/city.meta.json"
if command -v python3 >/dev/null 2>&1; then
  python3 "$repo/tools/build_city.py" --out "$here/assets" || \
    echo "prepare-assets: build_city.py failed — deploying without a city" >&2
else
  echo "prepare-assets: no python3 — deploying without a city" >&2
fi

echo "prepare-assets: $(ls "$here/assets/med" | wc -l | tr -d ' ') med, $(ls "$here/assets/thumb" | wc -l | tr -d ' ') thumb"
