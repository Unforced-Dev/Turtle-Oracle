"""Companion meanings booklet -> print/booklet.pdf.

Half-letter (5.5x8.5in @ 200dpi), saddle-stitch: cover, intro, a divider and
paired card pages per realm, an index, a colophon. Page count is padded to a
multiple of 4 so the signature folds.

Everything is read from data/cards.json — the realms, how many ranks each one
holds, the totals printed on the cover, the index table. The deck doubles as a
playing deck (realms = suits, numbers = ranks, 1=A / 11=J / 12=Q / 13=K), so a
rebuild after the deck grows a rank needs no edit here.

    python3 tools/booklet.py            # write print/booklet.pdf
    python3 tools/booklet.py --png DIR  # ...and every page as DIR/NN.png
"""
from PIL import Image, ImageDraw, ImageFont
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cardtitle import set_title

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = f"{REPO}/cards/art"


def art_src(cid):
    # The committed q95 .jpg archive is the build source, so every clone builds
    # identical bytes; the local-only .png master is the fallback for fresh gens.
    p = f"{ART}/{cid}.jpg"
    return p if os.path.exists(p) else f"{ART}/{cid}.png"


d = json.load(open(f"{REPO}/data/cards.json"))
DECK = d["deck"]
lore = json.load(open(f"{REPO}/data/card_lore.json"))

# Realm order is the deck's own; anything the deck adds later falls in behind.
_pref = ["shell", "roots", "trunk", "branches"]
REALMS = [r for r in _pref if r in DECK["realms"]] + \
         [r for r in DECK["realms"] if r not in _pref]
_ord = {r: i for i, r in enumerate(REALMS)}
cards = sorted(d["cards"], key=lambda c: (_ord[c["realm"]], c["number"]))
by_realm = {}
for c in cards:
    by_realm.setdefault(c["realm"], []).append(c)

W, H = 1100, 1700           # ~5.5x8.5in @ 200dpi
KRAFT = (233, 220, 192); INK = (38, 30, 16); GOLD = (150, 110, 40); DIM = (110, 96, 64)
DARK = (20, 17, 12); PALE = (190, 174, 138); RULE = (200, 185, 150)
CREAM = (245, 240, 230); BRONZE = (92, 70, 30)
REALM_TINT = {"shell": (150, 110, 40), "roots": (70, 70, 120),
              "trunk": (150, 95, 45), "branches": (70, 110, 140)}
REALM_DESC = {
    "shell": "THE SHELL · the Turtle beneath — the axis speaks",
    "roots": "ROOTS · the underworld — what to face",
    "trunk": "TRUNK · the middle world — where you stand",
    "branches": "BRANCHES · the heavens — what to reach for",
}
REALM_SUIT = {"shell": "the wild suit", "roots": "the buried suit",
              "trunk": "the standing suit", "branches": "the reaching suit"}


def tint(realm):
    return REALM_TINT.get(realm, GOLD)


def realm_head(realm):
    return REALM_DESC.get(realm, realm.upper()).split("·")[0].strip()


def realm_tag(realm):
    txt = REALM_DESC.get(realm)
    return txt.split("·", 1)[1].strip() if txt and "·" in txt else ""


# ------------------------------------------------------- playing-card map ---
COURT = {1: "A", 11: "J", 12: "Q", 13: "K"}


def rank_label(n):
    return COURT.get(n, str(n))


_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
          "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
          "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]


