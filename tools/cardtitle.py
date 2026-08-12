"""The title cartouche — one typesetting rule, shared by every export of the deck.

The generated art deliberately leaves the bottom banner EMPTY. Image models misspell,
and 48 cards each misspelling differently would wreck the cohesion the style guide
exists to protect. So the name is set here instead: one font, one size rule, one
baseline, identical across the deck — and identical between the printed cards and
the web images, which is the whole reason this lives in its own module.

Every measurement is a fraction of the image, so the same call works on a 1024px
master, a 1050px print trim, or a 900px web JPEG.
"""
from PIL import ImageDraw, ImageFont

TITLE_FONTS = [
    "/System/Library/Fonts/Supplemental/Bodoni 72 Smallcaps Book.ttf",  # the style guide's face
    "/System/Library/Fonts/Supplemental/Baskerville.ttc",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
]
TITLE_Y = 0.888        # baseline centre, as a fraction of card height — inside the banner
TITLE_MAX_W = 0.66     # longest names shrink to fit rather than crowding the frame
TITLE_INK = (38, 28, 14)
TRACKING = 0.14        # letter-spacing, in ems — small caps want air


def _title_font(size):
    for path in TITLE_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


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


def set_title(im, name):
    """Composite the card name into the empty banner. Returns a new image."""
    im = im.copy()
    draw = ImageDraw.Draw(im)
    W, H = im.size
    size = int(H * 0.030)
    font = _title_font(size)
    # shrink until it fits the banner's usable width, tracking included
    while size > 8:
        widths = [draw.textlength(ch, font=font) for ch in name]
        total = sum(widths) + font.size * TRACKING * (len(name) - 1)
        if total <= W * TITLE_MAX_W:
            break
        size -= 2
        font = _title_font(size)
    _draw_tracked(draw, name, font, W / 2, H * TITLE_Y, TITLE_INK, TRACKING)
    return im
