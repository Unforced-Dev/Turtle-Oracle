"""The Turtle's memory of the city: what is on, where camps and art stand, what a card means.

Stdlib only. Reads the gitignored BRC dump (``data/brc_2026_snapshot.json``) lazily, on the
first question anyone asks, and builds a small in-memory index. If that file is not on the
box — it is gitignored, because the API ToS embargoes public display of placements — the
guide still answers about the 52 cards, and says plainly that it has no city in it.

TIME IS NOT THE MACHINE'S TIME. The Spark's clock runs America/Denver; the playa runs
America/Los_Angeles, one hour behind. A naive ``datetime.now()`` puts "tonight" an hour
into the future and quietly serves tomorrow's events. Everything here starts from
``datetime.now(timezone.utc)`` and converts explicitly, and every caller may pass its own
``now`` so a test can pin one.
"""
import datetime
import json
import os
import re
import threading

from .deck import REPO, load_deck
from .weave import card_lore

try:                                            # py3.9+ on the Spark
    from zoneinfo import ZoneInfo
    PLAYA_TZ = ZoneInfo("America/Los_Angeles")
except Exception:                               # pragma: no cover - ancient python
    PLAYA_TZ = datetime.timezone(datetime.timedelta(hours=-7), "PDT")

SNAPSHOT = os.environ.get("ORACLE_SNAPSHOT") or os.path.join(
    REPO, "data", "brc_2026_snapshot.json")
PLAYA_FILE = os.path.join(REPO, "data", "playa_2026.json")

# ~1500 tokens of context, measured the cheap way. English prose runs near four characters
# to the token; place lines run denser, so this is a ceiling, not an estimate.
MAX_BLOCK_CHARS = int(os.environ.get("ORACLE_GUIDE_CHARS", "6000"))

STOP = set("""a an and are as at be been being but by can could did do does for from get got
had has have he her here him his how i if in into is it its just me my no not of on or our
out over she should so some such than that the their them then there these they this those
to too us was we were what when where which who whom why will with would you your yours
about after again all any because before between during more most other same up down
tell told know knows want need find give given say says see look looking let ask asked
please thing things something anything someone somewhere near around much many kind
best good great turtle oracle shell camp place places going come coming""".split())

# Words that steer the clock, not the search. "what is happening tonight" must not go
# hunting for a camp with "tonight" in its name.
TIME_WORDS = set("""now tonight today tomorrow morning afternoon evening night sunrise
sunset later happening going soon next upcoming right currently""".split())

# The one thing the dump does not hold: who is behind the decks. There are no set times,
# no lineups, no art-car schedules in the API. Never let the Turtle improvise one.
LINEUP_RE = re.compile(
    r"\b(dj|djs|line[- ]?up|lineups?|set ?times?|headlin\w*|b2b|playing at|who'?s? (is )?playing|"
    r"spinning|on the decks|schedule for|art car)\b", re.I)

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9:'&]*")

_LOCK = threading.Lock()
_INDEX = None


def _tokens(text):
    return [t for t in TOKEN_RE.findall((text or "").lower()) if len(t) > 2 and t not in STOP]


def _tokenset(text):
    return set(_tokens(text))


def _parse_time(s):
    """'2026-09-05T21:00:00-07:00' -> aware datetime in playa time, or None."""
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PLAYA_TZ)
    return dt.astimezone(PLAYA_TZ)


def now_playa():
    """The only clock this module trusts."""
    return datetime.datetime.now(datetime.timezone.utc).astimezone(PLAYA_TZ)


def home_camp():
    """Our own placement, from the app overlay — the one address the Turtle may hand out."""
    try:
        with open(PLAYA_FILE, encoding="utf-8") as f:
            hook = json.load(f)["hooks"]["camp:terrible-turtle"]
        return {"name": "Terrible Turtle Camp",
                "address": hook.get("address") or "",
                "directions": hook.get("directions") or ""}
    except Exception:
        return {"name": "Terrible Turtle Camp", "address": "", "directions": ""}


# --- the index ----------------------------------------------------------------------

