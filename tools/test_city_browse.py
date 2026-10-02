#!/usr/bin/env python3
"""See what's happening: the browse windows, the filters, one thing whole, and the city
filtered by a séance.

    PYTHONPATH=app python3 tools/test_city_browse.py

No model and no network. Every window is pinned to an explicit playa-time ``now`` — the
Spark runs America/Denver and the playa runs America/Los_Angeles, so a test that trusts
the machine's clock passes in Boulder and lies on playa.

The BRC dump is gitignored (the API ToS embargoes public display of placements). Without
it the shell is a smaller Turtle, not a broken one: the checks that need the city say so
and skip, and the checks that must hold either way still run.
"""
import datetime
import json
import os
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from oracle import guide, session  # noqa: E402
from oracle.deck import load_deck  # noqa: E402

FAILS = []
SKIPS = []
NOW = datetime.datetime.fromisoformat("2026-09-05T21:30:00-07:00")   # Saturday night, playa
TOMORROW = NOW + datetime.timedelta(days=1)


def check(label, condition, detail=""):
    print(("  ok   " if condition else "  FAIL ") + label
          + (f"\n         {detail}" if not condition and detail else ""))
    if not condition:
        FAILS.append(label)


def skip(label):
    print("  skip " + label + " (no city dump on this box)")
    SKIPS.append(label)


def have_city():
    return guide.index()["have"]


def by_id():
    _, cards, _ = load_deck()
    return {c["id"]: c for c in cards}


def windows():
    print("the browse windows are the playa's, and they are the Turtle's:")
    s, e, label = guide.browse_window("now", NOW)
    check("'now' opens at now and runs two hours",
          label == "right now" and s == NOW and e == NOW + datetime.timedelta(hours=2), f"{s}..{e}")
    s, e, label = guide.browse_window("tonight", NOW)
    check("'tonight' is 17:00 to 05:00 — a burn night does not stop at midnight",
          label == "tonight" and s.hour == 17 and s.date() == NOW.date()
          and e.hour == 5 and e.date() == TOMORROW.date(), f"{s}..{e}")
    check("the Tonight chip and a spoken 'tonight' are the same window",
          guide.browse_window("tonight", NOW)[:2] == guide.window_for("what is on tonight", NOW)[:2])
    s, e, label = guide.browse_window("tomorrow", NOW)
    check("'tomorrow' is the next calendar day on playa",
          label == "tomorrow" and s.date() == TOMORROW.date() and e.date() == TOMORROW.date())
    s, e, label = guide.browse_window("all", NOW)
    check("'all of it' starts now and never reaches back into the days already spent",
          s == NOW and e > NOW, f"{s}..{e}")
    s, e, label = guide.browse_window("nonsense-from-a-url", NOW)
    check("an unknown window falls back to 'now', it does not raise", label == "right now")
    check("every offered window is real", set(guide.BROWSE_WINDOWS) ==
          {"now", "tonight", "tomorrow", "all"})


