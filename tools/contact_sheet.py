from PIL import Image, ImageDraw, ImageFont
import json, os

REPO = "/Users/parachute/Code/oracle-ai"
d = json.load(open(f"{REPO}/data/cards.json"))
order = {"shell": 0, "roots": 1, "trunk": 2, "branches": 3}
cards = sorted(d["cards"], key=lambda c: (order[c["realm"]], c["number"]))

COLS = 8
TW, TH, LBL, PAD, TITLE = 240, 360, 22, 8, 64
rows = (len(cards) + COLS - 1) // COLS
W = COLS * (TW + PAD) + PAD
H = TITLE + rows * (TH + LBL + PAD) + PAD
sheet = Image.new("RGB", (W, H), (20, 17, 12))
draw = ImageDraw.Draw(sheet)
try:
    gio = "/System/Library/Fonts/Supplemental/Georgia.ttf"
    font = ImageFont.truetype(gio, 30)
    small = ImageFont.truetype(gio, 13)
except Exception:
    font = small = ImageFont.load_default()

draw.text((PAD, 20), "The Terrible Turtle Oracle  —  48 cards  (Shell · Roots · Trunk · Branches)",
          fill=(200, 162, 74), font=font)

realm_tint = {"shell": (200,162,74), "roots": (120,120,180), "trunk": (200,140,80), "branches": (150,190,220)}
for i, c in enumerate(cards):
    r, col = divmod(i, COLS)
    x = PAD + col * (TW + PAD)
    y = TITLE + r * (TH + LBL + PAD)
    try:
        im = Image.open(f"{REPO}/cards/art/{c['id']}.png").convert("RGB").resize((TW, TH))
        sheet.paste(im, (x, y))
    except Exception:
        draw.rectangle([x, y, x + TW, y + TH], fill=(70, 40, 40))
        draw.text((x + 8, y + 8), "MISSING", fill=(255, 180, 120), font=small)
    draw.text((x + 2, y + TH + 4), c["name"][:36], fill=realm_tint.get(c["realm"], (180,180,180)), font=small)

sheet.save(f"{REPO}/cards/contact-sheet.png")
print("saved contact-sheet.png", W, "x", H)