def _build(raw):
    camps, art, events = [], [], []
    by_uid = {}
    for c in raw.get("camps") or []:
        rec = {"kind": "camp", "name": c.get("name") or "", "where": c.get("location_string") or "",
               "desc": (c.get("description") or "")[:600],
               "extra": c.get("landmark") or c.get("hometown") or ""}
        rec["name_tok"] = _tokenset(rec["name"])
        rec["tok"] = rec["name_tok"] | _tokenset(rec["desc"]) | _tokenset(rec["extra"])
        camps.append(rec)
        if c.get("uid"):
            by_uid[c["uid"]] = rec
    for a in raw.get("art") or []:
        rec = {"kind": "art", "name": a.get("name") or "", "where": a.get("location_string") or "",
               "desc": (a.get("description") or "")[:600],
               "extra": a.get("artist") or "", "category": a.get("category") or ""}
        rec["name_tok"] = _tokenset(rec["name"])
        rec["tok"] = rec["name_tok"] | _tokenset(rec["desc"]) | _tokenset(rec["extra"])
        art.append(rec)
        if a.get("uid"):
            by_uid[a["uid"]] = rec
    for e in raw.get("events") or []:
        host = by_uid.get(e.get("hosted_by_camp")) or by_uid.get(e.get("located_at_art"))
        where = ""
        if host:
            where = f"{host['name']}" + (f" at {host['where']}" if host["where"] else "")
        elif e.get("other_location"):
            where = str(e["other_location"])
        rec = {
            "kind": "event",
            "name": e.get("title") or "",
            "type": ((e.get("event_type") or {}).get("label") or "Other"),
            "desc": (e.get("description") or "")[:500],
            "where": where,
            "all_day": bool(e.get("all_day")),
            "occ": [],
        }
        for o in e.get("occurrence_set") or []:
            start = _parse_time(o.get("start_time"))
            if not start:
                continue
            rec["occ"].append((start, _parse_time(o.get("end_time"))))
        if not rec["occ"]:
            continue
        rec["name_tok"] = _tokenset(rec["name"])
        rec["tok"] = rec["name_tok"] | _tokenset(rec["desc"]) | _tokenset(rec["type"]) \
            | _tokenset(rec["where"])
        events.append(rec)
    occ = []
    for i, rec in enumerate(events):
        for start, end in rec["occ"]:
            occ.append((start, end, i))
    occ.sort(key=lambda t: t[0])
    return {"camps": camps, "art": art, "events": events, "occ": occ,
            "fetched_at": raw.get("fetched_at"), "have": True}


