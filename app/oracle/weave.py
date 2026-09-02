"""Weave the three cards into one reading + one adventure. LLM -> template fallback."""
import json
import os
import re
import time

from .deck import REPO

# Same knob as session.py's T_LONG — the weave is the single most expensive call in the
# séance and was hardcoded to 120s, so tuning the others left this one untouched.
T_WEAVE = float(os.environ.get("ORACLE_T_LONG", "60"))

_LORE = None


def card_lore():
    """Per-card lore bundles (data/card_lore.json) — big-model judgment baked into data
    so the small runtime model inherits it. Tolerant of the file being absent."""
    global _LORE
    if _LORE is None:
        try:
            with open(os.path.join(REPO, "data", "card_lore.json"), encoding="utf-8") as f:
                _LORE = json.load(f)
        except Exception:
            _LORE = {}
    return _LORE

SYSTEM = (
    "You are the Terrible Turtle Oracle — the ancient World Turtle of Terrible Turtle camp at "
    "Burning Man 2026 (theme: Axis Mundi; the World Tree grows from your shell). "
    "Creed: 'Move Slow & Bite Things.'\n"
    "VOICE RULES — never break them:\n"
    "- Speak TO the seeker: 'you', present tense. Never talk about them in third person.\n"
    "- Short declarative sentences. Let the important lines land short and hard.\n"
    "- This is spoken aloud. Write for the ear: sentences under 18 words; clean pauses; no semicolons, "
    "parentheses, headings, bullets, or throat-clearing.\n"
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


REALMS = ("roots", "trunk", "branches")

# The four placements nobody can miss. A bearing is the rule — "out past the last lamp",
# "the first person who hands you water" — and these are its only exception: naming one is
# not an errand, because a seeker who cannot find the Man has bigger problems tonight.
# Every other placement is an address however it is dressed, and an address in a quest
# turns it into homework.
UNMISSABLE = {"the_man", "temple", "center_camp", "trash_fence"}

# What the Turtle says for those four. The placement data carries the clock-and-street
# line ("Playa Info is in Center Camp (6:00 & Esplanade)…") and that line would go straight
# onto the parchment — an address in a quest that has none. A landmark is named by its name
# and a direction, never by its address.
LANDMARK_WHERE = {
    "the_man": "The Man — the center of everything. Walk toward the light.",
    "temple": "The Temple — out past the Man, where the city goes quiet.",
    "center_camp": "Center Camp — the heart of the city. Walk toward the center.",
    "trash_fence": "The trash fence — walk any direction until the city ends.",
}


def landmark_where(loc):
    """The short bearing for a placement at one of the four landmarks, else ''."""
    return LANDMARK_WHERE.get((loc or {}).get("geo_ref"), "")


def landmark_realm(located):
    """The realm whose card stands at one of those four, or None — usually None."""
    located = located or {}
    for realm in REALMS:
        loc = located.get(realm) or {}
        if loc.get("directions") and loc.get("geo_ref") in UNMISSABLE:
            return realm
    return None


def bite_realm(located, cards):
    """THE BITE. The quest is ONE act now, so exactly one card carries it — the other two
    are still read, they are just not chores. This picks that card: the one the city put
    somewhere unmissable, if there is one, because that is the only draw where the quest
    may name a place out loud. Otherwise it rotates off the draw itself, so the bite does
    not come from the same arm of the Tree every night. Decided once, in one place: the
    spoken quest, the refinement and the sealed parchment all bite the same card."""
    lm = landmark_realm(located)
    if lm:
        return lm
    n = (cards.get("roots", {}).get("number") or 1) + (cards.get("branches", {}).get("number") or 1)
    return REALMS[n % len(REALMS)]


# THE PROOF: the one thing the seeker carries back to the shell, which is what feeds the
# vow. One flavor per realm, rotated by card number so two séances differ. It lives here
# rather than in session.py because the spoken quest and the sealed parchment have to ask
# for the SAME proof — offline they are both built from this table.
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


def proof_for(realm, card):
    """The proof for a card, the same one the seal reaches for."""
    return PROOFS[realm][((card or {}).get("number", 1) - 1) % 4]


# The offline half of ONE BEARING: what the bite says instead of an address. A bearing and
# a quality, in the Turtle's mouth — never a street. Read by the seal too, so the parchment
# says what the quest said out loud.
OPEN_WHERE = {
    "roots": "No address for this one. Walk until the sound thins and you can hear your own feet.",
    "trunk": "No address for this one. It is wherever you already stand — your camp, your street, your hour.",
    "branches":
        "No address for this one. Go where the strangers are thickest, at whatever hour you are bravest.",
}

# A `where` that is an address however it is dressed: a clock, a lettered street, the
# Esplanade — or "the address is in the WWW guide", which is an address one lookup away and
# lands on the parchment as an errand. Only a bite at an unmissable landmark may carry one.
#
# The word "address" is matched only where it POINTS AT one ("the address is in the WWW
# guide", "its exact address"). A bare \baddress\b — which is what the cloud port has —
# also fires on the Turtle's own bearing, "No address for this one.", which is the
# offline OPEN_WHERE line and the exact opposite of an address: it would burn a re-roll
# on a good quest and mark the template's own words as the thing the template exists to
# prevent.
ADDRESS_LINE = re.compile(
    r"\b\d{1,2}:\d{2}\b|\bEsplanade\b|\b[A-L]\s*(?:&|and)\s*\d"
    r"|\b(?:the|its|it's|full|exact|street)\s+address\b|\bWWW guide\b", re.I)


def names_an_address(text):
    return bool(ADDRESS_LINE.search(text or ""))


def open_where(realm, loc):
    """The bearing for a bite that is not at a landmark: the card's own citywide line when
    that line is a kind of place rather than a lookup ("Anywhere the playa is open under
    you"), else the Turtle's standing bearing for that realm. One function, because the
    parchment has to say what the spoken quest said — offline they are the same words."""
    loc = loc or {}
    line = (loc.get("directions") or "").strip()
    if loc.get("status") == "citywide" and line and not names_an_address(line):
        return line
    return OPEN_WHERE[realm]


def _line(label, c, loc):
    where = (loc or {}).get("directions", "")
    lo = card_lore().get(c["id"], {})
    extra = (f' essence="{lo["essence"]}" bridge="{lo["bridge"]}" seed="{lo["seed"]}"'
             if lo else "")
    return (f'{label} — {c["name"]} ({c["realm"]}): '
            f'reading="{c["reading"]}" shadow="{c.get("shadow", "")}" dare="{c["turtle_dare"]}" '
            f'real_2026="{c["real_2026"]["name"]}" where="{where}"{extra}')


def weave_llm(question, cards, llm, located=None, context="", pulled=False, look=""):
    """`pulled`: the seeker said nothing and let the cards speak — now the ordinary case.
    `look`: the read of the table the Turtle already gave at the asking, so the reading
    CONTINUES that rather than starting the séance over on the same three cards."""
    located = located or {}
    look = (look or "").strip()
    bite = bite_realm(located, cards)
    bite_card = cards[bite]
    landmark = landmark_realm(located) == bite
    bite_where = landmark_where(located.get(bite)).rstrip(" .") if landmark else ""
    body = "\n".join([
        _line("WHAT TO FACE (root)", cards["roots"], located.get("roots")),
        _line("WHERE YOU STAND (trunk)", cards["trunk"], located.get("trunk")),
        _line("WHAT TO REACH FOR (branch)", cards["branches"], located.get("branches")),
    ])
    prompt = (
        ("A seeker gave their name and asked for nothing else. They chose to let the cards "
         "speak. That is an answer, not a refusal — never mention that they said nothing, never "
         "apologize for it, never ask them for more.\n\n"
         if pulled else f'A seeker shared: "{question}"\n\n')
        + (f"CONTEXT: {context}\n\n" if context else "")
        + ("YOU HAVE ALREADY SPOKEN ONCE. When the cards turned over you looked at the table and "
           f'told them this, and they heard it:\n"{look}"\n\n'
           "The reading below CONTINUES that one. Go deeper into it — never repeat a sentence of "
           "it back to them, and never start the reading over as if they had not heard it.\n\n"
           if look else "")
        + f"Three cards rose along the World Tree:\n{body}\n\n"
        + ("THE BINDING — read this first: these cards were drawn BLIND, by the playa's own chance, "
           "not chosen to match. That is the craft: bind the three to each other so tightly they "
           "look inevitable. For each card take one image from it (use its essence and bridge lines) "
           "and tie it into one thought. You know nothing about this seeker, so say what is TRUE of "
           "these three standing together: open enough that anyone in this city tonight could find "
           "themselves in it, concrete enough to be about something — an image, an hour, a weight. "
           "Never a horoscope, never a guess about their life, never 'you said'. Never apologize "
           "for a card or call it random.\n\n"
           if pulled else
           "THE BINDING — read this first: these cards were drawn BLIND, by the playa's own chance, "
           "not chosen to match. That is the craft: bind them to this seeker so tightly they look "
           "inevitable. For each card, take one EXACT word or phrase the seeker said and one image "
           "from the card (use its essence and bridge lines) and tie them into one thought. Never "
           "apologize for a card or call it random.\n\n")
        + "Weave the three into ONE reading ("
        + ("60-120 words" if pulled else "90-120 words, or 60-85 when CONTEXT asks for grounding")
        + ") spoken directly TO the seeker in the "
        "Turtle's voice, honoring the REGISTER in CONTEXT. Move as one connected thought about "
        + ("what the three of them say together" if pulled else "THEIR words")
        + ": what to face -> how to stand -> what to reach for. Fold one card's shadow in as a plain "
        "warning, in your own words — never write the word 'shadow', never write 'the root/trunk/branch "
        "says', never label which card anything came from. The reading contains NO instructions and NO "
        "place names — it names what is true, not what to do or where to go; all doing belongs to the "
        "quest below. If CONTEXT says the seeker is here with a partner or friends, the reading should "
        "sound like it knows that — not describe someone facing this alone. End the reading by handing "
        "them a choice, not a prophecy.\n\n"
        "Then give ONE quest at Burning Man — ONE BITE, not an errand list — in 20-40 words, built "
        f"from the “{bite_card['name']}” card (its seed line and its dare are your raw material). It will "
        "also be spoken aloud, once, to someone tired and lit up who will remember one sentence and "
        "nothing else. So: one act, imperative, verb first, no preamble and no explaining. A second "
        "clause is allowed only when it is the payoff or the sting — never a second chore. No headings, "
        "no bullets, no First and Second and Third. Build it on these rules:\n"
        + ("- THE BITE: one act, and only one. Build it out of one image from "
           f"“{bite_card['name']}” — its seed line and its dare are the raw material — so it is an act, "
           "not an errand. No 'and then', no 'stay until…', no 'leave when you have…' — those are "
           "interior doors, and a bite has none.\n"
           "- THE CROSSING: the act crosses something. It is the thing most people out here quietly "
           "avoid — speaking first, sitting still, asking for something, giving something away, "
           "being seen. Not visit it. Not think about it. Do it.\n"
           if pulled else
           "- THE BITE: one act, and only one. Tie one EXACT word or phrase the seeker said to one "
           f"image from “{bite_card['name']}”, so the act could only be theirs. No 'and then', no 'stay "
           "until…', no 'leave when you have…' — those are interior doors, and a bite has none.\n"
           "- THE CROSSING: the act is the thing the seeker confessed they avoid, don't do, or "
           "secretly want. Not visit it. Not think about it. Do it.\n")
        + "- THE SACRIFICE, when it falls out of that on its own: the act leaves something behind — a "
        "written word, an object, a habit named out loud — left, not kept. Never bolted on.\n"
        # ONE BEARING, opened up. The rule used to be "never a camp name", with the four
        # unmissable landmarks as its only exception — and it made every quest metaphorical,
        # which is beautiful and which throws away the one thing the deck actually knows: this
        # card stands somewhere real in this year's city. So both are offered now, the model
        # chooses, and roughly half should point at the real place. The line that never moves
        # is the address: a clock and a street is homework however it is dressed.
        + "- ONE BEARING: say where, in one short phrase, and you have two ways to say it. Either NAME "
        f"THE PLACE this card stands at in this year's city — {bite_card['real_2026']['name']} — with a "
        "rough direction and nothing else pinned to it"
        + (f", said like this: {bite_where}" if landmark and bite_where else "")
        + ". Or give an OPEN BEARING: a kind of place, a kind of person, or a time of day — 'out past "
        "the last lamp', 'wherever the music is worst', 'the first person who hands you water', "
        "'before the sun is up'. Both are true tonight. Choose by what the act needs, and take the "
        "real place about half the time. Either way: NO address, NO clock time, NO lettered street, "
        f"NO Esplanade, and no camp but {bite_card['real_2026']['name']}. It is the burn — what is on the "
        "map moved, and finding it is half the quest.\n"
        "- ONE PROOF: end on the single thing they carry back to the Turtle — 'Bring back what their "
        "face did.' One line, concrete, theirs. It is the only thing the quest asks them to keep.\n"
        "- Fit the act to the hour given in CONTEXT (heat, dark, sunrise). If CONTEXT says they are here "
        "with a partner or friends, the one act is done with them, or told to them straight after — "
        "still one act, never two. If it is their first burn, keep it simple and kind.\n\n"
        'Return JSON only: {"reading": "...", "adventure": "..."}'
    )
    # Two rolls, one budget. A reading that was the SYSTEM example and nothing else, or a
    # quest that gave a clock-and-street after being asked for a bearing, is worth one more
    # roll of the model before the template — but only while half the budget is still
    # unspent, and the second roll gets half the timeout. Worst case is one full T_WEAVE.
    started = time.monotonic()
    reason = "example"
    for attempt in range(2):
        t = (T_WEAVE / 2) if attempt else T_WEAVE
        # The retry names the ACTUAL reason: "you copied the example" is no help to a model
        # that gave a bearing with a street in it. Only ever sent on the second roll.
        p = prompt + (ADDRESS_NOTE if reason == "address" else RETRY_NOTE) if attempt else prompt
        resp = llm.generate(p, system=SYSTEM, as_json=True, timeout=t)
        try:
            out = json.loads(resp) if resp else None
        except Exception:
            out = None
        if isinstance(out, dict) and out.get("reading") and out.get("adventure"):
            reading = unquote_example(out["reading"].strip())
            adventure = out["adventure"].strip()
            # The quest is address-checked HERE, where it can still be re-rolled. The seal
            # checks the parchment's bearing, but the seeker hears the SPOKEN quest first
            # and a clock-and-street in that is heard whatever the parchment later says.
            if reading and not QUEST_EXAMPLE_RE.search(adventure):
                if not names_an_address(adventure):
                    return {"reading": reading, "adventure": adventure}
                reason = "address"
            else:
                reason = "example"
        if time.monotonic() - started > T_WEAVE / 2:
            break
    return None


RETRY_NOTE = (
    "\n\nYour last answer repeated the EXAMPLE from your instructions word for word. That example "
    "is not this seeker's reading. Write this reading fresh: its first sentence must contain one "
    "exact word or phrase the seeker said above, and no sentence may come from the example.")

# The other reason the second roll happens: the quest was asked for a bearing and gave an
# address anyway — a clock, a lettered street, the Esplanade, a camp.
ADDRESS_NOTE = (
    "\n\nYour last quest gave an ADDRESS — a clock time, a lettered street, or the Esplanade. That "
    "is homework, not a quest. Write the quest again and say where the other way: name the place "
    "this card stands at, with a rough direction and no address on it, or give a bearing — a kind "
    "of place, a kind of person, or a time of day ('out past the last lamp', 'wherever the music "
    "is worst', 'the first person who hands you water'). Finding it is half the quest.")

# Measured on the cloud port of this same prompt: with the scratchpad off — which is exactly
# how llm.py runs qwen3 on the Spark — readings OPEN with the SYSTEM prompt's own example,
# word for word, and then go on in the seeker's words. Every seeker would hear the same two
# sentences first. The cure is on the way out: drop the copied sentences and keep the rest.
# Only the example's long, distinctive phrases are fingerprints — "then bite it" and "the
# Man" are the Turtle's own register and a reading that ends on them is a good reading.
EXAMPLE_RE = re.compile(
    r"built all year for other people|a fine way to disappear|tonight nobody needs you", re.I)
# the example's second half is a quest, and lands in `adventure`, not `reading`
QUEST_EXAMPLE_RE = re.compile(
    r"stay until you want one thing|past the man to where the map runs out", re.I)


def unquote_example(reading):
    """Drop any sentence copied from the SYSTEM example. None if too little is left."""
    parts = re.split(r"(?<=[.!?…][”\"'])\s+|(?<=[.!?…])\s+", reading)
    kept = [s for s in parts if not EXAMPLE_RE.search(s)]
    if len(kept) == len(parts):
        return reading
    cleaned = " ".join(kept).strip()
    return cleaned if len(cleaned.split()) >= 40 else None


def _opener():
    """Time-aware first words for the offline quest."""
    import datetime
    h = datetime.datetime.now().hour
    if 5 <= h < 12:
        return "Today, before the heat wins, one bite."
    if 12 <= h < 17:
        return "This afternoon — move through shade and ice, save the far playa for dark. One bite."
    if 17 <= h < 21:
        return "As the light goes gold, one bite."
    if 21 <= h < 24 or h < 2:
        return "Tonight, one bite."
    return "In the deep night, one bite — and if your legs hold, take it facing the sunrise."


def _first_sentence(text):
    text = (text or "").strip()
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    return parts[0] if parts else text


def _short_words(text, limit):
    words = (text or "").split()
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]).rstrip(" ,;:—-") + "…"


