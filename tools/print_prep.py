"""Build print-ready card assets: full-bleed fronts + back, and a proof PDF.

Card: 3.5 x 5.25 in (exact 2:3, matches the art — no cropping), 300 DPI, 1/8" bleed.
Bleed is added by extending edge pixels OUTWARD, so no card's gold border is ever trimmed.
"""
from PIL import Image, ImageDraw, ImageFont
import json, os

import os
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = f"{REPO}/cards/art"
OUT = f"{REPO}/print"
os.makedirs(f"{OUT}/fronts", exist_ok=True)


def art_src(cid):
    # .png masters are local-only (gitignored); the committed archive is q95 .jpg
    p = f"{ART}/{cid}.png"
    return p if os.path.exists(p) else f"{ART}/{cid}.jpg"

DPI = 300
TRIM = (int(3.5 * DPI), int(5.25 * DPI))   # 1050 x 1575
BLEED = int(0.125 * DPI)                    # 38 px

d = json.load(open(f"{REPO}/data/cards.json"))
order = {"shell": 0, "roots": 1, "trunk": 2, "branches": 3}
cards = sorted(d["cards"], key=lambda c: (order[c["realm"]], c["number"]))


def add_bleed(im, b):
    w, h = im.size
    canvas = Image.new("RGB", (w + 2 * b, h + 2 * b))
    canvas.paste(im, (b, b))
    canvas.paste(im.crop((0, 0, 1, h)).resize((b, h)), (0, b))            # left
    canvas.paste(im.crop((w - 1, 0, w, h)).resize((b, h)), (b + w, b))    # right
    canvas.paste(im.crop((0, 0, w, 1)).resize((w, b)), (b, 0))            # top
    canvas.paste(im.crop((0, h - 1, w, h)).resize((w, b)), (b, b + h))    # bottom
    canvas.paste(im.crop((0, 0, 1, 1)).resize((b, b)), (0, 0))
    canvas.paste(im.crop((w - 1, 0, w, 1)).resize((b, b)), (b + w, 0))
    canvas.paste(im.crop((0, h - 1, 1, h)).resize((b, b)), (0, b + h))
    canvas.paste(im.crop((w - 1, h - 1, w, h)).resize((b, b)), (b + w, b + h))
    return canvas


# --- the title cartouche -----------------------------------------------------------
# The generated art deliberately leaves the bottom banner EMPTY. Image models misspell,
# and 48 cards each misspelling differently would wreck the cohesion the style guide
# exists to protect. So the name is set here instead: one font, one size rule, one
# baseline, identical across the deck.
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


def print_ready(src, name=None):
    im = Image.open(src).convert("RGB").resize(TRIM, Image.LANCZOS)
    if name:
        im = set_title(im, name)
    return add_bleed(im, BLEED)


# --- fronts + back with bleed ---
for c in cards:
    print_ready(art_src(c["id"]), c["name"]).save(
        f"{OUT}/fronts/{c['id']}.png", dpi=(DPI, DPI))
print_ready(f"{REPO}/cards/back.png").save(f"{OUT}/back.png", dpi=(DPI, DPI))

# --- proof PDF: one card per page, name caption, for review (not for the printer) ---
try:
    gio = "/System/Library/Fonts/Supplemental/Georgia.ttf"
    fname = ImageFont.truetype(gio, 34)
    fsub = ImageFont.truetype(gio, 22)
except Exception:
    fname = fsub = ImageFont.load_default()

PW, PH = 850, 1350
pages = []
cover = Image.new("RGB", (PW, PH), (20, 17, 12))
cd = ImageDraw.Draw(cover)
cd.text((PW // 2, 480), "THE TERRIBLE TURTLE ORACLE", font=fname, fill=(200, 162, 74), anchor="mm")
cd.text((PW // 2, 540), "48 cards · Black Rock City MMXXVI", font=fsub, fill=(182, 166, 132), anchor="mm")
cd.text((PW // 2, 600), "PROOF — full-art fronts + uniform back", font=fsub, fill=(150, 140, 110), anchor="mm")
pages.append(cover)

seq = cards + [{"id": "back", "name": "Card Back (all cards)", "realm": "", "number": 0}]
for c in seq:
    page = Image.new("RGB", (PW, PH), (245, 240, 230))
    src = f"{OUT}/back.png" if c["id"] == "back" else art_src(c["id"])
    im = Image.open(src).convert("RGB")
    tw = PW - 120
    th = int(tw * im.size[1] / im.size[0])
    im = im.resize((tw, th), Image.LANCZOS)
    page.paste(im, ((PW - tw) // 2, 40))
    dr = ImageDraw.Draw(page)
    label = c["name"] if c["id"] == "back" else f"{c['name']}  ·  {c['realm']}"
    dr.text((PW // 2, 40 + th + 40), label, font=fname, fill=(30, 24, 12), anchor="mm")
    pages.append(page)

pages[0].save(f"{OUT}/proof.pdf", save_all=True, append_images=pages[1:], resolution=150.0)
print(f"fronts: {len(cards)}  |  back: 1  |  proof pages: {len(pages)}")
print(f"card: 3.5x5.25in @ {DPI}dpi  trim={TRIM}  bleed={BLEED}px  full={tuple(t+2*BLEED for t in TRIM)}")
