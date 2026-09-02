"""The séance: a staged Oracle conversation → theatrical pull → reading → quest negotiation.

Heavily structured, lightly LLM. The stages are fixed (the ritual); the LLM only fills
warm specifics inside them (the voice). Every LLM touch has a template fallback, so the
whole ceremony runs offline on playa with nothing but the deck.

THE PULL COMES FIRST. There is a potency in simply pulling the cards and giving a reading,
and every intake question asked before that is a form standing between a seeker and the
thing they came for. So: a name, three cards face up, the Turtle's read of them, and then
ONE open question they may answer or let be. Context is offered, never required.

Seeker stages:  naming → asking → proposed → accepted
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

from .deck import load_deck, card_payload, draw_spread, REPO
from .select import select_fallback, _tokens
from .weave import (weave, weave_fallback, SYSTEM, card_lore, bite_realm, landmark_realm,
                    landmark_where, open_where, proof_for, names_an_address, PROOFS,
                    REALMS, _first_sentence)
from .geo import locate_spread, directions_lines, COMPASS_ROSE
from . import lore

WEATHER = json.load(open(os.path.join(REPO, "data", "weather.json"), encoding="utf-8"))
WEATHERS = {w["id"]: w for w in WEATHER["weathers"]}
STONES = WEATHER["stones"]
WEATHER_ASK = WEATHER["meta"]["ask"]

SESSIONS = {}
MAX_SESSIONS = 200  # two stations plus phones on the camp network: many séances at once

# LLM patience, set from measurement on the DGX Spark (qwen3:30b-a3b, 2026-08-07).
#
#   1 seeker,  warm:   full séance 10.5s   (weave+echoes 5.7, refine 2.1, seal 2.7)
#   6 seekers, warm:   slowest single call 24.4s, whole séance ~57s wall
#
# Ollama serialises on one GPU, so per-call latency scales with how many seekers are
# mid-séance. 25s looked generous against the solo number and would have tripped at a
# busy moment — the worst possible time, because that is when the most people are
# watching. These are guards against a genuinely hung model, not pacing controls: the
# fallback is a VISIBLE drop in quality, so let the model win whenever it is merely slow.
T_SHORT = float(os.environ.get("ORACLE_T_SHORT", "45"))   # one-liners: follow-up, echoes
T_LONG = float(os.environ.get("ORACLE_T_LONG", "60"))     # structured: refine, seal

NAME_ASKS = [
    "Ah. A traveler. Come closer — the shell is warm. First things first: what do they call you out here?",
    "Welcome, dusty one. Before any card moves, the Turtle takes names. What name do you carry tonight?",
    "Mm. The Tree said someone was coming. Sit. Tell me the name you go by in this city.",
]

STONES_ASK = ("Words are hard tonight. No matter — the shell reads weight. "
              "Touch what you are carrying. Leave the rest in the dust.")

# What the Turtle says over the pull when the seeker has said NOTHING — which is now the
# ordinary way in. DRAWN_LINES all claim to have heard something ("Enough. The Turtle has
# heard you"), and a séance that opens by thanking you for words you never said is a
# séance that is not listening.
PULL_LINES = [
    "Then the Turtle will not ask you anything yet. Watch — the Tree is choosing.",
    "Good. Sit. The shell hums, and three cards rise for you.",
    "No questions first. That is how the old ones did it. The Tree is choosing your three.",
]

DRAWN_LINES = [
    "Enough. The Turtle has heard you. Watch — the Tree is choosing.",
    "The shell hums. Three cards rise for you: what to face, where you stand, what to reach for.",
    "Good. That is enough truth to pull on. The Tree is choosing your three.",
]

# Spoken when the reading finally arrives. The cards were already turned at `asking`, so
# the DRAWN/PULL lines cannot do this job twice.
WOVEN_LINES = [
    "Mm. Now the Turtle can see it. Hear what the three of them say together.",
    "Enough. The shell has what it needs. This is what rose for you.",
    "Good. That is the shape of it. Hear it whole.",
]

ASK_RETRY = "The Turtle heard only wind. Say it again, or let it be."

# Spoken instead of the usual line when a Shell card substitutes into a slot — roughly
# one séance in ten. The Turtle interrupting its own format is the whole point.
AXIS_LINE = ("The shell goes quiet. Mm. That is not a card from the Tree — that is the "
             "Tree's own spine. “{card}” has come up for you, and the Turtle does not "
             "choose when that happens. Sit with it.")

REFINE_ACKS = [
    "Mm. That changes the shape of it. The Tree bends — hear your quest again.",
    "Good. More truth makes a better quest. Listen.",
    "The Turtle chews on that. Slowly. Yes — the quest turns like this.",
]

DECISION_ASK = "Do you accept this quest? Or shall the Turtle hear more before it is sealed?"

# What the Turtle says when the seeker answers the standing decision with something that is
# not a refinement — a stray {pass:true} or {chip} from the screen before, or an empty body
# from a tablet whose reply was lost. Nothing has moved, so the whole decision is re-offered.
DECISION_REASK = ("The quest stands as it was spoken. Accept it, or tell the Turtle more "
                  "before it is sealed.")

ALREADY_SEALED = "The quest is already sealed, traveler. Go live it — the shell will wait."

SETTLED_LINE = ("The Turtle has heard enough. The Tree has settled — it will not turn again "
                "tonight. Accept this quest as it stands, or walk away and leave it in the dust.")

# Each refinement is a fresh model call on an already-good quest, and on one playa GPU that
# is a minute of somebody else's séance. Past this the Turtle says the Tree has settled.
MAX_REFINES = 3

ACCEPT_LINES = [
    "So be it. The quest is sealed. Move slow, bite things, and bring your proof back to the shell.",
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

VOW = ("When the bite is taken, return to the Terrible Turtle shell. Find a turtle. "
       "Tell the tale aloud, to their face — your proof is the witness. Those who return and tell "
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
    # Filler words can stack ("um, hi there, I'm Wren") — strip repeatedly, not once,
    # or a second filler word left behind gets read as the name itself.
    t = (text or "").strip()
    filler = re.compile(r"^(hi|hey|hello|hiya|there|um|uh|er|well|ok|okay|so|yeah)[,!. ]+", re.I)
    while True:
        stripped = filler.sub("", t)
        if stripped == t:
            break
        t = stripped
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
        parts.append("When words were hard, they touched what they carry, instead of speaking: "
                     + ", ".join(names) + ". These are weight felt, not words said — never write "
                     "'you said' or quote a stone's name back to them as if they spoke it.")
    if sess.get("ground", 0) >= 0.5:
        parts.append("IMPORTANT — the seeker is far from shore tonight (altered, exhausted, or "
                     "unmoored). Keep the reading SHORT (60-90 words), warm, concrete. The quest "
                     "stays small-radius, physical, gentle. Grounding is the gift; no mysteries.")
    c = _company(sess["shares"])
    if c:
        parts.append(c)
    if sess.get("axis_slot"):
        parts.append("THE AXIS HAS SPOKEN: one of the three is not a Tree card but a Shell "
                     "card — the World Turtle's own axis, which surfaces for roughly one "
                     "seeker in ten. Name that this is rare, once, without ceremony or "
                     "flattery, and let it carry more weight in the reading than the "
                     "other two.")
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
        "shares": [], "weather": None, "stones": [], "ground": 0.0,
        "picks": None, "located": None, "reading": None, "adventure": None,
        "axis_slot": None, "bite": None,
        # the asking: the Turtle's read of the table, its one question, its three guesses
        "look": None, "question": None, "chips": None,
        # "pull" when the seeker came straight from their name — no words yet, by choice
        "door": None, "refines": 0, "accept_say": None,
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
    return _clean_line(llm.generate(prompt, system=SYSTEM, timeout=T_SHORT), max_words=32)


def _seeker_words(sess):
    """Return only words the seeker actually supplied, without UI stems or stone labels."""
    stem = WEATHERS.get(sess.get("weather"), {}).get("stem", "").strip()
    spoken = []
    for share in sess.get("shares", []):
        text = (share or "").strip()
        if text.startswith("I am carrying:"):
            continue
        if stem and text.startswith(stem):
            text = text[len(stem):].strip()
        if text:
            spoken.append(text)
    return spoken


def _quote_tokens(text):
    return re.findall(r"[\w’'-]+", text or "", flags=re.UNICODE)


def _quote_windows(spoken):
    """Make up to three distinct, natural 3-8-word quote candidates per answer."""
    windows = []
    for answer in spoken:
        words = _quote_tokens(answer)
        if len(words) < 3:
            continue
        width = min(7, len(words))
        starts = (0, max(0, (len(words) - width) // 2), max(0, len(words) - width))
        for start in starts:
            phrase = " ".join(words[start:start + width])
            if phrase not in windows:
                windows.append(phrase)
    return windows


def _valid_echo(line, spoken):
    quotes = re.findall(r"“([^”]+)”", line or "")
    if len(quotes) != 1 or not 3 <= len(_quote_tokens(quotes[0])) <= 8:
        return False
    phrase = " ".join(w.casefold() for w in _quote_tokens(quotes[0]))
    return any(phrase in " ".join(w.casefold() for w in _quote_tokens(source))
               for source in spoken)


def _echoes_llm(sess, llm):
    picks = sess["picks"]
    cl = card_lore()
    spoken = _seeker_words(sess)
    if not _quote_windows(spoken):
        return None
    lines = "\n".join(
        f'{r}: {picks[r]["name"]} — essence: {cl.get(picks[r]["id"], {}).get("essence", "")}; '
        f'bridge: {cl.get(picks[r]["id"], {}).get("bridge", "")}'
        for r in ("roots", "trunk", "branches"))
    prompt = (
        "SEEKER'S ACTUAL WORDS (the only source you may quote from):\n"
        + "\n".join(f"- {s}" for s in spoken)
        + f"\n\nCARD NOTES (for meaning only — NEVER quote these):\n{lines}\n\n"
        "For each card, write ONE line (under 22 words) the Turtle speaks as that card turns over. "
        "Each line quotes exactly ONE phrase of 3-8 words copied verbatim from SEEKER'S WORDS inside "
        "curly quotation marks — never words from CARD NOTES — then ties that phrase to the card in plain "
        "speech. No card mechanics, no fortune-telling.\n"
        "Example shape: You said “yes to everyone” — and the tide kept none of it for you.\n"
        'Return JSON only: {"roots": "...", "trunk": "...", "branches": "..."}'
    )
    resp = llm.generate(prompt, system=SYSTEM, as_json=True, timeout=T_SHORT)
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
            line = _clean_line(out[r], 22)
            result[r] = line if (line and _valid_echo(line, spoken)) else fb[r]
        return result
    return None


def _echoes_fallback(sess):
    spoken = _seeker_words(sess)
    windows = _quote_windows(spoken)
    out = {}
    used = set()
    for realm in ("roots", "trunk", "branches"):
        c = sess["picks"][realm]
        kw = _tokens(" ".join(c.get("keywords", [])) + " " + c.get("reading", ""))
        ranked = sorted(enumerate(windows), key=lambda x: (-len(_tokens(x[1]) & kw), x[0]))
        frag = next((phrase for _, phrase in ranked if phrase not in used), "")
        if frag:
            used.add(frag)
        essence = card_lore().get(c["id"], {}).get("essence") or c.get("reading", "")
        essence_words = essence.split()
        bite = " ".join(essence_words[:10]).rstrip(" ,;:—-")
        if len(essence_words) > 10:
            bite += "…"
        elif bite and bite[-1] not in ".!?":
            bite += "."
        out[realm] = (f"You said “{frag}” — {bite}"
                      if frag else f"{c['name']} rose. {bite}")
    return out


# ---- the asking: cards first, then one open question -------------------------------

# An oracle turns the cards and then asks you something. Doing it in that order is the
# difference between an intake form and a reading — the cards are on the table, they are
# strange, and the question the Turtle asks about them is the one a seeker will actually
# answer. So the spread is revealed HERE, before any reading exists, and whatever the
# seeker says back goes into the weave with everything else.

# One open question per realm, built from the card's own name and a keyword.
ASK_FALLBACKS = {
    "roots": lambda c, kw: (f'“{c["name"]}” rose for what you have to face, and it carries {kw}. '
                            "What have you been walking around out here?"),
    "trunk": lambda c, kw: (f'“{c["name"]}” is where you are standing tonight, and it carries {kw}. '
                            "What has been holding you up this week?"),
    "branches": lambda c, kw: (f'“{c["name"]}” is what you are reaching for, and it carries {kw}. '
                               "What do you want before this city comes down?"),
}

ASK_CHIPS = {
    "roots": ["Something I keep avoiding", "A person, mostly", "I honestly do not know"],
    "trunk": ["My camp", "Strangers, so far", "Nothing solid yet"],
    "branches": ["To be seen once", "Rest", "Something I cannot name"],
}


def _ask_realm(sess):
    """Which card the Turtle asks about. The axis, if it spoke; otherwise it rotates."""
    if sess.get("axis_slot"):
        return sess["axis_slot"]
    n = (sess["picks"]["roots"].get("number") or 1) + (sess["picks"]["branches"].get("number") or 1)
    return REALMS[n % len(REALMS)]


def card_gloss(card):
    """One plain line per card: what it means, in words a stranger in the dust can take in.
    The lore's essence line when there is one, else the card's own reading, cut short."""
    lo = card_lore().get(card["id"]) or {}
    g = lo.get("essence") or _first_sentence(card.get("reading", ""))
    return str(g or "").strip().rstrip(".")


def _look_fallback(sess):
    """The Turtle looks at the whole table before it asks anything — offline version.
    Three cards, three plain lines, each one named for the slot it fills."""
    p = sess["picks"]
    return (
        f'Three cards, and here is what they say. “{p["roots"]["name"]}” is what you have to face: '
        f'{card_gloss(p["roots"])}. “{p["trunk"]["name"]}” is where you stand tonight: '
        f'{card_gloss(p["trunk"])}. “{p["branches"]["name"]}” is what you are reaching for: '
        f'{card_gloss(p["branches"])}.'
    )


def _ask_fallback(sess):
    realm = _ask_realm(sess)
    card = sess["picks"][realm]
    kw = (card.get("keywords") or ["weight"])[0]
    return {"look": _look_fallback(sess), "question": ASK_FALLBACKS[realm](card, kw),
            "chips": ASK_CHIPS[realm], "mode": "fallback"}


def _clean_chips(raw):
    """Clean the model's three chips: their words, six words each, or none of them."""
    if not isinstance(raw, list):
        return None
    out = []
    for c in raw:
        s = re.sub(r"^[\s\"'“”\-•]+|[\s\"'“”]+$", "", str("" if c is None else c))
        s = re.sub(r"\.+$", "", s).strip()   # a chip is a tap, not a sentence
        if not s or _words(s) > 6 or len(s) > 48:
            continue
        if s not in out:
            out.append(s)
        if len(out) == 3:
            break
    return out if len(out) == 3 else None