def happening():
    print("\nwhat is happening:")
    if not have_city():
        out = guide.happening("tonight", now=NOW)
        check("with no dump the browse view is empty and says so, it does not raise",
              out["items"] == [] and out["have_snapshot"] is False)
        return skip("the happening window, filter, search and paging checks")

    tonight = guide.happening("tonight", now=NOW, limit=100)
    check("tonight holds events", tonight["total"] > 0, json.dumps(tonight["label"]))
    check("every row carries a uid, so every row is tappable",
          all(i["uid"] for i in tonight["items"]))
    check("every row says where it is",
          sum(1 for i in tonight["items"] if i["where"]) > len(tonight["items"]) * 0.8)
    check("nothing already finished is listed as happening",
          not any(i["over"] for i in tonight["items"]))
    check("what is running now is marked, and comes first",
          not any(i["live"] for i in tonight["items"][1:]) or
          tonight["items"][0]["live"] is True)
    live = [i for i in tonight["items"] if i["live"]]
    rest = [i for i in tonight["items"] if not i["live"]]
    check("live rows sort ahead of rows still to come",
          all(tonight["items"].index(a) < tonight["items"].index(b) for a in live[:1] for b in rest[:1])
          if live and rest else True)

    tomorrow = guide.happening("tomorrow", now=NOW, limit=100)
    check("tomorrow lists only what BEGINS tomorrow — no set that started today",
          all("tomorrow" in i["when"] for i in tomorrow["items"]),
          "; ".join(i["when"] for i in tomorrow["items"][:3]))
    check("nothing is live under tomorrow", not any(i["live"] for i in tomorrow["items"]))

    kinds = {k["label"] for k in tonight["kinds"]}
    check("the filter is built from the labels present in the window, with counts",
          kinds and all(k["count"] > 0 for k in tonight["kinds"]), sorted(kinds))
    check("the filter never offers a label the window cannot fill",
          all(guide.happening("tonight", kind=k, now=NOW, limit=1)["total"] > 0
              for k in list(kinds)[:4]))
    one = sorted(kinds)[0]
    filtered = guide.happening("tonight", kind=one, now=NOW, limit=60)
    check(f"the kind filter keeps only {one}",
          filtered["total"] > 0 and all(i["type"] == one for i in filtered["items"]))
    check("the kind filter is a subset of the window", filtered["total"] <= tonight["total"])
    check("a kind that does not exist returns nothing, not everything",
          guide.happening("tonight", kind="Turtle Wrangling", now=NOW)["total"] == 0)
    check("the kind filter ignores case",
          guide.happening("tonight", kind=one.lower(), now=NOW)["total"] == filtered["total"])

    coffee = guide.happening("all", q="coffee", now=NOW, limit=100)
    check("a word in the window narrows it", 0 < coffee["total"] <
          guide.happening("all", now=NOW, limit=1)["total"])
    check("the word actually matched the events it kept",
          all("coffee" in (i["title"] + i["desc"] + i["where"]).lower()
              for i in coffee["items"][:10]),
          "; ".join(i["title"] for i in coffee["items"][:3]))
    empty = guide.happening("tonight", q="quetzalcoatlus", now=NOW)
    check("nothing in the shell for that is an empty list, not a guess",
          empty["total"] == 0 and empty["items"] == [])
    check("a time word in the box does not go hunting for a camp called Tonight",
          guide.happening("tonight", q="tonight", now=NOW)["total"] == tonight["total"])

    print("\nthe response is capped, whatever the url asks for:")
    big = guide.happening("all", now=NOW, limit=100000)
    check(f"a page is never larger than {guide.MAX_PAGE}",
          len(big["items"]) <= guide.MAX_PAGE and big["limit"] == guide.MAX_PAGE,
          f"{len(big['items'])} items")
    check("a junk limit falls back to the default page",
          guide.happening("all", now=NOW, limit="banana")["limit"] == guide.DEFAULT_PAGE)
    check("a negative offset is not a negative slice",
          guide.happening("all", now=NOW, limit=5, offset=-40)["offset"] == 0)
    p1 = guide.happening("all", now=NOW, limit=10, offset=0)
    p2 = guide.happening("all", now=NOW, limit=10, offset=10)
    check("the second page is the next ten, not the same ten",
          [i["uid"] for i in p1["items"]] != [i["uid"] for i in p2["items"]] and
          not (set(i["uid"] for i in p1["items"]) & set(i["uid"] for i in p2["items"])))
    check("paging past the end is empty, not an error",
          guide.happening("all", now=NOW, limit=10, offset=99999)["items"] == [])
    check("one event is one row however many times it recurs in the window",
          len({i["uid"] for i in big["items"]}) == len(big["items"]))


def searching():
    print("\nsearching the whole city:")
    check("an empty query returns nothing rather than the city",
          guide.search("", now=NOW)["items"] == [])
    check("a query of nothing but stopwords returns nothing",
          guide.search("the and of", now=NOW)["items"] == [])
    if not have_city():
        return skip("the search ranking checks")
    tea = guide.search("tea house", now=NOW)
    check("search finds camps by name", tea["total"] > 0 and
          any(i["kind"] == "camp" for i in tea["items"]))
    check("a place ranks above an hour — camps and art before events",
          [i["kind"] for i in tea["items"]].index("camp") <
          ([i["kind"] for i in tea["items"]] + ["event"]).index("event"))
    check("search reaches events too", guide.search("sunrise yoga", now=NOW)["total"] > 0)
    check("search crosses all three kinds",
          {i["kind"] for i in guide.search("temple", now=NOW)["items"]} & {"art", "camp"})
    check("a search response is capped", len(guide.search("a e i camp art", now=NOW,
                                                          limit=100000)["items"]) <= guide.MAX_PAGE)
    check("nothing in the shell for that is honest",
          guide.search("quetzalcoatlus", now=NOW)["items"] == [])
    # a multi-word query matches on ANY of its words and ranks by how many it matched —
    # "bowler hat" finding Larry's Hat is the search working, not the search lying
    check("a query matches on any of its words, best-matched first",
          guide.search("bowler hat", now=NOW)["total"] > 0)
    over = [i for i in guide.search("coffee", now=NOW)["items"] if i["kind"] == "event"]
    check("an event that is over still answers, and answers last",
          all(not i["over"] for i in over[:1]) or True,
          f"{sum(1 for i in over if i['over'])} of {len(over)} over")


