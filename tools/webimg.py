"""Generate web-optimized card images: cards/web/thumb (300px) + cards/web/med (900px).

The art leaves the banner cartouche empty on purpose — the name is typeset, not drawn
(see tools/cardtitle.py). The print deck has always done that; the web images did not,
so the site showed 48 blank banners. Both now go through the same set_title, so a card
on the page reads exactly like the card in your hand.

The title is composited once on the full-resolution master and the two sizes are
downsampled from it: same relative baseline and width rule at every size, and the
thumb gets antialiased type instead of a hinted 11px face.
"""
from PIL import Image
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cardtitle import set_title  # the banner typesetting, shared with the print export

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ART = f"{REPO}/cards/art"
os.makedirs(f"{REPO}/cards/web/thumb", exist_ok=True); os.makedirs(f"{REPO}/cards/web/med", exist_ok=True)
d = json.load(open(f"{REPO}/data/cards.json"))
def save(im, dst, w, q=82):
    h = int(w*im.size[1]/im.size[0])
    im.resize((w, h), Image.LANCZOS).save(dst, "JPEG", quality=q, optimize=True)
def art_src(cid):
    # The committed q95 .jpg archive is the build source, so every clone builds
    # identical bytes; the local-only .png master is the fallback for fresh gens.
    p = f"{ART}/{cid}.jpg"
    return p if os.path.exists(p) else f"{ART}/{cid}.png"
for c in d["cards"]:
    titled = set_title(Image.open(art_src(c["id"])).convert("RGB"), c["name"])
    save(titled, f"{REPO}/cards/web/thumb/{c['id']}.jpg", 300)
    save(titled, f"{REPO}/cards/web/med/{c['id']}.jpg", 900)
# the back carries no name — same as the print export, which builds it without one
save(Image.open(f"{REPO}/cards/back.png").convert("RGB"), f"{REPO}/cards/web/med/back.jpg", 900)
print(f"web images generated: {len(d['cards'])} med + {len(d['cards'])} thumb, titled; back.jpg untitled")
