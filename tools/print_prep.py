"""Build print-ready card assets: full-bleed fronts + back, and a proof PDF.

Card: 3.5 x 5.25 in (exact 2:3, matches the art — no cropping), 300 DPI, 1/8" bleed.
Bleed is added by extending edge pixels OUTWARD, so no card's gold border is ever trimmed.
"""
from PIL import Image, ImageDraw, ImageFont
import json, os

REPO = "/Users/parachute/Code/oracle-ai"
ART = f"{REPO}/cards/art"
OUT = f"{REPO}/print"
os.makedirs(f"{OUT}/fronts", exist_ok=True)

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


def print_ready(src):
    im = Image.open(src).convert("RGB").resize(TRIM, Image.LANCZOS)
    return add_bleed(im, BLEED)


# --- fronts + back with bleed ---
for c in cards:
    print_ready(f"{ART}/{c['id']}.png").save(f"{OUT}/fronts/{c['id']}.png", dpi=(DPI, DPI))
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
    src = f"{OUT}/back.png" if c["id"] == "back" else f"{ART}/{c['id']}.png"
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