def words(n):
    if n < 20: return _UNITS[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _TENS[t] + ("-" + _UNITS[u] if u else "")
    return str(n)


def rank_phrase(numbers):
    """'A, 2 through 10, J, Q and K' — from whatever ranks the deck actually has."""
    ns = sorted(set(numbers))
    plain = [n for n in ns if n not in COURT]
    parts = []
    if 1 in ns: parts.append("A")
    if plain:
        parts.append(str(plain[0]) if len(plain) == 1
                     else f"{plain[0]} through {plain[-1]}")
    parts += [COURT[n] for n in ns if n in COURT and n != 1]
    if len(parts) > 1:
        return ", ".join(parts[:-1]) + " and " + parts[-1]
    return parts[0] if parts else ""


N_CARDS = len(cards)
N_REALMS = len(REALMS)
RANKS = sorted({c["number"] for c in cards})
N_RANKS = len(RANKS)

G = "/System/Library/Fonts/Supplemental/Georgia.ttf"
GB = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
GI = "/System/Library/Fonts/Supplemental/Georgia Italic.ttf"


def font(path, sz):
    try: return ImageFont.truetype(path, sz)
    except Exception: return ImageFont.load_default()


F_TITLE = font(GB, 46)      # cover / divider display
F_NAME = font(GB, 30)       # card name, page headings
F_SUB = font(GB, 22)        # sub-headings
F_LBL = font(GB, 16)        # Shadow / Turtle Dare labels
F_BODY = font(G, 19)        # the Reading, intro prose
F_ESS = font(GI, 20)        # the essence line
F_SM = font(G, 15)          # shadow, dare, captions
F_TINY = font(G, 13)        # folio, index ranks
F_IDX = font(G, 17)         # index names
F_IDXH = font(GB, 15)       # index column heads


def wrap_lines(draw, text, fnt, maxw):
    out, line = [], ""
    for w in text.split():
        t = (line + " " + w).strip()
        if draw.textlength(t, font=fnt) <= maxw:
            line = t
        else:
            if line: out.append(line)
            line = w
    if line: out.append(line)
    return out


def wrap(draw, text, fnt, x, y, maxw, fill, lh):
    for line in wrap_lines(draw, text, fnt, maxw):
        draw.text((x, y), line, font=fnt, fill=fill); y += lh
    return y


def measure(draw, text, fnt, maxw, lh):
    return len(wrap_lines(draw, text, fnt, maxw)) * lh


def new_page(bg=KRAFT):
    pg = Image.new("RGB", (W, H), bg)
    dr = ImageDraw.Draw(pg); dr._image = pg
    return pg, dr


pages = []          # (image, kind) — kind suppresses the folio on plates
overflow = []
_probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))


def add(pg, kind="body"):
    pages.append((pg, kind))


# ---------------------------------------------------------------- cover ----
cov, cd = new_page(DARK)
cd.rectangle([38, 38, W - 39, H - 39], outline=GOLD, width=3)
cd.rectangle([50, 50, W - 51, H - 51], outline=BRONZE, width=1)
try:
    back = Image.open(f"{REPO}/cards/back.png").convert("RGB")
    bw = 560; bh = int(bw * back.size[1] / back.size[0]); back = back.resize((bw, bh))
    bx, by = (W - bw) // 2, 470
    cd.rectangle([bx - 7, by - 7, bx + bw + 6, by + bh + 6], fill=BRONZE)
    cov.paste(back, (bx, by))
except Exception:
    pass
