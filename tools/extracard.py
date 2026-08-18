"""The extras' typesetting — the third rule, after the title cartouche and the rank.

The eleven cards in data/extras.json are not oracle cards: nine of them carry no unique
art at all, only an empty frame master and words. Every one of those words is set here,
deterministically, in the deck's own two faces — Bodoni 72 Smallcaps for anything that
behaves like a title (the display lines, the rules' captions, the realm essences) and
Baskerville for running copy, which small caps cannot carry at eight words a line. The
image model never renders a letter; that is the deck's hardest-won rule and the extras
do not get an exemption.

WHAT IS MEASURED AND WHAT IS FIXED
----------------------------------
The type column and the vertical field are taken from the card's OWN title banner
(`cardtitle.detect_banner`), for the same reason the title is: every master draws its
plaque a little differently, and a fraction of the image that centres copy on one of
them rides up on the next. The column is the banner's width, so the copy stacks exactly
over the name — and it is comfortably inside the trim: the banner is 76% of the width,
which leaves 12% (0.42 in at print size) of margin against a 1/8 in requirement.

Type sizes are fractions of the card HEIGHT, so the same spec sets a 1024x1536 master,
a 1000x1500 MPC front or anything else handed in.

THE REALM GLYPHS ARE THE DECK'S OWN
-----------------------------------
The four glyphs on the realm cards and the "how to deal" card are not redrawn: they are
lifted from real oracle cards, the roundel FOUND by rankmark's own circle vote and cut
out with its keyline. Redrawing them would put a fifth turtle-shell and a second
root-knot into a deck whose whole discipline is that there is only ever one of each.
"""
from PIL import Image, ImageDraw, ImageFont
import functools
import json
import os

import cardtitle
from cardtitle import (TITLE_FONTS, TITLE_INK, TRACKING, CAP_FRACTION, FILL_W, MAX_SIZE,
                       detect_banner)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GOLD_INK = (150, 110, 40)      # the booklet's gold, and the realm tint rankmark uses
DIM_INK = (110, 96, 64)        # for a caption that must not compete with an empty card

BODY_FONTS = ["/System/Library/Fonts/Supplemental/Baskerville.ttc"] + list(TITLE_FONTS)
# The lining-figure cut, for the one line on these cards that is mostly numerals.
# rankmark.py learned this the hard way and the note is worth repeating: Bodoni 72
# Smallcaps sets oldstyle figures, so "A · 2-10 · J · Q · K" comes out with digits two
# thirds the height of the letters and a "10" that reads as "IO".
RANK_FONTS = ["/System/Library/Fonts/Supplemental/Bodoni 72.ttc"] + list(TITLE_FONTS)
FACES = {"title": TITLE_FONTS, "body": BODY_FONTS, "rank": RANK_FONTS}

# --- the styles, as fractions of the card height ---------------------------
STYLE = {
    #                size    line    tracking  ink        face
    "display": dict(size=0.0455, lead=1.26, track=0.10, ink=TITLE_INK, face="title"),
    "gold":    dict(size=0.0250, lead=1.45, track=0.10, ink=GOLD_INK, face="title"),
    "line":    dict(size=0.0245, lead=1.50, track=0.06, ink=TITLE_INK, face="title"),
    "body":    dict(size=0.0225, lead=1.42, track=0.00, ink=TITLE_INK, face="body"),
    "rank":    dict(size=0.0245, lead=1.50, track=0.10, ink=TITLE_INK, face="rank"),
    "small":   dict(size=0.0195, lead=1.50, track=0.08, ink=DIM_INK, face="title"),
    "caption": dict(size=0.0165, lead=1.50, track=0.12, ink=DIM_INK, face="title"),
}
SHRINK = 0.72                  # a display line may lose this much size to stay one line
RULE_W = 0.34                  # gold hairline width, as a fraction of the column
RULE_H = 0.0016                # ...and its weight, as a fraction of the card height
GLYPH_D = 0.200                # the big realm glyph's diameter, fraction of card height
GLYPH_ROW_D = 0.072            # the four-glyph row's diameter
GLYPH_LABEL = 0.0135           # the label under each glyph in that row
GLYPH_CROP = 1.14              # how much past the roundel's radius is lifted with it
GLYPH_MASK = 1.05              # ...and where the circular mask cuts, so the keyline stays
FIELD_TOP = 0.085              # the typesetting field starts here (below the frame)
FIELD_GAP = 0.028              # ...and stops this far above the title banner
CAPTION_GAP = 0.030            # a caption sits this far above the banner

