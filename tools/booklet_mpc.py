"""MakePlayingCards in-order booklet -> print/mpc-booklet/.

MPC sells a booklet printed into the deck order and packed with every deck. On
the 3.5x5 jumbo game-card product the perfect-bound option runs 52/72/96/...
"sides"; we target 72. One side per card, so the booklet is the deck's index.

    python3 tools/booklet_mpc.py               # 72 sides + the cover spread
    python3 tools/booklet_mpc.py --sides 96    # the fallback page count
    python3 tools/booklet_mpc.py --pdf         # ...and a proof PDF to flip through

Output — the numeric prefix leads so a filename sort IS the page order, which is
how MPC's uploader wants them dragged in:

    print/mpc-booklet/sides/01-cover.png ... 72-back.png    (1125x1575 each)
    print/mpc-booklet/cover/cover-spread.png                (2238x1575)

TEMPLATE SPEC — measured off MPC's own templates (recovered from the Wayback
Machine; the live /dl/booklet-template/ links 404 as of Aug 2026) and
cross-checked against https://www.makeplayingcards.com/pops/booklet-guide.html:

    inside page   upload 3.75 x 5.25 in = 1125 x 1575 px @ 300dpi
                  trim   3.5  x 5    in = 1050 x 1500
                  safe                    897 x 1428
    cover (72pp)  upload 7.46 x 5.25 in = 2238 x 1575 px
                  trim   7.2  x 5    in = 2160 x 1500, spine 0.2088 in

MPC's spec has the safe area NOT centred: ~117px inset on the binding edge,
~37.5px on the outer edge, mirrored recto/verso. That asymmetry depends on
knowing which physical side (left/right) each uploaded file lands on — and
that turned out to be exactly the thing to get wrong: v1 assumed odd sides
are recto (gutter left), but MPC's own designer preview showed the actual
upload pairing odd-on-left / even-on-right, the opposite parity, so the wide
margin sat on the wrong edge of every page and body text ran close to the
true spine on nearly every side (caught from a screenshot of MPC's preview,
2026-08-18). Rather than re-guess the parity, every side now gets the wider
117px inset on BOTH edges — safe regardless of which side is recto, at the
cost of a narrower text measure.

Upload format is one raster per side (PNG/JPEG/TIFF; MPC does NOT take a PDF for
booklets), RGB, 300 dpi. The --pdf proof is for us, never for them.

CAVEAT, flagged rather than smoothed over: MPC does not publish whether the "72
sides" count includes the cover faces. The defensible reading — their spec table
lists "Cover page FOR 72 pages" as a separate artwork item at its own size, and
ships no inside-front/inside-back template — is that 72 means 72 interior faces
and the cover is extra. This tool emits both, so either reading is covered:
72 numbered interior sides, plus the cover spread as its own file.
"""
from PIL import Image
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bookkit as K
from bookkit import (REPO, DECK, cards, by_realm, REALMS, lore, jokers,
                     REALM_INTRO, REALM_SUIT, PLAY_RANKS, FULL_SUITS, RANKS,
                     KRAFT, INK, GOLD, DIM, DARK, PALE, RULE, CREAM, BRONZE,
                     tint, realm_head, rank_label, words, keyword_line, art_src,
                     JOKER_SCENE, JOKER_TINT, second_ink, joker_art, joker_pack_line,
                     wrap, wrap_lines, measure, draw_w, fit, probe, font, G, GB, GI)
from cardtitle import set_title

# --------------------------------------------------------------- geometry ---
DPI = 300
W, H = 1125, 1575               # full-bleed upload canvas
BLEED = 38                      # 0.125in -> trim box starts here
TRIM_L, TRIM_T = BLEED, BLEED
TRIM_R, TRIM_B = W - BLEED, H - BLEED
GUTTER = 117                    # safe inset on the binding edge, from trim
VPAD = 36                       # safe inset top and bottom, from trim

# Applied to BOTH left and right — see the geometry note above: we don't
# actually know which parity MPC treats as recto, so both edges get the
# wider binding-edge inset rather than gambling on which side is the spine.
CW = (TRIM_R - TRIM_L) - 2 * GUTTER         # 816 — the safe measure
CY = TRIM_T + VPAD                          # 74
CH = (TRIM_B - TRIM_T) - 2 * VPAD           # 1427


def box(side):
    """Safe content box for a 1-based side. Symmetric — see geometry note above."""
    return TRIM_L + GUTTER, CY, CW, CH


