from PIL import Image, ImageDraw
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bookkit as K
from bookkit import (REPO, DECK, cards, by_realm, REALMS, lore,
                     REALM_INTRO, REALM_SUIT, PLAY_RANKS, FULL_SUITS, RANKS,
                     N_CARDS, N_REALMS, N_RANKS, COURT,
                     KRAFT, INK, GOLD, DIM, DARK, PALE, RULE, CREAM, BRONZE,
                     tint, realm_head, rank_label, rank_phrase, words,
                     keyword_line, art_src, wrap, wrap_lines, measure, draw_w,
                     font, G, GB, GI)
from cardtitle import set_title

W, H = 1100, 1700           # ~5.5x8.5in @ 200dpi

# This book's own type scale — 200dpi on a 5.5in page. The MPC booklet sits at
# 300dpi on a 3.5in page and picks its own, which is why sizes don't live in
# bookkit.
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
F_KEY = font(G, 15)         # the keyword string under a card name


def new_page(bg=KRAFT):
    return K.new_page(W, H, bg)


pages = []          # (image, kind) — kind suppresses the folio on plates
overflow = []
drawn = []          # every card_block call, so the build can prove coverage
_probe = K.probe


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
    kw = keyword_line(c)
    if kw: h += measure(_probe, kw, F_KEY, TW, 21) + 12
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
    drawn.append(c["id"])
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
    kw = keyword_line(c)
    if kw:
        yy = wrap(dr, kw, F_KEY, tx, yy, TW, DIM, 21) + 12
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
        # a lone card is the realm's King — give it the page, a shade above centre
        y1 = TOP + int((avail - hs[0]) * 0.42)
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


