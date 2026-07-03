"""The séance: a staged Oracle conversation → theatrical pull → reading → quest negotiation.

Heavily structured, lightly LLM. The stages are fixed (the ritual); the LLM only fills
warm specifics inside them (the voice). Every LLM touch has a template fallback, so the
whole ceremony runs offline on playa with nothing but the deck.

Seeker stages:  naming → listening → deepening → proposed → accepted
Tale stages:    tale_naming → tale_listening → tale_told
The Tale-Book (lore.py) makes the Turtle remember returning seekers across the burn.
"""
import datetime
import json
import random
import re
import time
import uuid

import os

from .deck import load_deck, card_payload, REPO
from .select import select_fallback, _tokens
from .weave import weave, SYSTEM, card_lore
from .geo import locate_spread, directions_lines, COMPASS_ROSE
from . import lore

WEATHER = json.load(open(os.path.join(REPO, "data", "weather.json"), encoding="utf-8"))
WEATHERS = {w["id"]: w for w in WEATHER["weathers"]}
STONES = WEATHER["stones"]
WEATHER_ASK = WEATHER["meta"]["ask"]

SESSIONS = {}
MAX_SESSIONS = 60  # kiosk = one seeker at a time; keep a small tail for stragglers

NAME_ASKS = [
    "Ah. A traveler. Come closer — the shell is warm. First things first: what do they call you out here?",
    "Welcome, dusty one. Before any card moves, the Turtle takes names. What name do you carry tonight?",
    "Mm. The Tree said someone was coming. Sit. Tell me the name you go by in this city.",
]

STEM_ASKS = [
    "Mm. Then finish this, out loud, and only this:",
    "The Turtle believes you. Now finish this sentence — nothing more:",
    "Good. One sentence is enough, if it is true. Finish this:",
]

STONES_ASK = ("Words are hard tonight. No matter — the shell reads weight. "
              "Touch what you are carrying. Leave the rest in the dust.")

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

TALE_NAME_ASKS = [
    "You came back. The shell felt your steps. First — the name you carry.",
    "A returner. Good. The Turtle keeps its ledger by name — what is yours?",
]

TALE_INVITES = [
    "Now. A turtle of the shell must stand beside you — the tale is told to a living creature, "
    "not a machine. Tell them the tale aloud, and let the shell listen too. Speak when ready.",
]