# ------------------------------------------------------------ typography ----
# 300dpi on a 3.5in page: the safe measure is 894px = 2.98in, so body sits at
# ~8pt. Sizes are px; divide by 300 and multiply by 72 for points.
F_DISP = font(GB, 82)       # cover display
F_TITLE = font(GB, 60)      # realm display
F_NAME = font(GB, 46)       # card name
F_SUB = font(GB, 36)        # section heads
F_BODY = font(G, 33)        # the Reading, prose
F_ESS = font(GI, 33)        # the essence line
F_SM = font(G, 28)          # shadow, dare, captions
F_LBL = font(GB, 25)        # SHADOW / TURTLE DARE labels
F_KEY = font(G, 25)         # keyword string
F_TINY = font(G, 22)        # folio

LH_BODY, LH_SM = 44, 37

sides = []                  # (image, kind)
overflow = []
drawn = []


def add(im, kind="body"):
    sides.append((im, kind))


def page(bg=KRAFT):
    return K.new_page(W, H, bg)


# ------------------------------------------------------------- card side ----
_thumbs = {}


def thumb(c, w, h):
    key = (c["id"], w, h)
    if key not in _thumbs:
        im = Image.open(art_src(c["id"])).convert("RGB")
        try:
            im = set_title(im, c["name"])
        except Exception:
            pass
        _thumbs[key] = im.resize((w, h), Image.LANCZOS)
    return _thumbs[key]


ART_MIN, ART_MAX = 360, 540         # art width; height is 1.5x