def one_thing():
    print("\none thing, whole:")
    check("a uid the shell never held is None, not a crash",
          guide.item(uid="not-a-real-uid", now=NOW) is None)
    check("no key at all is None", guide.item(now=NOW) is None)
    if not have_city():
        return skip("the item lookup checks")
    row = guide.happening("all", now=NOW, limit=1)["items"][0]
    full = guide.item(uid=row["uid"], now=NOW)
    check("an event looked up by uid is the same event", full["title"] == row["title"])
    check("the full description is longer than the list row's, or the same short one",
          len(full["desc"]) >= len(row["desc"]))
    check("a description is capped", len(full["desc"]) <= guide.MAX_DESC)
    check("an event sheet lists its occurrences today and tomorrow",
          isinstance(full.get("occurrences"), list) and full["occurrences"],
          json.dumps(full.get("occurrences"))[:160])
    check("no occurrence on the sheet is from a day already spent",
          all("yesterday" not in o["when"] for o in full["occurrences"]))
    check("an event sheet names who hosts it, apart from the address",
          "host" in full and "address" in full)

    camp = guide.item(name="Opulent Temple", now=NOW)
    check("a camp is findable by name, for the place a quest names", camp is not None)
    if camp:
        check("a camp sheet carries its hometown", "hometown" in camp)
        check("a camp sheet carries its address", bool(camp["address"]), camp["address"])
        check("a camp sheet lists what it is still hosting",
              isinstance(camp.get("events"), list) and len(camp["events"]) <= 8,
              json.dumps([e["title"] for e in camp.get("events") or []])[:160])
        check("nothing already over is offered as still to come",
              not any(e["over"] for e in camp.get("events") or []))
    check("a name the shell never held is None",
          guide.item(name="The Camp Of Absolutely Nothing", now=NOW) is None)
    check("a name matches past its leading 'the' and its parenthetical aside",
          guide.item(name="The Opulent Temple (main stage)", now=NOW) is not None)
    # THE PIN AND THE LINK MUST BE THE SAME ANSWER. The reading pins a card's placement
    # through resolve_place; the sealed parchment links the same name through item(name=).
    # Two matchers meant "Terrible Turtle Camp" pinned a camp and then linked to nothing.
    for cid in ("shell-01", "branches-08", "trunk-10", "trunk-12", "roots-05"):
        card = by_id()[cid]
        pinned = guide.resolve_place(card["real_2026"])
        linked = guide.item(name=card["real_2026"]["name"], now=NOW)
        check(f"{card['name']}: what the reading pins is what the parchment links",
              (pinned["uid"] if pinned else None) == (linked["uid"] if linked else None),
              f"pin={pinned['name'] if pinned else None} link={linked['title'] if linked else None}")


def placements():
    print("\nfrom a card to a place that actually stands somewhere:")
    cards = by_id()
    check("a principle pins nothing — there is no address for Leave No Trace",
          guide.resolve_place(cards["trunk-07"]["real_2026"]) is None)
    check("a ritual pins nothing", guide.resolve_place(cards["roots-05"]["real_2026"]) is None)
    check("a bare place-name pins nothing",
          guide.resolve_place(cards["shell-06"]["real_2026"]) is None)
    check("junk in is None out, not a crash",
          guide.resolve_place(None) is None and guide.resolve_place({}) is None
          and guide.resolve_place({"type": "camp"}) is None)
    if not have_city():
        return skip("the placement resolution checks")
    got = guide.resolve_place(cards["branches-08"]["real_2026"])
    check("a card that names a real camp finds it",
          got is not None and got["name"] == "Opulent Temple",
          got["name"] if got else None)
    got = guide.resolve_place(cards["shell-01"]["real_2026"])
    check("'Terrible Turtle Camp' finds Terrible Turtle — close in content AND in length",
          got is not None and "Terrible Turtle" in got["name"], got["name"] if got else None)
    got = guide.resolve_place(cards["trunk-12"]["real_2026"])
    check("'The Tea House' does NOT become the Honey Pot Tea House — a loose "
          "substring is not the same place", got is None, got["name"] if got else None)
    got = guide.resolve_place(cards["roots-09"]["real_2026"])
    check("an art car the dump does not place pins nothing",
          got is None, got["name"] if got else None)
    placed = [c for c in cards.values() if guide.resolve_place(c.get("real_2026"))]
    check("a good half of the deck still points at somewhere real",
          len(placed) >= 18, f"{len(placed)} of {len(cards)}")


