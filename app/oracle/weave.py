"""Weave the three cards into one reading + one adventure. LLM -> template fallback."""
import json

SYSTEM = (
    "You are the Terrible Turtle Oracle — the oracle of Terrible Turtle camp at Burning Man 2026 "
    "(theme: Axis Mundi, the World Tree carried on the back of the World Turtle). Your voice is slow, "
    "grounded, warm, and wry, with a little bite. Your creed is 'Move Slow & Bite Things.' You are honest "
    "and specific, never vague or saccharine, never a generic fortune-teller. You speak directly to the "
    "seeker about their real question, weave the drawn cards into a single arc, and always end by sending "
    "them on one concrete, doable adventure into the actual 2026 playa."
)


def _line(label, c, loc):
    where = (loc or {}).get("directions", "")
    return (f'{label} — {c["name"]} ({c["realm"]}): '
            f'reading="{c["reading"]}" dare="{c["turtle_dare"]}" '
            f'real_2026="{c["real_2026"]["name"]}" where="{where}"')


def weave_llm(question, cards, llm, located=None):
    located = located or {}
    body = "\n".join([
        _line("WHAT TO FACE (root)", cards["roots"], located.get("roots")),
        _line("WHERE YOU STAND (trunk)", cards["trunk"], located.get("trunk")),
        _line("WHAT TO REACH FOR (branch)", cards["branches"], located.get("branches")),
    ])
    prompt = (
        f'A seeker asks: "{question}"\n\n'
        f"Three cards were drawn along the World Tree:\n{body}\n\n"
        "Weave them into ONE reading (about 130-170 words) spoken directly TO the seeker in the Turtle's "
        "voice. Move as one connected thought about THEIR question: what to face -> how to stand -> what to "
        "reach for. Be honest and warm, a little bite, not saccharine. Then give ONE concrete adventure they "
        "can do tonight at Burning Man that sequences the three cards' dares, names the real 2026 "
        "places/art/camps, and gives simple directions using the 'where' hints (Black Rock City is a "
        "clock + street grid, e.g. '6:00 & Esplanade', the Man at center, deep playa out past it).\n\n"
        'Return JSON only: {"reading": "...", "adventure": "..."}'
    )
    resp = llm.generate(prompt, system=SYSTEM, as_json=True, timeout=120)
    if not resp:
        return None
    try:
        out = json.loads(resp)
    except Exception:
        return None
    if isinstance(out, dict) and out.get("reading") and out.get("adventure"):
        return {"reading": out["reading"].strip(), "adventure": out["adventure"].strip()}
    return None


def weave_fallback(question, cards, located=None):
    located = located or {}
    r, t, b = cards["roots"], cards["trunk"], cards["branches"]
    reading = (
        f"You came asking, and the Tree answered in three parts, so hear them as one. "
        f"First, what to face. {r['reading']} "
        f"Now, where you stand. {t['reading']} "
        f"And what to grow toward. {b['reading']} "
        f"Move slow through all three — face “{r['name']},” plant your feet in “{t['name']},” "
        f"then bite down on “{b['name']}.”"
    )

    def move(label, c, realm):
        where = located.get(realm, {}).get("directions", "")
        tail = f" → {where}" if where else ""
        return f"{label} {c['real_2026']['name']} — {_lower_first(c['turtle_dare'])}{tail}"

    adventure = (
        "Tonight, an adventure in three moves. "
        + move("Begin at", r, "roots") + " "
        + move("Then, where you stand:", t, "trunk") + " "
        + move("Finish by reaching,", b, "branches")
    )
    return {"reading": reading, "adventure": adventure}


def _lower_first(s):
    s = s.strip()
    return s[0].lower() + s[1:] if s else s


def weave(question, cards, llm=None, located=None):
    """Returns ({reading, adventure}, mode: 'llm'|'fallback')."""
    if llm and llm.available():
        out = weave_llm(question, cards, llm, located)
        if out:
            return out, "llm"
    return weave_fallback(question, cards, located), "fallback"
