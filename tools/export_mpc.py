"""Export vendor-ready files for MakePlayingCards' 3.5x5" jumbo game cards.

MPC's template: 300 DPI, trim 1050x1500, 1/8" bleed each side -> upload 1125x1575.
Our art is exact 2:3 (taller than MPC's 0.70), so each card is fitted by HEIGHT
(1000x1500), then the side edges are extended outward with their own edge pixels
to reach the 1050 trim width — the same trick print_prep.py uses for bleed, and
invisible against the art's kraft-paper margins. Titles are composited with the
identical typography rules as the house 3.5x5.25 export.

63 cards go up, not 52: MPC charges the same for anything up to 63 in a deck, so the
spare eleven are the extras in data/extras.json — two jokers, a title card, two
reference cards, one card per realm and two blanks. They are NOT oracle cards and are
not in cards.json; everything printed on them is typeset by tools/extracard.py.

Files are named <NN>-<slug>.jpg, NN being the card's place in the deck: a plain
filename sort is the order a fresh deck should arrive in, which is the order the
files get dragged into MPC's designer. Writes print/mpc/fronts/ + print/mpc/back.jpg.
"""
from PIL import Image
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cardtitle import set_title            # the one cartouche rule, shared with print + web
from rankmark import set_rank, set_word    # the rank medallion — makes the deck deal as 52
from extracard import set_extra            # the extras' copy, in the same two faces
from extracard import art_src as extra_src
from print_prep import art_src             # same archive-first master lookup as the house export

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{REPO}/print/mpc"
os.makedirs(f"{OUT}/fronts", exist_ok=True)

DPI = 300
TRIM = (int(3.5 * DPI), int(5 * DPI))      # 1050 x 1500
FULL = (TRIM[0] + 75, TRIM[1] + 75)        # 1125 x 1575 — 1/8" bleed each side
RANK_VARIANT = "gold"                      # "gold" (uniform antique) | "realm" (tinted)
REALMS = ("shell", "roots", "trunk", "branches")   # the deck's own order, from cards.json


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


def mpc_ready(src, name=None, rank=None, realm=None, variant=RANK_VARIANT, report=None,
              extra=None):
    im = Image.open(src).convert("RGB")
    fit_w = int(TRIM[1] * im.size[0] / im.size[1])          # height-fit: 1000 wide
    im = im.resize((fit_w, TRIM[1]), Image.LANCZOS)
    if extra:
        # An extra's mark goes on first for the same reason a rank does — the plaque
        # has to still be flat when it is probed — and its title is set inside
        # set_extra, off a box measured there, because an EMPTY card defeats
        # cardtitle's own flat-and-light banner detector.
        if extra.get("mark"):
            im = set_word(im, extra["mark"], report=report)
        im = set_extra(im, extra)
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


def deck_sequence():
    """The 63 cards in the order a fresh deck should arrive in.

    Title, then how to read it, then how to deal it; then each realm — its own
    reference card first, then its thirteen from Ace to King; then the two jokers, then
    the two blanks to draw your own. Realm order is cards.json's own (shell, roots,
    trunk, branches: the tree read from the turtle up).
    """
    cards = json.load(open(f"{REPO}/data/cards.json"))["cards"]
    extras = json.load(open(f"{REPO}/data/extras.json"))["cards"]
    x = {e["id"]: e for e in extras}
    by_realm = {r: sorted([c for c in cards if c["realm"] == r],
                          key=lambda c: c["number"]) for r in REALMS}

    seq = [x["extra-title"], x["extra-howto-read"], x["extra-howto-deal"]]
    for r in REALMS:
        seq.append(x[f"extra-realm-{r}"])
        seq += by_realm[r]
    seq += [x["extra-joker-radiant"], x["extra-joker-shadow"],
            x["extra-blank-01"], x["extra-blank-02"]]
    if len(seq) != 63:
        raise SystemExit(f"deck sequence is {len(seq)} cards, expected 63")
    # <NN>-<slug>: an oracle card keeps its id, an extra drops the "extra-" prefix.
    return [(f"{i:02d}-" + (c["id"][6:] if c["id"].startswith("extra-") else c["id"]), c)
            for i, c in enumerate(seq, 1)]


def build():
    for f in os.listdir(f"{OUT}/fronts"):       # names carry the order; stale ones lie
        os.remove(f"{OUT}/fronts/{f}")

    missed = []
    seq = deck_sequence()
    for stem, c in seq:
        rep = {}
        if "kind" in c:                          # an extra
            im = mpc_ready(extra_src(c["art"], "extras"), extra=c, report=rep)
            if c.get("mark") and not rep.get("ok"):
                missed.append(f"{stem} ({rep.get('why')})")
        else:
            im = mpc_ready(art_src(c["id"]), c["name"], c["number"], c["realm"], report=rep)
            if not rep.get("ok"):
                missed.append(f"{stem} ({rep.get('why')})")
        im.save(f"{OUT}/fronts/{stem}.jpg", "JPEG",
                quality=95, optimize=True, subsampling=0, dpi=(DPI, DPI))
    mpc_ready(f"{REPO}/cards/back.png").save(
        f"{OUT}/back.jpg", "JPEG", quality=95, optimize=True, subsampling=0, dpi=(DPI, DPI))

    print(f"mpc: {len(seq)} fronts + back at {FULL[0]}x{FULL[1]} "
          f"(trim {TRIM[0]}x{TRIM[1]}) -> {OUT}")
    if missed:
        print(f"mpc: NO CORNER MARK on {len(missed)}: {', '.join(missed)}")


if __name__ == "__main__":
    build()
