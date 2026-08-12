"""Export vendor-ready files for The Game Crafter's Jumbo Deck.

TGC's template: 300 DPI, trim 3.5x5.5 in (1050x1650), 1/8" bleed on every side
-> upload 1125x1725. RGB is mandatory — they reject CMYK — and they take PNG or
JPG; this writes the same q95 4:4:4 JPEG the MPC export writes.

Our art is exact 2:3 (0.667). TGC's jumbo is 0.636 — taller than the art rather
than shorter, which is the opposite of MPC's 3.5x5 (0.700). So where export_mpc.py
fits by height and extends the SIDES outward, this one has nothing to extend into:
the ornate frame runs the full perimeter, and letterboxing the top and bottom
would print a band of bare kraft outside the border while cropping to fill would
cut the border off. The deck's answer, and it is the same answer the MPC export
gives at 5% in the other direction, is to take the size change in the art: the
master is resized straight onto the 1050x1650 trim, a 4.76% vertical stretch
(1.5714/1.5). At that magnitude nothing in a woodcut reads as distorted — the
hatching just gets a hair taller — and the frame still reaches all four edges.

The title is composited AFTER the resize, never before, so it is set by the same
relative rule as every other export (cardtitle.TITLE_Y = 0.888 of the height,
tracked, shrunk to 0.66 of the width): the banner stretched with the art, the
type is sized off the stretched height, and the name lands in the box exactly as
it does on the house 3.5x5.25 card. Typesetting first and then stretching would
smear the type 4.8% taller than the rest of the deck.

Bleed is added last, by extending the trim's own edge pixels outward — the trick
print_prep.py uses — so no card's gold border is ever trimmed.

Writes print/tgc/fronts/<id>.jpg (48) + print/tgc/back.jpg + print/tgc/README.md.
"""
from PIL import Image
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cardtitle import set_title            # the one cartouche rule, shared with print + web
from print_prep import art_src             # same archive-first master lookup as the house export

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{REPO}/print/tgc"
os.makedirs(f"{OUT}/fronts", exist_ok=True)

DPI = 300
TRIM = (int(3.5 * DPI), int(5.5 * DPI))    # 1050 x 1650
FULL = (TRIM[0] + 75, TRIM[1] + 75)        # 1125 x 1725 — 1/8" bleed each side

README = """# The Game Crafter — Jumbo Deck upload

`fronts/<id>.jpg` (48) and `back.jpg`, cut to The Game Crafter Jumbo Card
template: **1125 x 1725 px @ 300 DPI**, which is the 3.5 x 5.5 in trim plus the
1/8 in bleed TGC asks for on every side. RGB, as TGC requires (they reject CMYK).

**Upload as-is.** Do not crop, rotate, resize, or convert the colour space — the
files already are the template. The soft, slightly smeared margin around each
card is the bleed: it is meant to be cut away, and it is there so the gold border
never gets trimmed into.

The art is the deck's native 3.5 x 5.25 in (2:3) master resized onto the taller
jumbo trim — a 4.76% vertical stretch — so the engraved frame still runs to all
four edges. Card names are typeset after the resize, by the same rule the rest of
the deck uses, so every title sits inside its banner.

Rebuild with `python3 tools/export_tgc.py`.
"""


def extend(im, left, right, top, bottom):
    """Grow the canvas by repeating the outermost row/column of pixels."""
    w, h = im.size
    canvas = Image.new("RGB", (w + left + right, h + top + bottom))
    canvas.paste(im, (left, top))
    if left:
        canvas.paste(im.crop((0, 0, 1, h)).resize((left, h)), (0, top))
    if right:
        canvas.paste(im.crop((w - 1, 0, w, h)).resize((right, h)), (left + w, top))
    fw = w + left + right
    if top:
        canvas.paste(canvas.crop((0, top, fw, top + 1)).resize((fw, top)), (0, 0))
    if bottom:
        canvas.paste(canvas.crop((0, top + h - 1, fw, top + h)).resize((fw, bottom)),
                     (0, top + h))
    return canvas


def tgc_ready(src, name=None):
    im = Image.open(src).convert("RGB").resize(TRIM, Image.LANCZOS)   # 4.76% taller
    if name:
        im = set_title(im, name)                                     # after the stretch
    bw, bh = FULL[0] - TRIM[0], FULL[1] - TRIM[1]
    return extend(im, bw // 2, bw - bw // 2, bh // 2, bh - bh // 2)


def save(im, dst):
    im.save(dst, "JPEG", quality=95, optimize=True, subsampling=0, dpi=(DPI, DPI))


def build():
    d = json.load(open(f"{REPO}/data/cards.json"))
    order = {"shell": 0, "roots": 1, "trunk": 2, "branches": 3}
    cards = sorted(d["cards"], key=lambda c: (order[c["realm"]], c["number"]))

    for c in cards:
        save(tgc_ready(art_src(c["id"]), c["name"]), f"{OUT}/fronts/{c['id']}.jpg")
    save(tgc_ready(f"{REPO}/cards/back.png"), f"{OUT}/back.jpg")
    with open(f"{OUT}/README.md", "w") as f:
        f.write(README)

    print(f"tgc: {len(cards)} fronts + back at {FULL[0]}x{FULL[1]} "
          f"(trim {TRIM[0]}x{TRIM[1]}, 1/8in bleed, RGB) -> {OUT}")


if __name__ == "__main__":
    build()
