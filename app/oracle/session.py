"""The séance: a staged Oracle conversation → theatrical pull → reading → quest negotiation.

Heavily structured, lightly LLM. The stages are fixed (the ritual); the LLM only fills
warm specifics inside them (the voice). Every LLM touch has a template fallback, so the
whole ceremony runs offline on playa with nothing but the deck.

Stages:
  listening  — the Oracle greeted the seeker, waiting for their first share
  deepening  — the Oracle asked one light follow-up, waiting for more
  proposed   — cards drawn, reading + adventure offered; seeker may accept or share more
  accepted   — the quest is sealed (printable)
"""
import json
import random
import re
import time
import uuid

from .deck import load_deck, card_payload
from .select import select_cards, select_fallback
from .weave import weave, SYSTEM
from .geo import locate_spread, directions_lines, COMPASS_ROSE

SESSIONS = {}
MAX_SESSIONS = 60  # kiosk = one seeker at a time; keep a small tail for stragglers

GREETINGS = [
    "Ah. A traveler. Come closer — the shell is warm. Tell me: how is your burn treating you, truly?",
    "Slow down. Good. Now — what is happening out there in your burn? Tell the Turtle.",
    "Welcome, dusty one. Before any card moves, I must hear you. How are you — not the polite answer, the true one?",
    "Mm. The Tree said someone was coming. Sit. What are you carrying tonight?",
    "You found the shell, which means something in you was looking. How is your burn going — what has it given, what has it taken?",
    "Hello, little flame. The Turtle moves slow, so we have time. Tell me what your burn has been like so far.",
]

FOLLOWUPS = [
    "Mm. And beneath that — what are you most hungry for out here?",
    "The Turtle hears more than words. What have you been avoiding, out there in the dust?",
    "Slowly now. If tonight went exactly right, what would happen?",
    "And what have you been circling — the thing you keep almost doing?",
    "Who or what do you think about when the music stops?",
]

DRAWN_LINES = [
    "Enough. The Turtle has heard you. Watch — the Tree is choosing.",
    "The shell hums. Three cards rise for you: what to face, where you stand, what to reach for.",
    "Good. That is enough truth to pull on. The Tree is choosing your three.",
]

REFINE_ACKS = [
    "Mm. That changes the shape of it. The Tree bends — hear your quest again.",
    "Good. More truth makes a better quest. Listen.",
    "The Turtle chews on that. Slowly. Yes — the quest turns like this.",
]

DECISION_ASK = "Do you accept this quest? Or shall the Turtle hear more before it is sealed?"

ACCEPT_LINES = [
    "So be it. The quest is sealed. Move slow, bite things, and bring your proofs back to the shell.",
    "Sealed. The Tree will be watching, and trees see everything slowly. Go — and come back with the tale.",
]

# Proof-of-quest tokens, one flavor per realm (rotated by card number so quests differ).
PROOFS = {
    "roots": [
        "Bring back the hardest true sentence spoken there — yours or a stranger's.",
        "Bring back the name of what you almost didn't face.",
        "Bring back one word for what you left behind in the dust there.",
        "Bring back the thing you understood there that you didn't before.",
    ],
    "trunk": [
        "Bring back the name of a stranger who stood beside you.",
        "Bring back one thing you only noticed because you stayed still.",
        "Bring back the story of who was there, and why they had come.",
        "Bring back a description of the ground you stood on — exactly as it was.",
    ],
    "branches": [
        "Bring back something given to you freely — a word, a bead, a taste, a promise.",
        "Bring back the wish you said out loud there.",
        "Bring back proof of one small brave thing: what it was, and how it felt.",
        "Bring back the name of the first person you told about it.",
    ],
}

VOW = ("When your three moves are made, return to the Terrible Turtle shell. Find a turtle. "
       "Tell the tale true — your proofs are the witnesses. Those who return and tell "
       "receive a gift from the shell — and while the shell still holds them, that gift "
       "is a deck of this very oracle.")
VOW_WHERE = "Camp placement posts in August — until then, ask any turtle where the shell is parked."

SLOT_TITLES = {"roots": "FACE", "trunk": "STAND", "branches": "REACH"}


def _new_id():
    return uuid.uuid4().hex[:12]


def _gc():
    if len(SESSIONS) <= MAX_SESSIONS:
        return
    for sid, _ in sorted(SESSIONS.items(), key=lambda kv: kv[1]["created"])[:-MAX_SESSIONS]:
        SESSIONS.pop(sid, None)


