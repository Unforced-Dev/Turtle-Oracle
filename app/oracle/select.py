"""Choose the resonant three (1 Root, 1 Trunk, 1 Branch). LLM pick -> keyword score -> random."""
import json
import random
import re

STOP = set("the a an and or but of to in on for with i im i'm my me you your it its is am are was "
           "be do dont don't should would could can cant can't what how why when if about at as this "
           "that these those we our us they them he she his her".split())


def _tokens(s):
    return {t for t in re.findall(r"[a-z']+", (s or "").lower()) if t not in STOP and len(t) > 2}


def _score(qt, card):
    kw = _tokens(" ".join(card.get("keywords", [])))
    body = _tokens(card.get("reading", "") + " " + card.get("shadow", ""))
    return 4 * len(qt & kw) + len(qt & body)


def _brief(cards):
    return "\n".join(f'- {c["id"]}: {c["name"]} — {", ".join(c.get("keywords", []))}' for c in cards)


def select_llm(question, by_realm, llm):
    prompt = (
        f'A seeker asks: "{question}"\n\n'
        "Choose the ONE most resonant card from EACH realm for this question. "
        'Return JSON only: {"roots":"<id>","trunk":"<id>","branches":"<id>"}.\n\n'
        f"ROOTS (what to face):\n{_brief(by_realm['roots'])}\n\n"
        f"TRUNK (where you stand):\n{_brief(by_realm['trunk'])}\n\n"
        f"BRANCHES (what to reach for):\n{_brief(by_realm['branches'])}"
    )
    resp = llm.generate(prompt, system="You are a precise card selector. Output only valid JSON.",
                        as_json=True, timeout=60)
    if not resp:
        return None
    try:
        pick = json.loads(resp)
    except Exception:
        return None
    out = {}
    for realm in ("roots", "trunk", "branches"):
        match = next((c for c in by_realm[realm] if c["id"] == pick.get(realm)), None)
        if not match:
            return None
        out[realm] = match
    return out


def select_fallback(question, by_realm):
    qt = _tokens(question)
    out = {}
    for realm in ("roots", "trunk", "branches"):
        ranked = sorted(by_realm[realm], key=lambda c: (_score(qt, c), random.random()), reverse=True)
        out[realm] = ranked[0]
    return out


def select_cards(question, by_realm, llm=None):
    """Returns ({roots,trunk,branches}: card, mode: 'llm'|'fallback')."""
    if llm and llm.available():
        picked = select_llm(question, by_realm, llm)
        if picked:
            return picked, "llm"
    return select_fallback(question, by_realm), "fallback"
