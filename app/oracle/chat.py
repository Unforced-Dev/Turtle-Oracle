"""ASK THE TURTLE — open-ended talk, grounded in the city dump and the cards.

The séance is a ceremony with an order. This is not: it is the thing a seeker actually does
at 2am, which is lean on the shell and ask where the coffee is. Same voice (``weave.SYSTEM``,
never forked), same cards, but the Turtle answers from ``guide.retrieve`` and from nothing
else — and says so when the shell does not hold the answer.

State is a dict of chats in memory, LRU, capped. Nothing persists: a chat is a conversation
at a kiosk, and when the tablet goes back to sleep it is gone.
"""
import os
import re
import threading
import time
from collections import OrderedDict

from . import guide
from .llm import THINK_RE
from .weave import SYSTEM

T_CHAT = float(os.environ.get("ORACLE_T_CHAT", "30"))
# A spoken answer is 2-5 sentences; this stops a model that starts reasoning out loud from
# running the clock out. Measured on the Spark 2026-09-05: unbounded, one answer took 45 s.
MAX_TOKENS = int(os.environ.get("ORACLE_CHAT_TOKENS", "220"))
MAX_TURNS = 12          # seeker+Turtle pairs kept per chat
MAX_CHATS = 200         # two tablets and a handful of phones; the oldest chat falls off
MAX_TEXT = 600          # a question, not an essay — anything longer is a stuck mic

CHATS = OrderedDict()
_LOCK = threading.Lock()

# What a spoken answer may never contain. The model is told this, and the cleaner enforces
# the shape it can enforce.
BULLET_RE = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+", re.M)
HEADING_RE = re.compile(r"^\s*#{1,6}\s*", re.M)

ADDENDUM = """
YOU ARE ANSWERING A QUESTION AT THE SHELL, not weaving a reading. Rules, absolute:
- Answer in 2 to 5 sentences. Spoken aloud, so no bullets, no headings, no lists, no
  markdown, no emoji. Plain sentences.
- Every place, time and name you say must come from THE SHELL HOLDS below. Never invent a
  camp, an address, a time, or an event.
- If the answer is not in THE SHELL HOLDS, say "the Turtle does not know that" and say what
  you do know instead. The shell has NO DJ lineups, NO set times, NO art-car schedules and
  NO who-is-playing — never guess one, not even a likely one.
- If you offer a quest, it is ONE BITE: one act, one bearing, one proof. You may name a camp,
  an art piece or an event from below by NAME. Never put an address block in a quest.
- Never lecture about safety; never dare physical risk, substances, climbing on art, or
  anything done to another person without their consent.
"""


# qwen3 with thinking OFF still reasons out loud when the prompt reads like a checklist:
# "Hmm, the seeker is asking about…", "Let me check the Shell Holds…", "We must answer in
# 2-5 sentences…". Seen 4 of 5 answers on the Spark, 2026-09-05. These are the openers;
# a sentence that starts this way is scratchpad, not speech.
NARRATION_RE = re.compile(
    r"^\s*(hmm+|okay|ok|alright|well|so|first|now|wait|the seeker|the user|we (must|are|need|should|have)"
    r"|let me|let's|i need to|i should|i will|i'll|looking at|checking|based on|according to the shell"
    r"|the shell holds|the question is|they are asking|they're asking|the answer (must|should|needs))\b",
    re.I)


def _unnarrate(parts):
    """Drop leading scratchpad sentences; return (spoken_parts, was_narrating)."""
    narr = False
    while parts and NARRATION_RE.match(parts[0]):
        parts = parts[1:]
        narr = True
    return parts, narr


def _clean(text):
    """A spoken answer: no scratchpad, no markdown, no more than five sentences."""
    t = THINK_RE.sub("", text or "").strip()
    t = re.sub(r"^```.*?$|^```$", "", t, flags=re.M)
    t = HEADING_RE.sub("", t)
    t = BULLET_RE.sub("", t)
    t = re.sub(r"\*\*|\*|__|`", "", t)
    t = re.sub(r"^\s*(turtle|oracle|answer)\s*[:\-]\s*", "", t, flags=re.I)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    parts = re.findall(r"[^.!?…]+[.!?…]+['\"”]?|[^.!?…]+$", t.replace("\n", " "))
    parts = [p.strip() for p in parts if p.strip()]
    parts, _clean.narrated = _unnarrate(parts)
    if len(parts) > 5:
        parts = parts[:5]
    return " ".join(parts).strip()


_clean.narrated = False

SPEAK_NOW = ("Speak now as the Turtle, straight to the seeker, first spoken sentence first. "
             "No preamble, no notes to yourself, no describing what you are checking or which "
             "rule applies. Only the words the seeker hears.")


def _seance_block(sid):
    """The seeker's own cards and reading, verbatim, when this chat hangs off a live séance."""
    if not sid:
        return ""
    try:
        from . import session
        sess = session.SESSIONS.get(sid)
    except Exception:
        return ""
    if not sess or not sess.get("picks"):
        return ""
    lines = ["THE SEEKER'S CARDS AND READING TONIGHT (yours, already spoken — do not re-weave "
             "them, but you may lean on them):"]
    if sess.get("name"):
        lines.append(f"name: {sess['name']}")
    for realm in ("roots", "trunk", "branches"):
        card = (sess["picks"] or {}).get(realm)
        if card:
            lines.append(f"{realm}: {card['name']}")
    for key, label in (("reading", "the reading"), ("adventure", "the quest offered"),):
        if sess.get(key):
            lines.append(f"{label}: {sess[key]}")
    quest = sess.get("quest")
    if quest and quest.get("moves"):
        m = quest["moves"][0]
        lines.append("the sealed quest: " + " ".join(
            str(m.get(f) or "") for f in ("task", "where", "proof")).strip())
    return "\n".join(lines)


