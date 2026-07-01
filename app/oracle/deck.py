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
