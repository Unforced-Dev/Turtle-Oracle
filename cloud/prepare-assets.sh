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

echo "prepare-assets: $(ls "$here/assets/med" | wc -l | tr -d ' ') med, $(ls "$here/assets/thumb" | wc -l | tr -d ' ') thumb"