REALM_LABEL = {"shell": "Shell", "roots": "Roots",
               "trunk": "Trunk", "branches": "Branches"}


def _font(face, size):
    for p in FACES.get(face, TITLE_FONTS):
        try:
            return ImageFont.truetype(p, int(max(6, size)))
        except Exception:
            continue
    return ImageFont.load_default()


def _tracked_width(draw, text, font, track):
    widths = [draw.textlength(ch, font=font) for ch in text]
    return sum(widths) + font.size * track * (len(text) - 1), widths


def _draw_line(draw, text, font, cx, top, ink, track):
    """Draw one centred line with letter-spacing; `top` is the line box's top."""
    total, widths = _tracked_width(draw, text, font, track)
    x = cx - total / 2
    gap = font.size * track
    for ch, w in zip(text, widths):
        draw.text((x, top), ch, font=font, fill=ink)
        x += w + gap


def _wrap(draw, text, font, colw, track):
    """Greedy wrap to the column width, measured with the tracking that will be used."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if _tracked_width(draw, t, font, track)[0] <= colw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    # No one-word last line. Centred ragged copy ending on a lone "up." reads as a
    # mistake; pulling a word down from the line above costs nothing and fixes it.
    if len(lines) > 1 and len(lines[-1].split()) == 1 and len(lines[-2].split()) > 2:
        head, tail = lines[-2].rsplit(" ", 1)
        lines[-2], lines[-1] = head, tail + " " + lines[-1]
    return lines


def art_src(cid, sub="art"):
    """The committed q95 JPEG archive first, the local-only PNG master as fallback."""
    p = f"{REPO}/cards/{sub}/{cid}.jpg"
    return p if os.path.exists(p) else f"{REPO}/cards/{sub}/{cid}.png"


@functools.lru_cache(maxsize=8)
def glyph_disc(realm, size):
    """The realm's own roundel, cut from a real card of that realm, as an RGBA disc.

    Measured, not placed: rankmark's circle vote finds the roundel on the source card,
    so this works whatever that card's frame did with it. The source card per realm is
    named in data/extras.json (`glyph_source`) — chosen as the largest, cleanest gold
    roundel in the realm, so the enlargement is the gentlest available.
    """
    import numpy as np
    from rankmark import _find_roundel
    src = json.load(open(f"{REPO}/data/extras.json"))["glyph_source"][realm]
    im = Image.open(art_src(src)).convert("RGB")
    found = _find_roundel(im)
    if not found:
        raise RuntimeError(f"no roundel found on glyph source {src}")
    cx, cy, r = found[0], found[1], found[2]
    half = int(round(r * GLYPH_CROP))
    a = np.asarray(im, dtype=np.uint8)
    # Pad by edge replication: on the shell cards the roundel sits so far into the
    # corner that its crop runs off the top-left of the card by a pixel or two.
    a = np.pad(a, ((half, half), (half, half), (0, 0)), mode="edge")
    x, y = int(round(cx)) + half, int(round(cy)) + half
    crop = Image.fromarray(a[y - half:y + half, x - half:x + half])

    S = 4
    n = 2 * half
    mask = Image.new("L", (n * S, n * S), 0)
    m = r * GLYPH_MASK * S
    ImageDraw.Draw(mask).ellipse((n * S / 2 - m, n * S / 2 - m,
                                  n * S / 2 + m, n * S / 2 + m), fill=255)
    mask = mask.resize((n, n), Image.LANCZOS)
    disc = crop.convert("RGBA")
    disc.putalpha(mask)
    return disc.resize((int(size), int(size)), Image.LANCZOS)


# --- finding the banner on a card that is otherwise EMPTY ------------------
# cardtitle.detect_banner finds the plaque by looking for the one region down there that
# is flat and light. On an oracle card that is unambiguous — everything around the plaque
# is hatched woodcut. On an empty frame master the WHOLE CARD is flat and light, and the
# detector duly answers with a band from 0.60 to 0.83 of the height (frame-plain) or
# gives up entirely (frame-aged). Measured, both times.
#
# So the empty masters are measured by the only thing actually drawn on them: the gold
# keylines. Gold is blue-starved, kraft is not, so R-B averaged across the card's central
# span spikes on a rule and nowhere else — and it spikes whether the rule prints darker
# than the paper (frame-plain) or brighter (frame-aged), which a luminance test does not.
BANNER_OK = (0.78, 0.965, 0.14, 0.50)  # plausible detect_banner answer: top, bottom,
#                                        max height, min width — all fractions
RULE_SEARCH = (0.70, 0.965)    # where the banner's own rules are looked for
RULE_SPAN = 0.40               # the central span rows are averaged over
RULE_K = 4.0                   # a rule is this many MADs above the local median ...
RULE_FLOOR = 6.0               # ... and at least this much, in R-B units
RULE_MIN_H = 0.045             # the two rules of one banner are at least this far apart
BANNER_FALLBACK = (0.12, 0.845, 0.88, 0.930)   # the spec's own geometry, last resort


def _rule_runs(sat, lo, hi, span_lo, span_hi):
    """Runs of rows (indices into `sat`) that read as a drawn gold rule."""
    import numpy as np
    row = sat[:, span_lo:span_hi].mean(axis=1)
    seg = row[lo:hi]
    med = float(np.median(seg))
    mad = float(np.median(np.abs(seg - med)))
    thr = med + max(RULE_FLOOR, RULE_K * mad)
    runs = []
    for y in range(lo, hi):
        if row[y] > thr:
            if runs and y - runs[-1][-1] <= 3:
                runs[-1].append(y)
            else:
                runs.append([y])
    return runs


def _keyline_banner(im):
    """The banner's inner box on an empty master, found from its gold rules. Or None."""
    import numpy as np
    a = np.asarray(im.convert("RGB"), dtype=np.float32)
    H, W = a.shape[:2]
    sat = a[..., 0] - a[..., 2]
    rows = _rule_runs(sat, int(H * RULE_SEARCH[0]), int(H * RULE_SEARCH[1]),
                      int(W * (1 - RULE_SPAN) / 2), int(W * (1 + RULE_SPAN) / 2))
    # The FIRST pair far enough apart to be a banner, not the widest: below the plaque
    # sit the frame's own two horizontal rules, and pairing the plaque's top rule with
    # the frame's bottom one made the "banner" a third of the card deep.
    pair = None
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if rows[j][0] - rows[i][-1] >= H * RULE_MIN_H:
                pair = (rows[i][-1] + 1, rows[j][0])
                break
        if pair:
            break
    if not pair:
        return None
    y0, y1 = pair
    band = sat[y0:y1, :]                      # the same test, run down the columns
    cols = _rule_runs(band.T, 0, W, 0, band.shape[0])
    # The INNERMOST rule on each side, not the outermost: the frame's own two vertical
    # keylines cross this band as well, and taking the outer pair measured the card
    # instead of the plaque — the title then set itself 800px wide inside a 755px
    # banner. Nothing else is drawn between the frame and the plaque, so the run
    # nearest the centre from each side is the plaque's.
    left = [r for r in cols if r[-1] < W / 2]
    right = [r for r in cols if r[0] > W / 2]
    if not left or not right:
        return None
    x0, x1 = left[-1][-1] + 1, right[0][0]
    if x1 - x0 < W * BANNER_OK[3]:
        return None
    return (x0, y0, x1, y1)


