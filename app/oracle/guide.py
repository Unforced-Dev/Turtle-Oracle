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

# What a detail sheet may show. The dump's longest camp blurb is a few thousand characters;
# this is a ceiling against one pathological record filling a tablet (and the wire).
MAX_DESC = 2400
# What one browse response may carry. A tablet on camp wifi does not want the whole city.
MAX_PAGE = 120
DEFAULT_PAGE = 40

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


def _normname(s):
    """A name flattened for matching: no parenthetical aside, no punctuation, no leading 'the'."""
    s = re.sub(r"\(.*?\)", " ", s or "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"^the ", "", s)


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
        rec = {"kind": "camp", "uid": c.get("uid") or "", "name": c.get("name") or "",
               "where": c.get("location_string") or "", "addr": c.get("location_string") or "",
               "desc": (c.get("description") or "")[:600],
               # the sheet shows the WHOLE description; the retrieval block never does,
               # because the model's context is the thing being rationed, not the tablet's
               "full": (c.get("description") or "")[:MAX_DESC],
               "hometown": c.get("hometown") or "", "landmark": c.get("landmark") or "",
               "extra": c.get("landmark") or c.get("hometown") or ""}
        rec["name_tok"] = _tokenset(rec["name"])
        rec["tok"] = rec["name_tok"] | _tokenset(rec["desc"]) | _tokenset(rec["extra"])
        camps.append(rec)
        if c.get("uid"):
            by_uid[c["uid"]] = rec
    for a in raw.get("art") or []:
        rec = {"kind": "art", "uid": a.get("uid") or "", "name": a.get("name") or "",
               "where": a.get("location_string") or "", "addr": a.get("location_string") or "",
               "desc": (a.get("description") or "")[:600],
               "full": (a.get("description") or "")[:MAX_DESC],
               "hometown": a.get("hometown") or "", "artist": a.get("artist") or "",
               "extra": a.get("artist") or "", "category": a.get("category") or ""}
        rec["name_tok"] = _tokenset(rec["name"])
        rec["tok"] = rec["name_tok"] | _tokenset(rec["desc"]) | _tokenset(rec["extra"])
        art.append(rec)
        if a.get("uid"):
            by_uid[a["uid"]] = rec
    for e in raw.get("events") or []:
        host_uid = e.get("hosted_by_camp") or e.get("located_at_art") or ""
        host = by_uid.get(e.get("hosted_by_camp")) or by_uid.get(e.get("located_at_art"))
        where = ""
        if host:
            where = f"{host['name']}" + (f" at {host['where']}" if host["where"] else "")
        elif e.get("other_location"):
            where = str(e["other_location"])
        rec = {
            "kind": "event",
            "uid": e.get("uid") or "",
            "name": e.get("title") or "",
            "type": ((e.get("event_type") or {}).get("label") or "Other"),
            "desc": (e.get("description") or "")[:500],
            "full": (e.get("description") or "")[:MAX_DESC],
            "where": where,
            "host_name": host["name"] if host else "",
            "host_uid": host_uid if host else "",
            "host_addr": (host.get("addr") or "") if host else "",
            "other_location": str(e.get("other_location") or ""),
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
    by_host = {}
    for i, rec in enumerate(events):
        for start, end in rec["occ"]:
            occ.append((start, end, i))
        if rec["host_uid"]:
            by_host.setdefault(rec["host_uid"], []).append(i)
        if rec["uid"]:
            by_uid[rec["uid"]] = rec
    occ.sort(key=lambda t: t[0])
    # name -> record, for resolving a card's real_2026 placement and a quest's named place
    by_name = {}
    for rec in camps + art:
        by_name.setdefault(_normname(rec["name"]), rec)
    return {"camps": camps, "art": art, "events": events, "occ": occ,
            "by_uid": by_uid, "by_host": by_host, "by_name": by_name,
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
                      "by_uid": {}, "by_host": {}, "by_name": {},
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
        # ...and it runs to 5am, because a burn night does. Ending "tonight" at 23:59 hid
        # every 1am set from both the Turtle and the browse view's Tonight chip.
        return _at(day, 17), _at(tomorrow, 5), "tonight"
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
        hits.append({"title": rec["name"], "kind": rec["type"], "uid": rec["uid"],
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
                         "uid": r["uid"], "when": "", "where": r["where"]})

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


# --- browsing the city: what is on, what a thing is, where it stands ------------------
#
# THE THIRD LENS. The Turtle answers questions well, but a seeker who does not yet know
# what to ask needs to be able to just LOOK — and then to tap what they see. Everything
# below serves that: one shape for an item (a camp, an art piece, an event), one window
# vocabulary, and a server-side filter over the in-memory index so the tablet never holds
# the city. Same clock rules as the rest of this module: playa time, caller may pin it.

BROWSE_WINDOWS = ("now", "tonight", "tomorrow", "all")
# How far "all" reaches. The dump ends on the Sunday; a week from now covers whatever is
# left of the burn without ever handing back the days already spent.
ALL_DAYS = 7


def browse_window(key, now=None):
    """(start, end, label) for a browse chip. 'tonight' and 'tomorrow' are the SAME windows
    the Turtle uses when it is asked in words — one meaning of tonight in the whole kiosk."""
    now = now or now_playa()
    key = (key or "now").strip().lower()
    if key == "tonight":
        return window_for("tonight", now)
    if key == "tomorrow":
        return window_for("tomorrow", now)
    if key == "all":
        return now, now + datetime.timedelta(days=ALL_DAYS), "the rest of the burn"
    return now, now + datetime.timedelta(hours=2), "right now"


def _current_or_next(rec, now):
    """(start, end, live) for the occurrence a seeker can still walk to — the one running
    now if there is one, else the next to come. None when the burn is done with it."""
    best = None
    for s, e in rec["occ"]:
        stop = e or (s + datetime.timedelta(hours=1))
        if s <= now < stop:
            return (s, e, True)
        if s >= now and (best is None or s < best[0]):
            best = (s, e, False)
    return best


def _occurrences(rec, now, days=2, cap=12):
    """Every occurrence today and tomorrow, playa time, each flagged if it is live."""
    out = []
    horizon = (now + datetime.timedelta(days=days - 1)).date()
    for s, e in sorted(rec["occ"], key=lambda t: t[0]):
        if s.date() < now.date() or s.date() > horizon:
            continue
        stop = e or (s + datetime.timedelta(hours=1))
        out.append({"when": _when(s, e, now), "live": bool(s <= now < stop),
                    "over": bool(stop <= now)})
        if len(out) >= cap:
            break
    return out


def item_payload(rec, now=None, full=False):
    """The one shape every list row and every detail sheet is drawn from."""
    now = now or now_playa()
    out = {"uid": rec.get("uid") or "", "kind": rec["kind"], "title": rec["name"],
           "where": rec.get("where") or "", "address": rec.get("addr") or "",
           "desc": (rec.get("full") if full else rec.get("desc")) or ""}
    if rec["kind"] == "event":
        nxt = _current_or_next(rec, now)
        out.update({
            "type": rec["type"], "host": rec.get("host_name") or "",
            "host_uid": rec.get("host_uid") or "",
            "address": rec.get("host_addr") or "",
            "other_location": rec.get("other_location") or "",
            "all_day": bool(rec.get("all_day")),
            "when": _when(nxt[0], nxt[1], now) if nxt else "no more of it this burn",
            "live": bool(nxt and nxt[2]),
            "over": nxt is None,
        })
        if full:
            out["occurrences"] = _occurrences(rec, now)
    else:
        out.update({
            "type": rec.get("category") or ("Camp" if rec["kind"] == "camp" else "Art"),
            "hometown": rec.get("hometown") or "", "artist": rec.get("artist") or "",
            "landmark": rec.get("landmark") or "",
            "when": "", "live": False, "over": False,
        })
    return out


def happening(window="now", kind="", q="", now=None, limit=DEFAULT_PAGE, offset=0):
    """Events in a window, soonest first, filtered server-side over the in-memory index.

    Returns {items, total, offset, limit, window, label, kinds, have_snapshot}. ``kinds``
    is the event types actually present in this window — the filter never offers a label
    that would come back empty.
    """
    now = now or now_playa()
    idx = index()
    start, end, label = browse_window(window, now)
    try:
        limit = max(1, min(int(limit or DEFAULT_PAGE), MAX_PAGE))
    except (TypeError, ValueError):
        limit = DEFAULT_PAGE
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    qtok = set(t for t in _tokens(q) if t not in TIME_WORDS)
    want = (kind or "").strip().lower()

    # TOMORROW MEANS THINGS THAT BEGIN TOMORROW. A set that starts at 13:00 today and runs
    # to 01:00 overlaps the tomorrow window, and listing it there — under a stamp reading
    # "today" — is how a browse view stops being believable. Every other window keeps plain
    # overlap, because a thing already running IS happening now.
    starts_only = (window or "").strip().lower() == "tomorrow"
    rows, kinds, seen = [], {}, set()
    for s, e, i in idx["occ"]:
        if s >= end:
            break                       # occ is sorted by start: nothing later can qualify
        stop = e or (s + datetime.timedelta(hours=1))
        # An all-day thing that ran 06:00-18:00 overlaps the Tonight window and is still
        # over at half past nine. "What's happening" may never lead with a thing that has
        # already finished — the window says which hours, `now` says which are left.
        if stop <= start or stop <= now or (starts_only and s < start):
            continue
        rec = idx["events"][i]
        key = rec["uid"] or rec["name"]
        if key in seen:                 # one row per event, at its soonest occurrence
            continue
        if qtok and not (qtok & rec["tok"]):
            continue
        seen.add(key)
        kinds[rec["type"]] = kinds.get(rec["type"], 0) + 1
        if want and rec["type"].lower() != want:
            continue
        rows.append((not (s <= now < stop), s, e, rec))

    # what is already going, then what is coming, soonest first
    rows.sort(key=lambda t: (t[0], t[1]))
    total = len(rows)
    items = []
    for _live, s, e, rec in rows[offset:offset + limit]:
        it = item_payload(rec, now)
        stop = e or (s + datetime.timedelta(hours=1))
        it["when"] = _when(s, e, now)   # the occurrence IN THIS WINDOW, not the next one
        it["live"] = bool(s <= now < stop)
        items.append(it)
    return {"items": items, "total": total, "offset": offset, "limit": limit,
            "window": (window or "now").strip().lower(), "label": label,
            "kinds": [{"label": k, "count": v}
                      for k, v in sorted(kinds.items(), key=lambda t: (-t[1], t[0]))],
            "have_snapshot": idx["have"]}


# Camps and art are places you can walk to; an event is a time. When a search matches both,
# the place goes first — it is the answer that is still true in an hour.
KIND_RANK = {"camp": 0, "art": 1, "event": 2}
MAX_SEARCH = 60


def search(q, now=None, limit=MAX_SEARCH):
    """One ranked list across events, camps and art. Empty query returns nothing, honestly."""
    now = now or now_playa()
    idx = index()
    try:
        limit = max(1, min(int(limit or MAX_SEARCH), MAX_PAGE))
    except (TypeError, ValueError):
        limit = MAX_SEARCH
    qtok = set(t for t in _tokens(q) if t not in TIME_WORDS)
    if not qtok:
        return {"items": [], "total": 0, "q": q or "", "have_snapshot": idx["have"]}
    scored = []
    for bucket, weight in ((idx["camps"], 5), (idx["art"], 5), (idx["events"], 3)):
        for rec in bucket:
            sc = _score(rec, qtok, name_weight=weight)
            if sc <= 0:
                continue
            over = False
            if rec["kind"] == "event":
                over = _current_or_next(rec, now) is None
            # a thing that is over still answers the question, but it answers it last
            scored.append((over, -sc, KIND_RANK[rec["kind"]], rec))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    items = [item_payload(rec, now) for _o, _s, _k, rec in scored[:limit]]
    return {"items": items, "total": len(scored), "q": q or "",
            "have_snapshot": idx["have"]}


def item(uid=None, name=None, now=None):
    """One thing, whole: full description, where it stands, and — for a camp or an art
    piece — what it is still hosting. None when the shell has never heard of it."""
    now = now or now_playa()
    idx = index()
    rec = None
    if uid:
        rec = idx["by_uid"].get(uid)
    if rec is None and name:
        rec = idx["by_name"].get(_normname(name))
    if rec is None:
        return None
    out = item_payload(rec, now, full=True)
    if rec["kind"] == "event":
        host = idx["by_uid"].get(rec.get("host_uid") or "")
        if host:
            out["host_hometown"] = host.get("hometown") or ""
            out["host_landmark"] = host.get("landmark") or ""
    else:
        upcoming = []
        for i in idx["by_host"].get(rec.get("uid") or "", []):
            ev = idx["events"][i]
            nxt = _current_or_next(ev, now)
            if not nxt:
                continue
            it = item_payload(ev, now)
            upcoming.append((nxt[0], it))
        upcoming.sort(key=lambda t: t[0])
        out["events"] = [it for _s, it in upcoming[:8]]
    return out


# Which real_2026 types name a thing that STANDS somewhere. The rest — principle, ritual,
# workshop, deep-playa, place — are ideas about the city, not addresses in it, and pinning
# a made-up placement under "Leave No Trace" is the one thing this must never do.
PLACED_TYPES = {
    "camp": ("camp", "art"), "camp-terrible-turtle": ("camp", "art"),
    "art": ("art", "camp"), "man": ("art",), "temple": ("art",), "artcar": ("art", "camp"),
}
# A loose substring match is how "Terrible Turtle Camp" finds "Terrible Turtle" — and also
# how "The Tea House" would wrongly find "Honey Pot Tea House". Names must be close in
# LENGTH as well as content before the shell will call them the same place.
NEAR_ENOUGH = 0.6


def resolve_place(real, now=None):
    """The snapshot record a card's ``real_2026`` placement points at, or None."""
    if not isinstance(real, dict):
        return None
    pools = PLACED_TYPES.get(real.get("type") or "")
    if not pools:
        return None
    want = _normname(real.get("name") or "")
    if not want:
        return None
    idx = index()
    by = {"camp": idx["camps"], "art": idx["art"]}
    exact = idx["by_name"].get(want)
    if exact is not None and exact["kind"] in pools:
        return exact
    if len(want) < 6:
        return None
    for kind in pools:
        for rec in by[kind]:
            got = _normname(rec["name"])
            if len(got) < 6 or not (want in got or got in want):
                continue
            if min(len(want), len(got)) / float(max(len(want), len(got))) < NEAR_ENOUGH:
                continue
            return rec
    return None


SEANCE_HOURS = 6
MAX_SEANCE_ITEMS = 24


def for_seance(sid, now=None):
    """The city, filtered by one seeker's draw: the bite card's real placement pinned at
    the top, then what is on in the next six hours that touches the same words.

    Returns the same item shape as everything else, so the kiosk draws one kind of row.
    """
    now = now or now_playa()
    idx = index()
    out = {"pin": None, "items": [], "card": None, "label": "the next six hours",
           "have_snapshot": idx["have"]}
    try:
        from . import session
        from .weave import bite_realm
        sess = session.SESSIONS.get(sid)
    except Exception:
        return out
    if not sess or not sess.get("picks") or not sess.get("located"):
        return out
    bite = sess.get("bite") or bite_realm(sess["located"], sess["picks"])
    card = sess["picks"].get(bite) or sess["picks"].get("trunk")
    if not card:
        return out
    out["card"] = {"name": card["name"], "realm": card["realm"], "slot": bite,
                   "keywords": list(card.get("keywords") or [])}

    place = resolve_place(card.get("real_2026"), now)
    if place is not None:
        out["pin"] = item_payload(place, now)
        out["pin"]["why"] = f'where {card["name"]} stands in the city'

    # the words of the draw: the card's name and keywords, plus what the Turtle actually
    # said. The reading is the seeker's own thread — an event that echoes it is the point.
    words = " ".join([card["name"], " ".join(card.get("keywords") or []),
                      card.get("reading") or "", sess.get("reading") or "",
                      sess.get("adventure") or ""])
    ctok = set(t for t in _tokens(words) if t not in TIME_WORDS)
    start, end = now, now + datetime.timedelta(hours=SEANCE_HOURS)
    pin_uid = (out["pin"] or {}).get("uid")
    scored, seen = [], set()
    for s, e, i in idx["occ"]:
        if s >= end:
            break
        stop = e or (s + datetime.timedelta(hours=1))
        if stop <= start:
            continue
        rec = idx["events"][i]
        key = rec["uid"] or rec["name"]
        if key in seen:
            continue
        seen.add(key)
        sc = _score(rec, ctok)
        # an event AT the pinned place belongs on this list whatever its words say
        if rec.get("host_uid") and rec["host_uid"] == pin_uid:
            sc += 6
        if sc <= 0:
            continue
        it = item_payload(rec, now)
        it["when"] = _when(s, e, now)
        it["live"] = bool(s <= now < stop)
        scored.append((-sc, s, it))
    scored.sort(key=lambda t: (t[0], t[1]))
    out["items"] = [it for _sc, _s, it in scored[:MAX_SEANCE_ITEMS]]
    return out