def _clean_look(raw):
    """Gate the model's read of the table. Returns the look, or None for the template.

    Why a look was refused is stashed on the function — the reason and the size, never the
    words, which are the seeker's. Without it a template on the kiosk is indistinguishable
    from a model that never answered."""
    s = re.sub(r"\s+", " ", str("" if raw is None else raw)).strip()
    s = re.sub(r"^[\s\"'“”]+|[\s\"'“”]+$", "", s).strip()
    s = re.sub(r"^(look|reading|turtle|oracle)\s*[:\-]\s*", "", s, flags=re.I).strip()
    _clean_look.refused = None

    def refuse(why):
        _clean_look.refused = f"{why}, {_words(s)}w"
        return None

    if not s:
        return refuse("empty")
    if re.search(r"[?]\s*$", s):
        return refuse("ends in a question")
    # the two ways the model spoils it, both seen live: slot labels written back as
    # headings, and the SYSTEM prompt's own example handed to the seeker as their reading.
    # Either one is the template's turn.
    if re.search(r"\b(FACE|STAND|REACH)\s*:", s):
        return refuse("slot labels")
    if re.search(r"built all year|fine way to disappear|map runs out|nobody needs you", s, re.I):
        return refuse("quotes the system example")
    # The look is now the WHOLE reading of the spread — it is what most seekers will take
    # away, because most of them will let the cards speak and never add a word. Under ~45
    # words it is a caption rather than a reading and the template's three lines beat it;
    # past ~130 the ear stops following.
    n = _words(s)
    if n < 45 or n > 130:
        return refuse("too short" if n < 45 else "too long")
    return s


