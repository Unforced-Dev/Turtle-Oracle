"""Load the deck and model the Tree spread."""
import json
import os
import random
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CARDS_PATH = os.path.join(REPO, "data", "cards.json")

SPREAD_REALMS = ("roots", "trunk", "branches")

# The Tree spread pulls Root / Trunk / Branch. The twelve Shell cards are the axis itself,
# and cards.json has always promised they "can substitute into any position" — but nothing
# ever implemented it, so a quarter of the printed deck (including The World Turtle, the
# camp's own mascot) could never appear in a reading.
#
# One slot per spread may become a Shell card, at most, so it stays an event rather than a
# flavour. At 1-in-10 a busy night sees a handful — often enough that the turtles witness
# it, rare enough that it means something when it lands.
SHELL_CHANCE = float(os.environ.get("ORACLE_SHELL_CHANCE", "0.10"))


def draw_spread(by_realm, rng=random):
    """Pure chance, one card per slot. Returns (picks, axis_slot|None).

    axis_slot names the slot the Turtle's own axis spoke into, if any.
    """
    picks = {slot: rng.choice(by_realm[slot]) for slot in SPREAD_REALMS}
    axis_slot = None
    if by_realm.get("shell") and rng.random() < SHELL_CHANCE:
        axis_slot = rng.choice(SPREAD_REALMS)
        picks[axis_slot] = rng.choice(by_realm["shell"])
    return picks, axis_slot
SLOT_LABEL = {
    "roots": "what to face",
    "trunk": "where you stand",
    "branches": "what to reach for",
    "shell": "the axis speaks",
}


def load_deck(path=CARDS_PATH):
    """Read cards.json, tolerating a concurrent writer (the art batch) mid-write."""
    last_err = None
    for _ in range(8):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            break
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            time.sleep(0.25)
    else:
        raise RuntimeError(f"could not read {path}: {last_err}")
    cards = data["cards"]
    by_realm = {}
    for c in cards:
        by_realm.setdefault(c["realm"], []).append(c)
    return data, cards, by_realm


def card_by_id(cards, cid):
    return next((c for c in cards if c["id"] == cid), None)


def card_payload(c, loc=None):
    """The card as the web clients see it (med/thumb image routes + location)."""
    loc = loc or {}
    med = os.path.join(REPO, "cards/web/med", f"{c['id']}.jpg")
    thumb = os.path.join(REPO, "cards/web/thumb", f"{c['id']}.jpg")
    art = os.path.join(REPO, "cards/art", f"{c['id']}.png")
    return {
        "id": c["id"], "name": c["name"], "realm": c["realm"],
        "slot": SLOT_LABEL.get(c["realm"], ""),
        "reading": c["reading"], "shadow": c.get("shadow", ""),
        "turtle_dare": c["turtle_dare"],
        "real_2026": c["real_2026"]["name"],
        "location": {"directions": loc.get("directions", ""), "status": loc.get("status", ""),
                     "clock": loc.get("clock")},
        "image": (f"/med/{c['id']}.jpg" if os.path.exists(med)
                  else (f"/art/{c['id']}.png" if os.path.exists(art) else None)),
        "thumb": (f"/thumb/{c['id']}.jpg" if os.path.exists(thumb)
                  else (f"/med/{c['id']}.jpg" if os.path.exists(med) else None)),
    }