def weave_fallback(question, cards, located=None, pulled=False):
    located = located or {}
    bite = bite_realm(located, cards)
    r, t, b = cards["roots"], cards["trunk"], cards["branches"]
    warning = _first_sentence(t.get("shadow") or r.get("shadow") or b.get("shadow"))
    question_short = _short_words(question, 12).rstrip(".!?")
    question_quote = f"“{question_short}”" if question_short.endswith("…") else f"“{question_short}.”"
    # A seeker who let the cards speak brought the Turtle nothing to quote, and quoting
    # "The seeker could not put it into words" back at them is the template calling them
    # mute. The rest of the reading is the same three cards, unchanged.
    opening = ("You brought the Turtle no words, and the Turtle does not need them. Hear the three as one. "
               if pulled else
               f"You brought the Turtle this: {question_quote} Hear the answer as one. ")
    reading = (
        opening
        + f"{_first_sentence(r['reading'])} {_first_sentence(t['reading'])} "
        + f"{_first_sentence(b['reading'])} Mind the teeth: {warning} "
        "Nothing here predicts you. Choose what you will face, what you will stand in, and what you "
        "will reach for. Then bite."
    )
    # One act, one bearing, one proof — the same three parts the model is asked for, stitched
    # from the card instead of written. The dare IS the act; the Turtle only has to say where
    # and what to bring home.
    c = cards[bite]
    loc = located.get(bite) or {}
    where = (landmark_where(loc) if bite == landmark_realm(located) and landmark_where(loc)
             else open_where(bite, loc))
    adventure = f"{_opener()} {c['turtle_dare'].strip()} {where} {proof_for(bite, c)}"
    return {"reading": reading, "adventure": adventure}


def _lower_first(s):
    s = s.strip()
    return s[0].lower() + s[1:] if s else s


def weave(question, cards, llm=None, located=None, context="", pulled=False, look=""):
    """Returns ({reading, adventure}, mode: 'llm'|'fallback')."""
    if llm and llm.available():
        out = weave_llm(question, cards, llm, located, context, pulled=pulled, look=look)
        if out:
            return out, "llm"
    return weave_fallback(question, cards, located, pulled=pulled), "fallback"