_clean_look.refused = None

# the slots are given as phrases, not as FACE/STAND/REACH — handed the labels, the model
# writes them back as headings in the look ("FACE: The Taproot. …")
SLOT_PHRASE = {"roots": "what to face", "trunk": "where they stand",
               "branches": "what to reach for"}


def _ask_llm(sess, llm):
    picks = sess["picks"]
    cl = card_lore()
    told = _seeker_words(sess)
    lines = "\n".join(
        f'{SLOT_PHRASE[r]} — {picks[r]["name"]}: keywords={", ".join(picks[r].get("keywords") or [])}; '
        f'essence="{(cl.get(picks[r]["id"]) or {}).get("essence") or picks[r].get("reading", "")}"'
        for r in REALMS)
    # THE ZERO-CONTEXT CASE IS THE PRIMARY ONE. Almost every seeker now arrives here having
    # said nothing but their name, so this prompt is written for that first and treats
    # anything they did offer as a bonus. A reading that needs the seeker's words to exist
    # is not an oracle; it is an intake form with a mood.
    prompt = (
        "Three cards are face up on the table. The seeker gave their name and asked for nothing "
        "else — no question, no story. That is the ordinary way in: they came for a reading, so "
        "give them one, and let it stand on the cards alone.\n\n"
        f"The cards:\n{lines}\n\n"
        + ("This one did offer something, which is more than most give. Use it:\n"
           + "\n".join(f"- {s}" for s in told) + "\n\n" if told else "")
        + "FIRST, READ THE SPREAD — the whole table, the way an oracle reads it before it asks "
        "anything. Write 60-100 words in whole spoken sentences. Name each card once, and in the "
        "same breath say what it is in plain words, so a stranger who has never seen “the Heartwood” "
        "knows what just landed in front of them. Then let the three run as ONE thought: what to "
        "face, where they stand, what they reach for. "
        + ("Tie it to what they told you above — two or three of their own words, for at least two "
           "of the three cards. " if told else
           "You know nothing about this one. So read what is actually on the table: open enough "
           "that anyone in this city tonight could find themselves in it, and concrete enough to be "
           "about something — an image, an hour, a weight, a thing you can hold. Never a horoscope, "
           "never a guess about their life, never 'you said', never a fact you invented for them. ")
        + "Say it the way you would say it across a fire — never a card's name followed by a colon and "
        "a list of words, never 'X says… Y says… Z says…'. No question in it, no instruction, no "
        "place name, no explaining how the cards work. The example in your instructions is about a "
        "different seeker: never quote it or its ideas. This IS the reading they came for.\n"
        "THEN ask ONE open question in the Turtle's voice, under 25 words, that follows from what you "
        "just said. It invites them to say something and never requires it — they may well let the "
        "cards speak instead, and that is a whole answer. Answerable out loud in one sentence, never "
        "yes or no, predicting nothing. Then give three answers a seeker might actually give — in "
        "THEIR words, not yours, under six words each.\n"
        'Return JSON only: {"look": "...", "question": "...", "chips": ["...", "...", "..."]}'
    )
    resp = llm.generate(prompt, system=SYSTEM, as_json=True, timeout=T_SHORT)
    try:
        out = json.loads(resp) if resp else None
    except Exception:
        out = None
    if not isinstance(out, dict):
        return None
    question = _clean_line(out.get("question"), 30)
    if not question:
        return None
    # The look is allowed to be a short paragraph, not a line: keep it whole, keep it spoken
    # (no headings, no bullets), and cap it where the ear stops following. A model that
    # skipped it, or wrote an essay, gets the plain three-line version instead.
    look = _clean_look(out.get("look")) or _look_fallback(sess)
    return {
        "look": look, "question": question,
        "chips": _clean_chips(out.get("chips")) or _ask_fallback(sess)["chips"],
        "mode": "llm",
        # which of the two wrote the look — the event says so, as it does for the echoes
        "look_mode": f"template ({_clean_look.refused})" if _clean_look.refused else "llm",
    }