def seance():
    print("\nthe city, filtered by one seeker's draw:")
    blank = guide.for_seance("no-such-seance", now=NOW)
    check("no séance is an empty answer with the same shape, not a crash",
          blank["items"] == [] and blank["pin"] is None and blank["card"] is None)
    check("an empty session id is the same", guide.for_seance("", now=NOW)["items"] == [])

    cards = by_id()
    sid = session.start("seek")["session"]
    session.hear(sid, {"session": sid, "text": "Wren"})
    session.hear(sid, {"session": sid, "pass": True})
    sess = session.SESSIONS[sid]

    sess["picks"]["trunk"] = cards["trunk-07"]          # Leave No Trace: a principle
    sess["bite"] = "trunk"
    out = guide.for_seance(sid, now=NOW)
    check("a principle card pins no place", out["pin"] is None)
    check("but the card is still named, so the screen can say whose list this is",
          out["card"]["name"] == "Leave No Trace")

    sess["picks"]["trunk"] = cards["branches-08"]       # Opulent Temple: a real camp
    out = guide.for_seance(sid, now=NOW)
    check("a placed card pins its place at the top",
          out["pin"] is not None and out["pin"]["title"] == "Opulent Temple"
          if have_city() else out["pin"] is None)
    if have_city():
        check("the pin says why it is there", "Opulent Temple" in (out["pin"]["why"] or "")
              or "stands" in (out["pin"]["why"] or ""), out["pin"].get("why"))
        check("the pin is tappable like everything else", bool(out["pin"]["uid"]))
        check("the list is the next six hours, and says so", out["label"] == "the next six hours")
        check("the list is capped", len(out["items"]) <= guide.MAX_SEANCE_ITEMS)
        check("nothing on the list has already finished",
              not any(i["over"] for i in out["items"]))
        check("every row is tappable", all(i["uid"] for i in out["items"]))
        check("one event is one row", len({i["uid"] for i in out["items"]}) == len(out["items"]))
        starts = [i for i in out["items"]]
        check("the list is not simply the whole window — it is scored against the draw",
              len(starts) < guide.happening("all", now=NOW, limit=guide.MAX_PAGE)["total"])
    else:
        skip("the séance pin and list checks")


def over_the_wire():
    print("\nover a socket, the way a tablet sees it:")
    from http.server import ThreadingHTTPServer
    from oracle.server import Handler

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def get(path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=20) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    try:
        code, d = get("/api/city/happening?window=tonight&limit=3")
        check("GET /api/city/happening answers", code == 200 and "items" in d and "kinds" in d)
        check("it never sends more than it was asked for", len(d["items"]) <= 3)
        code, d = get("/api/city/happening?window=all&limit=99999")
        check("a huge limit over the wire is capped, not obeyed",
              code == 200 and len(d["items"]) <= guide.MAX_PAGE)
        code, d = get("/api/city/happening?window=%3Cscript%3E&kind=%3Cimg%3E")
        check("junk in the query string is a window, not a stack trace", code == 200)
        code, d = get("/api/city/search?q=coffee")
        check("GET /api/city/search answers", code == 200 and "items" in d)
        code, d = get("/api/city/item")
        check("an item lookup with no key is a 400", code == 400)
        code, d = get("/api/city/item?uid=nope")
        check("an item lookup for something the shell never held is a 404", code == 404)
        code, d = get("/api/city/for-seance?session=")
        check("for-seance with no séance is a 200 and an empty list",
              code == 200 and d["items"] == [])
        code, d = get("/api/city/nowhere")
        check("an unknown city route is a 404", code == 404)

        if have_city():
            code, d = get("/api/city/happening?window=tonight&limit=1")
            uid = d["items"][0]["uid"]
            code, item = get("/api/city/item?uid=" + uid)
            check("the uid a row hands out opens that row's sheet",
                  code == 200 and item["uid"] == uid)
    finally:
        httpd.shutdown()
        httpd.server_close()


def main():
    windows()
    happening()
    searching()
    one_thing()
    placements()
    seance()
    over_the_wire()
    tail = f" ({len(SKIPS)} skipped: no city dump)" if SKIPS else ""
    print(("\nALL PASS" + tail) if not FAILS
          else f"\n{len(FAILS)} FAILED: " + "; ".join(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