def index():
    """Load once, on the first question. Missing file is not an error — it is a smaller Turtle."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    with _LOCK:
        if _INDEX is not None:
            return _INDEX
        try:
            with open(SNAPSHOT, encoding="utf-8") as f:
                _INDEX = _build(json.load(f))
        except Exception:
            _INDEX = {"camps": [], "art": [], "events": [], "occ": [],
                      "fetched_at": None, "have": False}
        return _INDEX


def loaded():
    """True once the dump is in memory. Never forces the parse — /api/health must not be
    the thing that spends 300ms on a cold box."""
    return bool(_INDEX and _INDEX["have"])


def warm():
    """Parse the dump off the request path, so the first seeker does not pay for it."""
    try:
        index()
    except Exception:
        pass


# --- time windows -------------------------------------------------------------------

def _at(day, hour, minute=0):
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def window_for(question, now=None):
    """(start, end, label) in playa time. Default: the next six hours."""
    now = now or now_playa()
    q = (question or "").lower()
    day = now
    tomorrow = now + datetime.timedelta(days=1)
    if "sunrise" in q or "sunup" in q or "dawn" in q:
        target = day if now.hour < 8 else tomorrow
        return _at(target, 4, 30), _at(target, 8, 30), "around sunrise"
    if "tomorrow" in q:
        return _at(tomorrow, 0), _at(tomorrow, 23, 59), "tomorrow"
    if "tonight" in q or "this evening" in q or re.search(r"\blate(r)? tonight\b", q):
        # before 5am the night in progress is still "tonight" — it started yesterday
        if now.hour < 5:
            y = now - datetime.timedelta(days=1)
            return _at(y, 17), _at(now, 5), "tonight"
        return _at(day, 17), _at(day, 23, 59), "tonight"
    if "afternoon" in q:
        return _at(day, 12), _at(day, 17), "this afternoon"
    if "morning" in q:
        target = day if now.hour < 12 else tomorrow
        return _at(target, 6), _at(target, 12), "this morning"
    if re.search(r"\b(right now|now|happening|going on|open now)\b", q):
        return now, now + datetime.timedelta(hours=2), "right now"
    if "today" in q:
        return now, _at(day, 23, 59), "today"
    return now, now + datetime.timedelta(hours=6), "the next six hours"


# --- retrieval ----------------------------------------------------------------------

def _day_word(dt, now):
    if dt.date() == now.date():
        return "today"
    if dt.date() == (now + datetime.timedelta(days=1)).date():
        return "tomorrow"
    if dt.date() == (now - datetime.timedelta(days=1)).date():
        return "yesterday"
    return dt.strftime("%A")


def _when(start, end, now):
    s = start.strftime("%H:%M")
    e = end.strftime("%H:%M") if end else ""
    return (f"{s}–{e}" if e else s) + " " + _day_word(start, now)


def _score(rec, qtok, name_weight=3):
    if not qtok:
        return 0
    return name_weight * len(qtok & rec["name_tok"]) + len(qtok & rec["tok"])


def _line(hit):
    bits = [hit["title"]]
    if hit.get("kind"):
        bits.append(hit["kind"])
    if hit.get("when"):
        bits.append(hit["when"])
    if hit.get("where"):
        bits.append(hit["where"])
    return " — ".join(b for b in bits if b)


def find_card(question):
    """The card a question names, if it names one. Longest name first, so 'The Shell'
    never wins over 'The Shell' inside a longer title."""
    q = " " + re.sub(r"[^a-z0-9 ]+", " ", (question or "").lower()) + " "
    q = re.sub(r"\s+", " ", q)
    _, cards, _ = load_deck()
    best = None
    for c in sorted(cards, key=lambda c: -len(c["name"])):
        n = re.sub(r"[^a-z0-9 ]+", " ", c["name"].lower())
        n = re.sub(r"\s+", " ", n).strip()
        bare = re.sub(r"^the ", "", n)
        for probe in (n, bare):
            if len(probe) >= 4 and (" " + probe + " ") in q:
                return c
    return best


def describe_card(name):
    """One block about a card — meaning, shadow, the dare, and the lore bundle. None if
    nothing in the deck answers to that name."""
    card = None
    _, cards, _ = load_deck()
    want = re.sub(r"^the\s+", "", (name or "").strip().lower())
    for c in cards:
        cn = re.sub(r"^the\s+", "", c["name"].lower())
        if cn == want or want and want in cn:
            card = c
            break
    if not card:
        card = find_card(name)
    if not card:
        return None
    lore = card_lore().get(card["id"], {})
    parts = [f"CARD: {card['name']} ({card['realm']} · {', '.join(card.get('keywords') or [])})",
             f"meaning: {card.get('reading','')}"]
    if card.get("shadow"):
        parts.append(f"the bite: {card['shadow']}")
    if lore.get("essence"):
        parts.append(f"essence: {lore['essence']}")
    if card.get("turtle_dare"):
        parts.append(f"the dare it carries: {card['turtle_dare']}")
    return "\n".join(parts)


def retrieve(question, now=None, k=6):
    """Everything the Turtle is allowed to know about this question, as one block.

    Returns {block, hits, window, have_snapshot, lineup}. ``hits`` is what the kiosk
    draws under the spoken answer; ``block`` is what the model is allowed to speak from.
    """
    now = now or now_playa()
    idx = index()
    start, end, label = window_for(question, now)
    qtok = set(t for t in _tokens(question) if t not in TIME_WORDS)

    hits, lines = [], []

    # events: inside the window first, then ranked by what the question actually said
    scored = []
    for s, e, i in idx["occ"]:
        stop = e or (s + datetime.timedelta(hours=1))
        if stop <= start or s >= end:
            continue
        rec = idx["events"][i]
        scored.append((_score(rec, qtok), -s.timestamp(), s, e, rec))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    seen = set()
    for score, _neg, s, e, rec in scored:
        if rec["name"] in seen:
            continue
        seen.add(rec["name"])
        hits.append({"title": rec["name"], "kind": rec["type"],
                     "when": _when(s, e, now), "where": rec["where"]})
        if len(hits) >= k:
            break

    if hits:
        lines.append(f"EVENTS ({label}):")
        lines += ["- " + _line(h) for h in hits]
    else:
        lines.append(f"EVENTS ({label}): the shell holds none in that window.")

    # camps and art, by what the question named
    for kind, bucket, cap in (("CAMPS", idx["camps"], 4), ("ART", idx["art"], 3)):
        ranked = sorted(((_score(r, qtok, name_weight=5), r) for r in bucket),
                        key=lambda t: -t[0])[:cap]
        keep = [r for sc, r in ranked if sc > 0]
        if not keep:
            continue
        lines.append(f"{kind}:")
        for r in keep:
            desc = re.sub(r"\s+", " ", r["desc"])[:180]
            lines.append(f"- {r['name']}" + (f" at {r['where']}" if r["where"] else "")
                         + (f" — {desc}" if desc else ""))
            hits.append({"title": r["name"], "kind": kind.title()[:-1] if kind != "ART" else "Art",
                         "when": "", "where": r["where"]})

    card = find_card(question)
    if card:
        lines.append(describe_card(card["name"]))

    if not idx["have"]:
        lines = ["THE CITY IS NOT IN THE SHELL: the camp/art/event dump is not on this "
                 "machine, so you know nothing about placements or what is on. Say so "
                 "plainly if you are asked. You still know the 52 cards."] + \
            ([describe_card(card["name"])] if card else [])

    block = "\n".join(lines)
    if len(block) > MAX_BLOCK_CHARS:
        block = block[:MAX_BLOCK_CHARS].rsplit("\n", 1)[0] + "\n(…the rest is dust.)"
    return {"block": block, "hits": hits, "window": label,
            "have_snapshot": idx["have"],
            "card": card["name"] if card else None,
            # the plain meaning, for the no-model answer: a Turtle with no city in it can
            # still say what a card means, and that is most of what it is asked
            "card_meaning": (card.get("reading") if card else None),
            "lineup": bool(LINEUP_RE.search(question or ""))}