TALE_THANKS = [
    "So it happened, and now it is story. The shell keeps it in the Tale-Book. "
    "Turtle who witnessed: this one has earned the gift.",
    "That is a true tale — the Turtle can taste the dust in it. It joins the Tale-Book. "
    "Witness: give this one their gift.",
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

LEAVES = [
    "Write one word on a scrap and leave it there, weighted with a stone.",
    "Leave behind something small you have been carrying — and mean it.",
    "Say the name of a habit out loud there, once, and walk away from it.",
]

VOW = ("When your three moves are made, return to the Terrible Turtle shell. Find a turtle. "
       "Tell the tale aloud, to their face — your proofs are the witnesses. Those who return and tell "
       "receive a gift from the shell — and while the shell still holds them, that gift "
       "is a deck of this very oracle.")
VOW_WHERE = "Camp placement posts in August — until then, ask any turtle where the shell is parked."
CHOSEN = "Meaning is not found. It is chosen. Bite down."

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
    """Sanitize an LLM one-liner: strip quotes/labels, keep it one short line."""
    s = (s or "").strip().strip('"').strip("'").strip()
    s = re.sub(r"^(question|follow-?up|oracle|turtle)\s*[:\-]\s*", "", s, flags=re.I).strip()
    s = s.splitlines()[0].strip() if s else ""
    if not s or _words(s) > max_words:
        return None
    return s


def _extract_name(text):
    t = re.sub(r"^(hi|hey|hello|um|uh|well|ok|okay)[,!. ]+", "", (text or "").strip(), flags=re.I)
    t = re.sub(r"^(i am|i'm|im|they call me|people call me|my name is|my name's|call me|it's|its|"
               r"the name is|name's|this is)\s+", "", t, flags=re.I)
    t = re.split(r"[,.!?;\n]| and | but ", t)[0].strip()
    name = " ".join(w.capitalize() for w in t.split()[:3])
    return (name or "Traveler")[:28]


def _time_context():
    now = datetime.datetime.now()
    h = now.hour + now.minute / 60
    if 5 <= h < 8:
        pod = "dawn — sunrise is near or happening; if the quest can, it ends facing the sun"
    elif 8 <= h < 12:
        pod = "morning — the city wakes slowly; heat is coming"
    elif 12 <= h < 17:
        pod = ("the hot afternoon — route through shade, ice at Arctica, misters; "
               "save the far playa for after dark")
    elif 17 <= h < 20:
        pod = "golden hour into sunset — the playa softens, art is close and kind"
    elif 20 <= h < 24:
        pod = "night — the city is fully lit; deep playa and sound camps are alive"
    else:
        pod = "deep night — the quiet hours; the strongest ending is sunrise, near 6:20am"
    return f"It is {now.strftime('%A, %I:%M %p').replace(' 0', ' ')} in Black Rock City: {pod}."


def _company(shares):
    t = " ".join(shares).lower()
    if re.search(r"\b(my partner|my wife|my husband|my boyfriend|my girlfriend|my friend|"
                 r"my friends|my crew|my campmates|both of us|the two of us|we came|we keep|"
                 r"we are|we're)\b", t):
        return ("The seeker is clearly here WITH someone (they speak as 'we'). Write the quest "
                "for them together — shared moves, and one done apart, reunited with something to tell.")
    return ""


def _context(sess):
    parts = [_time_context()]
    w = WEATHERS.get(sess.get("weather"))
    if w:
        parts.append(f'The seeker named their inner weather "{w["name"]}". '
                     f'REGISTER: {w["register"]} QUEST TILT: {w["quest_tilt"]}')
    if sess.get("stones"):
        names = [s["name"] for s in STONES if s["id"] in sess["stones"]]
        parts.append("When words were hard, they touched what they carry: "
                     + ", ".join(names) + ".")
    if sess.get("ground", 0) >= 0.5:
        parts.append("IMPORTANT — the seeker is far from shore tonight (altered, exhausted, or "
                     "unmoored). Keep the reading SHORT (60-90 words), warm, concrete. The quest "
                     "stays small-radius, physical, gentle. Grounding is the gift; no mysteries.")
    c = _company(sess["shares"])
    if c:
        parts.append(c)
    if sess.get("prior_line"):
        parts.append(sess["prior_line"])
    return " ".join(parts)


def _ground_signals(sess, text, meta):
    """Passive groundedness inference: weather + latency + speech shape. 0..1-ish."""
    g = WEATHERS.get(sess.get("weather"), {}).get("grounding", 0.0)
    meta = meta or {}
    try:
        if float(meta.get("ms", 0)) > 25000:
            g += 0.2
        secs = float(meta.get("audio_secs", 0))
        words = len((text or "").split())
        if secs > 1 and meta.get("input") == "voice":
            rate = words / secs
            if rate < 1.2 or rate > 4.5:
                g += 0.3
    except (TypeError, ValueError):
        pass
    sess["ground"] = max(sess.get("ground", 0.0), g)


def start(mode="seek"):
    """Open a séance (mode 'seek') or a tale-telling (mode 'tale')."""
    _gc()
    sid = _new_id()
    tale = (mode == "tale")
    SESSIONS[sid] = {
        "id": sid, "stage": "tale_naming" if tale else "naming",
        "name": None, "prior_line": None,
        "shares": [], "weather": None, "stones": [], "ground": 0.0, "stem_tried": False,
        "picks": None, "located": None, "reading": None, "adventure": None,
        "quest": None, "echoes": None, "created": time.time(),
    }
    say = random.choice(TALE_NAME_ASKS if tale else NAME_ASKS)
    return {"session": sid, "stage": SESSIONS[sid]["stage"], "say": say, "expects": "name"}


def _followup_llm(shares, llm):
    prompt = (
        "A seeker at your shell just shared this about their burn:\n"
        + "\n".join(f"- {s}" for s in shares)
        + "\n\nAsk ONE short, warm follow-up question (under 25 words) in the Turtle's voice — wry, "
        "specific to their words, inviting one level deeper. It must be a question. "
        "Return the question only, no quotes, no preamble."
    )
    return _clean_line(llm.generate(prompt, system=SYSTEM, timeout=45), max_words=32)


def _echoes_llm(sess, llm):
    picks = sess["picks"]
    cl = card_lore()
    lines = "\n".join(
        f'{r}: {picks[r]["name"]} — essence: {cl.get(picks[r]["id"], {}).get("essence", "")}; '
        f'bridge: {cl.get(picks[r]["id"], {}).get("bridge", "")}'
        for r in ("roots", "trunk", "branches"))
    prompt = (
        "SEEKER'S WORDS (the only source you may quote from):\n"
        + "\n".join(f"- {s}" for s in sess["shares"])
        + f"\n\nCARD NOTES (for meaning only — NEVER quote these):\n{lines}\n\n"
        "For each card, write ONE line (under 22 words) the Turtle speaks as that card turns over. "
        "Each line quotes exactly ONE phrase of 3-8 words copied verbatim from SEEKER'S WORDS inside "
        "'single quotes' — never words from CARD NOTES — then ties that phrase to the card in plain "
        "speech. No card mechanics, no fortune-telling.\n"
        "Example shape: You said 'yes to everyone' — and the tide kept none of it for you.\n"
        'Return JSON only: {"roots": "...", "trunk": "...", "branches": "..."}'
    )
    resp = llm.generate(prompt, system=SYSTEM, as_json=True, timeout=60)
    if not resp:
        return None
    try:
        out = json.loads(resp)
    except Exception:
        return None
    if isinstance(out, dict) and all(out.get(r) for r in ("roots", "trunk", "branches")):
        # structural guarantee: every echo must carry a quoted seeker phrase, else that
        # card's echo falls back to the deterministic quote-builder
        fb = _echoes_fallback(sess)
        result = {}
        for r in ("roots", "trunk", "branches"):
            line = _clean_line(out[r], 30)
            result[r] = line if (line and line.count("'") >= 2) else fb[r]
        return result
    return None


def _echoes_fallback(sess):
    sents = [s.strip() for sh in sess["shares"] for s in re.split(r"[.!?,]+", sh) if s.strip()]
    words = " ".join(sess["shares"]).split()
    out = {}
    used = set()
    for i, realm in enumerate(("roots", "trunk", "branches")):
        c = sess["picks"][realm]
        kw = _tokens(" ".join(c.get("keywords", [])) + " " + c.get("reading", ""))
        ranked = sorted(sents, key=lambda s: len(_tokens(s) & kw), reverse=True)
        best = next((s for s in ranked if s not in used), ranked[0] if ranked else "")
        used.add(best)
        frag = " ".join(best.split()[:9])
        if not frag and len(words) > 6:
            # carve three different windows from one long share
            third = max(3, len(words) // 3)
            frag = " ".join(words[i * third:i * third + 8])
        out[realm] = (f"You said '{frag}…' — the Tree heard it. {c['name']} rose."
                      if frag else f"The Tree sent up {c['name']}.")
    return out


def _draw(sess, llm):
    """THE PLAYA PULLS: pure chance, one card per realm. The AI's craft is the binding,
    not the choosing — meaning is made, not matched."""
    _, _, by_realm = load_deck()
    told = " ".join(sess["shares"])
    picks = {realm: random.choice(by_realm[realm]) for realm in ("roots", "trunk", "branches")}
    sel_mode = "playa"
    located = locate_spread(picks)
    sess.update(picks=picks, located=located)
    out, weave_mode = weave(told, picks, llm, located, context=_context(sess))
    echoes = (_echoes_llm(sess, llm) if llm and llm.available() else None) or _echoes_fallback(sess)
    sess.update(reading=out["reading"], adventure=out["adventure"],
                echoes=echoes, stage="proposed")
    return {
        "session": sess["id"], "stage": "proposed",
        "say": random.choice(DRAWN_LINES),
        "cards": {r: card_payload(picks[r], located[r]) for r in ("roots", "trunk", "branches")},
        "echoes": echoes,
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
        + f"\nCONTEXT: {_context(sess)}\n"
        + f"\nThe drawn cards (KEEP these, do not swap):\n" + "\n".join(lines)
        + f"\n\nThe current quest:\n{sess['adventure']}\n\n"
        "Rewrite the quest around that new truth — same three cards, same three real places, but the "
        "tasks should now put what they just confessed at the center (if they said they secretly sing, "
        "the quest makes them sing). Keep the arc: FACE alone with a hard truth, STAND as presence at a "
        "place, REACH involving another human; keep one leave-something-behind. Concrete, doable, with "
        "directions. Also write one short acknowledgement line (under 20 words) the Turtle says first, "
        "naming the new truth.\n"
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
    sess["echoes"] = _echoes_fallback(sess)
    return {"say": random.choice(REFINE_ACKS), "adventure": out["adventure"],
            "reading": out["reading"]}


def _name_step(sess, text, tale):
    """The seeker gives their name; the Turtle checks its ledger."""
    sess["name"] = _extract_name(text)
    name = sess["name"]
    prior_q, prior_t = lore.last_quest(name), lore.last_tale(name)
    if tale:
        recall = (f"The ledger shows your quest: “{prior_q['title']}.” " if prior_q else "")
        sess["stage"] = "tale_listening"
        return {"session": sess["id"], "stage": "tale_listening",
                "say": f"{name}. {recall}{random.choice(TALE_INVITES)}",
                "expects": "tale"}
    sess["stage"] = "weather"
    tiles = [{"id": w["id"], "name": w["name"], "tile": f"/tiles/{w['id']}.jpg"}
             for w in WEATHER["weathers"]]
    if prior_q:
        sess["prior_line"] = (
            f"This seeker has quested with the Turtle before. Their last quest: “{prior_q['title']}”."
            + (f' The tale they told of it: "{prior_t["tale"][:300]}"' if prior_t else "")
            + " Build tonight on top of that — acknowledge it once, never repeat it.")
        say = (f"{name}. The Turtle remembers you — you carried “{prior_q['title']}.” "
               + ("Your tale is in the book. " if prior_t else "The book still waits for that tale. ")
               + WEATHER_ASK)
    else:
        say = f"{name}. Good — a name the dust can hold. {WEATHER_ASK}"
    return {"session": sess["id"], "stage": "weather", "say": say,
            "weathers": tiles, "expects": "weather"}


def _tale_step(sess, text, llm):
    """The tale, told aloud to a human turtle, recorded by the shell."""
    prior_q = lore.last_quest(sess["name"])
    lore.append({"type": "tale", "name": sess["name"], "tale": text,
                 "quest_title": (prior_q or {}).get("title", "")})
    sess["stage"] = "tale_told"
    say = None
    if llm and llm.available():
        say = _clean_line(llm.generate(
            f'A seeker named {sess["name"]} returned to the shell and told this tale of their quest'
            + (f' “{prior_q["title"]}”' if prior_q else "") + f':\n"{text}"\n\n'
            "In the Turtle's voice, honor the tale in TWO sentences (under 40 words): first name one "
            "specific detail from the tale itself, then address the human turtle who witnessed it, "
            "telling THEM to hand this seeker their gift. Return the lines only.",
            system=SYSTEM, timeout=60), max_words=50)
    return {"session": sess["id"], "stage": "tale_told",
            "say": say or random.choice(TALE_THANKS),
            "gift": True, "expects": "done"}


def hear(sid, body, llm=None):
    """The seeker speaks or taps. Routes on the session's stage; returns the next event."""
    sess = SESSIONS.get(sid)
    if not sess:
        return {"error": "no such séance — touch the shell to begin again", "stage": "gone"}
    body = body if isinstance(body, dict) else {"text": body}
    text = (body.get("text") or "").strip()
    meta = body.get("meta") or {}
    if sess["stage"] == "weather":
        w = WEATHERS.get((body.get("weather") or "").strip())
        if not w:
            return {"session": sid, "stage": "weather",
                    "say": "Touch one of the six skies, traveler.",
                    "weathers": [{"id": x["id"], "name": x["name"], "tile": f"/tiles/{x['id']}.jpg"}
                                 for x in WEATHER["weathers"]],
                    "expects": "weather"}
        sess["weather"] = w["id"]
        sess["ground"] = max(sess["ground"], w.get("grounding", 0.0))
        sess["stage"] = "stem"
        return {"session": sid, "stage": "stem",
                "say": f'{w["name"]}. {random.choice(STEM_ASKS)}',
                "stem": w["stem"], "expects": "stem"}
    if sess["stage"] == "stones":
        valid = {x["id"] for x in STONES}
        sess["stones"] = [s for s in (body.get("stones") or []) if s in valid]
        names = [x["name"] for x in STONES if x["id"] in sess["stones"]]
        sess["shares"].append("I am carrying: "
                              + (", ".join(names) if names else "nothing I can name") + ".")
        return _draw(sess, llm)
    if not text:
        return {"session": sid, "stage": sess["stage"],
                "say": "The Turtle heard only wind. Try again, slower.",
                "expects": "share"}
    if sess["stage"] == "naming":
        return _name_step(sess, text, tale=False)
    if sess["stage"] == "tale_naming":
        return _name_step(sess, text, tale=True)
    if sess["stage"] == "tale_listening":
        return _tale_step(sess, text, llm)
    if sess["stage"] == "tale_told":
        return {"session": sid, "stage": "tale_told", "gift": True,
                "say": "The tale is kept. Go get your gift, and let the next traveler in.",
                "expects": "done"}
    if sess["stage"] == "stem":
        _ground_signals(sess, text, meta)
        stem = WEATHERS.get(sess.get("weather"), {}).get("stem", "")
        sess["shares"].append(f"{stem} {text}" if stem else text)
        # thin answer → the stones rescue: recognition when words won't come
        if len(text.split()) < 4 and not sess["stem_tried"]:
            sess["stem_tried"] = True
            sess["stage"] = "stones"
            return {"session": sid, "stage": "stones", "say": STONES_ASK,
                    "stones": STONES, "expects": "stones"}
        return _draw(sess, llm)
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
        event["echoes"] = sess["echoes"]
        event["directions"] = directions_lines(picks, located)
        return event
    if sess["stage"] == "accepted":
        return {"session": sid, "stage": "accepted", "quest": sess["quest"],
                "say": "The quest is already sealed, traveler. Go live it — the shell will wait.",
                "expects": "done"}
    return {"error": "the Turtle is confused", "stage": sess["stage"]}


def _seal_llm(sess, llm):
    """Personalize the three sealed moves (task/where/proof + one leave) from the final quest."""
    picks, located = sess["picks"], sess["located"]
    lines = []
    for realm in ("roots", "trunk", "branches"):
        c, loc = picks[realm], located.get(realm, {})
        lines.append(f'{SLOT_TITLES[realm]}: card="{c["name"]}" at="{c["real_2026"]["name"]}" '
                     f'where="{loc.get("directions", "")}"')
    prompt = (
        "Seal this quest into exactly three moves, in order FACE, STAND, REACH.\n"
        f"The seeker's words:\n" + "\n".join(f"- {s}" for s in sess["shares"])
        + f"\n\nThe accepted quest:\n{sess['adventure']}\n\nThe cards:\n" + "\n".join(lines)
        + "\n\nFor each move give: task (1-2 concrete sentences drawn from the quest), where (short, "
        "from the card's where), proof (ONE specific thing to bring back to the shell, personal to "
        "their words). EXACTLY ONE move also gets leave: one small thing left behind there. "
        "FACE is done alone with a hard truth; STAND is presence at a place; REACH involves another "
        "human. Nothing risky, nothing without consent.\n"
        'Return JSON only: {"moves": [{"task":"","where":"","proof":"","leave":""}, {...}, {...}]}'
    )
    resp = llm.generate(prompt, system=SYSTEM, as_json=True, timeout=120)
    if not resp:
        return None
    try:
        moves = json.loads(resp).get("moves")
    except Exception:
        return None
    if not (isinstance(moves, list) and len(moves) == 3
            and all(isinstance(m, dict) and m.get("task") for m in moves)):
        return None
    return moves


def accept(sid, llm=None):
    """Seal the quest: three moves with places + proofs (+ one sacrifice), the vow, the map."""
    sess = SESSIONS.get(sid)
    if not sess:
        return {"error": "no such séance — touch the shell to begin again", "stage": "gone"}
    if sess["stage"] != "proposed" and not sess["quest"]:
        return {"error": "no quest to accept yet", "stage": sess["stage"]}
    if not sess["quest"]:
        picks, located = sess["picks"], sess["located"]
        r, t, b = picks["roots"], picks["trunk"], picks["branches"]
        sealed = (_seal_llm(sess, llm) if llm and llm.available() else None)
        moves = []
        leave_at = random.randrange(3)
        for i, realm in enumerate(("roots", "trunk", "branches")):
            c, loc = picks[realm], located.get(realm, {})
            where = loc.get("directions", "") or "Somewhere out there — ask Playa Info."
            if sealed:
                m = sealed[i]
                moves.append({
                    "slot": SLOT_TITLES[realm], "card": c["name"],
                    "task": m["task"].strip(),
                    "where": (m.get("where") or where).strip(),
                    "at": c["real_2026"]["name"],
                    "proof": (m.get("proof") or PROOFS[realm][(c.get("number", 1) - 1) % 4]).strip(),
                    "leave": (m.get("leave") or "").strip(),
                })
            else:
                moves.append({
                    "slot": SLOT_TITLES[realm], "card": c["name"],
                    "task": c["turtle_dare"],
                    "where": where, "at": c["real_2026"]["name"],
                    "proof": PROOFS[realm][(c.get("number", 1) - 1) % 4],
                    "leave": LEAVES[c.get("number", 1) % len(LEAVES)] if i == leave_at else "",
                })
        sess["quest"] = {
            "title": f'The Quest of {b["name"]}',
            "for": sess.get("name") or "Traveler",
            "charge": (f'Face “{r["name"]}.” Stand in “{t["name"]}.” Reach for “{b["name"]}.” '
                       "Three moves, made slow — then home to the shell."),
            "adventure": sess["adventure"],
            "moves": moves,
            "vow": VOW, "vow_where": VOW_WHERE, "chosen": CHOSEN,
            "map": COMPASS_ROSE,
        }
        sess["stage"] = "accepted"
        lore.append({"type": "quest", "name": sess["quest"]["for"],
                     "title": sess["quest"]["title"], "shares": sess["shares"],
                     "cards": [picks[r]["id"] for r in ("roots", "trunk", "branches")],
                     "quest": sess["quest"]})
    return {"session": sid, "stage": "accepted", "say": random.choice(ACCEPT_LINES),
            "quest": sess["quest"], "expects": "done"}


def snapshot(sid):
    """The raw picks/located/payload for the printer."""
    sess = SESSIONS.get(sid)
    if not sess or not sess["picks"]:
        return None
    return sess