def banner_box(im):
    """The title plaque's inner box on an extra. Measured three ways, in order of trust."""
    W, H = im.size
    try:
        b = detect_banner(im)
    except Exception:
        b = None
    if b is not None and (b[1] >= H * BANNER_OK[0] and b[3] <= H * BANNER_OK[1]
                          and b[3] - b[1] <= H * BANNER_OK[2]
                          and b[2] - b[0] >= W * BANNER_OK[3]):
        return b
    try:
        k = _keyline_banner(im)
    except Exception:
        k = None
    if k is not None:
        return k
    f = BANNER_FALLBACK
    return (W * f[0], H * f[1], W * f[2], H * f[3])


def set_title_in(im, name, box):
    """cardtitle's banner rule, applied to a box that was measured some other way.

    The fitting is cardtitle's own — its face, its tracking, its cap and width caps, its
    optical centring — called through its own helpers, so an extra's title is set by
    exactly the rule that set the other 52 names. Only the box comes from elsewhere.
    """
    im = im.copy()
    draw = ImageDraw.Draw(im)
    W, H = im.size
    x0, y0, x1, y1 = box
    cap_cap = (y1 - y0) * CAP_FRACTION
    width_cap = (x1 - x0) * FILL_W
    ceiling = max(10, int(H * MAX_SIZE))
    best = cardtitle._title_font(10)
    for s in range(11, ceiling + 1):
        f = cardtitle._title_font(s)
        total, _ = cardtitle._tracked_width(draw, name, f)
        if total > width_cap or cardtitle._cap_height(f, name) > cap_cap:
            break
        best = f
    cy = (y0 + y1) / 2 - cardtitle._optical_dy(best, name)
    cardtitle._draw_tracked(draw, name, best, (x0 + x1) / 2, cy, TITLE_INK, TRACKING)
    return im


