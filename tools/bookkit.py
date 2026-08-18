"""Shared furniture for the companion booklets.

Two booklets are built from one deck: `booklet.py` (half-letter, saddle-stitch,
two cards to a page — the fallback if we print outside the deck order) and
`booklet_mpc.py` (MakePlayingCards' in-order perfect-bound booklet, one card to
a side, at the card's own trim). They differ in geometry and in nothing else, so
the deck, the palette, the realm copy and the text measuring live here.

Type sizes deliberately do NOT live here. The two books sit at different
physical sizes and different DPI, so each one picks its own scale off `font()`.
"""
from PIL import Image, ImageDraw, ImageFont
import json, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = f"{REPO}/cards/art"


def art_src(cid):
    # The committed q95 .jpg archive is the build source, so every clone builds
    # identical bytes; the local-only .png master is the fallback for fresh gens.
    p = f"{ART}/{cid}.jpg"
    return p if os.path.exists(p) else f"{ART}/{cid}.png"


# ------------------------------------------------------------------ deck ----
_d = json.load(open(f"{REPO}/data/cards.json"))
DECK = _d["deck"]
lore = json.load(open(f"{REPO}/data/card_lore.json"))

# Realm order is the deck's own; anything the deck adds later falls in behind.
_pref = ["shell", "roots", "trunk", "branches"]
REALMS = [r for r in _pref if r in DECK["realms"]] + \
         [r for r in DECK["realms"] if r not in _pref]
_ord = {r: i for i, r in enumerate(REALMS)}

COURT = {1: "A", 11: "J", 12: "Q", 13: "K"}
PLAY_RANKS = list(range(1, 14))

# A card is an *oracle* card if it sits in a realm on the 1..13 grid. Jokers and
# utility cards (title, key, blanks) live outside it; they carry no rank
# medallion, and that is exactly how you spot them in the pack.
cards = sorted([c for c in _d["cards"] if c["realm"] in _ord],
               key=lambda c: (_ord[c["realm"]], c["number"]))
extras = [c for c in _d["cards"] if c["realm"] not in _ord]
jokers = [c for c in extras if "joker" in (c.get("realm", "") + c.get("id", "")).lower()]
utility = [c for c in extras if c not in jokers]

by_realm = {}
for c in cards:
    by_realm.setdefault(c["realm"], []).append(c)

N_CARDS = len(cards)
N_REALMS = len(REALMS)
RANKS = sorted({c["number"] for c in cards})
N_RANKS = len(RANKS)
FULL_SUITS = [r for r in REALMS
              if {c["number"] for c in by_realm[r]} >= set(PLAY_RANKS)]


# --------------------------------------------------------------- palette ----
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


# Realm intros. The domain line is lifted from docs/DECK_DESIGN.md's realm table;
# the prose is the Turtle's voice, written here because nothing in the data holds
# a realm-length statement — cards.json gives one clause, card_lore.json is
# per-card only. Kept short: the cards do the talking.
REALM_INTRO = {
    "shell": {
        "domain": "major archetypes · load-bearing life truths",
        "body": [
            "Underneath the tree is the thing that carries the tree. The Shell is "
            "the Turtle itself — the load-bearing truths, the ones that were true "
            "before you got here and will be true after.",
            "These are the biggest cards in the deck, and the least specific. A "
            "Shell card does not tell you what to do on Tuesday. It tells you what "
            "kind of ground you are standing on.",
        ],
        "reads": "Wild. A Shell card can stand in any position, and when one turns "
                 "up the whole reading swings around it — the axis itself is speaking.",
    },
    "roots": {
        "domain": "shadow · grief · the buried · ancestry · release",
        "body": [
            "Everything the tree is made of came up through here first, in the dark, "
            "through rot. The Roots are the underworld: what you buried, what buried "
            "you, what you are still quietly paying for.",
            "None of these cards are punishments. A root is not a wound — it is how "
            "a living thing holds on in wind. But you have to go down to find it, and "
            "down is the direction nobody volunteers for.",
        ],
        "reads": "Position: what to face. The thing under the question, not the question.",
    },
    "trunk": {
        "domain": "body · presence · endurance · survival · move slow",
        "body": [
            "The Trunk is the middle world — the part of the tree you can actually "
            "put a hand on. Body, breath, water, sleep, the plain daily work of "
            "staying upright in a place that would rather you didn't.",
            "This is the realm where 'Move Slow' stops being a joke on a flag and "
            "becomes a survival instruction. Nothing here is profound. All of it is "
            "load-bearing.",
        ],
        "reads": "Position: where you stand. The honest report on your current footing.",
    },
    "branches": {
        "domain": "connection · ecstasy · aspiration · the sunrise · reaching",
        "body": [
            "Up top, where the tree stops being structure and starts being gesture. "
            "The Branches are the heavens: other people, joy that arrives without "
            "being scheduled, the sunrise you stayed up for, the reach.",
            "Reaching is the only thing a tree does that has no immediate use. It is "
            "also the only reason anything stands under it. Do not mistake these "
            "cards for decoration.",
        ],
        "reads": "Position: what to reach for. The direction, not the destination.",
    },
}


# --------------------------------------------------- playing-card wording ----
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


def keyword_line(c):
    return " · ".join(k.upper() for k in c.get("keywords", []))


# ------------------------------------------------------------ typography ----
G = "/System/Library/Fonts/Supplemental/Georgia.ttf"
GB = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
GI = "/System/Library/Fonts/Supplemental/Georgia Italic.ttf"


def font(path, sz):
    try: return ImageFont.truetype(path, sz)
    except Exception: return ImageFont.load_default()


probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))


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


def draw_w(draw, text, fnt):
    return draw.textlength(text, font=fnt)


def new_page(w, h, bg=KRAFT):
    pg = Image.new("RGB", (w, h), bg)
    dr = ImageDraw.Draw(pg); dr._image = pg
    return pg, dr


def fit(text, fnt, maxw, draw=probe):
    """Ellipsize to one line — for index columns and running heads."""
    if draw.textlength(text, font=fnt) <= maxw:
        return text
    while len(text) > 4 and draw.textlength(text + "…", font=fnt) > maxw:
        text = text[:-1]
    return text + "…"
