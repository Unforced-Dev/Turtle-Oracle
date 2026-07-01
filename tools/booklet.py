"""Companion meanings booklet -> print/booklet.pdf (half-letter, 2 cards/page)."""
from PIL import Image, ImageDraw, ImageFont
import json, os

REPO = "/Users/parachute/Code/oracle-ai"
ART = f"{REPO}/cards/art"
d = json.load(open(f"{REPO}/data/cards.json"))
playa = json.load(open(f"{REPO}/data/playa_2026.json"))["hooks"]
order = {"shell": 0, "roots": 1, "trunk": 2, "branches": 3}
cards = sorted(d["cards"], key=lambda c: (order[c["realm"]], c["number"]))

W, H = 1100, 1700           # ~5.5x8.5in @ 200dpi
KRAFT = (233, 220, 192); INK = (38, 30, 16); GOLD = (150, 110, 40); DIM = (110, 96, 64)
REALM_TINT = {"shell": (150, 110, 40), "roots": (70, 70, 120), "trunk": (150, 95, 45), "branches": (70, 110, 140)}
REALM_DESC = {
    "shell": "THE SHELL · the Turtle beneath — the axis speaks",
    "roots": "ROOTS · the underworld — what to face",
    "trunk": "TRUNK · the middle world — where you stand",
    "branches": "BRANCHES · the heavens — what to reach for",
}
G = "/System/Library/Fonts/Supplemental/Georgia.ttf"
GB = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
def font(path, sz):
    try: return ImageFont.truetype(path, sz)
    except Exception: return ImageFont.load_default()
F_TITLE, F_NAME, F_LBL, F_BODY, F_SM = font(GB, 46), font(GB, 30), font(GB, 16), font(G, 19), font(G, 15)


def wrap(draw, text, fnt, x, y, maxw, fill, lh):
    words, line = text.split(), ""
    for w in words:
        t = (line + " " + w).strip()
        if draw.textlength(t, font=fnt) <= maxw:
            line = t
        else:
            draw.text((x, y), line, font=fnt, fill=fill); y += lh; line = w
    if line:
        draw.text((x, y), line, font=fnt, fill=fill); y += lh
    return y


pages = []

# --- cover ---
cov = Image.new("RGB", (W, H), (20, 17, 12)); cd = ImageDraw.Draw(cov)
try:
    back = Image.open(f"{REPO}/cards/back.png").convert("RGB")
    bw = 520; bh = int(bw * back.size[1] / back.size[0]); back = back.resize((bw, bh))
    cov.paste(back, ((W - bw) // 2, 360))
except Exception: pass
cd.text((W // 2, 150), "THE TERRIBLE TURTLE", font=F_TITLE, fill=GOLD, anchor="mm")
cd.text((W // 2, 205), "ORACLE", font=F_TITLE, fill=GOLD, anchor="mm")
cd.text((W // 2, 270), "A Companion Booklet · Black Rock City MMXXVI", font=F_BODY, fill=(190, 174, 138), anchor="mm")
cd.text((W // 2, H - 120), "Move Slow & Bite Things", font=F_NAME, fill=(190, 174, 138), anchor="mm")
pages.append(cov)

# --- intro ---
intro = Image.new("RGB", (W, H), KRAFT); dr = ImageDraw.Draw(intro)
y = 90
dr.text((80, y), "How to read the Tree", font=F_NAME, fill=GOLD); y += 70
for para in [
    "The World Turtle carries the World Tree. This deck is that tree: 48 cards in four realms.",
    "Draw one from the ROOTS (what to face), one from the TRUNK (where you stand), and one from the BRANCHES (what to reach for). Read them as a single arc, not three separate fortunes.",
    "A SHELL card is the axis itself — when it appears, the whole reading turns around it.",
    "Every card carries a Reading (the truth), its shadow (the warning), and a Turtle Dare — one real adventure to carry out on the playa.",
    "Move slow. Then bite down.",
]:
    y = wrap(dr, para, F_BODY, 80, y, W - 160, INK, 30) + 18
pages.append(intro)


def card_block(dr, c, x, y, h):
    tint = REALM_TINT[c["realm"]]
    tw = 300; th = int(tw * 1.5)
    try:
        im = Image.open(f"{ART}/{c['id']}.png").convert("RGB").resize((tw, th))
        dr._image.paste(im, (x, y))
    except Exception:
        dr.rectangle([x, y, x + tw, y + th], outline=tint, width=2)
    tx = x + tw + 40; tw2 = W - tx - 80
    yy = y + 4
    dr.text((tx, yy), c["name"], font=F_NAME, fill=GOLD); yy += 44
    dr.text((tx, yy), c["realm"].upper() + "  ·  " + c["real_2026"]["name"], font=F_SM, fill=tint); yy += 34
    yy = wrap(dr, c["reading"], F_BODY, tx, yy, tw2, INK, 27) + 10
    if c.get("shadow"):
        dr.text((tx, yy), "Shadow", font=F_LBL, fill=DIM); yy += 24
        yy = wrap(dr, c["shadow"], F_SM, tx, yy, tw2, DIM, 22) + 10
    dr.text((tx, yy), "Turtle Dare", font=F_LBL, fill=tint); yy += 24
    yy = wrap(dr, c["turtle_dare"], F_SM, tx, yy, tw2, INK, 22)


# --- realm sections, 2 cards per page ---
by_realm = {}
for c in cards:
    by_realm.setdefault(c["realm"], []).append(c)

for realm in ("shell", "roots", "trunk", "branches"):
    rc = by_realm[realm]
    # realm divider
    dv = Image.new("RGB", (W, H), KRAFT); dd = ImageDraw.Draw(dv)
    dd.rectangle([0, H // 2 - 90, W, H // 2 + 90], fill=REALM_TINT[realm])
    dd.text((W // 2, H // 2 - 20), realm.upper(), font=F_TITLE, fill=(245, 240, 230), anchor="mm")
    dd.text((W // 2, H // 2 + 40), REALM_DESC[realm].split("·", 1)[1].strip(), font=F_BODY, fill=(245, 240, 230), anchor="mm")
    pages.append(dv)
    for i in range(0, len(rc), 2):
        pg = Image.new("RGB", (W, H), KRAFT); dr = ImageDraw.Draw(pg); dr._image = pg
        card_block(dr, rc[i], 80, 80, 720)
        if i + 1 < len(rc):
            dr.line([80, 850, W - 80, 850], fill=(200, 185, 150), width=2)
            card_block(dr, rc[i + 1], 80, 880, 720)
        pages.append(pg)

os.makedirs(f"{REPO}/print", exist_ok=True)
pages[0].save(f"{REPO}/print/booklet.pdf", save_all=True, append_images=pages[1:], resolution=200.0)
print(f"booklet.pdf — {len(pages)} pages")
