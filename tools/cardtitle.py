"""The title cartouche — one typesetting rule, shared by every export of the deck.

The generated art deliberately leaves the bottom banner EMPTY. Image models misspell,
and 48 cards each misspelling differently would wreck the cohesion the style guide
exists to protect. So the name is set here instead: one font, one ink, one tracking,
identical across the deck — and identical between the printed cards and the web
images, which is the whole reason this lives in its own module.

What is NOT identical is the banner. Each of the 48 arts drew its own kraft plaque:
measured across the deck their centres sit anywhere from 0.855 to 0.921 of the card
height, and the tallest plaque is nearly twice the shortest (0.117 vs 0.060 of the
height). A single fraction of the image therefore cannot centre the name in every
one of them, and sizing the type for the shortest banner made the whole deck small.
So the banner is MEASURED on the rendered card (`detect_banner`) and the name is
centred in it and grown until it fills it. The fractional rule survives only as the
fallback for a card whose banner cannot be found.

Everything is computed from the image that is handed in, so the same call works on a
1024px master, a 1050px print trim, a height-fitted 1000x1500 MPC front, or the
4.8%-stretched TGC card.
"""
from PIL import ImageDraw, ImageFont

TITLE_FONTS = [
    "/System/Library/Fonts/Supplemental/Bodoni 72 Smallcaps Book.ttf",  # the style guide's face
    "/System/Library/Fonts/Supplemental/Baskerville.ttc",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
]
TITLE_INK = (38, 28, 14)
TRACKING = 0.14        # letter-spacing, in ems — small caps want air

# --- fallback rule: the old deck-wide fractions, used only when detection fails ---
TITLE_Y = 0.888        # baseline centre, as a fraction of card height — inside the banner
TITLE_MAX_W = 0.66     # longest names shrink to fit rather than crowding the frame

# --- how the name is fitted to the banner it was found in ---
CAP_FRACTION = 0.42    # cap height at most this much of the inner box height
FILL_W = 0.90          # tracked width at most this much of the inner box width
MAX_SIZE = 0.050       # never larger than this fraction of card height, whatever the box allows
#                        — the deck still has to look like one deck

# --- banner detection (all fractions of the rendered card) ---
BAND_TOP = 0.60        # search starts here; every banner in the deck sits below it
CENTRE_COLS = 0.40     # rows are judged on this central span only — narrower than any banner
FLAT_SPREAD = 60       # a banner-interior row's p90-p10 luminance spread stays under this
MIN_FILL = 110         # ...and the kraft fill is at least this light (0-255)
MIN_BAND_H = 0.045     # a band thinner than this is not a banner
MIN_BAND_W = 0.40      # ...nor is an inner box narrower than this
MAX_BAND_B = 0.985     # ...nor is one that runs off the bottom of the card (deepest real: 0.961)
EDGE_TOL = 24          # a column/row this far off the fill's luminance is the gold border
EDGE_RUN = 0.004       # ...and the border is at least this wide, as a fraction of the card:
#                        narrower breaks are specks in the kraft and get closed over


def _title_font(size):
    for path in TITLE_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _tracked_width(draw, text, font):
    widths = [draw.textlength(ch, font=font) for ch in text]
    return sum(widths) + font.size * TRACKING * (len(text) - 1), widths