# ---- the three events that carry a reveal ------------------------------------------

# `asking`, `proposed` and `accepted` are the only stages whose kiosk renderer reaches INTO
# the event: dealSpread deals `e.cards[slot]`, renderQuest walks `e.quest.moves`. So every
# event the séance can return at one of those stages is built here, in one place, whole —
# the retries included. A retry that carried only `say` is persisted by the kiosk's
# rememberStep and then blows up the next render: a blank screen that restores blank.


def _spread_payload(sess):
    out = {}
    for r in REALMS:
        # the gloss rides under the card's name on the kiosk: a card with a name and no
        # meaning is exactly the "what does the Heartwood even mean" moment
        payload = card_payload(sess["picks"][r], sess["located"][r])
        payload["gloss"] = card_gloss(sess["picks"][r])
        out[r] = payload
    return out


def _asking_event(sess, say, **extra):
    """The cards face up on the table, and the one open question asked about them."""
    event = {
        "session": sess["id"], "stage": "asking", "say": say,
        "cards": _spread_payload(sess),
        # which slot, if any, the Turtle's own axis spoke into — the kiosk marks it
        "axis_slot": sess.get("axis_slot"),
        "map": COMPASS_ROSE,
        "directions": directions_lines(sess["picks"], sess["located"]),
        # the Turtle's read of the whole table, said BEFORE the question — an oracle looks
        # first and asks second, and a question about a card nobody understands is a quiz
        "look": sess.get("look"), "question": sess.get("question"), "chips": sess.get("chips"),
        "expects": "answer",
    }
    event.update(extra)
    return event


def _proposed_event(sess, say, **extra):
    """The echoes, the reading, the quest as it stands, and the decision on it."""
    event = {
        "session": sess["id"], "stage": "proposed", "say": say,
        "cards": _spread_payload(sess), "echoes": sess.get("echoes"),
        "axis_slot": sess.get("axis_slot"),
        "reading": sess.get("reading"), "adventure": sess.get("adventure"),
        "map": COMPASS_ROSE,
        "directions": directions_lines(sess["picks"], sess["located"]),
        "ask": DECISION_ASK, "expects": "decision",
    }
    event.update(extra)
    return event


def _accepted_event(sess, say, **extra):
    """The sealed quest, spoken or replayed — always the same words, never a second seal."""
    event = {"session": sess["id"], "stage": "accepted", "say": say,
             "quest": sess.get("quest"), "expects": "done"}
    event.update(extra)
    return event


def _draw_step(sess, llm):
    """THE PLAYA PULLS: pure chance, one card per realm. The AI's craft is the binding, not
    the choosing — meaning is made, not matched. The cards are revealed HERE, face up, and
    the Turtle reads them and asks one question before any reading exists."""
    _, _, by_realm = load_deck()
    picks, axis_slot = draw_spread(by_realm)
    located = locate_spread(picks)
    # THE BITE, decided once and carried: weave.py builds the one act out of exactly one
    # card, and the refinement and the seal have to bite the SAME card or the parchment
    # contradicts the quest the seeker just heard.
    sess.update(picks=picks, located=located, axis_slot=axis_slot,
                bite=bite_realm(located, picks), stage="asking")
    ask = (_ask_llm(sess, llm) if llm and llm.available() else None) or _ask_fallback(sess)
    sess.update(look=ask["look"], question=ask["question"], chips=ask["chips"])
    # A séance that pulled first has heard nothing yet, so it cannot say "the Turtle has
    # heard you". One that came through a tap door has, and still does.
    say = random.choice(PULL_LINES if sess.get("door") == "pull" else DRAWN_LINES)
    if axis_slot:
        say = AXIS_LINE.format(card=picks[axis_slot]["name"])
    return _asking_event(sess, say,
                         modes={"ask": ask["mode"], "look": ask.get("look_mode", ask["mode"])})


