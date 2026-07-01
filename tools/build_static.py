"""Bake deck + locations into a static cards.web.json for the GitHub Pages site.

Produces the same card shape the local server's /api/cards returns, but with RELATIVE
image paths (so it works under the /Turtle-Oracle/ Pages subpath) and includes keywords
so the client-side oracle can select and weave with no server.
"""
import json, os, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO, "app"))
from oracle.deck import load_deck, SLOT_LABEL  # noqa: E402
from oracle.geo import locate, COMPASS_ROSE      # noqa: E402

_, cards, _ = load_deck()
order = {"shell": 0, "roots": 1, "trunk": 2, "branches": 3}
ordered = sorted(cards, key=lambda c: (order[c["realm"]], c["number"]))

out = []
for c in ordered:
    loc = locate(c)
    out.append({
        "id": c["id"], "name": c["name"], "realm": c["realm"],
        "slot": SLOT_LABEL.get(c["realm"], ""),
        "keywords": c.get("keywords", []),
        "reading": c["reading"], "shadow": c.get("shadow", ""),
        "turtle_dare": c["turtle_dare"],
        "real_2026": c["real_2026"]["name"],
        "location": {"directions": loc.get("directions", ""),
                     "status": loc.get("status", ""), "clock": loc.get("clock")},
        "image": f"cards/web/med/{c['id']}.jpg",
        "thumb": f"cards/web/thumb/{c['id']}.jpg",
    })

data = {"count": len(out), "compass": COMPASS_ROSE, "cards": out}
with open(os.path.join(REPO, "cards.web.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print("wrote cards.web.json —", len(out), "cards")
