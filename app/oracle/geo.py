"""Wayfinding: resolve a card's live_hook to a real BRC 2026 location + a compass map."""
import json
import os

from .deck import REPO

GEO = json.load(open(os.path.join(REPO, "data", "brc_geo.json"), encoding="utf-8"))
PLAYA = json.load(open(os.path.join(REPO, "data", "playa_2026.json"), encoding="utf-8"))
HOOKS = PLAYA["hooks"]
LANDMARKS = GEO["landmarks"]
ZONES = GEO["zones"]

# A small fixed compass rose of the city's permanent anatomy (<=32 cols for the thermal receipt).
COMPASS_ROSE = "\n".join([
    "      12  Temple / deep playa",
    "            \\   |   /",
    "  10 --------(MAN)-------- 2",
    "            /   |   \\",
    "       7   Center Camp   5",
    "               6",
])


def locate(card):
    """Return location info for a card via its live_hook + BRC geo."""
    hook = card.get("live_hook")
    h = HOOKS.get(hook, {})
    geo_ref = h.get("geo_ref")
    lm = LANDMARKS.get(geo_ref) or ZONES.get(geo_ref) if geo_ref else None
    directions = h.get("directions") or (lm.get("directions") if lm else "")
    return {
        "instances": h.get("instances") or [card.get("real_2026", {}).get("name", card["name"])],
        "directions": directions,
        "status": h.get("status", "citywide"),
        "clock": (lm or {}).get("clock"),
        "street": (lm or {}).get("street"),
        "geo_ref": geo_ref,
    }


def locate_spread(picks):
    """picks: {roots,trunk,branches: card} -> same keyed dict of location info."""
    return {realm: locate(card) for realm, card in picks.items()}


def directions_lines(picks, located):
    """Human-readable 'where to go' lines, one per drawn card."""
    out = []
    for realm in ("roots", "trunk", "branches"):
        c = picks[realm]
        loc = located[realm]
        where = loc["directions"] or "Somewhere out there — ask Playa Info."
        out.append(f"{c['name']}: {where}")
    return out