def _system(ctx, sid, now):
    home = guide.home_camp()
    where = f"{home['name']} is at {home['address']}." if home["address"] else ""
    head = (f"IT IS {now.strftime('%A %-d %B, %-I:%M %p').replace(' 0', ' ')} in Black Rock City "
            f"(playa time). {where}")
    seance = _seance_block(sid)
    return "\n".join([SYSTEM, "", ADDENDUM, "", head, "",
                      "THE SHELL HOLDS (everything you are allowed to say about the city):",
                      ctx["block"]] + ([""] + [seance] if seance else []))


def _prompt(history, text):
    lines = []
    for role, said in history[-(MAX_TURNS * 2):]:
        lines.append(("Seeker: " if role == "seeker" else "Turtle: ") + said)
    lines.append("Seeker: " + text)
    lines.append("")
    lines.append(SPEAK_NOW)
    lines.append("Turtle:")
    return "\n".join(lines)


# "what did my cards mean", "read my quest again" — with no model, the honest answer is
# the seeker's own draw read back, not a list of whatever is on this hour.
MINE_RE = re.compile(r"\bmy (cards?|reading|quest|draw|spread)\b|\b(this|the) (reading|quest)\b", re.I)


def fallback(ctx, text, sid=None):
    """No model. Say what the shell plainly holds, and never more than that."""
    hits = [h for h in ctx["hits"] if h.get("when")][:3]
    if sid and MINE_RE.search(text or ""):
        mine = _seance_block(sid)
        if mine:
            names, reading = [], ""
            for line in mine.splitlines():
                if line.startswith(("roots:", "trunk:", "branches:")):
                    names.append(line.split(": ", 1)[1])
                elif line.startswith("the reading: "):
                    reading = line.split(": ", 1)[1]
            said = "The Tree gave you " + ", ".join(names) + "." if names else ""
            first = " ".join(p.strip() for p in
                             re.findall(r"[^.!?…]+[.!?…]", reading)[:2])
            return (said + " " + first).strip() or None
    # A lineup question is answered by the refusal FIRST, whatever else the shell holds.
    # It is the one thing the dump has none of, and the one thing a model would happily
    # improvise — so the offline answer must not bury it behind anything friendlier.
    lead = ""
    if ctx["lineup"]:
        lead = ("The Turtle does not know that. No lineups live in this shell — no names, "
                "no set times, no art car schedules. ")
    # A named card is answerable with or without the city, and is the one thing the Turtle
    # always knows — so it wins over a list of whatever happens to be on.
    if ctx.get("card_meaning"):
        said = [p.strip() for p in re.findall(r"[^.!?…]+[.!?…]", ctx["card_meaning"])][:3]
        return (lead + f"{ctx['card']}. " + " ".join(said)).strip()
    if not ctx["have_snapshot"]:
        return (lead or "The Turtle does not know that. ") + \
            ("The city is not in this shell tonight. Ask it about a card instead, or ask "
             "a turtle with legs.")
    if not hits:
        return (lead or "The Turtle does not know that. ") + \
            f"Nothing is written in the shell for {ctx['window']}. Walk out and let the city tell you."
    body = " ".join(f"{h['title']}, {h['when']}"
                    + (f", at {h['where']}" if h.get("where") else "") + "."
                    for h in hits)
    return (lead + f"Here is what the shell holds for {ctx['window']}. " + body).strip()


def _get(chat_id):
    with _LOCK:
        if chat_id and chat_id in CHATS:
            CHATS.move_to_end(chat_id)
            return chat_id, CHATS[chat_id]
        cid = ("c" + os.urandom(6).hex())
        CHATS[cid] = {"history": [], "created": time.time()}
        while len(CHATS) > MAX_CHATS:
            CHATS.popitem(last=False)
        return cid, CHATS[cid]


def ask(body, llm, now=None):
    """One turn. Returns {chat_id, say, hits} — never raises for a bad question."""
    text = (str(body.get("text") or "").strip())[:MAX_TEXT]
    if not text:
        return None
    sid = (str(body.get("session") or "").strip() or None)
    cid, chat = _get(str(body.get("chat_id") or "").strip() or None)
    now = now or guide.now_playa()

    ctx = guide.retrieve(text, now=now)
    say, mode = None, "fallback"
    try:
        if llm is not None and llm.available():
            prompt = _prompt(chat["history"], text)
            system = _system(ctx, sid, now)
            raw = llm.generate(prompt, system=system, timeout=T_CHAT, max_tokens=MAX_TOKENS)
            say = _clean(raw)
            if not say and raw:
                # every sentence was scratchpad: one more roll, told plainly, half the clock
                raw = llm.generate(prompt + " Answer only, in the Turtle's voice.",
                                   system=system, timeout=T_CHAT / 2, max_tokens=MAX_TOKENS)
                say = _clean(raw)
            if say:
                mode = "llm"
    except Exception:
        say = None
    if not say:
        say = fallback(ctx, text, sid) or fallback(ctx, text)

    with _LOCK:
        chat["history"].append(("seeker", text))
        chat["history"].append(("turtle", say))
        del chat["history"][:-(MAX_TURNS * 2)]
    return {"chat_id": cid, "say": say, "hits": ctx["hits"][:8], "mode": mode,
            "grounded": ctx["have_snapshot"]}
