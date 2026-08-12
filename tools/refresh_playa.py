#!/usr/bin/env python3
"""Flip `pending_api` hooks in data/playa_2026.json using the API snapshot.

Reads `data/brc_<year>_snapshot.json` (written by tools/fetch_brc.py) and, for
every `camp:` / `art:` hook, tries to match the hook's `instances` against the
real registry by name. A hook is only rewritten when the match is
**unambiguous** — one candidate, exact name first, case-insensitive substring
second. Everything else is left exactly as it was and reported.

A rewritten hook gets: `status: "fixed"`, the real `address`
(`"E & 6:15"`, `"4:45 8000', Airport"`), `gps` for art, a `source` stamp, and
`directions` with the address in front and the now-stale "check the WWW guide in
August" hedge trimmed off the end.

**Embargo.** Third-party placements are under the Burning Man API terms (art
until gates, camps until the Sunday prior) and this repo is public — so a full
refresh belongs on the camp laptop, not in a commit. `--only-own-camp` applies
just the hooks that resolve to Terrible Turtle's own record, which we may
publish; that result is safe to commit. Run the full refresh on the playa.

Usage:
    python3 tools/refresh_playa.py --only-own-camp     # committable
    python3 tools/refresh_playa.py --dry-run           # report, write nothing
    python3 tools/refresh_playa.py                     # full refresh (local only)
    python3 tools/refresh_playa.py --report /tmp/refresh_report.txt
"""
import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYA = os.path.join(REPO, "data", "playa_2026.json")

OWN_CAMP_UID = "a1XVI00000FLKvx2AH"
OWN_CAMP_NAME = "Terrible Turtle"

# Sentences/parentheticals that only existed because the placement was unknown.
HEDGE = re.compile(r"art map|www guide|at gates|bm api|the api|in august|exact spot|"
                   r"address (?:via|in|drops)|placement drops|tbd", re.I)
MIN_REVERSE = 5   # a registry name shorter than this can't match by substring ("G", "NO")


def norm(s):
    """Lowercase, punctuation-free, single-spaced — for name comparison only."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def query_forms(instance):
    """The name(s) to try for one hook instance: the whole thing, and minus '(asides)'."""
    forms = [instance, re.sub(r"\(.*?\)", " ", instance)]
    seen, out = set(), []
    for f in forms:
        q = norm(f)
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def match(instances, rows):
    """Unambiguous match or nothing. Returns (rows_matched, tier)."""
    for tier, test in (("exact", lambda q, n: q == n),
                       ("substring", lambda q, n: (q in n) or (len(n) >= MIN_REVERSE and n in q))):
        hits, seen = [], set()
        for inst in instances:
            for q in query_forms(inst):
                for row in rows:
                    n = norm(row.get("name"))
                    if n and test(q, n) and row.get("uid") not in seen:
                        seen.add(row.get("uid"))
                        hits.append(row)
        if hits:
            return hits, tier
    return [], None


def trim_hedge(text):
    """Drop trailing '(…art map at gates)' asides, sentences and clauses that only
    existed while the placement was unknown. Never empties the text."""
    for _ in range(4):
        aside = re.search(r"\s*\(([^()]*)\)\s*\.?\s*$", text)
        if aside and HEDGE.search(aside.group(1)):
            text = text[:aside.start()].rstrip(" ,;—-")
            text += "" if text.endswith((".", "!", "?")) else "."
            continue
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if len(sentences) > 1 and HEDGE.search(sentences[-1]):
            text = " ".join(sentences[:-1]).strip()
            continue
        sep = None
        for m in re.finditer(r"\s*—\s*|\s*;\s*", text):
            sep = m
        if sep and sep.start() and HEDGE.search(text[sep.end():]):
            text = text[:sep.start()].rstrip(" ,")
            text += "" if text.endswith((".", "!", "?")) else "."
            continue
        break
    return text


def compose(address, detail, base, previous=None):
    """'E & 6:15 (mid-block facing man). Home. Your own shell — …'

    `previous` is the address a past run already prefixed, stripped so a re-run
    (placements move right up to the event) doesn't stack addresses.
    """
    head = address + (f" ({detail.strip().rstrip('.').lower()})" if detail else "")
    base = base or ""
    if previous:
        base = re.sub(r"^" + re.escape(previous) + r"(\s*\([^()]*\))?[.,]?\s*", "", base)
    base = trim_hedge(base)
    return f"{head}. {base}".strip() if base else f"{head}."


def events_for(camp_uid, events, limit=3):
    """This camp's registered events, earliest occurrence first — quest material."""
    out = []
    for e in events:
        if e.get("hosted_by_camp") != camp_uid:
            continue
        starts = sorted(o.get("start_time", "") for o in (e.get("occurrence_set") or []))
        out.append({"title": e.get("title"), "start": starts[0] if starts else None})
    out.sort(key=lambda e: e["start"] or "9999")
    return out[:limit]


