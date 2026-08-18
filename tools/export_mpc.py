"""Export vendor-ready files for MakePlayingCards' 3.5x5" jumbo game cards.

MPC's template: 300 DPI, trim 1050x1500, 1/8" bleed each side -> upload 1125x1575.
Our art is exact 2:3 (taller than MPC's 0.70), so each card is fitted by HEIGHT
(1000x1500), then the side edges are extended outward with their own edge pixels
to reach the 1050 trim width — the same trick print_prep.py uses for bleed, and
invisible against the art's kraft-paper margins. Titles are composited with the
identical typography rules as the house 3.5x5.25 export.

Writes print/mpc/fronts/<id>.jpg (q95, 4:4:4) + print/mpc/back.jpg.
"""
from PIL import Image
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cardtitle import set_title            # the one cartouche rule, shared with print + web
from rankmark import set_rank              # the rank medallion — makes the deck deal as 52
from print_prep import art_src             # same archive-first master lookup as the house export

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{REPO}/print/mpc"
os.makedirs(f"{OUT}/fronts", exist_ok=True)

DPI = 300
TRIM = (int(3.5 * DPI), int(5 * DPI))      # 1050 x 1500
FULL = (TRIM[0] + 75, TRIM[1] + 75)        # 1125 x 1575 — 1/8" bleed each side
RANK_VARIANT = "gold"                      # "gold" (uniform antique) | "realm" (tinted)


def extend(im, left, right, top, bottom):
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


def mpc_ready(src, name=None, rank=None, realm=None, variant=RANK_VARIANT, report=None):
    im = Image.open(src).convert("RGB")
    fit_w = int(TRIM[1] * im.size[0] / im.size[1])          # height-fit: 1000 wide
    im = im.resize((fit_w, TRIM[1]), Image.LANCZOS)
    if rank:
        # The rank goes on FIRST. It checks the title plaque so the bottom mark can
        # never land on the name, and cardtitle.detect_banner finds that plaque by
        # its flatness — which the name typeset into it destroys. Run the other way
        # round the check silently returns None on every card and stops guarding.
        im = set_rank(im, rank, realm, variant=variant, report=report)
    if name:
        # Typeset BEFORE the side extension: cardtitle's fractions assume the
        # art fills the canvas, and on the padded 1050 trim the 0.66 width cap
        # lets long names overrun the banner drawn in the 1000px-wide art.
        im = set_title(im, name)
    pad = TRIM[0] - fit_w
    im = extend(im, pad // 2, pad - pad // 2, 0, 0)          # -> exact trim
    bw, bh = FULL[0] - TRIM[0], FULL[1] - TRIM[1]
    return extend(im, bw // 2, bw - bw // 2, bh // 2, bh - bh // 2)


def build():
    d = json.load(open(f"{REPO}/data/cards.json"))
    order = {"shell": 0, "roots": 1, "trunk": 2, "branches": 3}
    cards = sorted(d["cards"], key=lambda c: (order[c["realm"]], c["number"]))

    missed = []
    for c in cards:
        rep = {}
        mpc_ready(art_src(c["id"]), c["name"], c["number"], c["realm"], report=rep).save(
            f"{OUT}/fronts/{c['id']}.jpg", "JPEG",
            quality=95, optimize=True, subsampling=0, dpi=(DPI, DPI))
        if not rep.get("ok"):
            missed.append(f"{c['id']} ({rep.get('why')})")
    mpc_ready(f"{REPO}/cards/back.png").save(
        f"{OUT}/back.jpg", "JPEG", quality=95, optimize=True, subsampling=0, dpi=(DPI, DPI))

    print(f"mpc: {len(cards)} fronts + back at {FULL[0]}x{FULL[1]} "
          f"(trim {TRIM[0]}x{TRIM[1]}) -> {OUT}")
    if missed:
        print(f"mpc: NO RANK MARK on {len(missed)}: {', '.join(missed)}")


if __name__ == "__main__":
    build()
