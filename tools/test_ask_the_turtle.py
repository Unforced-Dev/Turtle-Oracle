#!/usr/bin/env python3
"""Ask the Turtle, offline: retrieval, the clock, the refusals, and /api/chat end to end.

    PYTHONPATH=app python3 tools/test_ask_the_turtle.py

No model and no network. The Spark runs America/Denver and the playa runs
America/Los_Angeles, so every window here is pinned to an explicit playa-time ``now`` —
a test that trusts the machine's clock passes in Boulder and lies on playa.
"""
import datetime
import json
import os
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from oracle import chat, guide  # noqa: E402

FAILS = []
NOW = datetime.datetime.fromisoformat("2026-09-05T21:30:00-07:00")   # Saturday night, playa time


def check(label, condition, detail=""):
    print(("  ok   " if condition else "  FAIL ") + label
          + (f"\n         {detail}" if not condition and detail else ""))
    if not condition:
        FAILS.append(label)


class FakeLLM:
    """A model that answers, so the LLM path is exercised without Ollama. Records prompts."""

    model = "fake"

    def __init__(self, reply="The shell holds three things tonight. Go to the nearest one."):
        self.reply = reply
        self.prompts = []
        self.systems = []

    def available(self):
        return True

    def generate(self, prompt, system=None, as_json=False, timeout=None, **kw):
        self.prompts.append(prompt)
        self.systems.append(system or "")
        return self.reply


class DeadLLM:
    model = "dead"

    def available(self):
        return False

    def generate(self, *a, **k):      # pragma: no cover - never called
        raise AssertionError("a dead model must never be asked")


def snapshot_present():
    return os.path.exists(guide.SNAPSHOT)


