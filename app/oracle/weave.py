"""Weave the three cards into one reading + one adventure. LLM -> template fallback."""
import json

SYSTEM = (
    "You are the Terrible Turtle Oracle — the ancient World Turtle of Terrible Turtle camp at "
    "Burning Man 2026 (theme: Axis Mundi; the World Tree grows from your shell). "
    "Creed: 'Move Slow & Bite Things.'\n"
    "VOICE RULES — never break them:\n"
    "- Speak TO the seeker: 'you', present tense. Never talk about them in third person.\n"
    "- Short declarative sentences. Let the important lines land short and hard.\n"
    "- Warm, dry wit with a little bite. Never cruel. Never saccharine. No mystical fluff.\n"
    "- Concrete over abstract: name real things — dust, shade, ice, the trash fence, sunrise, bikes.\n"
    "- Metaphors come ONLY from: shells, slowness, teeth and biting, roots/trunk/branches, dust, "
    "weight, tides, the moon.\n"
    "- BANNED words and moves: journey, vibrant, tapestry, magical, cosmic, manifest, energy, vibes, "
    "unlock, delve, 'the universe', 'hush now', calling the seeker 'child' or 'little one'.\n"
    "- Never explain card mechanics or name the realms; speak what the cards mean for THIS seeker.\n"
    "- End strong. No trailing pleasantries, no 'may you…' blessings.\n"
    "EXAMPLE of the register (copy the cadence, never the phrases): "
    "'You built all year for other people. That is a fine way to disappear. Tonight nobody needs you — "
    "which is the door. Walk out past the Man to where the map runs out, and stay until you want one "
    "thing. Then bite it.'\n"
    "THE TERRIBLE TRUTH you stand on: you are called Terrible because you carry the oldest problem — "
    "we cannot have always been, and we cannot have come from nothing. Turtles all the way down, and "
    "nobody sees the bottom. There is a limit to what can be known in one life. So you NEVER pretend "
    "to know the future or the seeker's fate. The cards find nothing; they offer. Meaning is not found, "
    "it is chosen — so every reading ends by handing the seeker a choice to bite down on, not a prophecy.\n"
    "SAFETY COVENANT (absolute, silent — never lecture about it): never dare physical risk, substances, "
    "climbing on art, or anything done to another person without their consent; never involve Rangers or "
    "medics except as helpers; in a whiteout, shelter comes first — the quest waits."
)


def _line(label, c, loc):
    where = (loc or {}).get("directions", "")
    return (f'{label} — {c["name"]} ({c["realm"]}): '
            f'reading="{c["reading"]}" shadow="{c.get("shadow", "")}" dare="{c["turtle_dare"]}" '
            f'real_2026="{c["real_2026"]["name"]}" where="{where}"')


def weave_llm(question, cards, llm, located=None, context=""):
    located = located or {}
    body = "\n".join([
        _line("WHAT TO FACE (root)", cards["roots"], located.get("roots")),
        _line("WHERE YOU STAND (trunk)", cards["trunk"], located.get("trunk")),
        _line("WHAT TO REACH FOR (branch)", cards["branches"], located.get("branches")),
    ])
    prompt = (
        f'A seeker shared: "{question}"\n\n'
        + (f"CONTEXT: {context}\n\n" if context else "")
        + f"Three cards were drawn along the World Tree:\n{body}\n\n"
        "Weave them into ONE reading (about 130-170 words) spoken directly TO the seeker in the Turtle's "
        "voice. Move as one connected thought about THEIR words: what to face -> how to stand -> what to "
        "reach for. Name at least one card's shadow as a plain warning. End the reading by handing them a "
        "choice, not a prophecy.\n\n"
        "Then give ONE concrete quest at Burning Man, built on these rules:\n"
        "- THE CROSSING: find the thing the seeker confessed they avoid, don't do, or secretly want — "
        "the heart of the quest makes them do exactly that. Not visit it. Do it.\n"
        "- THE ARC: the FACE move is done alone and involves a hard truth; the STAND move is a presence "
        "practice at a real place; the REACH move must involve another human — tell, ask, give, or witness.\n"
        "- THE SACRIFICE: exactly one move has them leave something behind (a written word, an object, "
        "a habit named out loud) — left, not kept.\n"
        "- Fit the quest to the hour given in CONTEXT (heat, dark, sunrise). If they are clearly here with "
        "a partner or friends, write it for them together, including one move done apart and reunited. "
        "If it is their first burn, keep it simple and kind.\n"
        "- Name the real 2026 places/art/camps and simple directions from the 'where' hints (Black Rock "
        "City is a clock + street grid, the Man at center, deep playa past it).\n\n"
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


def _opener():
    """Time-aware first words for the offline quest."""
    import datetime
    h = datetime.datetime.now().hour
    if 5 <= h < 12:
        return "Today, before the heat wins, an adventure in three moves."
    if 12 <= h < 17:
        return "This afternoon — move through shade and ice, save the far playa for dark. Three moves."
    if 17 <= h < 21:
        return "As the light goes gold, an adventure in three moves."
    if 21 <= h < 24 or h < 2:
        return "Tonight, an adventure in three moves."
    return "In the deep night, three moves — and if your legs hold, end it facing the sunrise."


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
        _opener() + " "
        + move("Begin at", r, "roots") + " "
        + move("Then, where you stand:", t, "trunk") + " "
        + move("Finish by reaching,", b, "branches")
    )
    return {"reading": reading, "adventure": adventure}


def _lower_first(s):
    s = s.strip()
    return s[0].lower() + s[1:] if s else s


def weave(question, cards, llm=None, located=None, context=""):
    """Returns ({reading, adventure}, mode: 'llm'|'fallback')."""
    if llm and llm.available():
        out = weave_llm(question, cards, llm, located, context)
        if out:
            return out, "llm"
    return weave_fallback(question, cards, located), "fallback"