def resolve(key, hook, snap):
    """(action, note, patch) for one hook. action: updated/ambiguous/not-found/skipped."""
    kind = "camp" if key.startswith("camp:") else "art" if key.startswith("art:") else None
    if kind is None:
        return "skipped", f"not a camp/art hook (status={hook.get('status')})", None
    if hook.get("status") != "pending_api" and "source" not in hook:
        return "skipped", f"status={hook.get('status')} — not from the API, left alone", None

    rows = snap["camps"] if kind == "camp" else snap["art"]
    hits, tier = match(hook.get("instances") or [], rows)
    if not hits:
        return "not-found", f"no {kind} named {hook.get('instances')}", None
    if len(hits) > 1:
        return "ambiguous", f"{len(hits)} candidates: {[h.get('name') for h in hits]}", None

    row = hits[0]
    loc = row.get("location") or {}
    address = row.get("location_string")
    if not address:
        return "not-found", f"matched {row.get('name')!r} but it has no location_string yet", None

    patch = {
        "status": "fixed",
        "address": address,
        "directions": compose(address, loc.get("exact_location", ""),
                              hook.get("directions"), previous=hook.get("address")),
        "source": {"kind": kind, "uid": row.get("uid"), "name": row.get("name"),
                   "year": snap.get("year"), "fetched_at": snap.get("fetched_at")},
    }
    if loc.get("gps_latitude") is not None and loc.get("gps_longitude") is not None:
        patch["gps"] = [round(loc["gps_latitude"], 6), round(loc["gps_longitude"], 6)]
    if kind == "camp":
        evs = events_for(row.get("uid"), snap.get("events") or [])
        if evs:
            patch["events"] = evs
    note = f"{tier} match {row.get('name')!r} -> {address}"
    if HEDGE.search(patch["directions"]):
        note += "  [directions still hedge — worth a human line edit]"
    return "updated", note, patch


def is_own_camp(patch):
    src = (patch or {}).get("source") or {}
    return src.get("kind") == "camp" and (
        src.get("uid") == OWN_CAMP_UID or OWN_CAMP_NAME.lower() in (src.get("name") or "").lower())


def dump_playa(playa, path):
    """Rewrite the file the way it is kept by hand: meta indented, one line per hook."""
    if set(playa) != {"meta", "hooks"}:                      # shape changed — don't guess
        with open(path, "w", encoding="utf-8") as f:
            json.dump(playa, f, ensure_ascii=False, indent=1)
            f.write("\n")
        return
    meta = json.dumps(playa["meta"], ensure_ascii=False, indent=2)
    meta = "\n".join(("  " + ln) if i else ln for i, ln in enumerate(meta.split("\n")))
    hooks = []
    for key, hook in playa["hooks"].items():
        inner = ", ".join(f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
                          for k, v in hook.items())
        hooks.append(f"    {json.dumps(key, ensure_ascii=False)}: {{ {inner} }}")
    with open(path, "w", encoding="utf-8") as f:
        f.write('{\n  "meta": ' + meta + ',\n  "hooks": {\n'
                + ",\n".join(hooks) + "\n  }\n}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--snapshot", help="default data/brc_<year>_snapshot.json")
    ap.add_argument("--playa", default=PLAYA)
    ap.add_argument("--only-own-camp", action="store_true",
                    help="apply only hooks resolving to Terrible Turtle (embargo-safe)")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    ap.add_argument("--report", help="also write the report to this file")
    args = ap.parse_args()

    snapshot = args.snapshot or os.path.join(REPO, "data", f"brc_{args.year}_snapshot.json")
    if not os.path.exists(snapshot):
        sys.exit(f"no snapshot at {snapshot} — run: python3 tools/fetch_brc.py --year {args.year}")
    with open(snapshot, encoding="utf-8") as f:
        snap = json.load(f)
    with open(args.playa, encoding="utf-8") as f:
        playa = json.load(f)

    lines = [f"refresh_playa {args.year} — snapshot {snap.get('fetched_at')} "
             f"({len(snap.get('camps', []))} camps, {len(snap.get('art', []))} art, "
             f"{len(snap.get('events', []))} events)",
             f"mode: {'own-camp-only' if args.only_own_camp else 'full'}"
             f"{' (dry run)' if args.dry_run else ''}", ""]
    counts = {}
    for key, hook in playa["hooks"].items():
        action, note, patch = resolve(key, hook, snap)
        if action == "updated" and args.only_own_camp and not is_own_camp(patch):
            action, note = "held", f"embargoed — {note}"
            patch = None
        counts[action] = counts.get(action, 0) + 1
        lines.append(f"  {action:10s} {key:24s} {note}")
        if patch:
            hook.update(patch)

    lines += ["", "  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
    if not args.dry_run:
        dump_playa(playa, args.playa)
        lines.append(f"  wrote {os.path.relpath(args.playa, REPO)}")
        if not args.only_own_camp:
            lines.append("  EMBARGO: third-party placements are in this file — do not commit it.")

    report = "\n".join(lines)
    print(report)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report + "\n")


if __name__ == "__main__":
    main()