def main():
    print("the clock is the playa's, not the machine's:")
    start, end, label = guide.window_for("what is on tonight", NOW)
    check("'tonight' is the evening of the day it is asked, not the next one",
          label == "tonight" and start.date() == NOW.date() and end.date() == NOW.date(),
          f"{start} .. {end}")
    check("'tonight' opens at 17:00 playa time", start.hour == 17 and start.utcoffset()
          == datetime.timedelta(hours=-7), f"{start}")
    s2, e2, l2 = guide.window_for("what about tomorrow", NOW)
    check("'tomorrow' is the next calendar day on playa",
          l2 == "tomorrow" and s2.date() == (NOW + datetime.timedelta(days=1)).date())
    s3, _, l3 = guide.window_for("anything at sunrise", NOW)
    check("'sunrise' asked at night points at the morning to come",
          l3 == "around sunrise" and s3.date() == (NOW + datetime.timedelta(days=1)).date())
    _, e4, l4 = guide.window_for("what should I do", NOW)
    check("with no time named the window is the next six hours",
          l4 == "the next six hours" and (e4 - NOW) == datetime.timedelta(hours=6))
    _, _, l5 = guide.window_for("what is happening this afternoon", NOW)
    check("'this afternoon' is its own window", l5 == "this afternoon")

    print("\nthe cards answer with or without a city:")
    tap = guide.describe_card("Taproot")
    check("a card is described from cards.json + card_lore.json",
          tap and "The Taproot" in tap and "essence:" in tap)
    check("a card is found inside a spoken sentence",
          (guide.find_card("tell me about the Heartwood") or {}).get("name") == "The Heartwood")
    check("a question that names no card finds none",
          guide.find_card("where is the nearest ice") is None)
    check("a name the deck has never heard of describes nothing",
          guide.describe_card("The Fourteenth Bicycle") is None)

    if not snapshot_present():
        print("\n  !! data/brc_2026_snapshot.json is not on this box — city tests skipped")
    else:
        print("\nretrieval, in the window the question asked for:")
        r = guide.retrieve("what is happening tonight near 9:00 and Esplanade", now=NOW)
        check("tonight's window is the one used", r["window"] == "tonight")
        check("every event hit falls on the day it was asked about, not the next one",
              all(h["when"].endswith("today") for h in r["hits"] if h["when"]),
              json.dumps([h["when"] for h in r["hits"]]))
        check("a tonight question does not surface yesterday",
              not any("yesterday" in h["when"] for h in r["hits"] if h["when"]))
        check("the block names real placements",
              "Esplanade" in r["block"] and "EVENTS (tonight)" in r["block"])
        check("the context block stays inside its ceiling",
              len(r["block"]) <= guide.MAX_BLOCK_CHARS,
              f"{len(r['block'])} chars")

        # the pinned case the whole feature turns on: 21:30 on the 5th must be the 5th
        idx = guide.index()
        s, e, _ = guide.window_for("tonight", NOW)
        picked = [rec["name"] for st, en, i in idx["occ"]
                  for rec in [idx["events"][i]]
                  if (en or st) > s and st < e]
        sixth = [st for st, en, i in idx["occ"] if st.date().day == 6 and st < e and (en or st) > s
                 and st.hour >= 5]
        check("the tonight window selects 2026-09-05 evening and no 09-06 start",
              picked and not sixth, f"{len(picked)} tonight, {len(sixth)} from the 6th")

        print("\nlooking a place up by part of its name:")

        def places(question):
            return [h for h in guide.retrieve(question, now=NOW)["hits"]
                    if h["kind"] in ("Camp", "Art")]

        found = places("tell me about Roasted Breauxs")
        check("a camp is found by the first two words of its name, and comes back first",
              found and found[0]["title"] == "Roasted Breauxs & Coffee Heauxs",
              json.dumps([h["title"] for h in found][:4]))
        check("the camp comes back with its address",
              found and found[0]["where"] == "A & 4:15",
              json.dumps(found[:1]))
        found = places("where is Planned Playahood")
        check("a two-word camp name lands on that camp",
              found and found[0]["title"] == "Planned Playahood",
              json.dumps([h["title"] for h in found][:4]))
        found = places("where is the ARTery")
        check("a landmark is found by one distinctive word",
              found and "ARTery" in found[0]["title"],
              json.dumps([h["title"] for h in found][:4]))

        print("\nwhat the shell does not hold, it does not invent:")
        r = guide.retrieve("who is playing at Mayan Warrior tonight", now=NOW)
        check("a lineup question is flagged as one", r["lineup"] is True)
        check("no DJ set, lineup or art-car schedule is in the context",
              "lineup" not in r["block"].lower() and "set time" not in r["block"].lower())
        check("the dump holds no Mayan Warrior placement to hand out",
              not any(h["title"].lower() == "mayan warrior" and h.get("where")
                      for h in r["hits"]))
        said = chat.fallback(r, "who is playing at Mayan Warrior tonight")
        check("the offline answer says it does not know",
              "does not know" in said.lower(), said)
        check("the offline answer leads with the refusal, not with a guess",
              said.lower().startswith("the turtle does not know"), said)

    print("\n/api/chat, in process:")
    fake = FakeLLM()
    out = chat.ask({"text": "what is on tonight"}, fake, now=NOW)
    check("a chat comes back with an id, a spoken answer and its places",
          out and out["chat_id"] and out["say"] and isinstance(out["hits"], list))
    check("the model was reached", out["mode"] == "llm")
    check("the system prompt is the Turtle's own voice, not a fork",
          "Move Slow & Bite Things" in fake.systems[0]
          and "YOU ARE ANSWERING A QUESTION AT THE SHELL" in fake.systems[0])
    check("the system prompt carries the playa clock and our own address",
          "Black Rock City" in fake.systems[0] and "E & 6:15" in fake.systems[0],
          fake.systems[0].split("THE SHELL HOLDS")[0][-200:])
    check("no séance means no seeker's cards in the prompt",
          "THE SEEKER'S CARDS" not in fake.systems[0])
    check("an empty question is refused", chat.ask({"text": "   "}, fake, now=NOW) is None)

    cid = out["chat_id"]
    second = chat.ask({"text": "and where is that", "chat_id": cid}, fake, now=NOW)
    check("the same chat id keeps the same chat", second["chat_id"] == cid)
    check("the previous turn is in the prompt", "what is on tonight" in fake.prompts[-1])

    print("\na chat that hangs off a live séance hears the séance:")
    from oracle import session
    sid = session.start()["session"]
    sess = session.SESSIONS[sid]
    from oracle.deck import load_deck
    _, cards, by_realm = load_deck()
    sess["name"] = "Wren"
    sess["picks"] = {r: by_realm[r][0] for r in ("roots", "trunk", "branches")}
    sess["reading"] = "You built all year for other people."
    sess["adventure"] = "Walk out past the last lamp and stay until you want one thing."
    fake2 = FakeLLM()
    out2 = chat.ask({"text": "what did my cards mean", "session": sid}, fake2, now=NOW)
    sysp = fake2.systems[0]
    check("the séance's cards ride in the prompt", "THE SEEKER'S CARDS" in sysp
          and sess["picks"]["roots"]["name"] in sysp)
    check("the reading rides verbatim", "You built all year for other people." in sysp)
    check("the quest offered rides verbatim", "past the last lamp" in sysp)
    check("a chat with a séance still answers", bool(out2["say"]))
    out3 = chat.ask({"text": "hello", "session": "not-a-session"}, FakeLLM(), now=NOW)
    check("an unknown session id is not an error", bool(out3["say"]))

    print("\nmemory does not grow forever:")
    cid = chat.ask({"text": "one"}, DeadLLM(), now=NOW)["chat_id"]
    for i in range(30):
        chat.ask({"text": f"turn {i}", "chat_id": cid}, DeadLLM(), now=NOW)
    hist = chat.CHATS[cid]["history"]
    check(f"history is capped at {chat.MAX_TURNS} turns", len(hist) <= chat.MAX_TURNS * 2,
          f"{len(hist)} entries")
    check("the cap keeps the newest turns", hist[-2][1] == "turn 29")
    before = len(chat.CHATS)
    for i in range(chat.MAX_CHATS + 20):
        chat.ask({"text": "hi"}, DeadLLM(), now=NOW)
    check(f"no more than {chat.MAX_CHATS} chats are kept", len(chat.CHATS) <= chat.MAX_CHATS,
          f"{len(chat.CHATS)} chats (was {before})")

    print("\nno model at all still answers:")
    out = chat.ask({"text": "what is on tonight"}, DeadLLM(), now=NOW)
    check("a dead model falls back to a template, not an error", bool(out["say"]))
    check("the template is marked as one", out["mode"] == "fallback")
    out = chat.ask({"text": "tell me about the Taproot"}, DeadLLM(), now=NOW)
    check("with no model the Turtle still explains a card",
          "Taproot" in out["say"] and "worst years" in out["say"], out["say"])

    print("\nno city dump at all still answers about the cards:")
    saved_idx, saved_path = guide._INDEX, guide.SNAPSHOT
    guide._INDEX = None
    guide.SNAPSHOT = "/nonexistent/brc_2026_snapshot.json"
    try:
        r = guide.retrieve("what is on tonight", now=NOW)
        check("a missing dump is not an error, it is a smaller Turtle",
              r["have_snapshot"] is False and r["hits"] == [])
        check("the context says plainly that the city is not in the shell",
              "THE CITY IS NOT IN THE SHELL" in r["block"])
        out = chat.ask({"text": "what is on tonight"}, DeadLLM(), now=NOW)
        check("with no city the Turtle says it does not know",
              "does not know" in out["say"].lower(), out["say"])
        out = chat.ask({"text": "tell me about the Crown"}, DeadLLM(), now=NOW)
        check("with no city the Turtle still knows the cards",
              "Crown" in out["say"], out["say"])
    finally:
        guide.SNAPSHOT, guide._INDEX = saved_path, saved_idx

    print("\nover HTTP, on a real socket:")
    os.environ.setdefault("ORACLE_PORT", "0")
    from oracle import server as srv
    httpd = srv.OracleServer(("127.0.0.1", 0), srv.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())

    try:
        code, d = post("/api/chat", {"text": "what is happening tonight"})
        check("POST /api/chat answers 200", code == 200, str(code))
        check("the wire carries chat_id, say and hits",
              d.get("chat_id") and d.get("say") and isinstance(d.get("hits"), list))
        code2, d2 = post("/api/chat", {"text": "and after that", "chat_id": d["chat_id"]})
        check("the same chat continues over the wire", d2["chat_id"] == d["chat_id"])
        try:
            post("/api/chat", {"text": ""})
            check("an empty question is a 400", False, "no error raised")
        except urllib.error.HTTPError as e:
            check("an empty question is a 400", e.code == 400, str(e.code))
        code3, d3 = post("/api/chat", {"text": "what did my cards mean", "session": sid})
        check("a session id over the wire is accepted", code3 == 200 and bool(d3["say"]))
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=10) as r:
            health = json.loads(r.read().decode())
        check("health reports the chats and whether the city is loaded",
              "live_chats" in health and "city" in health, json.dumps(health)[:200])
    finally:
        httpd.shutdown()
        httpd.server_close()

    # --- the narration guard: scratchpad sentences are not speech ---------------------
    from oracle import chat as _chat
    said = _chat._clean("Hmm, the seeker is asking about coffee. Let me check the Shell Holds. "
                        "GaiaDome pours coffee until eight tonight at Esplanade and 3:00. Go slow.")
    check("narration guard drops the scratchpad openers", said.startswith("GaiaDome"), said)
    check("narration guard keeps the spoken tail", "Go slow." in said, said)
    check("narration guard flags that it narrated", _chat._clean.narrated is True)
    said = _chat._clean("Okay, the seeker asked about the Taproot. We must answer in 2-5 sentences.")
    check("all-scratchpad answer cleans to nothing so the caller re-rolls", said == "", repr(said))
    said = _chat._clean("The Taproot is the dark you came out of. It is your deepest water.")
    check("a real answer passes the guard untouched", said.startswith("The Taproot"), said)
    check("a real answer is not flagged", _chat._clean.narrated is False)
    check("prompt ends by telling the model to speak, not to plan",
          _chat._prompt([], "hi").rstrip().endswith("Turtle:") and "Speak now as the Turtle" in _chat._prompt([], "hi"))

    print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED: " + "; ".join(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
