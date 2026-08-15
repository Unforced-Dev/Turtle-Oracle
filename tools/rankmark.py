"""The rank medallion — the second typesetting rule, and the one that makes the
oracle deck deal as a 52-card playing deck.

Every card already carries its suit: the realm glyph in the gold roundel at the
top-left. What it lacks is a rank you can read from a fanned hand. This module
cuts one in, in the frame's own language: a small medallion below the top-left
roundel, and a 180-degree copy of it at the bottom-right, so the card reads the
same either way up.

WHY IT IS MEASURED AND NOT PLACED BY FRACTION
---------------------------------------------
The 48 arts do not share a frame. What the generator actually produced, measured
card by card rather than assumed:

  * the BAND family (11 cards, nearly all shell) — an ornate gold-on-black
    border band, the realm roundel set into its top-left corner, and a rosette
    medallion at the bottom-right (13 cards have one);
  * the KEYLINE family (the other 37) — one or two thin gold rules on the kraft
    margin, the realm roundel floating free in the art field near the corner,
    and NO bottom-right rosette at all;
  * and cutting across both, 14 cards draw the roundel in BLACK INK rather than
    gold — a black keyline circle or a solid black disc, no gold anywhere in it.

Measured over all 48 the roundel's centre wanders from 0.067 to 0.139 of the
card width and its radius from 0.038 to 0.076 — a factor of two. A fixed
fraction would put the rank mark inside the roundel on one card and out in the
artwork on the next. So the roundel is FOUND on the rendered card (a Hough-style
vote for the outermost COMPLETE circle in the corner: the gold field first, the
ink field where there is no gold to find), the frame band below it is probed
for, and every dimension of the mark is a multiple of that card's own roundel.

The pigment is measured too. `_palette` samples the near-black of the card's own
frame and the gold of the card's own corner, so the mark is drawn in inks
already on that card. Where there is no black band the fill comes out as that
card's own deepest tone, tinted by the ground it is cut into — dark russet on
trunk, deep navy on branches — which is the point: it should look like an inlay
the engraver cut, not a sticker.

TWO WEIGHTS, ONE DRAWING
------------------------
The medallion is drawn to one design and struck at two weights. Against kraft or
an art field it is the lighter cut: the dark disc carries the mark and the gold
only has to sit in it. Against the shell realm's black band it is the heavier
cut — keyline half again as thick, the rank struck twice, the gold taken to the
top of the card's own range — because there the disc is invisible against the
band and the gold IS the mark, set an inch from a vine drawn in full leaf. The
switch is `field_lum`, the median luminance of the square the TOP-LEFT mark
lands in, against DARK_FIELD. Measured over all 52: the 13 shell cards come in
at 7.8-47.9 and every other card at 69.4-164.2.

Nothing here guesses. If the roundel cannot be found, `set_rank` returns the
image unchanged and says so through `report`. (Measured 2026-08-15: found on
48 of 48, 34 by gold and 14 by ink, lowest score 0.35 against a floor of 0.20.)

Coordinates are all computed from the image handed in, so the same call works
on a 1024x1536 master or a height-fitted 1000x1500 MPC front.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from cardtitle import TITLE_FONTS, detect_banner, _close_gaps

# --- rank alphabet ---------------------------------------------------------
RANKS = {1: "A", 11: "J", 12: "Q", 13: "K"}

# The title's own face, but the LINING-figure cut of it. Bodoni 72 Smallcaps —
# cardtitle's first choice, and the deck's voice — sets digits as oldstyle small
# figures: they come out two thirds the height of A/J/Q/K, and its "1" is a
# serifed stem, so "10" reads as "IO" at index size. Rendered both and looked:
# the regular Bodoni 72 is the same family, same drawing, with figures that are
# figures. Smallcaps stays in the stack behind it so the fallback chain is the
# title's.
RANK_FONTS = ["/System/Library/Fonts/Supplemental/Bodoni 72.ttc"] + list(TITLE_FONTS)

# --- where the roundel is allowed to be (fractions of the rendered card) ----
# Measured over all 48: centre x 0.070-0.130 W, centre y 0.045-0.090 H,
# radius 0.030-0.065 W. The windows below are those ranges with headroom.
SEARCH_X = (0.035, 0.205)      # roundel centre x, fraction of width
SEARCH_Y = (0.022, 0.135)      # roundel centre y, fraction of height
SEARCH_R = (0.027, 0.082)      # roundel radius, fraction of width
R_STEP = 0.0018                # radius quantisation, fraction of width
N_ANGLES = 48                  # votes per circle
OUTER_RING = 1.28              # a true edge has gold ON r and not on 1.28r ...
OUTER_PENALTY = 0.55           # ... which is what keeps the vote off inner rings
OUTER_SLACK = 0.85             # ties within this fraction of the best go to the wider ring
CONCENTRIC = 0.30              # ...but only if they share the winner's centre, to within
#                                this fraction of its radius
STRIDE = 2                     # candidate centres are tested every this many pixels — the
#                                medallion is 60px across, so 1px of centre is noise
GOLD_TRUST = 0.35              # a gold vote below this is not believed; the ink vote runs
INK_BLUR = 0.022               # the ink field's "local ground" scale, fraction of width
INK_HI = 99.3                  # ...and the percentile its contrast is stretched against
RING_TOL = (-0.035, 0.0, 0.035)  # radial tolerance, as a fraction of the radius
RING_PCTL = 20                 # a ring is scored by its weakest fifth, not its average
MIN_SCORE = 0.20               # below this the corner has no roundel in it

GOLD_LO, GOLD_HI = 25.0, 99.5  # percentiles the goldness field is stretched between

# --- the mark, as multiples of the roundel's own radius --------------------
MARK_R = 0.315                 # medallion RADIUS / roundel DIAMETER -> 63% of its size
MARK_GAP = 0.30                # clear air between roundel edge and medallion edge
KEYLINE = 0.085                # keyline weight / medallion radius
INNER_RULE = 0.145             # hairline second rule, inset by this much
TEXT_W = 0.87                  # rank width / medallion inner diameter ("10" lives here)
TEXT_H = 0.74                  # rank cap height / medallion inner diameter
SHADOW = 0.42                  # the recess's cast shadow, as alpha
SHADOW_BLUR = 0.11             # ...blurred by this much of the medallion radius
GOLD_MOTTLE = 0.16             # the gold picks up this much of the paper's own mottle
SS = 4                         # supersampling for the drawn medallion

# --- band probe ------------------------------------------------------------
# Absolute, because "near-black frame band" is an absolute property of these arts:
# measured, a band column sits at luminance 12-30 while the darkest ART field in the
# deck (trunk's russet) sits at 66-81. Nothing in between.
BAND_DARK = 55                 # a band column is at most this bright
BAND_GAP = 0.014               # bright breaks narrower than this are the band's own rules
BAND_SOLID = 0.85              # ...and a band column is solid black to at least this depth
BAND_MIN_W = 0.030             # a strip narrower than this (fraction of W) is not a band
BAND_MAX_W = 0.200             # ...wider than this is a dark ART field, not a band
EDGE_MARGIN = 0.014            # the mark never comes closer than this to the card edge
BR_TOL_R = 0.25                # a bottom-right rosette must match the roundel's radius ...
BR_TOL_XY = 0.05               # ... and its inset, or it is not a rosette but artwork
CLEARANCE = 0.010              # air the bottom mark keeps from the title plaque

# --- the same mark, cut into the black frame band -------------------------------
# On the 13 shell cards the medallion is not cut into paper or artwork but into the
# ornate gold-on-black BAND, an inch from a vine whose stems are drawn three or four
# pixels thick in full leaf. The mark as specified above is correct against kraft and
# against a flat art field, and underweight there: its keyline came out thinner than
# the vine beside it and its rank duskier, and at the scale of a fanned hand the whole
# medallion dropped out of the card. Nothing about the drawing is wrong; it is the
# WEIGHT that has to answer to what it is set next to. So on a dark field the same
# medallion is drawn heavier — thicker keyline, doubled character, gold taken to the
# top of the card's own range and no mottle allowed to take it back down.
DARK_FIELD = BAND_DARK         # a mark whose ground is at most this bright is on the band.
#                                Measured over the deck at the TOP-LEFT mark's own tile:
#                                the 13 shell cards run 7.8-47.9 and every other card runs
#                                69.4-164.2. The threshold sits in a gap 21 wide, and it is
#                                BAND_DARK because it is the same fact: near-black frame.
DARK_KEYLINE = 1.5             # keyline weight, x the light-field weight
DARK_RULE_ALPHA = 200          # the inner hairline, opaque enough to be a rule not a smudge
DARK_BOLD = 0.034              # faux-bold: the rank is struck twice, this far apart as a
#                                fraction of the medallion radius (~1.3px at print size)
DARK_MOTTLE = 0.06             # the mottle survives, but only upward: on black, taking 16%
#                                off a gold line is what made it dusky
DARK_REALM_LUM = 1.0           # ...and the realm ink is not held BELOW the card's gold on a
#                                band either. REALM_LUM's 0.80 is a discount a light field
#                                can pay — there the dark disc carries the mark and the ink
#                                only has to sit in it. On black the ink IS the mark, and at
#                                0.80 the shell realm cell was the one thing on the compare
#                                sheet that still would not read. The hue still says which
#                                realm; only the discount goes.

# --- ink -------------------------------------------------------------------
FILL_LUM = 27.0                # the medallion's fill is pushed to this luminance
FILL_TEXTURE = 0.42            # ...but keeps this much of the paper grain under it
FILL_GROUND = 0.55             # ...and this much of the GROUND's hue, darkened:
#                                a recess cut into russet is dark russet, into navy dark
#                                navy. A flat neutral black is the thing that reads pasted.
GOLD_LUM = (150.0, 196.0)      # sampled gold is held inside this luminance window
REALM_LUM = 0.80               # a realm tint is held at this much of the card gold's own
#                                luminance. The four tints as specified are dark — indigo
#                                is luminance 76 against a fill of 27 — and at their face
#                                values the rank stops being readable at index size. Hue is
#                                what carries the realm; brightness is what carries the
#                                rank; so the hue is kept and the brightness is matched to
#                                the gold the card already uses.
REALM_WARM = 0.18              # realm tints are pulled this far toward the card's own
#                                gold — enough to keep them antique, not enough to hide
#                                which realm you are holding
REALM_INK = {
    "shell":    (150, 110, 40),
    "roots":    (70, 70, 120),
    "trunk":    (150, 95, 45),
    "branches": (70, 110, 140),
}


def rank_text(number):
    """1 -> A, 2-10 -> numerals, 11 -> J, 12 -> Q, 13 -> K."""
    return RANKS.get(number, str(number))


def _font(size):
    for path in RANK_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _scaled(c, k):
    return tuple(int(round(max(0, min(255, v * k)))) for v in c)


def _goldness(rgb):
    """Per-card-normalised "this pixel is the frame's gold" field, 0..1.

    Gold is the one thing in a corner that is both bright and blue-starved. Kraft
    paper is warm too but far less blue-starved, and the russet/navy art fields are
    warm-but-dark or cold — so (R-B)*V separates all four. The stretch is per card
    because a black-band corner and a bare-kraft corner have nothing in common in
    absolute terms.
    """
    import numpy as np
    r = rgb[..., 0].astype(np.float32)
    g = rgb[..., 1].astype(np.float32)
    b = rgb[..., 2].astype(np.float32)
    v = np.maximum(r, np.maximum(g, b))
    raw = (r - b) * v / (255.0 * 255.0)
    lo = float(np.percentile(raw, GOLD_LO))
    hi = float(np.percentile(raw, GOLD_HI))
    if hi - lo < 1e-4:
        return None
    return np.clip((raw - lo) / (hi - lo), 0.0, 1.0)


def _inkness(rgb, W):
    """Per-card-normalised "this pixel differs from what surrounds it" field, 0..1.

    The fallback field, and the one that covers the cards `_goldness` cannot see: ten
    of the 48 draw the realm glyph as BLACK ink — a black keyline circle, or a solid
    black disc — with no gold in the roundel at all (roots-01, -02, -05, -06, -09,
    -10, -11 and trunk-02, -04, and branches-01 among them). A gold detector reports
    those as absent, which is a search that could not have found them.

    Distance from a Gaussian-blurred copy of the same crop answers "ink of any colour
    against whatever this card's ground happens to be", which is the property all 48
    share. It is the weaker cue — hatched artwork lights it up too — so it is only
    consulted when the gold vote comes back unconvinced.
    """
    import numpy as np
    from PIL import ImageFilter
    crop = Image.fromarray(rgb)
    blur = np.asarray(crop.filter(ImageFilter.GaussianBlur(INK_BLUR * W)),
                      dtype=np.float32)
    d = np.sqrt(((rgb.astype(np.float32) - blur) ** 2).sum(axis=2))
    hi = float(np.percentile(d, INK_HI))
    return np.clip(d / max(hi, 1e-3), 0.0, 1.0)


def _vote(F, W, H, x00, y00, w, h, rmin, rmax):
    """The circle vote: (cx, cy, r, score) over a feature field, or None.

    Every candidate centre in the corner window is scored, for every quantised
    radius, by the COMPLETENESS of the feature around that circle less a share of the
    average feature on a circle 28% wider. The subtraction is what finds the roundel's
    OUTER edge rather than one of the rules inside it, on the shell cards where the
    roundel is a filled gold disc and almost any small circle inside it scores well.
    """
    import numpy as np
    pad = int(rmax * OUTER_RING) + 2
    Fp = np.pad(F, pad, mode="edge")
    ang = np.arange(N_ANGLES) * (2 * np.pi / N_ANGLES)
    cos, sin = np.cos(ang), np.sin(ang)

    def ring(rad, complete):
        """Feature around the circle of radius `rad`, per candidate centre.

        Sampled with a radial tolerance: a keyline is two or three pixels wide, so a
        circle quantised to exact integer offsets slides off it and the vote lands on
        something fatter. Taking the best of three nearby radii per angle is what
        makes a hairline circle findable.

        `complete` scores the ring by its WEAKEST fifth instead of its average, and
        that one choice is what makes the detector work. Measured on shell-01, mean
        goldness is ~0.28 at half a dozen radii inside the roundel's gold disc and
        0.38 on its true outer keyline — no separation at all. The 20th percentile is
        0.02 everywhere except the true keyline, where it is 0.33: only there is the
        gold all the way round. Completeness is the property, so completeness is the
        statistic.
        """
        stack = np.empty((N_ANGLES, h, w), dtype=np.float32)
        for i, (c, s) in enumerate(zip(cos, sin)):
            hit = None
            for k in RING_TOL:
                dy = int(round((rad + k * rad) * s))
                dx = int(round((rad + k * rad) * c))
                v = Fp[pad + y00 + dy: pad + y00 + dy + h * STRIDE: STRIDE,
                       pad + x00 + dx: pad + x00 + dx + w * STRIDE: STRIDE]
                hit = v if hit is None else np.maximum(hit, v)
            stack[i] = hit
        return np.percentile(stack, RING_PCTL, axis=0) if complete else stack.mean(axis=0)

    cache, rows = {}, []
    for rad in np.arange(rmin, rmax + 1e-6, max(1.0, R_STEP * W)):
        for r2, comp in ((rad, True), (rad * OUTER_RING, False)):
            if (r2, comp) not in cache:
                cache[(r2, comp)] = ring(r2, comp)
        score = cache[(rad, True)] - OUTER_PENALTY * cache[(rad * OUTER_RING, False)]
        i = int(np.argmax(score))
        sy, sx = divmod(i, w)
        rows.append((float(x00 + sx * STRIDE), float(y00 + sy * STRIDE),
                     float(rad), float(score[sy, sx])))
    if not rows:
        return None
    best = max(rows, key=lambda r: r[3])
    if best[3] < MIN_SCORE:
        return None
    # "the OUTERMOST complete circle": among the radii that score within OUTER_SLACK
    # of the best AND share its centre, take the largest. Concentricity is the part
    # that matters — without it a bright arc elsewhere in the artwork can win the
    # widen-the-ring tie-break and put the mark in the middle of the picture.
    ok = [r for r in rows
          if r[3] >= best[3] * OUTER_SLACK
          and abs(r[0] - best[0]) <= CONCENTRIC * best[2]
          and abs(r[1] - best[1]) <= CONCENTRIC * best[2]]
    return max(ok, key=lambda r: r[2])


def _find_roundel(im):
    """(cx, cy, r, score, field) of the top-left realm roundel, or None.

    Two passes. The gold vote first, because on the cards that HAVE a gold roundel it
    is decisive and unambiguous. It is trusted only if it is confident and did not
    come back pinned to the edge of the search window — a radius at the ceiling or a
    centre on the boundary is the signature of a vote that found nothing and settled.
    When it is not trusted, the ink vote runs instead. Measured over the deck: 34
    cards are decided by gold, 14 by ink.
    """
    try:
        import numpy as np
    except ImportError:
        return None
    W, H = im.size
    if W < 200 or H < 200:
        return None

    rmin, rmax = SEARCH_R[0] * W, SEARCH_R[1] * W
    cx0, cx1 = int(SEARCH_X[0] * W), int(SEARCH_X[1] * W)
    cy0, cy1 = int(SEARCH_Y[0] * H), int(SEARCH_Y[1] * H)
    bx = int(min(W, cx1 + rmax * OUTER_RING + 3))
    by = int(min(H, cy1 + rmax * OUTER_RING + 3))
    rgb = np.asarray(im.convert("RGB").crop((0, 0, bx, by)))
    w = (cx1 - cx0) // STRIDE + 1
    h = (cy1 - cy0) // STRIDE + 1
    if w < 4 or h < 4:
        return None

    G = _goldness(rgb)
    gold = None if G is None else _vote(G, W, H, cx0, cy0, w, h, rmin, rmax)
    if gold is not None and gold[3] >= GOLD_TRUST \
            and gold[2] <= rmax * 0.95 \
            and cx0 + STRIDE < gold[0] < cx1 - STRIDE \
            and cy0 + STRIDE < gold[1] < cy1 - STRIDE:
        return gold + ("gold",)
    ink = _vote(_inkness(rgb, W), W, H, cx0, cy0, w, h, rmin, rmax)
    if ink is not None:
        return ink + ("ink",)
    return None if gold is None else gold + ("gold",)


def _palette(im, cx, cy, r):
    """(fill, gold) sampled from this card's own corner.

    fill: the darkest tone the frame actually contains, pushed to FILL_LUM but
    keeping its hue — the band black on a band card, the woodcut ink on a kraft
    card, the deep navy on branches-10.
    gold: the median of the goldest pixels on the roundel itself, held inside a
    luminance window so a blown-out gold leaf highlight cannot make it garish.
    """
    import numpy as np
    W, H = im.size
    x0 = max(0, int(cx - 2.4 * r)); x1 = min(W, int(cx + 2.4 * r))
    y0 = max(0, int(cy - 2.4 * r)); y1 = min(H, int(cy + 3.2 * r))
    box = np.asarray(im.convert("RGB").crop((x0, y0, x1, y1)), dtype=np.float32)
    lum = 0.299 * box[..., 0] + 0.587 * box[..., 1] + 0.114 * box[..., 2]

    dark = box[lum <= np.percentile(lum, 6)]
    fill = dark.mean(axis=0) if len(dark) else np.array([20.0, 18.0, 16.0])
    fl = max(6.0, _lum(fill))
    fill = _scaled(tuple(fill), FILL_LUM / fl)

    yy, xx = np.mgrid[y0:y1, x0:x1]
    on = ((xx - cx) ** 2 + (yy - cy) ** 2) <= (r * 1.06) ** 2
    disc = box[on]
    if len(disc) < 40:
        disc = box.reshape(-1, 3)
    gscore = (disc[:, 0] - disc[:, 2]) * disc.max(axis=1)
    pick = disc[gscore >= np.percentile(gscore, 97)]
    gold = pick.mean(axis=0) if len(pick) else np.array([196.0, 158.0, 78.0])
    gl = max(1.0, _lum(gold))
    if gl < GOLD_LUM[0]:
        gold = _scaled(tuple(gold), GOLD_LUM[0] / gl)
    elif gl > GOLD_LUM[1]:
        gold = _scaled(tuple(gold), GOLD_LUM[1] / gl)
    else:
        gold = tuple(int(round(v)) for v in gold)
    return tuple(fill), tuple(gold)


def _band_centre(im, cx, cy, r, mark_r):
    """x of the frame band running below the roundel, or None if there is no band.

    On the band family the roundel bulges out of a narrow vertical band; hanging the
    mark off the roundel's own centre would push it off the band and into the art.
    So the row below the roundel is probed for a near-black strip that starts at the
    card's edge, and the mark is centred in that instead. On the keyline family no
    such strip exists and the roundel's own centre is the honest answer.
    """
    import numpy as np
    W, H = im.size
    y0 = int(cy + 1.35 * r); y1 = int(cy + 2.6 * r)
    if y1 >= H or y0 >= y1:
        return None
    strip = np.asarray(im.convert("L").crop((0, y0, min(W, int(cx + 3 * r)), y1)),
                       dtype=np.float32)
    # Not the column's median but the FRACTION of it that is near-black, then a max
    # over a rule's width. A band column is solid black top to bottom (fraction 1.0)
    # except where its own gold rule or vine crosses, which the max filter steps over.
    # Hatched artwork next to the band is dark on average but never solid: measured on
    # shell-09 it holds 0.46-0.64 across sixty columns and never once reaches 0.9, so
    # a threshold at 0.85 parts the band from the art where a median could not.
    frac = (strip <= BAND_DARK).mean(axis=0)
    k = max(3, int(W * BAND_GAP))
    sm = np.array([frac[max(0, i - k): i + k + 1].max() for i in range(len(frac))])
    dark = _close_gaps(list(sm >= BAND_SOLID), k)
    runs, i = [], 0
    while i < len(dark):
        if dark[i]:
            j = i
            while j < len(dark) and dark[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    for a, b in runs:
        if a > W * 0.10:                  # the band hugs the card's edge
            continue
        if not (W * BAND_MIN_W <= b - a <= W * BAND_MAX_W):
            continue
        if b - a < 2.1 * mark_r:
            return None                   # a band, but too thin to carry the mark
        return (a + b) / 2.0
    return None


def _corner(im):
    """Measure the TOP-LEFT corner of whatever image is handed in.

    Called twice: once on the card, once on the card turned upside down — which is
    what makes the bottom mark sit on the bottom-right ROSETTE and its own band,
    rather than on wherever the top-left one's mirror image happens to fall.
    """
    found = _find_roundel(im)
    if not found:
        return None
    cx, cy, r, score, field = found
    W, _ = im.size
    mark_r = 2 * r * MARK_R
    band = _band_centre(im, cx, cy, r, mark_r)
    mx = band if band is not None else cx
    my = cy + r + mark_r + MARK_GAP * r
    return {"cx": cx, "cy": cy, "r": r, "score": score, "field": field, "band": band,
            "mark_r": mark_r, "mark": (max(mx, mark_r + EDGE_MARGIN * W),
                                       max(my, mark_r + EDGE_MARGIN * W))}


def detect_corner(im):
    """Everything the mark needs, measured. None if the roundel could not be found.

    dict: cx, cy, r (roundel), score, band (band centre x or None), mark_r,
    tl (x, y), br (x, y), br_from ('rosette' | 'mirror'), clamped (the bottom mark
    was lifted clear of the title plaque).

    The bottom-right corner is measured in its own right, but only TRUSTED if what it
    found agrees with the top-left one: same radius to within BR_TOL_R, same inset to
    within BR_TOL_XY. Half the deck has no rosette down there at all (the keyline
    family draws the frame corner and nothing else), and on those cards the circle
    vote will happily latch onto some disc in the artwork. Agreement is the test that
    tells a rosette from a coincidence; when it fails, the top-left mark's mirror is
    the honest answer, because the frame itself is symmetric even when its ornament
    is not.
    """
    tl = _corner(im)
    if tl is None:
        return None
    W, H = im.size
    mx, my = tl["mark"]
    bx, by = W - mx, H - my
    br_from = "mirror"
    try:
        rot = _corner(im.transpose(Image.ROTATE_180))
    except Exception:
        rot = None
    if rot is not None and rot["field"] == "gold":
        # Gold only. Every rosette in this deck is a gold ornament; the ink field, run
        # on a corner that has no rosette, will happily find a circle in the cracked
        # earth and pass the agreement test by luck.
        rx, ry = W - rot["mark"][0], H - rot["mark"][1]
        if (abs(rot["r"] - tl["r"]) <= BR_TOL_R * tl["r"]
                and abs(rx - bx) <= BR_TOL_XY * W and abs(ry - by) <= BR_TOL_XY * W):
            bx, by, br_from = rx, ry, "rosette"

    # Keep clear of the title plaque — but only if the mark is actually over it. The
    # plaque is centred and the bottom mark sits at ~0.89 W, outside its right edge on
    # every card in the deck, so this fires on none of the 48 as measured. It is a
    # guard against a future art whose plaque runs the full width, not a fudge.
    # NOTE this is why the rank must be set BEFORE the title: cardtitle.detect_banner
    # finds the plaque by its flatness, and the name typeset into it destroys exactly
    # that. Called after set_title it returns None on all 48 and the guard is inert.
    clamped = False
    try:
        banner = detect_banner(im)
    except Exception:
        banner = None
    if banner is not None:
        # Circle against rectangle, not box against box: the mark sits off the plaque's
        # top-RIGHT corner, where a bounding-box test calls a gap the disc never
        # crosses an overlap. Measured, the honest test fires on 9 of the 48 — five of
        # them resolved by a slide of 2-35px, four by a lift.
        mr = tl["mark_r"] + CLEARANCE * W
        qx = min(max(bx, banner[0]), banner[2])
        qy = min(max(by, banner[1]), banner[3])
        if (bx - qx) ** 2 + (by - qy) ** 2 < mr ** 2:
            dx = 0.0 if banner[0] <= bx <= banner[2] else min(abs(bx - banner[0]),
                                                              abs(bx - banner[2]))
            # Resolve by the smaller of two moves, preferring the one that keeps the
            # mark in the CORNER, which is the whole point of an index: slide it
            # outward past the plaque's edge, or lift it above the plaque's top.
            up = by - (banner[1] - (mr ** 2 - dx ** 2) ** 0.5)
            out = (banner[2] + mr) - bx
            edge = W - tl["mark_r"] - EDGE_MARGIN * W
            if out <= up and bx + out <= edge:
                bx += out
            else:
                by -= up
            clamped = True
    out = dict(tl)
    out.pop("mark")
    out.update({"tl": (mx, my), "br": (bx, by), "br_from": br_from, "clamped": clamped,
                "br_r": None if rot is None else rot["r"],
                "br_score": None if rot is None else rot["score"],
                "br_field": None if rot is None else rot["field"],
                "br_band": None if rot is None else rot["band"]})
    return out


def _ink(gold, fill, realm, variant, dark=False):
    if variant != "realm":
        return gold
    ink = REALM_INK.get(realm, gold)
    ink = tuple(a * (1 - REALM_WARM) + b * REALM_WARM for a, b in zip(ink, gold))
    il = max(1.0, _lum(ink))              # indigo on near-black is a rumour, not a rank
    return _scaled(ink, (DARK_REALM_LUM if dark else REALM_LUM) * _lum(gold) / il)


def _tile_box(x, y, mark_r):
    """The square of card the medallion is cut out of: (x0, y0, size, R, pad)."""
    R = int(round(mark_r))
    pad = max(3, int(round(R * 0.35)))
    return int(round(x)) - R - pad, int(round(y)) - R - pad, 2 * (R + pad), R, pad


def field_lum(im, x, y, mark_r):
    """Median luminance of the ground the medallion at (x, y) will be cut into.

    The switch between the two weights, and measured rather than assumed for the same
    reason every other dimension here is: `_band_centre` already knows a band when it
    probes one, but it answers about the strip BELOW the roundel, not about the square
    the bottom mark lands in, and on shell-12 it declines a band the eye plainly sees.
    The ground's own brightness is the property that actually governs how heavy the
    mark has to be drawn, so that is what is asked.
    """
    import numpy as np
    x0, y0, size, _, _ = _tile_box(x, y, mark_r)
    u = np.asarray(im.crop((x0, y0, x0 + size, y0 + size)).convert("RGB"),
                   dtype=np.float32)
    return float(np.median(0.299 * u[..., 0] + 0.587 * u[..., 1] + 0.114 * u[..., 2]))


def _medallion(im, x, y, mark_r, text, fill, ink, rotate, dark=False):
    """Cut one medallion into `im` at (x, y). rotate=True draws it upside down.

    Drawn as a recess, in this order: a blurred shadow the disc casts on the ground,
    then a fill that is FILL_GROUND parts the ground's own darkened hue and keeps
    FILL_TEXTURE of the paper grain showing through, then the keyline, hairline and
    rank in one antique gold. The shadow is what stops it reading as a sticker; the
    grain is what stops it reading as vector.

    `dark` is the band weight: see DARK_FIELD above. It changes only the gold — how
    thick the keyline is, how solid the hairline, whether the rank is struck once or
    twice, and how far the mottle is allowed to pull the gold down. The geometry, the
    fill, the shadow and the grain are the approved drawing either way.
    """
    import numpy as np
    x0, y0, size, R, pad = _tile_box(x, y, mark_r)
    tile = im.crop((x0, y0, x0 + size, y0 + size)).convert("RGB")

    u = np.asarray(tile, dtype=np.float32)
    ul = 0.299 * u[..., 0] + 0.587 * u[..., 1] + 0.114 * u[..., 2]
    ground = np.median(u.reshape(-1, 3), axis=0)
    gl = max(6.0, _lum(ground))
    ground = ground * (FILL_LUM / gl)                      # the ground, in shadow
    flat = (np.array(fill, dtype=np.float32) * (1 - FILL_GROUND)
            + ground * FILL_GROUND)[None, None, :]
    grain = np.clip(u * (FILL_LUM / max(6.0, float(np.median(ul)))), 0, 255)
    body = Image.fromarray(np.clip(flat * (1 - FILL_TEXTURE) + grain * FILL_TEXTURE,
                                   0, 255).astype("uint8"))

    S = SS
    c = (R + pad) * S
    mask = Image.new("L", (size * S, size * S), 0)
    ImageDraw.Draw(mask).ellipse((c - R * S, c - R * S, c + R * S, c + R * S), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)

    shadow = Image.new("L", (size, size), 0)
    sr = R * 1.02
    ImageDraw.Draw(shadow).ellipse((pad + R - sr, pad + R - sr + R * 0.06,
                                    pad + R + sr, pad + R + sr + R * 0.06),
                                   fill=int(255 * SHADOW))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(1.0, SHADOW_BLUR * R)))
    tile = Image.composite(Image.new("RGB", (size, size), (0, 0, 0)), tile, shadow)

    art = Image.new("RGBA", (size * S, size * S), (0, 0, 0, 0))
    ad = ImageDraw.Draw(art)
    kw = max(1.0, KEYLINE * R * (DARK_KEYLINE if dark else 1.0)) * S
    ad.ellipse((c - R * S + kw / 2, c - R * S + kw / 2, c + R * S - kw / 2, c + R * S - kw / 2),
               outline=ink + (255,), width=int(round(kw)))
    ir = R * S * (1 - INNER_RULE)
    hw = max(1.0, 0.032 * R * S)
    ad.ellipse((c - ir, c - ir, c + ir, c + ir),
               outline=ink + (DARK_RULE_ALPHA if dark else 140,), width=int(round(hw)))

    inner = 2 * R * (1 - INNER_RULE - 0.07)
    f = _font(int(round(_fit(text, inner) * S)))
    bb = f.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    # Faux-bold, on the band only: the same character struck twice a little over a pixel
    # apart on the diagonal. Bodoni has no bold in this weight range that is still Bodoni
    # at 40px, and a stroked outline thickens the hairlines and the stems by the same
    # amount, which is the one thing a Didone cannot survive. Two strikes fatten the stems
    # and leave the hairlines to overlap themselves.
    d = (DARK_BOLD * R * S) if dark else 0.0
    tx, ty = c - tw / 2 - bb[0] - d / 2, c - th / 2 - bb[1] - d / 2
    for ox, oy in (((0, 0), (d, 0), (0, d), (d, d)) if dark else ((0, 0),)):
        ad.text((tx + ox, ty + oy), text, font=f, fill=ink + (255,))
    art = art.resize((size, size), Image.LANCZOS)
    if rotate:
        art = art.rotate(180)

    # Take the paper's own mottle into the gold. Every gold line already on these cards
    # is speckled leaf; a perfectly even ring is the one thing in the corner that could
    # only have been printed by a machine.
    a = np.asarray(art, dtype=np.float32)
    m = DARK_MOTTLE if dark else GOLD_MOTTLE
    mot = np.clip(ul / max(6.0, float(np.median(ul))), 1.0 if dark else 1 - m, 1 + m)
    a[..., :3] = np.clip(a[..., :3] * mot[..., None], 0, 255)
    art = Image.fromarray(a.astype("uint8"), "RGBA")

    tile.paste(body, (0, 0), mask)
    tile = tile.convert("RGBA")
    tile.alpha_composite(art)
    im.paste(tile.convert("RGB"), (x0, y0))


def _fit(text, inner):
    """Largest font size whose `text` fits the medallion's inner disc. '10' is wide."""
    size = max(6, int(inner))
    while size > 5:
        f = _font(size)
        bb = f.getbbox(text)
        if (bb[2] - bb[0]) <= inner * TEXT_W and (bb[3] - bb[1]) <= inner * TEXT_H:
            return size
        size -= 1
    return 6