def _field(im, box):
    """(cx, top, bottom, colw): where copy may go — the column is the banner's own."""
    W, H = im.size
    x0, y0, x1 = box[0], box[1], box[2]
    return W / 2, H * FIELD_TOP, y0 - H * FIELD_GAP, x1 - x0


def _measure(draw, blocks, im, colw):
    """[(block, height, payload)] and the total height of the stack."""
    W, H = im.size
    out, total = [], 0.0
    for b in blocks:
        st = b["style"]
        if st == "gap":
            h, payload = H * b["size"], None
        elif st == "rule":
            h, payload = max(2.0, H * RULE_H), None
        elif st == "glyph":
            d = H * GLYPH_D
            h, payload = d, glyph_disc(b["realm"], round(d))
        elif st == "glyphs":
            d = H * GLYPH_ROW_D
            lf = _font("title", H * GLYPH_LABEL)
            h = d + H * 0.010 + lf.size * 1.25
            payload = (d, lf, [glyph_disc(r, round(d)) for r in
                               ("shell", "roots", "trunk", "branches")])
        else:
            s = STYLE[st]
            f = _font(s["face"], H * s["size"])
            if s["face"] == "body":
                lines = _wrap(draw, b["text"], f, colw, s["track"])
            else:
                # A display line is one line. "Draw one BRANCHES — what to reach for."
                # wrapped, and left the word "for." alone on a line of its own; a
                # display face that gives up a little size instead is the lesser evil.
                lines = [b["text"]]
                floor = int(H * s["size"] * SHRINK)
                while (_tracked_width(draw, b["text"], f, s["track"])[0] > colw
                       and f.size > floor):
                    f = _font(s["face"], f.size - 1)
                if _tracked_width(draw, b["text"], f, s["track"])[0] > colw:
                    lines = _wrap(draw, b["text"], f, colw, s["track"])
            h = f.size * s["lead"] * len(lines)
            payload = (f, lines, s)
        out.append((b, h, payload))
        total += h
    return out, total


def _render(im, draw, measured, cx, y, colw):
    W, H = im.size
    for b, h, payload in measured:
        st = b["style"]
        if st == "gap":
            pass
        elif st == "rule":
            w = colw * RULE_W
            draw.rectangle([cx - w / 2, y, cx + w / 2, y + h - 1], fill=GOLD_INK)
        elif st == "glyph":
            im.alpha_composite(payload, (int(cx - payload.width / 2), int(y)))
        elif st == "glyphs":
            d, lf, discs = payload
            step = colw / 4.0
            for i, (disc, realm) in enumerate(zip(discs, ("shell", "roots",
                                                          "trunk", "branches"))):
                dx = cx - colw / 2 + step * (i + 0.5)
                im.alpha_composite(disc, (int(dx - d / 2), int(y)))
                _draw_line(draw, REALM_LABEL[realm], lf, dx, y + d + H * 0.010,
                           DIM_INK, STYLE["caption"]["track"])
        else:
            f, lines, s = payload
            for i, line in enumerate(lines):
                _draw_line(draw, line, f, cx, y + i * f.size * s["lead"]
                           + (f.size * (s["lead"] - 1)) / 2, s["ink"], s["track"])
        y += h


def set_extra(im, spec):
    """Typeset one extra card: its title in the banner, then its body copy or caption.

    The stack of blocks is centred in the field between the frame and the banner; a
    caption (the blank cards' one line) is set just above the banner instead, so the
    middle of the card stays genuinely empty for whoever draws on it.
    """
    box = banner_box(im)
    if spec.get("title"):
        im = set_title_in(im, spec["title"], box)
    im = im.convert("RGBA")
    draw = ImageDraw.Draw(im)
    W, H = im.size
    cx, top, bottom, colw = _field(im, box)

    blocks = spec.get("blocks") or []
    if blocks:
        measured, total = _measure(draw, blocks, im, colw)
        y = top + max(0.0, (bottom - top - total) / 2)
        _render(im, draw, measured, cx, y, colw)

    if spec.get("caption"):
        s = STYLE["caption"]
        f = _font(s["face"], H * s["size"])
        _draw_line(draw, spec["caption"], f, cx, bottom + H * FIELD_GAP
                   - H * CAPTION_GAP - f.size, s["ink"], s["track"])
    return im.convert("RGB")
