#!/usr/bin/env python3
"""Slim the 4.3MB BRC dump down to something a Cloudflare Worker can hold.

    python3 tools/build_city.py            # -> cloud/assets/city.json + city.meta.json

The Spark reads ``data/brc_2026_snapshot.json`` off its own disk and keeps the whole
thing in memory (app/oracle/guide.py). A Worker has no disk and a CPU budget measured in
milliseconds, so the cloud turtle gets a BUILT artefact instead: the same three tables,
stripped to the fields the phone and the model actually use, with the times already
resolved to integers and the places already joined.

Three rules shaped the format:

1. **Nothing derived goes in git.** Burning Man's API terms embargo public display of
   placements, and the embargo lifting when the gates opened does not make the dump ours
   to redistribute. ``cloud/assets/city*.json`` is gitignored and this runs at deploy
   time, out of prepare-assets.sh, from a snapshot that is itself gitignored. A machine
   without the snapshot builds a Worker with no city in it, which is a smaller Turtle and
   not a broken one — src/guide.js says so out loud and /api/health reports city:false.

2. **Bytes are CPU.** JSON.parse is the single most expensive thing the Worker does with
   this file, it is paid once per isolate, and it is paid on some seeker's request. So
   descriptions are capped, empty fields are omitted rather than written as "", the event
   kind is an index into a table of eight strings rather than eight strings repeated 3410
   times, and every timestamp is an integer.

3. **Sorted here, not there.** Occurrences come out sorted by start time, so the Worker
   answers "what is on tonight" by walking a window of an already-ordered list rather
   than by sorting 6.5k rows on the request path.

Stdlib only, like everything else in tools/.
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SNAPSHOT = os.path.join(REPO, "data", "brc_2026_snapshot.json")
OUT_DIR = os.path.join(REPO, "cloud", "assets")

# An event blurb is read on a phone in the dark, in a sheet the seeker has to scroll.
# 240 characters is about three lines at the size that file draws them, and it is also
# the length the model can quote from without the prompt turning into a corpus.
EVENT_DESC = 240
# Camps and art are looked up to answer "what is that place" — a shorter answer.
PLACE_DESC = 200

WS = re.compile(r"\s+")


def clean(text, cap):
    """One line, collapsed, cut on a word boundary with an ellipsis when it is cut."""
    t = WS.sub(" ", str(text or "")).strip()
    if len(t) <= cap:
        return t
    cut = t[:cap].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return (cut or t[:cap]) + "…"


def epoch(s):
    """'2026-09-03T16:00:00-07:00' -> int seconds, or None.

    The dump writes every occurrence with an explicit -07:00 offset, so this is exact
    and needs no timezone database. A row that does not parse is dropped rather than
    guessed at: an event with an invented time is worse than an event nobody sees.
    """
    if not s:
        return None
    try:
        return int(datetime.datetime.fromisoformat(str(s)).timestamp())
    except ValueError:
        return None


def put(rec, key, value):
    """Write a field only when it carries something. Empty strings cost 6 bytes each and
    there are ~15k of them across the three tables."""
    if value:
        rec[key] = value


def build(raw):
    kinds, kind_idx = [], {}

    def kind_of(label):
        label = str(label or "Other")
        if label not in kind_idx:
            kind_idx[label] = len(kinds)
            kinds.append(label)
        return kind_idx[label]

    # --- camps and art, and the uid -> place map the events are joined through --------
    camps, art, place = [], [], {}
    for c in raw.get("camps") or []:
        uid, name = c.get("uid"), clean(c.get("name"), 120)
        if not uid or not name:
            continue
        rec = {"uid": uid, "kind": "camp", "name": name}
        put(rec, "where", clean(c.get("location_string"), 60))
        put(rec, "desc", clean(c.get("description"), PLACE_DESC))
        put(rec, "from", clean(c.get("hometown"), 60))
        # The landmark line is how a camp is actually found in the dark ("the lit
        # Snuggles sign") — worth its bytes, and the one field the location string
        # cannot stand in for.
        put(rec, "landmark", clean(c.get("landmark"), 90))
        camps.append(rec)
        place[uid] = rec
    for a in raw.get("art") or []:
        uid, name = a.get("uid"), clean(a.get("name"), 120)
        if not uid or not name:
            continue
        rec = {"uid": uid, "kind": "art", "name": name}
        put(rec, "where", clean(a.get("location_string"), 60))
        put(rec, "desc", clean(a.get("description"), PLACE_DESC))
        put(rec, "by", clean(a.get("artist"), 80))
        art.append(rec)
        place[uid] = rec

    # --- events ----------------------------------------------------------------------
    events, occurrences = [], 0
    for e in raw.get("events") or []:
        uid, title = e.get("uid"), clean(e.get("title"), 140)
        if not uid or not title:
            continue
        occ = []
        for o in e.get("occurrence_set") or []:
            start = epoch(o.get("start_time"))
            if start is None:
                continue
            end = epoch(o.get("end_time"))
            occ.append([start, end] if end is not None else [start])
        if not occ:
            # No time at all is no event: it can never be "on now", it can never be
            # listed under a window, and it would only ever surface as a ghost in search.
            continue
        occ.sort()
        host = place.get(e.get("hosted_by_camp")) or place.get(e.get("located_at_art"))
        where = ""
        if host:
            where = host["name"] + (" at " + host["where"] if host.get("where") else "")
        elif e.get("other_location"):
            where = clean(e["other_location"], 80)
        rec = {"uid": uid, "title": title, "kind": kind_of((e.get("event_type") or {}).get("label")),
               "occ": occ}
        put(rec, "desc", clean(e.get("description"), EVENT_DESC))
        put(rec, "where", where)
        # The uid of the camp or art the event hangs off, so the phone's detail sheet can
        # open THAT place from the event without a second index.
        if host:
            rec["at"] = host["uid"]
        if e.get("all_day"):
            rec["all_day"] = 1
        events.append(rec)
        occurrences += len(occ)

    events.sort(key=lambda r: (r["occ"][0][0], r["title"]))
    camps.sort(key=lambda r: r["name"].lower())
    art.sort(key=lambda r: r["name"].lower())
    return {
        "fetched_at": raw.get("fetched_at"),
        "year": raw.get("year"),
        "kinds": kinds,
        "events": events,
        "camps": camps,
        "art": art,
    }, occurrences


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=os.environ.get("ORACLE_SNAPSHOT") or SNAPSHOT)
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.snapshot):
        # Not an error: a checkout without the gitignored dump still deploys, and the
        # Worker degrades to a Turtle that knows the 52 cards and says so.
        print(f"build_city: no snapshot at {args.snapshot} — the Worker will have no city "
              f"in it (that is a supported state, not a failure)", file=sys.stderr)
        return 0

    with open(args.snapshot, encoding="utf-8") as f:
        raw = json.load(f)
    city, occurrences = build(raw)

    os.makedirs(args.out, exist_ok=True)
    city_path = os.path.join(args.out, "city.json")
    meta_path = os.path.join(args.out, "city.meta.json")
    # separators: no space after ':' or ',' — ~180KB of the raw file, all of it CPU.
    blob = json.dumps(city, ensure_ascii=False, separators=(",", ":"))
    with open(city_path, "w", encoding="utf-8") as f:
        f.write(blob)

    meta = {
        "fetched_at": city["fetched_at"],
        "year": city["year"],
        "built_at": datetime.datetime.now(datetime.timezone.utc)
                            .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "counts": {"events": len(city["events"]), "camps": len(city["camps"]),
                   "art": len(city["art"]), "occurrences": occurrences},
        "bytes": len(blob.encode("utf-8")),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    if not args.quiet:
        print(f"build_city: {meta['counts']['events']} events ({occurrences} occurrences), "
              f"{meta['counts']['camps']} camps, {meta['counts']['art']} art -> "
              f"{meta['bytes'] / 1024.0 / 1024.0:.2f} MB  {city_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