cd.text((W // 2, 168), "THE TERRIBLE TURTLE", font=F_TITLE, fill=GOLD, anchor="mm")
cd.text((W // 2, 228), "ORACLE", font=F_TITLE, fill=GOLD, anchor="mm")
cd.line([W // 2 - 190, 288, W // 2 + 190, 288], fill=BRONZE, width=2)
cd.text((W // 2, 330), DECK["subtitle"], font=F_BODY, fill=PALE, anchor="mm")
cd.text((W // 2, 388), f"A COMPANION BOOKLET · {words(N_CARDS).upper()} CARDS",
        font=F_LBL, fill=(120, 100, 62), anchor="mm")
cd.text((W // 2, H - 128), "Axis Mundi — the World Tree,", font=F_SM, fill=(120, 100, 62), anchor="mm")
cd.text((W // 2, H - 100), "carried on the back of the World Turtle", font=F_SM,
        fill=(120, 100, 62), anchor="mm")
add(cov, "plate")

# ---------------------------------------------------------------- intro ----
intro, dr = new_page()
y = 96
dr.text((80, y), "How to Read the Tree", font=F_NAME, fill=GOLD); y += 46
dr.line([80, y, W - 80, y], fill=GOLD, width=2); y += 30
for para in [
    f"The World Turtle carries the World Tree. This deck is that tree: {words(N_CARDS)} cards "
    f"in {words(N_REALMS)} realms, each card a piece of ordinary, uncomfortable, kindly-meant "
    "truth with a dare attached.",
    "Draw one from the ROOTS, one from the TRUNK, one from the BRANCHES — what to face, "
    "where you stand, what to reach for — and read them as a single arc, not three separate "
    "fortunes. A SHELL card is the axis itself; when it turns up the whole reading swings "
    "around it, and it may stand in any position.",
    "Every card carries a Reading (the truth), a Shadow (the same truth gone sour), and a "
    "Turtle Dare — one concrete adventure to actually carry out. The dares are the point. "
    "A reading you don't walk out of is just a nice sentence.",
]:
    y = wrap(dr, para, F_BODY, 80, y, W - 160, INK, 30) + 20

y += 10
dr.text((80, y), "The Four Realms" if N_REALMS == 4 else "The Realms",
        font=F_SUB, fill=GOLD); y += 40
for r in REALMS:
    t = tint(r)
    dr.rectangle([80, y + 4, 90, y + 30], fill=t)
    dr.text((106, y), realm_head(r), font=F_LBL, fill=t); y += 28
    # the position clause is drawn in the spread below — don't say it twice
    y = wrap(dr, DECK["realms"][r].split("Position:")[0].strip(), F_SM,
             106, y, W - 106 - 80, INK, 22) + 16

# --- the Tree spread, drawn ---
y += 10
dr.line([80, y, W - 80, y], fill=RULE, width=2); y += 26
dr.text((80, y), "The Tree Spread", font=F_SUB, fill=GOLD); y += 42

CW_, CH_ = 104, 156
cx = 190
spread = [("branches", "what to reach for"), ("trunk", "where you stand"),
          ("roots", "what to face")]
spread = [(r, p) for r, p in spread if r in by_realm]
sp_top = y
for i, (r, pos) in enumerate(spread):
    t = tint(r)
    by_ = sp_top + i * (CH_ + 16)
    dr.rectangle([cx, by_, cx + CW_, by_ + CH_], fill=(222, 208, 176), outline=t, width=3)
    dr.text((cx + CW_ // 2, by_ + CH_ // 2), realm_head(r)[:1], font=F_TITLE, fill=t, anchor="mm")
    if i:
        dr.line([cx + CW_ // 2, by_ - 16, cx + CW_ // 2, by_], fill=GOLD, width=2)
    dr.text((cx + CW_ + 40, by_ + CH_ // 2 - 20), realm_head(r), font=F_LBL, fill=t)
    dr.text((cx + CW_ + 40, by_ + CH_ // 2 + 6), pos, font=F_BODY, fill=INK)
sp_bot = sp_top + len(spread) * (CH_ + 16) - 16
if "shell" in by_realm:
    sx = W - 80 - CW_
    sy = sp_top + (sp_bot - sp_top - CH_) // 2
    for o in (0, 5, 10):
        dr.rectangle([sx - o, sy - o, sx + CW_ - o, sy + CH_ - o],
                     fill=(222, 208, 176), outline=tint("shell"), width=2)
    dr.text((sx - 10 + CW_ // 2, sy - 10 + CH_ // 2), "S", font=F_TITLE,
            fill=tint("shell"), anchor="mm")
    wrap(dr, "SHELL — wild. Stands in for any of the three.", F_SM,
         sx - 30, sy + CH_ + 8, CW_ + 30, DIM, 20)
y = sp_bot + 34

dr.line([80, y, W - 80, y], fill=RULE, width=2); y += 24
dr.text((80, y), "It is also a deck of playing cards", font=F_SUB, fill=GOLD); y += 38
y = wrap(dr,
         f"The realms are the suits and the numbers are the ranks — {rank_phrase(RANKS)}. "
         f"{words(N_RANKS).capitalize()} ranks across {words(N_REALMS)} realms is {N_CARDS} cards, "
         "and any game that wants suits will take it. The index at the back prints the whole mapping.",
         F_BODY, 80, y, W - 160, INK, 30)
if y > H - 90:
    overflow.append(("intro", y))
add(intro)


# ------------------------------------------------------------ card block ----
AX, AW = 80, 300            # art box
AH = int(AW * 1.5)
TX = AX + AW + 40           # text column
TW = W - TX - 80
CAP_H = 46                  # plate caption under the art
TOP, BOT = 96, 96


def block_height(c):
    h = 42 + 16
    ess = lore.get(c["id"], {}).get("essence")
    if ess: h += measure(_probe, ess, F_ESS, TW, 28) + 14
    h += measure(_probe, c["reading"], F_BODY, TW, 27) + 14
    if c.get("shadow"):
        h += 24 + measure(_probe, c["shadow"], F_SM, TW, 22) + 12
    h += 24 + measure(_probe, c["turtle_dare"], F_SM, TW, 22)
    anchor = c["real_2026"]["name"]
    cap = 0 if anchor.strip().lower() == c["name"].strip().lower() \
        else min(2, len(wrap_lines(_probe, anchor, F_SM, AW)))
    return max(h, AH + CAP_H + 20 * cap)


_thumbs = {}


def thumb(c):
    if c["id"] not in _thumbs:
        im = Image.open(art_src(c["id"])).convert("RGB")
        try:
            im = set_title(im, c["name"])
        except Exception:
            pass
        _thumbs[c["id"]] = im.resize((AW, AH), Image.LANCZOS)
    return _thumbs[c["id"]]


def card_block(dr, c, x, y):
    t = tint(c["realm"])
    try:
        dr._image.paste(thumb(c), (x, y))
        dr.rectangle([x - 1, y - 1, x + AW, y + AH], outline=(150, 130, 96), width=1)
    except Exception:
        dr.rectangle([x, y, x + AW, y + AH], outline=t, width=2)
    # plate caption: the playing-card coordinate, then the real playa anchor
    cy = y + AH + 14
    rl = rank_label(c["number"])
    coord = f"{c['realm'].upper()} · {c['number']}"
    if rl != str(c["number"]):
        coord += f" · {rl}"
    dr.text((x + AW // 2, cy), coord, font=F_LBL, fill=t, anchor="ma"); cy += 24
    anchor = c["real_2026"]["name"]
    if anchor.strip().lower() != c["name"].strip().lower():   # don't say the name twice
        for line in wrap_lines(dr, anchor, F_SM, AW)[:2]:
            dr.text((x + AW // 2, cy), line, font=F_SM, fill=DIM, anchor="ma"); cy += 20

    tx, yy = TX, y - 4
    dr.text((tx, yy), c["name"], font=F_NAME, fill=GOLD); yy += 42
    dr.line([tx, yy, tx + TW, yy], fill=GOLD, width=1); yy += 16
    ess = lore.get(c["id"], {}).get("essence")
    if ess:
        yy = wrap(dr, ess, F_ESS, tx, yy, TW, t, 28) + 14
    yy = wrap(dr, c["reading"], F_BODY, tx, yy, TW, INK, 27) + 14
    if c.get("shadow"):
        dr.text((tx, yy), "SHADOW", font=F_LBL, fill=DIM); yy += 24
        yy = wrap(dr, c["shadow"], F_SM, tx, yy, TW, DIM, 22) + 12
    dr.text((tx, yy), "TURTLE DARE", font=F_LBL, fill=t); yy += 24
    return max(wrap(dr, c["turtle_dare"], F_SM, tx, yy, TW, INK, 22), cy)


def card_page(pair):
    """Two cards (or one) justified down the page, slack shared top/middle/bottom."""
    pg, dr = new_page()
    avail = H - TOP - BOT
    hs = [block_height(c) for c in pair]
    if len(pair) == 1:
        y1 = TOP + int((avail - hs[0]) * 0.35)
        end = card_block(dr, pair[0], AX, y1)
    else:
        slack = avail - hs[0] - hs[1]
        if slack < 0:
            overflow.append((pair[0]["id"] + "+" + pair[1]["id"], slack))
            slack = 0
        gap = max(56, min(280, int(slack * 0.5)))
        y1 = TOP + int((slack - gap) * 0.5)
        y2 = y1 + hs[0] + gap
        ry = y1 + hs[0] + gap // 2
        dr.line([120, ry, W - 120, ry], fill=RULE, width=2)
        dr.ellipse([W // 2 - 4, ry - 4, W // 2 + 4, ry + 4], fill=GOLD)
        card_block(dr, pair[0], AX, y1)
        end = card_block(dr, pair[1], AX, y2)
    if end > H - 62:
        overflow.append((pair[-1]["id"], end))
    return pg


# ------------------------------------------------- realm sections ----------
for realm in REALMS:
    rc = by_realm[realm]
    t = tint(realm)

    dv, dd = new_page()
    # the band grows to whatever the realm's own description needs
    body = wrap_lines(_probe, DECK["realms"][realm], F_BODY, W - 260)
    inner = 62 + 26 + len(body) * 30                 # display line, rule, description
    band_h = max(320, inner + 150)
    band_t, band_b = H // 2 - band_h // 2, H // 2 + band_h // 2
    dd.rectangle([0, band_t, W, band_b], fill=t)
    dd.line([70, band_t + 24, W - 70, band_t + 24], fill=CREAM, width=1)
    dd.line([70, band_b - 24, W - 70, band_b - 24], fill=CREAM, width=1)

    cy = H // 2 - inner // 2
    dd.text((W // 2, cy + 22), realm.upper(), font=F_TITLE, fill=CREAM, anchor="mm")
    cy += 62
    dd.line([W // 2 - 90, cy, W // 2 + 90, cy], fill=(216, 206, 188), width=1); cy += 26
    for line in body:
        dd.text((W // 2, cy), line, font=F_BODY, fill=(240, 235, 224), anchor="ma"); cy += 30
    if cy > band_b - 30:
        overflow.append(("divider-" + realm, cy))

    dd.text((W // 2, band_b + 56),
            f"{words(len(rc))} cards · {REALM_SUIT.get(realm, 'a suit')}",
            font=F_SM, fill=DIM, anchor="mm")
    dd.text((W // 2, band_t - 56), f"ranks {rank_label(rc[0]['number'])} – "
            f"{rank_label(rc[-1]['number'])}", font=F_SM, fill=DIM, anchor="mm")
    add(dv, "plate")

    for i in range(0, len(rc), 2):
        add(card_page(rc[i:i + 2]))


# ---------------------------------------------------------------- index ----
idx, dr = new_page()
y = 96
dr.text((80, y), "The Deck as a Deck", font=F_NAME, fill=GOLD); y += 46
dr.line([80, y, W - 80, y], fill=GOLD, width=2); y += 28
y = wrap(dr, f"{words(N_REALMS).capitalize()} suits of {words(len(by_realm[REALMS[0]]))}. "
             "Realm and number are printed on every card; this is the whole mapping in one place.",
         F_BODY, 80, y, W - 160, INK, 28) + 34

M, GUT, GUTW = 60, 18, 46
NCOL = len(REALMS)
CW2 = (W - 2 * M - (NCOL - 1) * GUT) // NCOL
HEAD_H, LH_I = 30, 21
FOOT = H - 150

# pre-pass: the tallest column decides the row rhythm, and the rows are then
# spread to fill the page rather than bunching under the heading.
name_lines = {r: [wrap_lines(_probe, c["name"], F_IDX, CW2 - GUTW - 6)
                  for c in by_realm[r]] for r in REALMS}
n_rows = max(len(by_realm[r]) for r in REALMS)
# every rank is one row across all four columns, so the rules line up
row_lines = [max(len(name_lines[r][i]) for r in REALMS if i < len(name_lines[r]))
             for i in range(n_rows)]
text_h = sum(row_lines) * LH_I
avail = FOOT - y - (HEAD_H + 18)
pad = max(12, min(44, (avail - text_h) // max(n_rows, 1)))
row_top = []
acc = HEAD_H + 18
for n in row_lines:
    row_top.append(acc); acc += n * LH_I + pad
table_h = acc
top = y + max(0, (FOOT - y - table_h) // 3)   # a shade above centre, under the lede

for ci, realm in enumerate(REALMS):
    cx = M + ci * (CW2 + GUT)
    t = tint(realm)
    dr.rectangle([cx, top, cx + CW2, top + HEAD_H], fill=t)
    dr.text((cx + CW2 // 2, top + HEAD_H // 2), realm.upper(), font=F_IDXH,
            fill=CREAM, anchor="mm")
    for i, (c, lines) in enumerate(zip(by_realm[realm], name_lines[realm])):
        yy = top + row_top[i]
        rl = rank_label(c["number"])
        gut = str(c["number"]) if rl == str(c["number"]) else f"{c['number']} {rl}"
        dr.text((cx + GUTW - 12, yy + 2), gut, font=F_TINY, fill=t, anchor="ra")
        for ln in lines:
            dr.text((cx + GUTW, yy), ln, font=F_IDX, fill=INK, anchor="la"); yy += LH_I
        base = top + row_top[i] + row_lines[i] * LH_I + pad // 2
        dr.line([cx + 6, base, cx + CW2 - 6, base], fill=(216, 203, 174), width=1)
if top + table_h > FOOT:
    overflow.append(("index", top + table_h))
dr.line([80, H - 132, W - 80, H - 132], fill=RULE, width=2)
missing = [COURT[n] for n in sorted(COURT) if n not in RANKS]
note = ("The Shell is the wild suit — deal it as trumps, or set it aside and play "
        f"with {N_CARDS - len(by_realm.get('shell', []))}.")
if missing:
    note += " (No " + "/".join(missing) + " yet — the deck is still growing a rank.)"
wrap(dr, note, F_SM, 80, H - 116, W - 160, DIM, 22)
add(idx)

# ------------------------------------------------------------- colophon ----
col, dr = new_page(DARK)
dr.rectangle([38, 38, W - 39, H - 39], outline=BRONZE, width=2)
cy = 700
dr.text((W // 2, cy), DECK["title"].upper(), font=F_SUB, fill=GOLD, anchor="mm"); cy += 46
dr.line([W // 2 - 150, cy, W // 2 + 150, cy], fill=BRONZE, width=1); cy += 40
for line in [
    f"{words(N_CARDS).capitalize()} cards in {words(N_REALMS)} realms.",
    "Written, drawn and set for Black Rock City,",
    f"the year {DECK['year']}.",
    "",
    "Terrible Turtle Camp · E & 6:15",
    "",
    "Move Slow & Bite Things",
]:
    if line:
        dr.text((W // 2, cy), line, font=F_SM, fill=PALE, anchor="mm")
    cy += 30
add(col, "plate")

# pad to a multiple of 4 for saddle-stitch imposition
while len(pages) % 4:
    blank, bd = new_page()
    bd.text((W // 2, H // 2), "·", font=F_NAME, fill=RULE, anchor="mm")
    add(blank, "plate")

# folios
for n, (pg, kind) in enumerate(pages, start=1):
    if kind == "plate" or n == 1:
        continue
    ImageDraw.Draw(pg).text((W // 2, H - 52), str(n), font=F_TINY, fill=DIM, anchor="mm")

imgs = [p for p, _ in pages]
os.makedirs(f"{REPO}/print", exist_ok=True)
imgs[0].save(f"{REPO}/print/booklet.pdf", save_all=True, append_images=imgs[1:], resolution=200.0)
print(f"booklet.pdf — {len(imgs)} pages ({len(imgs) // 4} signatures of 4), "
      f"{N_CARDS} cards / {N_REALMS} realms / {N_RANKS} ranks")
print("OVERFLOW: " + repr(overflow) if overflow else "fit check: clean")

if "--png" in sys.argv:
    outdir = sys.argv[sys.argv.index("--png") + 1]
    os.makedirs(outdir, exist_ok=True)
    for n, im in enumerate(imgs, start=1):
        im.save(f"{outdir}/{n:02d}.png")
    print(f"pages -> {outdir}")