def _weave_step(sess, llm):
    """The reading and the quest, from the cards already on the table plus every share."""
    picks, located = sess["picks"], sess["located"]
    told = " ".join(_seeker_words(sess)) or "The seeker could not put it into words."
    # THE SEEKER MAY HAVE SAID NOTHING, and that is the ordinary case now. The weave is told
    # so explicitly — a reading built on "The seeker could not put it into words" is a
    # reading that opens by naming them mute — and it is handed the look it already gave at
    # the asking, so the reading CONTINUES that read of the table rather than starting the
    # séance over on the same three cards.
    pulled = not sess["shares"]
    out, weave_mode = weave(told, picks, llm, located, context=_context(sess),
                            pulled=pulled, look=sess.get("look") or "")
    spoken_echoes = _echoes_llm(sess, llm) if llm and llm.available() else None
    echoes = spoken_echoes or _echoes_fallback(sess)
    sess.update(reading=out["reading"], adventure=out["adventure"], echoes=echoes,
                stage="proposed")
    return _proposed_event(sess, random.choice(WOVEN_LINES), modes={
        "select": "playa", "weave": weave_mode,
        "echoes": "llm" if spoken_echoes else "fallback",
        # "cards" when the seeker let them speak, "told" when they fed something in
        "told": "cards" if pulled else "told",
    })


def _refine_llm(sess, llm):
    picks, located = sess["picks"], sess["located"]
    spoken = _seeker_words(sess)
    earlier, newest = spoken[:-1], (spoken[-1] if spoken else "")
    bite = sess.get("bite") or bite_realm(located, picks)
    c = picks[bite]
    lo = card_lore().get(c["id"]) or {}
    card = (f'{c["name"]}: dare="{c["turtle_dare"]}" seed="{lo.get("seed", "")}" '
            f'real_2026="{c["real_2026"]["name"]}" where="{_bearing_for(bite, located)}"')
    prompt = (
        "The seeker has heard their reading and wants the quest tuned before accepting.\n"
        "What they shared earlier:\n" + "\n".join(f"- {s}" for s in earlier)
        + f'\n\nWhat they JUST added — the new truth the rewritten quest MUST visibly use:\n"{newest}"\n'
        + f"\nCONTEXT: {_context(sess)}\n"
        + "\nThe card the bite was made from (KEEP it, do not swap):\n" + card
        + f"\n\nThe current quest:\n{sess['adventure']}\n\n"
        "Rewrite the ONE BITE around that new truth — same card, still one act, but the act now puts "
        "what they just confessed at the center (if they said they secretly sing, the quest makes them "
        "sing). REPLACE the act, do not reword it: put the new truth in its own words, don't just "
        "gesture at it. If the new truth is something they are keeping secret, the act is telling one "
        "person. Keep the shape it was spoken in: 20-40 words, one act, imperative, verb first, then "
        f"one bearing — either the place this card stands at ({c['real_2026']['name']}) with a rough "
        "direction, or a kind of place, a kind of person, or a time of day; never an address, a clock "
        "or a lettered street — and one proof to bring back to the Turtle. No second chore, no 'stay until…' "
        "interior door, no First and Second and Third, no headings or bullets. Also write one short "
        "acknowledgement line (under 20 words) the Turtle says first, naming the new truth.\n"
        'Return JSON only: {"say": "...", "adventure": "..."}'
    )
    resp = llm.generate(prompt, system=SYSTEM, as_json=True, timeout=T_LONG)
    try:
        out = json.loads(resp) if resp else None
    except Exception:
        out = None
    if isinstance(out, dict) and out.get("adventure"):
        adventure = out["adventure"].strip()
        # Reject a shrug or a ramble: a bite is 20-40 words spoken, and the gate is loose
        # around that so a good rewrite is never thrown away for a clause.
        if not 15 <= _words(adventure) <= 60:
            return None
        # Measured on the cloud port: asked to rewrite a short quest, the model handed back
        # the SAME quest, word for word, in 2 of 5 runs. It passes the length gate, so the
        # seeker hears "That changes the shape of it" and then their unchanged quest read
        # back at them — a visible lie from the Turtle. The prompt already demands the act
        # be REPLACED; this enforces it, the way _valid_echo enforces the quoted phrase.
        if _is_same_quest(adventure, sess["adventure"]):
            return None
        return {"say": _clean_line(out.get("say"), 30) or random.choice(REFINE_ACKS),
                "adventure": adventure}
    return None


def _is_same_quest(nxt, prev):
    """True when a "rewrite" is the old quest with at most cosmetic edits."""
    def norm(s):
        return [w for w in re.sub(r"[^a-z0-9\s]", " ", str(s or "").lower()).split() if w]
    a, b = norm(nxt), norm(prev)
    if not a or not b:
        return False
    if a == b:
        return True
    bag = set(b)
    return sum(1 for w in a if w in bag) / len(a) >= 0.95


def _refine_fallback(sess):
    """No LLM: re-score the realms against the fuller share; the Tree may reconsider a card."""
    _, _, by_realm = load_deck()
    told = " ".join(_seeker_words(sess)) or "The seeker could not put it into words."
    picks = select_fallback(told, by_realm)
    # select_fallback only knows the three Tree realms, so a re-score would quietly swap
    # out an axis card the seeker has already been shown. The Turtle does not take that
    # back — once the spine has spoken, it stays on the table.
    axis_slot = sess.get("axis_slot")
    if axis_slot and sess.get("picks"):
        picks[axis_slot] = sess["picks"][axis_slot]
    located = locate_spread(picks)
    out = weave_fallback(told, picks, located)
    sess.update(picks=picks, located=located, bite=bite_realm(located, picks),
                reading=out["reading"])
    sess["echoes"] = _echoes_fallback(sess)
    return {"say": random.choice(REFINE_ACKS), "adventure": out["adventure"],
            "reading": out["reading"]}