def _draw_tracked(draw, text, font, cx, cy, fill, tracking):
    """Centre `text` at (cx, cy) with letter-spacing. PIL has no tracking of its own."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    gap = font.size * tracking
    total = sum(widths) + gap * (len(text) - 1)
    x = cx - total / 2
    ascent, descent = font.getmetrics()
    y = cy - (ascent - descent) / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + gap


def _longest_run(flags):
    """(start, end) of the longest run of True in a 1-D boolean sequence."""
    best = (0, 0)
    start = None
    for i, ok in enumerate(flags):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    if start is not None and len(flags) - start > best[1] - best[0]:
        best = (start, len(flags))
    return best


def _close_gaps(flags, k):
    """Fill runs of False shorter than k — a speck in the kraft is not a border."""
    out = list(flags)
    n = len(out)
    i = 0
    while i < n:
        if not out[i]:
            j = i
            while j < n and not out[j]:
                j += 1
            if j - i < k and i > 0 and j < n:
                for m in range(i, j):
                    out[m] = True
            i = j
        else:
            i += 1
    return out


def detect_banner(im):
    """Measure the kraft plaque's INNER box (inside the gold border) in pixels.

    Returns (x0, y0, x1, y1), or None if this card has nothing banner-shaped in its
    lower 40%. Deterministic: pure statistics over the pixels, and every threshold is
    either a fraction of the image or a luminance the woodcut style fixes.

    The banner interior is the one thing down there that is both flat and light: the
    art around it is hatched woodcut and the frame is gold-on-dark. So rows are scored
    on the luminance spread across their central span, the longest flat-and-light run
    locates the plaque, a second pass trims that run to the rows sharing the plaque's
    own tone, and the inner width is then found by walking out from the centre of the
    band until the gold border darkens a column.
    """
    try:
        import numpy as np
    except ImportError:
        return None
    try:
        g = np.asarray(im.convert("L"), dtype=np.float32)
    except Exception:
        return None
    H, W = g.shape
    if H < 40 or W < 40:
        return None

    y_from = int(H * BAND_TOP)
    cx0, cx1 = int(W * (1 - CENTRE_COLS) / 2), int(W * (1 + CENTRE_COLS) / 2)
    strip = g[y_from:, cx0:cx1]
    if strip.shape[0] < 8:
        return None

    lo = np.percentile(strip, 10, axis=1)
    hi = np.percentile(strip, 90, axis=1)
    med = np.median(strip, axis=1)
    flat = (hi - lo <= FLAT_SPREAD) & (med >= MIN_FILL)

    # pass 1 — the longest run of flat, light rows locates the plaque
    a, b = _longest_run(flat)
    if b - a < H * MIN_BAND_H:
        return None
    seed = (a + b) // 2

    # pass 2 — trim to the rows that share the plaque's own tone. A card whose
    # margin below the frame is bare kraft too reads as one tall band in pass 1;
    # the gold rules between them are flat and light but nothing like the fill,
    # so re-cutting on tone parts them.
    tone = float(np.median(med[a:b]))
    same = flat & (np.abs(med - tone) <= EDGE_TOL)
    if not same[seed]:
        same = flat
    y0i = y1i = seed
    while y0i > 0 and same[y0i - 1]:
        y0i -= 1
    while y1i < len(same) - 1 and same[y1i + 1]:
        y1i += 1
    y1i += 1
    if y1i - y0i < H * MIN_BAND_H:
        return None

    y0, y1 = y_from + y0i, y_from + y1i
    if y1 > H * MAX_BAND_B:
        return None

    # inner width: from the band's own middle rows, walk out until the gold border
    m0 = y0 + max(1, (y1 - y0) // 4)
    m1 = y1 - max(1, (y1 - y0) // 4)
    core = g[m0:m1, :]
    col_med = np.median(core, axis=0)
    col_lo = np.percentile(core, 10, axis=0)
    col_hi = np.percentile(core, 90, axis=0)
    fill = float(np.median(col_med[cx0:cx1]))
    inside = (np.abs(col_med - fill) <= EDGE_TOL) & (col_hi - col_lo <= FLAT_SPREAD)
    inside = _close_gaps(inside, max(3, int(round(W * EDGE_RUN))))

    mid = W // 2
    if not inside[mid]:
        return None
    x0 = mid
    while x0 > 0 and inside[x0 - 1]:
        x0 -= 1
    x1 = mid
    while x1 < W - 1 and inside[x1 + 1]:
        x1 += 1
    x1 += 1
    # Every plaque in the deck is drawn on the card's own axis (measured: all 48 sit
    # within 0.7% of centre), so the narrower half is the trustworthy one — mirroring
    # it keeps a faint or mottled border on one side from pulling the title sideways.
    half = min(mid - x0, x1 - mid)
    x0, x1 = mid - half, mid + half
    if x1 - x0 < W * MIN_BAND_W:
        return None
    return (x0, y0, x1, y1)


def _ink_box(font, text):
    """(top, bottom) of the actual inked pixels, relative to the draw origin."""
    try:
        b = font.getbbox(text)
        return b[1], b[3]
    except Exception:
        a, d = font.getmetrics()
        return 0, a


def _cap_height(font, text):
    """Height of the inked caps — for small caps this IS the visual height of the line."""
    top, bot = _ink_box(font, text)
    return bot - top


def _optical_dy(font, text):
    """How far _draw_tracked's ascent/descent centre sits below the inked centre.

    _draw_tracked places the origin at cy - (ascent - descent) / 2, which is the
    right rule for a mixed-case line but leaves an all-caps line ~8% of its size
    low. Subtracting this puts the CAPS' own centre on cy, which is what centring
    inside a plaque means.
    """
    a, d = font.getmetrics()
    top, bot = _ink_box(font, text)
    return (top + bot) / 2 - (a - d) / 2


def set_title(im, name):
    """Composite the card name into its banner. Returns a new image."""
    im = im.copy()
    draw = ImageDraw.Draw(im)
    W, H = im.size
    try:
        box = detect_banner(im)
    except Exception:
        box = None

    if box is None:
        # fallback: the deck-wide fractional rule
        size = int(H * 0.030)
        font = _title_font(size)
        while size > 8:
            total, _ = _tracked_width(draw, name, font)
            if total <= W * TITLE_MAX_W:
                break
            size -= 2
            font = _title_font(size)
        _draw_tracked(draw, name, font, W / 2, H * TITLE_Y, TITLE_INK, TRACKING)
        return im

    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    cap_cap = bh * CAP_FRACTION
    width_cap = bw * FILL_W
    ceiling = max(10, int(H * MAX_SIZE))

    best = _title_font(10)
    for s in range(11, ceiling + 1):
        f = _title_font(s)
        total, _ = _tracked_width(draw, name, f)
        if total > width_cap or _cap_height(f, name) > cap_cap:
            break
        best = f
    cy = (y0 + y1) / 2 - _optical_dy(best, name)
    _draw_tracked(draw, name, best, (x0 + x1) / 2, cy, TITLE_INK, TRACKING)
    return im