def _words(s):
    return len((s or "").split())


def _clean_line(s, max_words=40):
    """Sanitize an LLM one-liner: strip quotes/labels, keep it one short question/line."""
    s = (s or "").strip().strip('"').strip("'").strip()
    s = re.sub(r"^(question|follow-?up|oracle|turtle)\s*[:\-]\s*", "", s, flags=re.I).strip()
    s = s.splitlines()[0].strip() if s else ""
    if not s or _words(s) > max_words:
        return None
    return s


def start():
    """Open a séance. Returns the event the kiosk renders/speaks."""
    _gc()
    sid = _new_id()
    SESSIONS[sid] = {
        "id": sid, "stage": "listening", "shares": [], "followups": 0,
        "picks": None, "located": None, "reading": None, "adventure": None,
        "quest": None, "created": time.time(),
    }
    return {"session": sid, "stage": "listening", "say": random.choice(GREETINGS), "expects": "share"}


def _followup_llm(shares, llm):
    prompt = (
        "A seeker at your shell just shared this about their burn:\n"
        + "\n".join(f"- {s}" for s in shares)
        + "\n\nAsk ONE short, warm follow-up question (under 25 words) in the Turtle's voice — wry, "
        "specific to their words, inviting one level deeper. It must be a question. "
        "Return the question only, no quotes, no preamble."
    )
    return _clean_line(llm.generate(prompt, system=SYSTEM, timeout=45), max_words=32)


def _draw(sess, llm):
    """Pull the three, locate them, weave the reading + adventure."""
    _, _, by_realm = load_deck()
    told = " ".join(sess["shares"])
    picks, sel_mode = select_cards(told, by_realm, llm)
    located = locate_spread(picks)
    out, weave_mode = weave(told, picks, llm, located)
    sess.update(picks=picks, located=located, reading=out["reading"],
                adventure=out["adventure"], stage="proposed")
    return {
        "session": sess["id"], "stage": "proposed",
        "say": random.choice(DRAWN_LINES),
        "cards": {r: card_payload(picks[r], located[r]) for r in ("roots", "trunk", "branches")},
        "reading": out["reading"], "adventure": out["adventure"],
        "map": COMPASS_ROSE, "directions": directions_lines(picks, located),
        "ask": DECISION_ASK, "expects": "decision",
        "modes": {"select": sel_mode, "weave": weave_mode},
    }


def _refine_llm(sess, llm):
    picks, located = sess["picks"], sess["located"]
    lines = []
    for realm in ("roots", "trunk", "branches"):
        c, loc = picks[realm], located.get(realm, {})
        lines.append(f'{SLOT_TITLES[realm]} — {c["name"]}: dare="{c["turtle_dare"]}" '
                     f'real_2026="{c["real_2026"]["name"]}" where="{loc.get("directions", "")}"')
    prompt = (
        "The seeker has heard their reading and wants the quest tuned before accepting.\n"
        f"What they shared earlier:\n" + "\n".join(f"- {s}" for s in sess["shares"][:-1])
        + f'\n\nWhat they JUST added — the new truth the rewritten quest MUST visibly use:\n"{sess["shares"][-1]}"\n'
        + f"\nThe drawn cards (KEEP these, do not swap):\n" + "\n".join(lines)
        + f"\n\nThe current quest:\n{sess['adventure']}\n\n"
        "Rewrite the quest around that new truth — same three cards, same three real places, but the "
        "tasks should now put what they just confessed at the center (if they said they secretly sing, "
        "the quest makes them sing). Keep it one night, concrete, doable, with directions. "
        "Also write one short acknowledgement line (under 20 words) the Turtle says first, naming the new truth.\n"
        'Return JSON only: {"say": "...", "adventure": "..."}'
    )
    resp = llm.generate(prompt, system=SYSTEM, as_json=True, timeout=120)
    if not resp:
        return None
    try:
        out = json.loads(resp)
    except Exception:
        return None
    if isinstance(out, dict) and out.get("adventure"):
        return {"say": _clean_line(out.get("say"), 30) or random.choice(REFINE_ACKS),
                "adventure": out["adventure"].strip()}
    return None


