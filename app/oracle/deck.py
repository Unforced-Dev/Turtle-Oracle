"""Load the deck and model the Tree spread."""
import json
import os
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CARDS_PATH = os.path.join(REPO, "data", "cards.json")

SPREAD_REALMS = ("roots", "trunk", "branches")
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
