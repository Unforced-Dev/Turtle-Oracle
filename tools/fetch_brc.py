#!/usr/bin/env python3
"""Pull the year's camps, art and events from the Burning Man Public API.

One request per collection, one snapshot file out:

    data/brc_<year>_snapshot.json
    {"fetched_at": <iso8601 utc>, "year": N, "camps": [...], "art": [...], "events": [...]}

**The snapshot is not committed.** Burning Man's API terms embargo public
display of placement data — art until gates open, camps until the Sunday before
the event — and this repo is public. `.gitignore` keeps the file local; only the
derived, camp-owned bits land in `data/playa_2026.json` (see refresh_playa.py).

Auth: an API key in `$BRC_API_KEY`, or the first line of
`~/.config/burningman/token`. The key is never printed and never passed on a
command line. Request it at https://innovate.burningman.org/apis-page/ .

Only `year` filters the collections (the event endpoint takes nothing else), so
everything is pulled whole and filtered client-side by refresh_playa.py.

Usage:
    python3 tools/fetch_brc.py                  # 2026 -> data/brc_2026_snapshot.json
    python3 tools/fetch_brc.py --year 2025
    python3 tools/fetch_brc.py --out /tmp/snap.json
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("BRC_API_BASE", "https://api.burningman.org")
TOKEN_FILE = os.path.expanduser("~/.config/burningman/token")
COLLECTIONS = {"camp": "camps", "art": "art", "event": "events"}  # endpoint -> snapshot key

# Terrible Turtle's own camp record — the one placement we're allowed to publish.
OWN_CAMP_UID = "a1XVI00000FLKvx2AH"
OWN_CAMP_NAME = "Terrible Turtle"


def api_key():
    """The API key, from the environment or the token file. Never logged."""
    key = os.environ.get("BRC_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            key = f.read().strip()
    except OSError as e:
        sys.exit(f"no API key: set $BRC_API_KEY or write one to {TOKEN_FILE} ({e})")
    if not key:
        sys.exit(f"no API key: {TOKEN_FILE} is empty")
    return key


def get(path, key, timeout=120, **params):
    """GET {BASE}{path}?params with the key in the X-API-Key header."""
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "X-API-Key": key,
        "Accept": "application/json",
        "User-Agent": "terrible-turtle-oracle/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        sys.exit(f"{path} -> HTTP {e.code} {e.reason}: {body}")
    except urllib.error.URLError as e:
        sys.exit(f"{path} -> {e.reason}")


def find_own_camp(camps):
    """Our camp record, by uid first and name second (uids can change year to year)."""
    for c in camps:
        if c.get("uid") == OWN_CAMP_UID:
            return c
    for c in camps:
        if OWN_CAMP_NAME.lower() in (c.get("name") or "").lower():
            return c
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--out", help="snapshot path (default data/brc_<year>_snapshot.json)")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    key = api_key()
    out = args.out or os.path.join(REPO, "data", f"brc_{args.year}_snapshot.json")

    snap = {
        "fetched_at": datetime.datetime.now(datetime.timezone.utc)
                              .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "year": args.year,
    }
    for endpoint, field in COLLECTIONS.items():
        rows = get(f"/api/{endpoint}", key, timeout=args.timeout, year=args.year)
        if not isinstance(rows, list):
            sys.exit(f"/api/{endpoint} returned {type(rows).__name__}, expected a list")
        snap[field] = rows
        print(f"  {field:6s} {len(rows):5d}")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)

    size = os.path.getsize(out) / 1e6
    print(f"\nwrote {os.path.relpath(out, REPO)} — {size:.1f} MB, fetched_at {snap['fetched_at']}")
    print("EMBARGO: placement data — keep this file local, do not commit it.")

    own = find_own_camp(snap["camps"])
    if own:
        loc = own.get("location") or {}
        print(f"\n{own.get('name')} ({own.get('uid')})")
        print(f"  location_string: {own.get('location_string')}")
        for k in ("frontage", "intersection", "intersection_type", "dimensions", "exact_location"):
            if loc.get(k):
                print(f"  {k}: {loc[k]}")
        mine = [e for e in snap["events"] if e.get("hosted_by_camp") == own.get("uid")]
        print(f"  events registered: {len(mine)}")
        for e in mine[:10]:
            when = (e.get("occurrence_set") or [{}])[0].get("start_time", "?")
            print(f"    {when}  {e.get('title')}")
    else:
        print(f"\n{OWN_CAMP_NAME}: NOT FOUND in {args.year} camps "
              f"(registration may not be in yet)")


if __name__ == "__main__":
    main()