def _refine_fallback(sess):
    """No LLM: re-score the realms against the fuller share; the Tree may reconsider a card."""
    _, _, by_realm = load_deck()
    told = " ".join(sess["shares"])
    picks = select_fallback(told, by_realm)
    located = locate_spread(picks)
    out = weave(told, picks, None, located)[0]
    sess.update(picks=picks, located=located, reading=out["reading"])
    return {"say": random.choice(REFINE_ACKS), "adventure": out["adventure"],
            "reading": out["reading"], "picks": picks, "located": located}


def hear(sid, text, llm=None):
    """The seeker speaks. Routes on the session's stage; returns the next event."""
    sess = SESSIONS.get(sid)
    if not sess:
        return {"error": "no such séance — touch the shell to begin again", "stage": "gone"}
    text = (text or "").strip()
    if not text:
        return {"session": sid, "stage": sess["stage"],
                "say": "The Turtle heard only wind. Try again, slower.",
                "expects": "share" if sess["stage"] in ("listening", "deepening") else "decision"}
    if sess["stage"] in ("listening", "deepening"):
        sess["shares"].append(text)
        total = sum(_words(s) for s in sess["shares"])
        # The ritual allows at most two questions; rich shares go straight to the pull.
        if sess["followups"] >= 2 or total >= 35 or (sess["followups"] == 1 and total >= 12):
            return _draw(sess, llm)
        sess["followups"] += 1
        sess["stage"] = "deepening"
        q = (_followup_llm(sess["shares"], llm) if llm and llm.available() else None) \
            or random.choice(FOLLOWUPS)
        return {"session": sid, "stage": "deepening", "say": q, "expects": "share"}
    if sess["stage"] == "proposed":
        sess["shares"].append(text)
        ref = (_refine_llm(sess, llm) if llm and llm.available() else None)
        event = {"session": sid, "stage": "proposed", "map": COMPASS_ROSE,
                 "ask": DECISION_ASK, "expects": "decision"}
        if ref:
            sess["adventure"] = ref["adventure"]
            event.update(say=ref["say"], adventure=ref["adventure"], reading=sess["reading"])
        else:
            fb = _refine_fallback(sess)
            sess["adventure"] = fb["adventure"]
            event.update(say=fb["say"], adventure=fb["adventure"], reading=fb["reading"])
        picks, located = sess["picks"], sess["located"]
        event["cards"] = {r: card_payload(picks[r], located[r]) for r in ("roots", "trunk", "branches")}
        event["directions"] = directions_lines(picks, located)
        return event
    if sess["stage"] == "accepted":
        return {"session": sid, "stage": "accepted", "quest": sess["quest"],
                "say": "The quest is already sealed, traveler. Go live it — the shell will wait.",
                "expects": "done"}
    return {"error": "the Turtle is confused", "stage": sess["stage"]}


def accept(sid):
    """Seal the quest: three moves with places + proofs, the vow, the map."""
    sess = SESSIONS.get(sid)
    if not sess:
        return {"error": "no such séance — touch the shell to begin again", "stage": "gone"}
    if sess["stage"] != "proposed" and not sess["quest"]:
        return {"error": "no quest to accept yet", "stage": sess["stage"]}
    if not sess["quest"]:
        picks, located = sess["picks"], sess["located"]
        r, t, b = picks["roots"], picks["trunk"], picks["branches"]
        moves = []
        for realm in ("roots", "trunk", "branches"):
            c, loc = picks[realm], located.get(realm, {})
            moves.append({
                "slot": SLOT_TITLES[realm], "card": c["name"],
                "where": loc.get("directions", "") or "Somewhere out there — ask Playa Info.",
                "task": f'{c["turtle_dare"]}',
                "at": c["real_2026"]["name"],
                "proof": PROOFS[realm][(c.get("number", 1) - 1) % len(PROOFS[realm])],
            })
        sess["quest"] = {
            "title": f'The Quest of {b["name"]}',
            "charge": (f'Face “{r["name"]}.” Stand in “{t["name"]}.” Reach for “{b["name"]}.” '
                       "Three moves, made slow — then home to the shell."),
            "adventure": sess["adventure"],
            "moves": moves,
            "vow": VOW, "vow_where": VOW_WHERE,
            "map": COMPASS_ROSE,
        }
        sess["stage"] = "accepted"
    return {"session": sid, "stage": "accepted", "say": random.choice(ACCEPT_LINES),
            "quest": sess["quest"], "expects": "done"}


def snapshot(sid):
    """The raw picks/located/payload for the printer."""
    sess = SESSIONS.get(sid)
    if not sess or not sess["picks"]:
        return None
    return sess