# -------------------------------------------------- realm intro page ------
def realm_intro(realm, rc, t):
    """Banded display head, then the realm's own prose, then how it reads."""
    pg, dr = new_page()
    M = 92

    # --- the band: realm name over the deck's own one-clause description ---
    clause = DECK["realms"][realm].split("Position:")[0].strip().rstrip(".")
    band_lines = wrap_lines(_probe, clause, F_BODY, W - 2 * M - 80)
    band_h = 62 + 26 + len(band_lines) * 30 + 108

    # Measure the whole stack first, then take up whatever slack is left as extra
    # air between the band and the prose — a short realm shouldn't strand the
    # bottom third of the page, and a long one shouldn't crowd the foot.
    info = REALM_INTRO.get(realm, {})
    reads_lines = wrap_lines(_probe, info["reads"], F_SM, W - 2 * M - 76) \
        if info.get("reads") else []
    box_h = (30 + 22 + len(reads_lines) * 22 + 26) if reads_lines else 0

    # the realm's own contents list, two columns, closes the page
    LCOL = (W - 2 * M) // 2
    lrows = (len(rc) + 1) // 2
    list_h = 34 + lrows * 30

    below = 92
    if info.get("domain"):
        below += 46
    for para in info.get("body", []):
        below += measure(_probe, para, F_BODY, W - 2 * M, 30) + 22
    if box_h:
        below += 14 + box_h
    below += 46 + list_h

    band_t = 150
    slack = H - 96 - (band_t + band_h + below)
    air = max(0, min(70, slack // 3))                 # a little, not a chasm
    band_t += max(0, min(60, slack - air * 2))        # push the band down a touch
    band_b = band_t + band_h
    dr.rectangle([0, band_t, W, band_b], fill=t)
    dr.line([70, band_t + 24, W - 70, band_t + 24], fill=CREAM, width=1)
    dr.line([70, band_b - 24, W - 70, band_b - 24], fill=CREAM, width=1)

    cy = band_t + 54
    dr.text((W // 2, cy), realm.upper(), font=F_TITLE, fill=CREAM, anchor="mm"); cy += 46
    dr.line([W // 2 - 90, cy, W // 2 + 90, cy], fill=(216, 206, 188), width=1); cy += 26
    for line in band_lines:
        dr.text((W // 2, cy), line, font=F_BODY, fill=(240, 235, 224), anchor="ma"); cy += 30
    if cy > band_b - 24:
        overflow.append(("intro-band-" + realm, cy))

    # the playing-deck coordinates ride outside the band
    dr.text((W // 2, band_t - 46), f"ranks {rank_label(rc[0]['number'])} – "
            f"{rank_label(rc[-1]['number'])}", font=F_SM, fill=DIM, anchor="mm")
    dr.text((W // 2, band_b + 44),
            f"{words(len(rc))} cards · {REALM_SUIT.get(realm, 'a suit')}",
            font=F_SM, fill=DIM, anchor="mm")

    y = band_b + 92 + air
    if info.get("domain"):
        dr.text((W // 2, y), info["domain"].upper(), font=F_LBL, fill=t, anchor="mm")
        y += 46
    for para in info.get("body", []):
        y = wrap(dr, para, F_BODY, M, y, W - 2 * M, INK, 30) + 22

    # --- how it reads: a tinted keyline box, not another paragraph ---
    if reads_lines:
        by = min(y + 14, H - 120 - box_h)
        dr.rectangle([M, by, W - M, by + box_h], outline=t, width=2)
        dr.text((M + 26, by + 22), "IN A READING", font=F_LBL, fill=t)
        yy = by + 22 + 30
        for line in reads_lines:
            dr.text((M + 26, yy), line, font=F_SM, fill=INK, anchor="la"); yy += 22
        y = by + box_h

    # --- the realm's thirteen, so the page doubles as its contents ---
    y += 46 + air
    dr.text((M, y), f"THE {words(len(rc)).upper()}", font=F_LBL, fill=t)
    dr.line([M + draw_w(dr, f"THE {words(len(rc)).upper()}", F_LBL) + 16, y + 9,
             W - M, y + 9], fill=RULE, width=1)
    y += 34
    for i, c in enumerate(rc):
        col, row = divmod(i, lrows)
        x = M + col * LCOL
        yy = y + row * 30
        dr.text((x + 30, yy), rank_label(c["number"]), font=F_LBL, fill=t, anchor="ra")
        nm = c["name"]
        while draw_w(dr, nm, F_IDX) > LCOL - 54 and len(nm) > 4:
            nm = nm[:-2] + "…"
        dr.text((x + 44, yy + 1), nm, font=F_IDX, fill=INK)
    y += lrows * 30

    if y > H - 96:
        overflow.append(("intro-" + realm, y))
    return pg


# ------------------------------------------------- realm sections ----------
for realm in REALMS:
    rc = by_realm[realm]
    t = tint(realm)

    add(realm_intro(realm, rc, t), "plate")

    for i in range(0, len(rc), 2):
        add(card_page(rc[i:i + 2]))


# -------------------------------------------------------- how to deal it ---
# Anything outside the 1..13 grid comes out of the pack before a game: the nine
# utility cards (title, the two reference cards, the four realm cards, two blanks)
# and the two jokers, all of them from data/extras.json. The copy counts them
# rather than hard-coding a 52, so a deck that drops one still reads true.
utility, full_suits, playing = K.utility, FULL_SUITS, cards

deal, dr = new_page()
y = 96
dr.text((80, y), "How to Deal It", font=F_NAME, fill=GOLD); y += 46
dr.line([80, y, W - 80, y], fill=GOLD, width=2); y += 30
y = wrap(dr, "This is an oracle that deals as a real pack of cards. The realm glyph "
             "on every card is its suit, and the gold medallion is its rank — so any "
             "game that wants four suits and thirteen ranks will take it, and the art "
             "keeps talking while you play.",
         F_BODY, 80, y, W - 160, INK, 30) + 30

# --- the suits ---
dr.text((80, y), "THE SUITS", font=F_LBL, fill=GOLD); y += 34
sw = (W - 160) // max(len(REALMS), 1)
for i, r in enumerate(REALMS):
    t = tint(r)
    x = 80 + i * sw
    dr.rectangle([x, y, x + sw - 18, y + 54], fill=t)
    dr.text((x + (sw - 18) // 2, y + 27), realm_head(r), font=F_LBL, fill=CREAM, anchor="mm")
    dr.text((x + (sw - 18) // 2, y + 74), REALM_SUIT.get(r, "a suit"),
            font=F_SM, fill=DIM, anchor="ma")
y += 116

# --- the ranks, drawn as a strip of little cards ---
dr.text((80, y), "THE RANKS", font=F_LBL, fill=GOLD); y += 34
rw, rh, rgap = 62, 84, 10
n_r = len(PLAY_RANKS)
strip_w = n_r * rw + (n_r - 1) * rgap
rx = (W - strip_w) // 2
for i, n in enumerate(PLAY_RANKS):
    x = rx + i * (rw + rgap)
    have = n in RANKS
    fill = (222, 208, 176) if have else KRAFT
    dr.rectangle([x, y, x + rw, y + rh], fill=fill,
                 outline=GOLD if have else RULE, width=2)
    dr.text((x + rw // 2, y + rh // 2), rank_label(n), font=F_SUB,
            fill=GOLD if have else RULE, anchor="mm")
y += rh + 22
dr.text((W // 2, y), f"{words(len(full_suits))} full suits of {words(len(PLAY_RANKS))}"
        f" — {len(full_suits) * len(PLAY_RANKS)} cards", font=F_SM, fill=DIM, anchor="mm")
y += 52

# --- what to take out ---
dr.line([80, y, W - 80, y], fill=RULE, width=2); y += 26
dr.text((80, y), "BEFORE A GAME", font=F_LBL, fill=GOLD); y += 32
if utility or K.jokers:
    bits = []
    if utility:
        bits.append(f"the {words(len(utility))} utility "
                    f"card{'s' if len(utility) != 1 else ''} ("
                    + ", ".join(c["name"] for c in utility[:4])
                    + (", and the rest)" if len(utility) > 4 else ")"))
    if K.jokers:
        bits.append(f"the {words(len(K.jokers))} jokers, unless the game wants them")
    lead = ("Deal out " + " and ".join(bits)
            + f", and you are holding a standard {len(full_suits) * len(PLAY_RANKS)}. "
              "They carry no rank medallion, which is how you spot them: no medallion, "
              "not in the game.")
else:
    lead = (f"Nothing to remove. The pack is exactly {len(playing)} — "
            f"{words(len(full_suits))} suits of {words(len(PLAY_RANKS))}, no jokers, no "
            "spares. Every card in the box has a rank medallion and a place in the game.")
y = wrap(dr, lead, F_SM, 80, y, W - 160, INK, 24) + 18
y = wrap(dr, "The Shell is the odd suit out at the table the way it is odd in a reading. "
             "Call it trumps, call it the bower suit, or set it aside and play three-suit "
             "games with " + str((len(full_suits) - 1) * len(PLAY_RANKS)) + ".",
         F_SM, 80, y, W - 160, DIM, 24) + 30

dr.line([80, y, W - 80, y], fill=RULE, width=2); y += 26
dr.text((80, y), "AT THE TABLE", font=F_LBL, fill=GOLD); y += 34
for game, how in [
    ("Poker, hearts, rummy, war",
     "Play it straight. Shell reads as the fourth suit and nothing changes."),
    ("Trick-taking (spades, euchre)",
     "Shell is permanent trumps — the axis outranks the world, as it should."),
    ("Cribbage",
     "A is one, J Q K are ten. The medallions are already numbered for you."),
    ("Solitaire in a dust storm",
     "The best use of this deck. Nobody wins. That is not the point of it."),
]:
    dr.text((80, y), game, font=F_LBL, fill=INK)
    yy = wrap(dr, how, F_SM, 80, y + 24, W - 160, DIM, 22)
    y = yy + 16

y += 10
dr.line([80, y, W - 80, y], fill=RULE, width=2); y += 24
y = wrap(dr, "And when a hand goes strange — when someone takes a trick they had no "
             "business taking, or the same card keeps coming back to you — stop the game "
             "and read it. The deck does not stop being an oracle because you dealt it "
             "for money.",
         F_ESS, 80, y, W - 160, GOLD, 28)
if y > H - 96:
    overflow.append(("deal", y))
add(deal)


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

# Pad to a multiple of 4 for saddle-stitch imposition. The signature has to fold,
# so these pages exist regardless — make them ruled "your own pulls" pages rather
# than dead leaves, and put them before the colophon so the book still ends well.
tail = pages.pop() if pages and pages[-1][1] == "plate" else None
while (len(pages) + (1 if tail else 0)) % 4:
    nb, bd = new_page()
    bd.text((80, 96), "Your Own Pulls", font=F_NAME, fill=GOLD)
    bd.line([80, 142, W - 80, 142], fill=GOLD, width=2)
    bd.text((80, 162), "DATE · ROOT · TRUNK · BRANCH · WHAT YOU DID ABOUT IT",
            font=F_LBL, fill=DIM)
    ly = 226
    while ly < H - 120:
        bd.line([80, ly, W - 80, ly], fill=RULE, width=1); ly += 46
    add(nb)
if tail:
    pages.append(tail)

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

# coverage: every card typeset once and only once, and the fold is a fold
missed = [c["id"] for c in cards if c["id"] not in drawn]
twice = sorted({i for i in drawn if drawn.count(i) > 1})
print(f"coverage: {len(drawn)}/{N_CARDS} blocks"
      + (f" — MISSING {missed}" if missed else "")
      + (f" — DUPLICATED {twice}" if twice else "")
      + ("" if missed or twice else " — every card exactly once"))
print("signature: " + ("ok" if len(imgs) % 4 == 0 else f"NOT a multiple of 4 ({len(imgs)})"))
if missed or twice or overflow or len(imgs) % 4:
    sys.exit(1)

if "--png" in sys.argv:
    outdir = sys.argv[sys.argv.index("--png") + 1]
    os.makedirs(outdir, exist_ok=True)
    for n, im in enumerate(imgs, start=1):
        im.save(f"{outdir}/{n:02d}.png")
    print(f"pages -> {outdir}")