def _name_step(sess, text, tale, llm=None):
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
    # THE PULL COMES FIRST. There is a potency in simply pulling the cards and giving a
    # reading, and the weather/stem screens made every seeker answer an intake question
    # before they were allowed one. So the name goes straight to the draw: three cards, the
    # Turtle's read of them, and then ONE question they may answer or let be. `door` is
    # stamped "pull" so the draw and the weave know the seeker has said nothing and that
    # this is a choice, not a failure.
    sess["door"] = "pull"
    if prior_q:
        sess["prior_line"] = (
            f"This seeker has quested with the Turtle before. Their last quest: “{prior_q['title']}”."
            + (f' The tale they told of it: "{prior_t["tale"][:300]}"' if prior_t else "")
            + " Build tonight on top of that — acknowledge it once, never repeat it.")
        ack = (f"{name}. The Turtle remembers you — you carried “{prior_q['title']}.” "
               + ("Your tale is in the book. " if prior_t else "The book still waits for that tale. "))
    else:
        ack = f"{name}. Good — a name the dust can hold. "
    event = _draw_step(sess, llm)
    # the name is still heard and said back; the draw's own line follows it in one breath
    event["say"] = ack + event["say"]
    return event


def _weather_event(sess, say):
    """The six skies. No longer entered by the pull-first flow — kept whole so a session
    written by an older build, or a tap door added back later, still lands correctly."""
    return {"session": sess["id"], "stage": "weather", "say": say,
            "weathers": [{"id": w["id"], "name": w["name"], "tile": f"/tiles/{w['id']}.jpg"}
                         for w in WEATHER["weathers"]],
            "expects": "weather"}


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
            system=SYSTEM, timeout=T_SHORT), max_words=50)
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

    # The wordless stages come first: a tap carries no text, so none of them may fall
    # through the "the Turtle heard only wind" guard below.
    if sess["stage"] == "weather":
        w = WEATHERS.get((body.get("weather") or "").strip())
        if not w:
            return _weather_event(sess, "Touch one of the six skies, traveler.")
        sess["weather"] = w["id"]
        sess["ground"] = max(sess["ground"], w.get("grounding", 0.0))
        sess["stage"] = "stones"
        return {"session": sid, "stage": "stones", "say": f'{w["name"]}. {STONES_ASK}',
                "stones": STONES, "expects": "stones"}
    if sess["stage"] == "stones":
        valid = {x["id"] for x in STONES}
        sess["stones"] = [s for s in (body.get("stones") or []) if s in valid]
        names = [x["name"] for x in STONES if x["id"] in sess["stones"]]
        sess["shares"].append("I am carrying: "
                              + (", ".join(names) if names else "nothing I can name") + ".")
        return _draw_step(sess, llm)

    # Past the draw the kiosk renders out of the event, so a session that reached one of
    # these stages without a spread cannot be answered at all. It cannot happen in this
    # build; a session written by an older one could, and an error the kiosk can toast is
    # better than a 500 it cannot.
    if sess["stage"] in ("asking", "proposed") and not (sess.get("picks") and sess.get("located")):
        return {"error": "the Turtle has lost the table — touch the shell to begin again",
                "stage": sess["stage"]}

    if sess["stage"] == "asking":
        # three ways to answer: say it, tap one of the Turtle's own guesses, or refuse
        chip = str(body.get("chip") or "").strip()[:120]
        if body.get("pass") is True or body.get("pass") == "true":
            # A refusal is an answer. Nothing is pushed — the weave runs on what it already
            # has, and _echoes_fallback names the cards instead of quoting words that were
            # never said.
            pass
        elif chip:
            sess["shares"].append(chip)
        elif text:
            _ground_signals(sess, text, meta)
            sess["shares"].append(text)
        else:
            # Nothing to weave on. The whole asking is sent again — cards included, because
            # the kiosk's renderer deals them out of this event — marked `retry` so a
            # tablet already looking at the spread re-draws only the answer row.
            return _asking_event(sess, ASK_RETRY, retry=True)
        return _weave_step(sess, llm)

    # The two stages the seeker can be standing in front of when a reply goes missing. Both
    # come BEFORE the "heard only wind" guard: at either of them a body with no text is a
    # normal thing for the kiosk to send (a stale {pass:true}, a chip from the screen
    # before, an empty retry) and the answer is the standing offer, sent again in full —
    # never a bare `say` the renderer would tear itself apart on.
    if sess["stage"] == "proposed":
        if text:
            return _refine_step(sess, text, llm)
        return _proposed_event(sess, DECISION_REASK, modes={"refine": "standing"})
    if sess["stage"] == "accepted":
        if not sess.get("quest"):
            return {"error": "the Turtle has lost the parchment — touch the shell to begin again",
                    "stage": "accepted"}
        return _accepted_event(sess, ALREADY_SEALED)

    if not text:
        return {"session": sid, "stage": sess["stage"],
                "say": "The Turtle heard only wind. Try again, slower.",
                "expects": "share"}
    if sess["stage"] == "naming":
        return _name_step(sess, text, tale=False, llm=llm)
    if sess["stage"] == "tale_naming":
        return _name_step(sess, text, tale=True, llm=llm)
    if sess["stage"] == "tale_listening":
        return _tale_step(sess, text, llm)
    if sess["stage"] == "tale_told":
        return {"session": sid, "stage": "tale_told", "gift": True,
                "say": "The tale is kept. Go get your gift, and let the next traveler in.",
                "expects": "done"}
    return {"error": "the Turtle is confused", "stage": sess["stage"]}


def _refine_step(sess, text, llm):
    """More truth after the quest was offered: tune it, or say the Tree has settled."""
    sess["shares"].append(text)
    # A quest can be tuned a few times and then it is the quest. Past that the Turtle says
    # so and spends nothing — the seeker's choice is now accept or walk away.
    if sess.get("refines", 0) >= MAX_REFINES:
        return _proposed_event(sess, SETTLED_LINE, modes={"refine": "settled"})
    sess["refines"] = sess.get("refines", 0) + 1
    ref = _refine_llm(sess, llm) if llm and llm.available() else None
    if ref:
        sess["adventure"] = ref["adventure"]
        return _proposed_event(sess, ref["say"], modes={"refine": "llm"})
    # the offline path genuinely re-scores the cards, so it rewrites the reading too
    fb = _refine_fallback(sess)
    sess["adventure"] = fb["adventure"]
    return _proposed_event(sess, fb["say"], modes={"refine": "fallback"})