def card_side(c, n):
    """One card to a side: art sized to whatever the text leaves it."""
    pg, dr = page()
    x0, y0, w, h = box(n)
    t = tint(c["realm"])
    drawn.append(c["id"])

    # --- measure the text first, then give the art the slack ---
    ess = (lore.get(c["id"]) or {}).get("essence")
    kw = keyword_line(c)
    th = 0
    th += 56                                                   # name
    if kw: th += measure(probe, kw, F_KEY, w, 32) + 10
    th += 14                                                   # rule
    if ess: th += measure(probe, ess, F_ESS, w, 42) + 14
    th += measure(probe, c["reading"], F_BODY, w, LH_BODY) + 16
    if c.get("shadow"):
        th += 34 + measure(probe, c["shadow"], F_SM, w, LH_SM) + 14
    th += 34 + measure(probe, c["turtle_dare"], F_SM, w, LH_SM)
    th += 46                                                   # coordinate strip

    aw = max(ART_MIN, min(ART_MAX, int((h - th - 60) / 1.5)))
    ah = int(aw * 1.5)
    if th + ah + 60 > h:
        overflow.append((c["id"], th + ah + 60 - h))

    y = y0
    # coordinate strip — the playing-card position, top of the side
    rl = rank_label(c["number"])
    coord = f"{c['realm'].upper()} · {c['number']}" + (f" · {rl}" if rl != str(c["number"]) else "")
    dr.text((x0 + w // 2, y), coord, font=F_LBL, fill=t, anchor="ma")
    y += 46

    # --- art, centred in the measure ---
    ax = x0 + (w - aw) // 2
    try:
        pg.paste(thumb(c, aw, ah), (ax, y))
        dr.rectangle([ax - 1, y - 1, ax + aw, y + ah], outline=(150, 130, 96), width=1)
    except Exception:
        dr.rectangle([ax, y, ax + aw, y + ah], outline=t, width=2)
    y += ah + 34

    # --- the words ---
    nm = c["name"]
    fnt = F_NAME
    if draw_w(probe, nm, fnt) > w:
        fnt = font(GB, 38)
    dr.text((x0 + w // 2, y), fit(nm, fnt, w), font=fnt, fill=GOLD, anchor="ma")
    y += 56
    if kw:
        y = wrap(dr, kw, F_KEY, x0, y, w, DIM, 32) + 10
    dr.line([x0, y, x0 + w, y], fill=GOLD, width=1); y += 14
    if ess:
        y = wrap(dr, ess, F_ESS, x0, y, w, t, 42) + 14
    y = wrap(dr, c["reading"], F_BODY, x0, y, w, INK, LH_BODY) + 16
    if c.get("shadow"):
        dr.text((x0, y), "SHADOW", font=F_LBL, fill=DIM); y += 34
        y = wrap(dr, c["shadow"], F_SM, x0, y, w, DIM, LH_SM) + 14
    dr.text((x0, y), "TURTLE DARE", font=F_LBL, fill=t); y += 34
    y = wrap(dr, c["turtle_dare"], F_SM, x0, y, w, INK, LH_SM)

    if y > y0 + h:
        overflow.append((c["id"] + "-tail", y - (y0 + h)))
    return pg


# ------------------------------------------------------------ front matter --
def cover_side(n):
    pg, dr = page(DARK)
    x0, y0, w, h = box(n)
    dr.rectangle([TRIM_L + 14, TRIM_T + 14, TRIM_R - 15, TRIM_B - 15], outline=GOLD, width=3)
    cx = x0 + w // 2
    dr.text((cx, y0 + 150), "THE TERRIBLE", font=F_DISP, fill=GOLD, anchor="mm")
    dr.text((cx, y0 + 242), "TURTLE", font=F_DISP, fill=GOLD, anchor="mm")
    dr.text((cx, y0 + 334), "ORACLE", font=F_DISP, fill=GOLD, anchor="mm")
    dr.line([cx - 200, y0 + 400, cx + 200, y0 + 400], fill=BRONZE, width=2)
    try:
        back = Image.open(f"{REPO}/cards/back.png").convert("RGB")
        # The panel is fitted by WIDTH but bounded by HEIGHT: the subtitle line at
        # y0 + h - 130 is set in PALE, and PALE on the kraft of the card back is
        # invisible — the art must stop above it, not run under it.
        bw = min(w, 560); bh = int(bw * back.size[1] / back.size[0])
        if bh > h - 660:
            bh = h - 660; bw = int(bh * back.size[0] / back.size[1])
        bx, by = cx - bw // 2, y0 + 470
        dr.rectangle([bx - 6, by - 6, bx + bw + 5, by + bh + 5], fill=BRONZE)
        pg.paste(back.resize((bw, bh)), (bx, by))
    except Exception:
        pass
    dr.text((cx, y0 + h - 130), DECK["subtitle"], font=F_SM, fill=PALE, anchor="mm")
    dr.text((cx, y0 + h - 78), f"A COMPANION BOOKLET · {words(len(cards)).upper()} CARDS",
            font=F_LBL, fill=(120, 100, 62), anchor="mm")
    return pg


def title_side(n):
    pg, dr = page()
    x0, y0, w, h = box(n)
    cx, cy = x0 + w // 2, y0 + h // 2
    dr.text((cx, cy - 250), DECK["title"].upper(), font=F_SUB, fill=GOLD, anchor="mm")
    dr.line([cx - 170, cy - 200, cx + 170, cy - 200], fill=RULE, width=2)
    y = cy - 150
    for line in [DECK["theme"], "", f"{words(len(cards)).capitalize()} cards in "
                 f"{words(len(REALMS))} realms.", "Written, drawn and set for",
                 f"Black Rock City, the year {DECK['year']}.", "",
                 "Terrible Turtle Camp · E & 6:15", "", "Move Slow & Bite Things"]:
        if line:
            for ln in wrap_lines(probe, line, F_SM, w):
                dr.text((cx, y), ln, font=F_SM, fill=INK if line else DIM, anchor="ma")
                y += 40
        else:
            y += 26
    return pg


def read_side(n):
    pg, dr = page()
    x0, y0, w, h = box(n)
    y = y0
    dr.text((x0, y), "How to Read the Tree", font=F_SUB, fill=GOLD); y += 52
    dr.line([x0, y, x0 + w, y], fill=GOLD, width=2); y += 28
    for para in [
        f"The World Turtle carries the World Tree. This deck is that tree: "
        f"{words(len(cards))} cards in {words(len(REALMS))} realms, each one a piece of "
        "ordinary, uncomfortable, kindly-meant truth with a dare attached.",
        "Draw one from the ROOTS, one from the TRUNK, one from the BRANCHES — what to "
        "face, where you stand, what to reach for — and read them as a single arc, not "
        "three separate fortunes.",
        "A SHELL card is the axis itself. When it turns up the whole reading swings "
        "around it, and it may stand in any position.",
        "Every card carries a Reading (the truth), a Shadow (the same truth gone sour), "
        "and a Turtle Dare — one concrete adventure to actually carry out. The dares are "
        "the point. A reading you don't walk out of is just a nice sentence.",
    ]:
        y = wrap(dr, para, F_BODY, x0, y, w, INK, LH_BODY) + 22

    y += 12
    dr.text((x0, y), "THE FOUR REALMS" if len(REALMS) == 4 else "THE REALMS",
            font=F_LBL, fill=GOLD); y += 40
    for r in REALMS:
        t = tint(r)
        dr.rectangle([x0, y + 4, x0 + 12, y + 34], fill=t)
        dr.text((x0 + 28, y), realm_head(r), font=F_LBL, fill=t); y += 34
        y = wrap(dr, DECK["realms"][r].split("Position:")[0].strip(), F_SM,
                 x0 + 28, y, w - 28, INK, LH_SM) + 16
    if y > y0 + h:
        overflow.append(("read-side", y - (y0 + h)))
    return pg


def deal_side(n):
    pg, dr = page()
    x0, y0, w, h = box(n)
    y = y0
    dr.text((x0, y), "How to Deal It", font=F_SUB, fill=GOLD); y += 52
    dr.line([x0, y, x0 + w, y], fill=GOLD, width=2); y += 28
    y = wrap(dr, "This oracle deals as a real pack. The realm glyph is the suit, the "
                 "gold medallion is the rank — any game that wants four suits and "
                 "thirteen ranks will take it.", F_BODY, x0, y, w, INK, LH_BODY) + 26

    dr.text((x0, y), "THE SUITS", font=F_LBL, fill=GOLD); y += 36
    for r in REALMS:
        t = tint(r)
        dr.rectangle([x0, y, x0 + 210, y + 42], fill=t)
        dr.text((x0 + 105, y + 21), realm_head(r), font=F_LBL, fill=CREAM, anchor="mm")
        dr.text((x0 + 228, y + 21), REALM_SUIT.get(r, "a suit"), font=F_SM,
                fill=DIM, anchor="lm")
        y += 52
    y += 14

    dr.text((x0, y), "THE RANKS", font=F_LBL, fill=GOLD); y += 36
    n_r = len(PLAY_RANKS)
    rw = (w - (n_r - 1) * 6) // n_r
    rh = int(rw * 1.35)
    for i, rk in enumerate(PLAY_RANKS):
        x = x0 + i * (rw + 6)
        have = rk in RANKS
        dr.rectangle([x, y, x + rw, y + rh], fill=(222, 208, 176) if have else KRAFT,
                     outline=GOLD if have else RULE, width=2)
        dr.text((x + rw // 2, y + rh // 2), rank_label(rk), font=F_KEY,
                fill=GOLD if have else RULE, anchor="mm")
    y += rh + 20
    dr.text((x0 + w // 2, y), f"{words(len(FULL_SUITS))} full suits of "
            f"{words(len(PLAY_RANKS))} — {len(FULL_SUITS) * len(PLAY_RANKS)} cards",
            font=F_SM, fill=DIM, anchor="ma")
    y += 40

    dr.line([x0, y, x0 + w, y], fill=RULE, width=2); y += 20
    dr.text((x0, y), "BEFORE A GAME", font=F_LBL, fill=GOLD); y += 34
    n_play = len(FULL_SUITS) * len(PLAY_RANKS)
    if K.utility or jokers:
        bits = []
        if K.utility:
            bits.append(f"the {words(len(K.utility))} utility cards")
        if jokers:
            bits.append(f"the {words(len(jokers))} jokers (unless the game wants them)")
        lead = ("Deal out " + " and ".join(bits) + f" and you are holding a standard "
                f"{n_play}. No rank medallion, not in the game.")
    else:
        lead = (f"Nothing to remove — the pack is exactly {n_play}. Every card has a "
                "medallion and a place in the game.")
    y = wrap(dr, lead, F_SM, x0, y, w, INK, LH_SM) + 16
    y = wrap(dr, "The Shell is the odd suit out at the table the way it is odd in a "
                 "reading: call it trumps, or set it aside and play three-suit games "
                 f"with {(len(FULL_SUITS) - 1) * len(PLAY_RANKS)}.",
             F_SM, x0, y, w, DIM, LH_SM) + 24

    dr.line([x0, y, x0 + w, y], fill=RULE, width=2); y += 24
    dr.text((x0, y), "AT THE TABLE", font=F_LBL, fill=GOLD); y += 36
    for game, how in [
        ("Poker, hearts, rummy, war", "Play it straight — Shell is just the fourth suit."),
        ("Spades, euchre", "Shell is permanent trumps. The axis outranks the world."),
        ("Cribbage", "A is one, J Q K are ten. The medallions are already numbered."),
    ]:
        dr.text((x0, y), game, font=F_LBL, fill=INK); y += 32
        y = wrap(dr, how, F_SM, x0, y, w, DIM, LH_SM) + 12

    y += 12
    y = wrap(dr, "And when a hand goes strange, stop the game and read it. The deck "
                 "does not stop being an oracle because you dealt it for money.",
             F_ESS, x0, y, w, GOLD, 42)
    if y > y0 + h:
        overflow.append(("deal-side", y - (y0 + h)))
    return pg


def realm_side(realm, n):
    pg, dr = page()
    x0, y0, w, h = box(n)
    t = tint(realm)
    rc = by_realm[realm]
    info = REALM_INTRO.get(realm, {})

    band_lines = wrap_lines(probe, DECK["realms"][realm].split("Position:")[0].strip()
                            .rstrip("."), F_SM, w - 40)
    band_h = 80 + 20 + len(band_lines) * LH_SM + 40
    band_t = y0 + 40
    dr.rectangle([0, band_t, W, band_t + band_h], fill=t)
    cy = band_t + 46
    dr.text((x0 + w // 2, cy), realm.upper(), font=F_TITLE, fill=CREAM, anchor="mm")
    cy += 50
    dr.line([x0 + w // 2 - 80, cy, x0 + w // 2 + 80, cy], fill=(216, 206, 188), width=1)
    cy += 22
    for ln in band_lines:
        dr.text((x0 + w // 2, cy), ln, font=F_SM, fill=(240, 235, 224), anchor="ma")
        cy += LH_SM

    y = band_t + band_h + 30
    dr.text((x0 + w // 2, y), f"{words(len(rc))} cards · ranks "
            f"{rank_label(rc[0]['number'])}–{rank_label(rc[-1]['number'])} · "
            f"{REALM_SUIT.get(realm, 'a suit')}", font=F_SM, fill=DIM, anchor="ma")
    y += 54
    if info.get("domain"):
        for ln in wrap_lines(probe, info["domain"].upper(), F_LBL, w):
            dr.text((x0 + w // 2, y), ln, font=F_LBL, fill=t, anchor="ma"); y += 32
        y += 16
    for para in info.get("body", []):
        y = wrap(dr, para, F_BODY, x0, y, w, INK, LH_BODY) + 20

    if info.get("reads"):
        rl = wrap_lines(probe, info["reads"], F_SM, w - 52)
        bh = 30 + 30 + len(rl) * LH_SM + 24
        dr.rectangle([x0, y + 10, x0 + w, y + 10 + bh], outline=t, width=2)
        dr.text((x0 + 26, y + 34), "IN A READING", font=F_LBL, fill=t)
        yy = y + 34 + 34
        for ln in rl:
            dr.text((x0 + 26, yy), ln, font=F_SM, fill=INK); yy += LH_SM
        y = y + 10 + bh

    # the realm's own contents, so the side doubles as its index
    y += 34
    dr.text((x0, y), f"THE {words(len(rc)).upper()}", font=F_LBL, fill=t); y += 34
    col_w = w // 2
    rows = (len(rc) + 1) // 2
    for i, c in enumerate(rc):
        col, row = divmod(i, rows)
        dr.text((x0 + col * col_w + 26, y + row * 34), rank_label(c["number"]),
                font=F_LBL, fill=t, anchor="ra")
        dr.text((x0 + col * col_w + 38, y + row * 34),
                fit(c["name"], F_SM, col_w - 48), font=F_SM, fill=INK)
    y += rows * 34
    if y > y0 + h:
        overflow.append(("realm-" + realm, y - (y0 + h)))
    return pg


def joker_thumb(c, w, h):
    """The joker's face as the deck prints it: its own master, its title in the banner.

    `extracard.set_extra` is the extras' typesetting rule and the one export_mpc.py
    runs, so the picture in the booklet is the picture in the pack. The JOKER plaque
    is left off for the same reason card_side leaves the rank medallion off: these
    thumbnails carry the art and the name, and the side says the rest in words.
    """
    key = ("X" + c["id"], w, h)
    if key not in _thumbs:
        im = Image.open(art_src(c["art"], "extras")).convert("RGB")
        try:
            from extracard import set_extra
            im = set_extra(im, {"title": c.get("title")})
        except Exception:
            pass
        _thumbs[key] = im.resize((w, h), Image.LANCZOS)
    return _thumbs[key]


def joker_side(n, idx, c=None):
    """A real joker once the deck has one; until then a marked placeholder.

    A joker is not an oracle card, so there is no Reading, no shadow and no dare to
    set — data/extras.json says as much in its own opening note. The side is built
    from what that file does hold: the card's `title` and `mark`, the ink named in
    its art entry's `tone`, the scene cut from that entry's `image_prompt`, and the
    pack arithmetic counted off the file itself.
    """
    pg, dr = page()
    x0, y0, w, h = box(n)
    if c is None:
        t = GOLD
        dr.rectangle([x0, y0 + 120, x0 + w, y0 + h - 120], outline=RULE, width=3)
        cx = x0 + w // 2
        dr.text((cx, y0 + h // 2 - 90), f"JOKER {idx}", font=F_TITLE, fill=RULE, anchor="mm")
        dr.text((cx, y0 + h // 2 - 10), "art and words pending", font=F_BODY,
                fill=DIM, anchor="mm")
        wrap(dr, "PLACEHOLDER — this side regenerates from data/extras.json the moment "
                 "the joker lands there. Re-run:  python3 tools/booklet_mpc.py",
             F_SM, x0 + 40, y0 + h // 2 + 40, w - 80, DIM, LH_SM)
        return pg

    spec = joker_art(c)
    t = JOKER_TINT.get(c.get("art"), GOLD)
    ink = second_ink(spec.get("tone", ""))
    scene = JOKER_SCENE.get(c.get("art"), "")
    pack = joker_pack_line()

    # --- measure the words first, then give the art whatever is left over ---
    th = 46 + 56 + 14                                          # strip, name, rule
    if ink: th += 32 + 10
    th += measure(probe, scene, F_BODY, w, LH_BODY) + 16
    th += 34 + measure(probe, pack, F_SM, w, LH_SM)
    aw = max(ART_MIN, min(ART_MAX, int((h - th - 60) / 1.5)))
    ah = int(aw * 1.5)
    if th + ah + 60 > h:
        overflow.append((c["id"], th + ah + 60 - h))

    y = y0
    # The strip an oracle card spends on its realm and rank: a joker has neither,
    # and saying so is the whole reason it is not in the game.
    dr.text((x0 + w // 2, y), f"{c.get('mark', 'JOKER')} · NO REALM · NO RANK",
            font=F_LBL, fill=t, anchor="ma")
    y += 46

    ax = x0 + (w - aw) // 2
    try:
        pg.paste(joker_thumb(c, aw, ah), (ax, y))
        dr.rectangle([ax - 1, y - 1, ax + aw, y + ah], outline=(150, 130, 96), width=1)
    except Exception:
        dr.rectangle([ax, y, ax + aw, y + ah], outline=t, width=2)
    y += ah + 34

    nm = c.get("title") or c["name"]
    fnt = F_NAME if draw_w(probe, nm, F_NAME) <= w else font(GB, 38)
    dr.text((x0 + w // 2, y), fit(nm, fnt, w), font=fnt, fill=GOLD, anchor="ma")
    y += 56
    if ink:
        dr.text((x0 + w // 2, y), f"SECOND INK · {ink.upper()}", font=F_KEY,
                fill=DIM, anchor="ma")
        y += 32 + 10
    dr.line([x0, y, x0 + w, y], fill=GOLD, width=1); y += 14
    y = wrap(dr, scene, F_BODY, x0, y, w, INK, LH_BODY) + 16
    dr.text((x0, y), "IN THE PACK", font=F_LBL, fill=t); y += 34
    y = wrap(dr, pack, F_SM, x0, y, w, DIM, LH_SM)

    if y > y0 + h:
        overflow.append((c["id"] + "-tail", y - (y0 + h)))
    return pg


def notes_side(n):
    pg, dr = page()
    x0, y0, w, h = box(n)
    dr.text((x0, y0), "Your Own Pulls", font=F_SUB, fill=GOLD)
    dr.line([x0, y0 + 50, x0 + w, y0 + 50], fill=GOLD, width=2)
    dr.text((x0, y0 + 66), "DATE · ROOT · TRUNK · BRANCH", font=F_LBL, fill=DIM)
    ly = y0 + 130
    while ly < y0 + h:
        dr.line([x0, ly, x0 + w, ly], fill=RULE, width=1); ly += 56
    return pg


def back_side(n):
    pg, dr = page(DARK)
    x0, y0, w, h = box(n)
    dr.rectangle([TRIM_L + 14, TRIM_T + 14, TRIM_R - 15, TRIM_B - 15],
                 outline=BRONZE, width=2)
    cx = x0 + w // 2
    try:
        back = Image.open(f"{REPO}/cards/back.png").convert("RGB")
        bw = min(w, 420); bh = int(bw * back.size[1] / back.size[0])
        pg.paste(back.resize((bw, bh)), (cx - bw // 2, y0 + 160))
    except Exception:
        pass
    dr.text((cx, y0 + h - 300), "MOVE SLOW & BITE THINGS", font=F_LBL, fill=GOLD, anchor="mm")
    dr.text((cx, y0 + h - 240), "Terrible Turtle Camp · E & 6:15", font=F_SM,
            fill=PALE, anchor="mm")
    dr.text((cx, y0 + h - 180), f"Black Rock City · {DECK['year']}", font=F_SM,
            fill=(120, 100, 62), anchor="mm")
    return pg


# ------------------------------------------------------------ cover spread --
# back cover | spine | front cover, one image. Spine width is a function of the
# page count; MPC's own table, in inches.
# MPC's published cover canvas width per page count. Taken as pixels rather than
# converted from their inch figure: their own table gives 2238px for 72 sides
# while 0.2088in of spine would compute to 2241, and it is their uploader that
# checks the dimensions, so their number wins.
COVER_W = {52: 2220, 72: 2238, 96: 2256, 120: 2271,
           144: 2286, 168: 2301, 192: 2319}


def cover_spread(n_sides):
    cw, ch = COVER_W.get(n_sides, 2238), 1575
    trim_w = cw - 78                            # 0.13in bleed each side
    spine = trim_w - 2 * 1050
    pg, dr = K.new_page(cw, ch, DARK)
    bl, bt = (cw - trim_w) // 2, (ch - 1500) // 2
    back_x, spine_x, front_x = bl, bl + 1050, bl + 1050 + spine

    # --- front cover (right panel) ---
    fx = front_x + 1050 // 2
    dr.rectangle([front_x + 30, bt + 30, front_x + 1020, bt + 1470], outline=GOLD, width=3)
    dr.text((fx, bt + 190), "THE TERRIBLE", font=F_DISP, fill=GOLD, anchor="mm")
    dr.text((fx, bt + 282), "TURTLE", font=F_DISP, fill=GOLD, anchor="mm")
    dr.text((fx, bt + 374), "ORACLE", font=F_DISP, fill=GOLD, anchor="mm")
    dr.line([fx - 210, bt + 440, fx + 210, bt + 440], fill=BRONZE, width=2)
    try:
        bk = Image.open(f"{REPO}/cards/back.png").convert("RGB")
        bw = 520; bh = int(bw * bk.size[1] / bk.size[0])
        dr.rectangle([fx - bw // 2 - 6, bt + 500 - 6, fx + bw // 2 + 5, bt + 500 + bh + 5],
                     fill=BRONZE)
        pg.paste(bk.resize((bw, bh)), (fx - bw // 2, bt + 500))
    except Exception:
        pass
    dr.text((fx, bt + 1330), DECK["subtitle"], font=F_SM, fill=PALE, anchor="mm")
    dr.text((fx, bt + 1390), f"A COMPANION BOOKLET · {words(len(cards)).upper()} CARDS",
            font=F_LBL, fill=(120, 100, 62), anchor="mm")

    # --- spine ---
    if spine >= 40:
        sp = Image.new("RGB", (1400, spine), DARK)
        K.ImageDraw.Draw(sp).text((700, spine // 2), "THE TERRIBLE TURTLE ORACLE",
                                  font=F_LBL, fill=GOLD, anchor="mm")
        pg.paste(sp.rotate(90, expand=True), (spine_x, bt + (1500 - 1400) // 2))

    # --- back cover (left panel) ---
    bx = back_x + 1050 // 2
    dr.rectangle([back_x + 30, bt + 30, back_x + 1020, bt + 1470], outline=BRONZE, width=2)
    y = bt + 300
    dr.text((bx, y), DECK["title"].upper(), font=F_SUB, fill=GOLD, anchor="mm"); y += 70
    dr.line([bx - 200, y, bx + 200, y], fill=BRONZE, width=1); y += 50
    for line in [f"{words(len(cards)).capitalize()} cards in {words(len(REALMS))} realms —",
                 "Shell, Roots, Trunk and Branches.", "",
                 "Every card carries a Reading, a Shadow,", "and one Turtle Dare you have",
                 "to actually go and do.", "", "It also deals as a full pack:",
                 "realm is suit, medallion is rank.", "", "",
                 "Terrible Turtle Camp · E & 6:15", f"Black Rock City · {DECK['year']}",
                 "", "Move Slow & Bite Things"]:
        if line:
            dr.text((bx, y), line, font=F_SM, fill=PALE, anchor="mm")
        y += 42
    return pg


# ----------------------------------------------------------------- build ----
def build(n_sides, want_pdf=False):
    plan = []                        # (slug, callable) — number assigned in order

    plan.append(("cover", cover_side))
    plan.append(("title", title_side))
    plan.append(("how-to-read", read_side))
    plan.append(("how-to-deal", deal_side))
    for realm in REALMS:
        plan.append((f"realm-{realm}", lambda n, r=realm: realm_side(r, n)))
        for c in by_realm[realm]:
            plan.append((c["id"], lambda n, c=c: card_side(c, n)))
    # jokers: the real card if the deck has one yet, else a marked placeholder.
    # The slug drops extras.json's "extra-" prefix, the way export_mpc.py does.
    for i in range(max(2, len(jokers))):
        jc = jokers[i] if i < len(jokers) else None
        slug = (jc["id"][6:] if jc["id"].startswith("extra-") else jc["id"]) if jc \
            else f"joker-{i + 1}-PLACEHOLDER"
        plan.append((slug, lambda n, i=i, jc=jc: joker_side(n, i + 1, jc)))

    body = len(plan)
    pad = n_sides - body - 1         # -1 for the back cover
    if pad < 0:
        print(f"ERROR: {body + 1} sides of content will not fit in {n_sides}. "
              f"Use --sides {((body + 1 + 23) // 24) * 24}.")
        return 1
    for i in range(pad):
        plan.append((f"notes-{i + 1}", notes_side))
    plan.append(("back", back_side))

    out = f"{REPO}/print/mpc-booklet"
    sd = f"{out}/sides"
    os.makedirs(sd, exist_ok=True)
    for f in os.listdir(sd):
        os.remove(os.path.join(sd, f))
    os.makedirs(f"{out}/cover", exist_ok=True)

    imgs = []
    for i, (slug, fn) in enumerate(plan, start=1):
        im = fn(i)
        # folio centred at the foot — at TRIM_B - 60 it stays inside MPC's 1/8"
        # safe inset (TRIM_B - 24 left its descenders 10px outside it), and on
        # the notes sides it clears their footer rule instead of touching it
        x0, y0, w, h = box(i)
        if slug not in ("cover", "back") and not slug.startswith("realm-"):
            K.ImageDraw.Draw(im).text((x0 + w // 2, TRIM_B - 60), str(i),
                                      font=F_TINY, fill=DIM, anchor="md")
        im.save(f"{sd}/{i:02d}-{slug}.png", dpi=(DPI, DPI))
        imgs.append(im)

    cov = cover_spread(n_sides)
    cov.save(f"{out}/cover/cover-spread.png", dpi=(DPI, DPI))

    print(f"mpc booklet — {len(imgs)} sides at {W}x{H} @{DPI}dpi -> {sd}")
    print(f"cover spread — {cov.size[0]}x{cov.size[1]} "
          f"(expected {COVER_W.get(n_sides)}x1575) -> {out}/cover/cover-spread.png")
    print(f"plan: 4 front matter + {len(REALMS)} realm intros + {len(cards)} cards "
          f"+ {max(2, len(jokers))} jokers + {pad} notes + 1 back")

    missed = [c["id"] for c in cards if c["id"] not in drawn]
    twice = sorted({i for i in drawn if drawn.count(i) > 1})
    print(f"coverage: {len(drawn)}/{len(cards)} card sides"
          + (f" — MISSING {missed}" if missed else "")
          + (f" — DUPLICATED {twice}" if twice else "")
          + ("" if missed or twice else " — every card exactly once"))
    ph = [s for s, _ in plan if "PLACEHOLDER" in s]
    if ph:
        print(f"PLACEHOLDERS ({len(ph)}): {', '.join(ph)}  "
              f"— rerun `python3 tools/booklet_mpc.py` once the jokers are in cards.json")
    print("OVERFLOW: " + repr(overflow) if overflow else "fit check: clean")
    print("size check: " + ("ok" if all(im.size == (W, H) for im in imgs)
                            else "WRONG CANVAS"))

    if want_pdf:
        p = f"{out}/proof.pdf"
        imgs[0].save(p, save_all=True, append_images=imgs[1:], resolution=float(DPI))
        print(f"proof (ours, not for MPC) -> {p}")
    return 1 if (missed or twice or overflow) else 0


if __name__ == "__main__":
    n = int(sys.argv[sys.argv.index("--sides") + 1]) if "--sides" in sys.argv else 72
    sys.exit(build(n, "--pdf" in sys.argv))
