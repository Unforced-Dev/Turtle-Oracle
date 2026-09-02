#!/usr/bin/env python3
"""The pull-first séance, offline: name -> cards -> one question -> one bite -> parchment.

    PYTHONPATH=app python3 tools/test_pull_first.py

Everything here runs with no model and no network, because that is the shape the Spark is
in whenever Ollama is cold — and because the whole point of the rebuild is that a seeker
who says nothing but their name still gets a real reading and a real quest.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from oracle import lore, printer, session  # noqa: E402
from oracle.deck import load_deck  # noqa: E402
from oracle.geo import locate_spread  # noqa: E402
from oracle.voice import is_interjection, strip_interjections  # noqa: E402
from oracle.weave import (bite_realm, landmark_realm, names_an_address,  # noqa: E402
                          weave_fallback)

FAILS = []


def check(label, condition, detail=""):
    print(("  ok   " if condition else "  FAIL ") + label + (f"\n         {detail}" if not condition and detail else ""))
    if not condition:
        FAILS.append(label)


LOOK = (
    "The table is not kind tonight and it is not cruel. Heart Remains sits where you have to "
    "face something, and it is the grief that keeps a room exactly as it was. Robot Heart is "
    "where you stand, which is to say inside a noise that never asks you anything. Above and "
    "Below is what you are reaching for, and that is the plain wish to be rooted and lifted at "
    "once. Three cards, and not one of them lets you stay in the middle. The dust settles on "
    "whichever you pick up first, so pick one up."
)


class FakeLLM:
    """Answers each prompt by the shape it asks for. Records every prompt it was given."""

    def __init__(self, **overrides):
        self.prompts = []
        self.overrides = overrides

    def available(self):
        return True

    def generate(self, prompt, system=None, as_json=False, timeout=None):
        self.prompts.append(prompt)
        if '"look"' in prompt:
            return self.overrides.get("ask", json.dumps({
                "look": LOOK,
                "question": "What have you not said out loud since you got here?",
                "chips": ["Something I avoid", "A person", "I do not know"]}))
        if '"reading"' in prompt:
            return self.overrides.get("weave", json.dumps({
                "reading": " ".join(f"w{i}" for i in range(95)),
                "adventure": ("Give away the thing in your pocket to the first stranger who asks "
                              "you a question. Out past the last lamp. Bring back what their "
                              "face did.")}))
        if '"move"' in prompt:
            return self.overrides.get("seal", json.dumps({"move": {
                "task": "Give away the thing in your pocket.",
                "where": "out past the last lamp",
                "proof": "Bring back what their face did.", "leave": ""}}))
        if '"roots"' in prompt:  # echoes
            return None
        return None


def a_seance(llm=None, name="Wren"):
    ev = session.start()
    sid = ev["session"]
    return sid, session.hear(sid, {"text": name}, llm)


def main():
    print("\nthe name goes straight to the cards:")
    sid, asking = a_seance()
    check("a name lands at `asking`, not at a stem or a sky", asking["stage"] == "asking",
          f'got {asking["stage"]}')
    check("no stem stage exists to fall into", not hasattr(session, "STEM_ASKS"))
    check("the three cards are in the event the kiosk renders from",
          all(asking["cards"][r].get("id") for r in ("roots", "trunk", "branches")))
    check("every card carries one plain line of meaning",
          all(asking["cards"][r].get("gloss") for r in ("roots", "trunk", "branches")))
    check("the Turtle read the table before it asked anything",
          bool(asking["look"]) and len(asking["look"].split()) >= 30)
    check("there is one open question, under 25 words",
          bool(asking["question"]) and len(asking["question"].split()) < 25,
          asking.get("question"))
    check("the question is a question", asking["question"].rstrip().endswith("?"))
    check("three chips are offered", len(asking["chips"]) == 3)
    check("the Turtle never claims to have heard words it was not given",
          "heard you" not in asking["say"], asking["say"])

    print("\nletting the cards speak is a whole answer:")
    proposed = session.hear(sid, {"pass": True})
    check("a pass reaches the weave, not the wind guard", proposed["stage"] == "proposed",
          proposed.get("say") or proposed.get("error"))
    check("the pass never became a share", session.SESSIONS[sid]["shares"] == [])
    check("the weave was told the seeker chose silence",
          proposed["modes"]["told"] == "cards")
    check("a reading arrived anyway", len(proposed["reading"].split()) >= 60)
    check("the offline reading never calls the seeker mute",
          "could not put it into words" not in proposed["reading"])
    check("a quest arrived anyway", bool(proposed["adventure"]))
    check("the quest is one bite, not First/Second/Third",
          not any(x in proposed["adventure"] for x in ("First.", "Second.", "Third.")))
    echoes = proposed["echoes"]
    check("echoes on a wordless séance quote nothing that was never said",
          all("“" not in line for line in echoes.values()), json.dumps(echoes, ensure_ascii=False))

    print("\nthe seal is one act, one bearing, one proof:")
    sealed = session.accept(sid)
    check("the seal lands", sealed["stage"] == "accepted", sealed.get("error"))
    quest = sealed["quest"]
    check("the parchment holds exactly one move", len(quest["moves"]) == 1,
          str(len(quest["moves"])))
    move = quest["moves"][0]
    for field in ("slot", "card", "task", "where", "at", "proof"):
        check(f"the move has a {field}", bool(move.get(field)))
    check("the vow no longer promises three moves", "three moves" not in quest["vow"])
    check("the charge says one bite", "One bite" in quest["charge"])
    check("the sealed bearing is not an address",
          not names_an_address(move["where"]), move["where"])
    check("accept replays rather than reseals",
          session.accept(sid)["say"] == sealed["say"])
    check("the tale-book keeps the sealed quest",
          (lore.last_quest(quest["for"]) or {}).get("title") == quest["title"])

    print("\nthe model path, end to end:")
    llm = FakeLLM()
    sid2, asking2 = a_seance(llm)
    check("the model's look survives the gates", asking2["look"] == LOOK)
    check("the event says who wrote the look", asking2["modes"]["look"] == "llm",
          json.dumps(asking2["modes"]))
    check("the zero-context case is the prompt's primary one",
          "asked for nothing" in llm.prompts[0] and "let it stand on the cards alone" in llm.prompts[0])
    p2 = session.hear(sid2, {"chip": "A person"}, llm)
    check("a chip is heard as a share", session.SESSIONS[sid2]["shares"] == ["A person"])
    check("the weave was handed the look it already spoke",
          any(LOOK in p for p in llm.prompts))
    s2 = session.accept(sid2, llm)
    check("the model's own bearing is kept when it is a bearing",
          s2["quest"]["moves"][0]["where"] == "out past the last lamp",
          s2["quest"]["moves"][0]["where"])
    check("a {moves:[…]} answer to a {move:…} prompt is still a seal",
          s2["modes"]["seal"] == "llm")

    print("\nthe bearing rules:")
    _, _, by_realm = load_deck()
    # the bite card's OWN camp may be named out loud; any other camp is a placement in disguise
    bite_card_name = "Questionmark Camp"
    check("the bite card's own camp is a usable bearing",
          session.usable_bearing("behind Questionmark Camp, toward the fence", bite_card_name))
    check("another camp's name is thrown out",
          not session.usable_bearing("behind Kidsville, toward the fence", bite_card_name))
    check("a lone camp name is thrown out even as its own sentence",
          not session.usable_bearing("Kidsville", bite_card_name))
    check("a clock and a street is thrown out",
          not session.usable_bearing("at 7:30 and E", bite_card_name))
    check("a bare hour is kept — a bearing may BE a time of day",
          session.usable_bearing("before 6:00, when the light is grey", bite_card_name))
    check("the Esplanade is thrown out",
          not session.usable_bearing("just off the Esplanade", bite_card_name))
    check("the unmissable landmarks are kept",
          session.usable_bearing("The Man — the center of everything. Walk toward the light.", ""))
    check("a metaphorical bearing is kept",
          session.usable_bearing("wherever the music is worst", ""))
    check("a bearing longer than a bearing is thrown out",
          not session.usable_bearing(" ".join(["word"] * 20), ""))

    print("\nthe bite is chosen once and never drifts:")
    picks = {r: by_realm[r][0] for r in ("roots", "trunk", "branches")}
    located = locate_spread(picks)
    b1 = bite_realm(located, picks)
    check("bite_realm is deterministic for a spread", b1 == bite_realm(located, picks))
    # Only five cards in the deck stand at one of the four unmissable placements, and the
    # only Tree-realm ones are the two Center Camp trunks. A shell card can substitute into
    # any slot, so the landmark rule has to hold from wherever it lands.
    lm_card = next(c for c in by_realm["trunk"]
                   if locate_spread({"trunk": c})["trunk"].get("geo_ref") == "center_camp")
    lm_picks = dict(picks, trunk=lm_card)
    lm_located = locate_spread(lm_picks)
    check("a card at an unmissable landmark takes the bite",
          bite_realm(lm_located, lm_picks) == "trunk" and landmark_realm(lm_located) == "trunk")
    lm_quest = weave_fallback("x", lm_picks, lm_located)["adventure"]
    check("a landmark is named by its name and a direction, never its address",
          "Center Camp" in lm_quest and not names_an_address(lm_quest), lm_quest)
    check("the placement data's own clock-and-street line WOULD have been an address",
          names_an_address(lm_located["trunk"]["directions"]),
          lm_located["trunk"]["directions"])

    print("\nnothing at a reveal stage may answer with a bare `say`:")
    sid3, _ = a_seance()
    retry = session.hear(sid3, {})
    check("an empty body at `asking` re-sends the whole spread",
          retry["stage"] == "asking" and retry.get("retry") and bool(retry.get("cards")))
    session.hear(sid3, {"pass": True})
    reask = session.hear(sid3, {})
    check("an empty body at `proposed` re-sends the whole offer",
          reask["stage"] == "proposed" and bool(reask.get("cards")) and bool(reask.get("adventure")))
    session.accept(sid3)
    resealed = session.hear(sid3, {})
    check("an empty body at `accepted` re-sends the parchment",
          resealed["stage"] == "accepted" and bool(resealed.get("quest")))

    print("\na séance written by an older build does not crash this one:")
    sid4, _ = a_seance()
    stale = session.SESSIONS[sid4]
    stale["picks"] = stale["located"] = None
    lost = session.hear(sid4, {"pass": True})
    check("a spreadless `asking` is an error the kiosk can toast, not a 500",
          "error" in lost and lost["stage"] == "asking")
    sid5, _ = a_seance()
    session.hear(sid5, {"pass": True})
    session.SESSIONS[sid5]["bite"] = None      # the field did not exist before the rebuild
    revived = session.accept(sid5)
    check("a session with no recorded bite still seals",
          revived["stage"] == "accepted" and len(revived["quest"]["moves"]) == 1)
    sid6, _ = a_seance()
    session.SESSIONS[sid6]["stage"] = "accepted"
    session.SESSIONS[sid6]["quest"] = None
    check("an `accepted` session with no parchment says so instead of throwing",
          "error" in session.hear(sid6, {"text": "hello"}))

    print("\nthe paper still reads, for a one-bite quest and a legacy three-move one:")
    snap = session.snapshot(sid)
    receipt = printer.format_receipt(
        {"question": " / ".join(snap["shares"]), "reading": snap["reading"],
         "adventure": snap["adventure"], "name": snap.get("name")},
        snap["picks"], snap["located"], quest=snap["quest"])
    check("a one-bite receipt heads its move THE ONE BITE",
          "THE ONE BITE" in receipt and "MOVE 1" not in receipt)
    check("a receipt survives a séance that told the Turtle nothing",
          "YOU TOLD THE TURTLE" in receipt and "THE READING" in receipt)
    legacy = dict(snap["quest"], moves=[dict(snap["quest"]["moves"][0], slot=s)
                                        for s in ("FACE", "STAND", "REACH")])
    old_receipt = printer.format_receipt(
        {"question": "", "reading": snap["reading"], "adventure": snap["adventure"],
         "name": "Wren"}, snap["picks"], snap["located"], quest=legacy)
    check("a legacy three-move receipt is numbered MOVE 1..3",
          all(f"MOVE {i}" in old_receipt for i in (1, 2, 3))
          and "THE ONE BITE" not in old_receipt)

    print("\nthe voice does not say the Turtle's written breaths:")
    for line in ("Mm.", "Hm.", "Ah.", "Mm", "“Mm.”", "Hmm..."):
        check(f"{line!r} is never sent to a voice", is_interjection(line))
    check("a real line is untouched", not is_interjection("Mind the teeth."))
    check("an interjection is dropped from the front of a real line",
          strip_interjections("Mm. That changes the shape of it.")
          == "That changes the shape of it.")
    check("a line that is only breath leaves nothing to say",
          strip_interjections("Mm. Hm.") == "")
    check("'Ah, the dust' is a sentence, not a breath",
          strip_interjections("Ah, the dust.") == "Ah, the dust.")

    print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED: " + "; ".join(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