# The words a bearing is allowed to capitalize. A bearing is made of common nouns — a
# direction, a kind of place, a kind of person, an hour — so a proper noun in one is a
# placement in disguise, and the model was told to give a bearing and names camps anyway.
# The exceptions are the placements nobody can miss, which the quest may say out loud, and
# the few common nouns the city happens to capitalize — the Deep Playa, a Ranger, Playa
# Info. None of those is a camp, and refusing them was throwing away real bearings.
BEARING_NAMES = {"man", "temple", "center", "camp", "playa", "black", "rock", "city",
                 "deep", "ranger", "rangers", "info", "greeters"}


def _bearing_for(bite, located):
    """The bearing the Turtle itself would say for this bite: the landmark line at one of
    the four unmissable placements, else the open bearing. The prompts, the fallback and
    the parchment all read from here so they never disagree."""
    loc = (located or {}).get(bite) or {}
    if landmark_realm(located) == bite and landmark_where(loc):
        return landmark_where(loc)
    return open_where(bite, loc)


def _address_in_bearing(s):
    """An address INSIDE a bearing — not the same rule as names_an_address, deliberately.
    That rule reads a whole quest, where a clock is nearly always the grid. But ONE BEARING
    asks the model for "a time of day" in as many words, so a bare hour is the thing being
    ASKED for, and "before 6:00, when the light is grey" would be thrown out as an address.
    A clock is only an address once the city's grid is attached to it."""
    if re.search(r"\bEsplanade\b|\b(?:the|its|it's|full|exact|street)\s+address\b|\bWWW guide\b",
                 s, re.I):
        return True
    return bool(re.search(r"\b[A-L]\s*(?:&|and)\s*\d|\d\s*(?:&|and)\s*[A-L]\b", s))


def usable_bearing(text, place=""):
    """Is the model's own bearing safe to seal? Short, no address, no proper noun but those.
    Worth taking when it passes: it is the bearing the seeker just HEARD, and the Turtle's
    standing line is the same three sentences every séance.

    A capital is forgiven only where a capital is forced — at the start of a SENTENCE, and a
    bearing may be two of them ("wherever the music is worst. Before the sun is up"), so the
    skip is per sentence, not once for the whole line. A bearing of ONE word has no sentence
    to forgive: "Kidsville" is a camp, and skipping it seals the camp whole.

    `place` is the ONE camp or landmark this bite is allowed to name out loud: the bite
    card's own real_2026 name. The quest prompt offers the model that place as half of what
    a bearing may be, so throwing it out here would seal a parchment that contradicted the
    quest the seeker just heard. It is allowed only when the bearing actually contains the
    whole name — "Camp Questionmark" does not become sealable because the card happens to
    stand at "Questionmark Camp"."""
    s = str(text or "").strip()
    if not s or _words(s) > 16 or _address_in_bearing(s):
        return False
    name = str(place or "").strip()
    named = bool(name) and name.lower() in s.lower()
    allowed = set(re.findall(r"[a-z0-9]+", name.lower())) if named else set()
    lone = _words(s) == 1
    checked = []
    for sentence in re.split(r"(?<=[.!?…])\s+", s):
        toks = sentence.split()
        # the first word starts a sentence, so it is capitalized
        checked.extend(toks if lone else toks[1:])
    for w in checked:
        if not re.match(r"^[“\"'(]*[A-Z]", w):
            continue
        bare = re.sub(r"[^A-Za-z0-9]", "", w).lower()
        if bare not in BEARING_NAMES and bare not in allowed:
            return False
    return True


def _seal_llm(sess, llm):
    """Personalize the sealed bite (task/where/proof, and a leave if the act leaves one)."""
    picks, located = sess["picks"], sess["located"]
    bite = sess.get("bite") or bite_realm(located, picks)
    c = picks[bite]
    landmark = landmark_realm(located) == bite
    prompt = (
        "Seal this quest into ONE BITE: one act, one bearing, one proof.\n"
        "The seeker's words:\n" + "\n".join(f"- {s}" for s in sess["shares"])
        + f"\n\nThe accepted quest:\n{sess['adventure']}\n\nThe card it was bitten from:\n"
        + f'card="{c["name"]}" at="{c["real_2026"]["name"]}" where="{_bearing_for(bite, located)}"\n\n'
        "Give: task (the ONE act, in one or two sentences, imperative and verb first, taken straight "
        "from the quest as it was spoken — no second chore, no 'stay until…' or 'leave when you have…' "
        "interior door), where (short — see THE BEARING below), proof (the ONE thing they carry back "
        "to the shell, concrete and personal to their words). leave is optional and usually empty: "
        "fill it only when the act itself leaves something behind, and then it is that same act, not "
        "another one. Nothing risky, nothing without consent.\n"
        "THE BEARING: two ways, and KEEP the one the quest above already spoke. Either the place "
        f"this card stands at — {c['real_2026']['name']} — with a rough direction and nothing else pinned"
        + (f", said like this: {_bearing_for(bite, located)}" if landmark else "")
        + ". Or a bearing that is a direction, a kind of place, a kind of person, or a time of day "
        "('out past the last lamp', 'wherever the music is worst', 'the first person who hands you "
        "water', 'before the sun is up'). Either way the where must NOT be an address: no clock, no "
        f"lettered street, no Esplanade, and no camp but {c['real_2026']['name']}. It is the burn: what is "
        "on the map moved, and finding it is half the quest.\n"
        'Return JSON only: {"move": {"task":"","where":"","proof":"","leave":""}}'
    )
    resp = llm.generate(prompt, system=SYSTEM, as_json=True, timeout=T_LONG)
    try:
        parsed = json.loads(resp) if resp else None
    except Exception:
        return None
    # The prompt asks for {"move": …} and the model sometimes answers with the shape it was
    # asked for for a year — {"moves": [ … ]}. That is a sealed quest in a list of one, and
    # throwing it away sends a good seal to the fallback. Take the first move out of it.
    move = None
    if isinstance(parsed, dict):
        move = parsed.get("move")
        if move is None and isinstance(parsed.get("moves"), list) and parsed["moves"]:
            move = parsed["moves"][0]
    if not (isinstance(move, dict) and move.get("task")):
        return None
    return move