def set_rank(im, number, realm, variant="gold", report=None):
    """Cut this card's rank into its frame, top-left and bottom-right. New image.

    Returns the image UNCHANGED if the realm roundel could not be measured; pass a
    dict as `report` to find out (it gets 'ok' plus the geometry, or 'ok': False).
    """
    im = im.copy()
    try:
        geom = detect_corner(im)
    except Exception as e:
        if report is not None:
            report.update({"ok": False, "why": f"{type(e).__name__}: {e}"})
        return im
    if geom is None:
        if report is not None:
            report.update({"ok": False, "why": "no roundel found in top-left corner"})
        return im

    fill, gold = _palette(im, geom["cx"], geom["cy"], geom["r"])
    # The weight is decided ONCE, from the top-left mark's ground, and both marks are
    # drawn to it. Per-mark would be the obvious thing and is wrong: the bottom mark on
    # every roots card lands on dark navy artwork (measured, luminance 14-30) and would
    # go to band weight on a card whose frame has no band and no vine anywhere near it.
    # What the heavier cut answers to is the card's FRAME, and the top-left corner —
    # roundel, band or keyline, ornament or bare kraft — is where this frame declares
    # itself. Measured: shell 7.8-47.9, everything else 69.4-164.2.
    dark = field_lum(im, geom["tl"][0], geom["tl"][1], geom["mark_r"]) <= DARK_FIELD
    if dark:
        # "the card's brightest roundel gold": on the band the sampled gold is held at
        # the TOP of the window instead of wherever it landed, so the mark is struck in
        # the same leaf as the vine rather than in the roundel's average.
        gold = _scaled(gold, GOLD_LUM[1] / max(1.0, _lum(gold)))
    ink = _ink(gold, fill, realm, variant, dark)
    text = rank_text(number)
    _medallion(im, geom["tl"][0], geom["tl"][1], geom["mark_r"], text, fill, ink, False, dark)
    _medallion(im, geom["br"][0], geom["br"][1], geom["mark_r"], text, fill, ink, True, dark)
    if report is not None:
        report.update({"ok": True, "fill": fill, "gold": gold, "ink": ink,
                       "text": text, "dark": dark, **geom})
    return im