# WHAT THE SEEKER HEARD, for the parchment the seal did not write.
#
# When _seal_llm falls back, the move used to be filled from the card's canned turtle_dare —
# which is what the OFFLINE quest was built from, so offline that is exactly right, but on
# the model path the seeker heard a quest written for them and then read a stock dare off
# the parchment. Two different quests in one séance. So: when the spoken quest still carries
# the dare it was stitched from, the dare is what they heard; otherwise the act is cut out
# of the spoken quest itself.


def _spoken_proof(adventure):
    """The "Bring back …" line the quest asked for out loud, or "" if it did not ask."""
    for s in re.split(r"(?<=[.!?…])\s+", str(adventure or "")):
        s = s.strip()
        if re.match(r"^bring back\b", s, re.I):
            return s
    return ""


def _spoken_task(adventure, where, place=""):
    """The one act out of the spoken quest: its sentences up to the bearing and the proof —
    the whole of what is left when that is already a bite, else its first two sentences."""
    w = str(where or "")
    kept = []
    for x in re.split(r"(?<=[.!?…])\s+", str(adventure or "")):
        x = x.strip()
        if not x or re.match(r"^bring back\b", x, re.I):
            continue
        # the proof and the Turtle's own standing bearing are not the act; they have their
        # own lines on the parchment, and printing them twice made it read as a list
        if len(x) > 3 and x.rstrip(" .") in w:
            continue
        kept.append(x)
    # a short last sentence that is itself a bearing is the WHERE the model spoke, not the act
    if (len(kept) > 1 and _words(kept[-1]) <= 8 and usable_bearing(kept[-1], place)
            and _words(" ".join(kept[:-1])) >= 10):
        kept.pop()
    if not kept:
        return ""
    whole = " ".join(kept)
    return whole if _words(whole) <= 40 else " ".join(kept[:2])


def accept(sid, llm=None):
    """Seal the quest: one bite with its bearing and its proof, the vow, the map."""
    sess = SESSIONS.get(sid)
    if not sess:
        return {"error": "no such séance — touch the shell to begin again", "stage": "gone"}
    # Replay, never reseal. A double-tap on the kiosk or a retried POST must get back the
    # quest that was sealed — same words, same move, no second LLM call.
    if sess.get("quest"):
        return _accepted_event(sess, sess.get("accept_say") or random.choice(ACCEPT_LINES))
    if sess["stage"] != "proposed":
        return {"error": "no quest to accept yet", "stage": sess["stage"]}
    picks, located = sess["picks"], sess["located"]
    r, t, b = picks["roots"], picks["trunk"], picks["branches"]
    # ONE BITE, from the card the spoken quest was built on. The seeker heard one act; the
    # parchment says that act, its bearing and its proof, and nothing else. `bite` is
    # re-derived defensively for a session that started before the field existed.
    bite = sess.get("bite") or bite_realm(located, picks)
    c = picks[bite]
    sealed = _seal_llm(sess, llm) if llm and llm.available() else None
    seal_mode = "llm" if sealed else "fallback"
    # Real BRC geo wins at a landmark, where the model's line only rides along as a suffix.
    # Everywhere else the bearing the seeker actually heard is worth keeping — but only when
    # it IS a bearing: usable_bearing throws out the camp names and the addresses the model
    # puts there however it is asked not to.
    standing = _bearing_for(bite, located)
    m_where = str((sealed or {}).get("where") or "").strip()
    where = m_where if usable_bearing(m_where, c["real_2026"]["name"]) else standing
    # No seal: the parchment still has to say the quest the seeker HEARD. Offline the spoken
    # quest was stitched from the dare, so the dare is that quest; on the model path it is
    # whatever the model spoke, and the canned dare would be a second, different quest.
    heard_task = (c["turtle_dare"] if c["turtle_dare"].strip() in (sess.get("adventure") or "")
                  else _spoken_task(sess.get("adventure"), standing, c["real_2026"]["name"])
                  or c["turtle_dare"])
    moves = [{
        "slot": SLOT_TITLES[bite], "card": c["name"],
        "task": str(sealed["task"]).strip() if sealed else heard_task,
        "where": where, "at": c["real_2026"]["name"],
        "proof": (str(sealed.get("proof") or proof_for(bite, c)).strip() if sealed
                  else (_spoken_proof(sess.get("adventure")) or proof_for(bite, c))),
        # THE SACRIFICE is folded into the act or it is not there at all — the offline
        # Turtle has no way to judge whether this act leaves anything, and bolting a second
        # errand onto a one-bite quest is exactly what this stopped being.
        "leave": str(sealed.get("leave") or "").strip() if sealed else "",
    }]
    sess["quest"] = {
        "title": f'The Quest of {b["name"]}',
        "for": sess.get("name") or "Traveler",
        "charge": (f'Face “{r["name"]}.” Stand in “{t["name"]}.” Reach for “{b["name"]}.” '
                   "One bite, taken slow — then home to the shell."),
        "adventure": sess["adventure"],
        "moves": moves,
        "vow": VOW, "vow_where": VOW_WHERE, "chosen": CHOSEN,
        "map": COMPASS_ROSE,
    }
    sess["stage"] = "accepted"
    # The spoken line is stored, not re-rolled, so a replayed accept is the same event.
    sess["accept_say"] = random.choice(ACCEPT_LINES)
    lore.append({"type": "quest", "name": sess["quest"]["for"],
                 "title": sess["quest"]["title"], "shares": sess["shares"],
                 "cards": [picks[x]["id"] for x in REALMS],
                 "quest": sess["quest"]})
    return _accepted_event(sess, sess["accept_say"], modes={"seal": seal_mode})


def snapshot(sid):
    """The raw picks/located/payload for the printer."""
    sess = SESSIONS.get(sid)
    if not sess or not sess["picks"]:
        return None
    return sess
