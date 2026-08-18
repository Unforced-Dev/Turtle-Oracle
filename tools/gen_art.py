#!/usr/bin/env python3
"""Generate card art through the Codex backend's image_generation tool.

Why this route: the Codex CLI authenticates a ChatGPT account and talks to
`chatgpt.com/backend-api/codex/responses`, which accepts the `image_generation`
tool. That means no OpenAI API key and no per-image billing — the ChatGPT plan
covers it. The same token gets 401 (missing scopes) against api.openai.com, so
this is the only door.

The model must be the one Codex itself uses (`gpt-5.6-sol`). Any other name comes
back "not supported when using Codex with a ChatGPT account", which reads like a
model problem and is really an entitlement one.

Usage:
    python3 tools/gen_art.py shell-01 roots-02        # specific cards
    python3 tools/gen_art.py --realm shell            # a whole realm
    python3 tools/gen_art.py --all                    # the deck
    python3 tools/gen_art.py --all --out cards/art2   # somewhere else
    python3 tools/gen_art.py --extras                 # the extras' masters
    python3 tools/gen_art.py --extras joker-radiant   # one of them

Writes <out>/<id>.png at 1024x1536 (exactly the deck's 2:3), and records the
prompt actually used in <out>/prompts-used.json so a run is reproducible.

The 11 utility cards (jokers, title, reference, realm, blank) are NOT oracle
cards and live in data/extras.json; --extras generates only the handful of
masters they share, out of the same constants below, into cards/extras/.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH = os.path.expanduser("~/.codex/auth.json")
URL = "https://chatgpt.com/backend-api/codex/responses"
MODEL = os.environ.get("CODEX_IMAGE_MODEL", "gpt-5.6-sol")

# docs/STYLE_GUIDE.md — every card prepends this so all 48 read as one deck.
#
# The v1 deck read as 48 individually decent cards rather than one deck, and the
# diagnosis was always furniture, never subject: two different frame systems inside the
# Shell twelve, three different cartouche shapes across the deck, ground value drifting
# light-to-dark inside a single realm, the realm glyph wandering between corners or
# vanishing, and a handful of cards (Center Camp, Playa Info & the Rangers) sliding out
# of the woodcut idiom into soft illustration. Everything below exists to nail one of
# those five down. The rule this file now follows everywhere: describe the furniture as
# a printer would specify it — which ink, exactly where, how much of the card it covers —
# never as an adjective. Adjectives are what drifted.
#
# Split in three because the extras need two of the three: an EMPTY card — the frame
# master the title, reference, realm and blank cards are typeset onto — is the one
# thing in this deck that must not carry a subject, an axis motif or a landscape. The
# idiom (ink, stock, three colours) still governs it, so that part alone is reused.
# PREAMBLE is the concatenation and is byte-identical to what it always was; every
# oracle card's prompt is therefore unchanged.
PREAMBLE_IDIOM = (
    # --- the idiom ---------------------------------------------------------------
    "Hand-carved woodblock print / letterpress relief illustration. Bold black ink "
    "linework with visible carving texture; EVERY tone is built from carved marks — "
    "parallel hatching, cross-hatch, stipple, chatter, and white gouges where the block "
    "was cut away. Flat opaque ink, hard edges, strong figure-ground. "
    # The named offenders both failed here and nowhere else: right subject, right palette,
    # rendered like a book illustration. Naming the failure modes individually is what
    # stops them; "woodcut" alone did not.
    "THIS IS A RELIEF PRINT, NOT A DRAWING OF ONE. No airbrush, no soft or blended "
    "shading, no gradients, no painterly or watercolour light, no rendered skin, cloth or "
    "metal, no 3D render, no photography, no pencil sketch, no comic or graphic-novel "
    "inking, no children's-book or storybook warmth, no cosy illustrated charm. Faces, "
    "hands and figures are carved exactly like rock and cloth — blunt, angular, built "
    "from hatching, never modelled, never smooth, never softly lit. If any passage could "
    "pass for a soft digital illustration it is WRONG: cut it back to hard black marks on "
    "bare paper. "
    "Exactly three inks touch this paper — black, metallic gold, and the realm's second "
    "ink named below — with no blends or intermediate colours between them. Printed on "
    "warm desert-tan kraft paper with visible paper grain. "
)
PREAMBLE_COMPOSITION = (
    "Mythic and heraldic. Centred, symmetrical, iconic composition with calm breathing "
    "space. A subtle vertical World-Tree axis motif somewhere in the composition — the "
    "spine of the deck. "
)
PREAMBLE_SETTING = (
    # Every card is the same place. Without this the model wanders somewhere prettier the
    # moment a subject turns abstract — the first draft of The Gift came back with pine
    # forests and green valleys, which is a lovely card for a different deck.
    "SETTING, ALWAYS AND WITHOUT EXCEPTION: the Black Rock Desert. A dead-flat pale alkali "
    "playa stretching to the horizon, cracked dust, distant low barren desert mountains, "
    "enormous open sky. NO trees, NO forest, NO pines, NO grass, NO green vegetation, NO "
    "rivers or lakes, NO rolling hills — the only tree that may ever appear is the World "
    "Tree itself. If the subject implies a landscape, that landscape is still this desert. "
)
PREAMBLE = PREAMBLE_IDIOM + PREAMBLE_COMPOSITION + PREAMBLE_SETTING

# --- the frame ---------------------------------------------------------------------
# Two frames in the deck, on purpose, and exactly two. The Shell twelve are the axis —
# the rare card the séance surfaces about one time in ten — and they are meant to be
# identifiable as one of the twelve from across a dusty tent before anyone reads the
# name, so they carry deliberately heavier furniture. That asymmetry is the design. What
# was NOT the design was half the Shell realm printing the heavy frame and half printing
# the plain one. Each frame is now specified to the millimetre so there is nothing left
# to interpret.
TREE_FRAME = (
    "FRAME — IDENTICAL ON EVERY ROOTS, TRUNK AND BRANCHES CARD, NO VARIATION: a plain "
    "rectangular double keyline in metallic gold and nothing else. The outer rule is a "
    "fine gold line inset 3% of the card width from the card edge on all four sides; the "
    "inner rule is a second, thinner gold line 1.5% of the card width further in. Both "
    "rules are thin — hairline weight, the outer barely heavier than the inner — and the "
    "bare kraft paper shows between them. Square corners, mitred cleanly. NOTHING ELSE "
    "IN THE FRAME: no corner bosses, no medallions, no rosettes, no filigree, no vine, "
    "no engraved band, no ornamental band, no black frame ground, no third rule. "
)
SHELL_FRAME = (
    "FRAME — IDENTICAL ON ALL TWELVE SHELL CARDS, NO VARIATION, and deliberately much "
    "heavier than the other realms: an ornate engraved gold-on-black border. A solid "
    "black band, inset 2% of the card width from the card edge, running the full "
    "perimeter at a width of 6% of the card width — roughly eight times a plain rule. "
    "The band is filled edge to edge with a repeating engraved gold ornament of vine, "
    "dot and lozenge, and is bounded by a fine gold hairline along both its outer and "
    "its inner edge. At each of the four corners sits a circular gold boss the full width "
    "of the band: a filled gold disc with a carved rosette inside it. The TOP-LEFT boss "
    "alone carries the turtle-shell glyph instead of the rosette; the other three bosses "
    "are identical plain rosettes. Same band width, same ornament, same four bosses on "
    "every one of the twelve. NEVER a plain thin keyline frame on a Shell card. "
)

# --- the cartouche -----------------------------------------------------------------
# One shape for all 48. The v1 deck grew three — a plain rectangle, an ornate shaped
# cartouche with scalloped ends, and a wavy ribbon scroll with rolled tails that took
# over most of the Branches row — and nothing wrecks a fan of cards faster than the
# title sitting on a different object each time.
#
# The geometry is not free: tools/print_prep.py sets the title with its baseline centred
# at 0.888 of the card height (TITLE_Y) and shrinks the face until the tracked line fits
# 0.66 of the card width (TITLE_MAX_W). The band specified here is centred on 0.888 and
# is 0.76 wide, which clears the longest name with margin on both sides. Move one and
# move the other.
CARTOUCHE = (
    "TITLE BANNER — IDENTICAL SHAPE, SIZE AND POSITION ON EVERY CARD IN THE DECK: one "
    "plain rectangular banner with square corners, lying flat and horizontal. Its top "
    "edge is 84.5% of the way down the image and its bottom edge is 93% of the way down; "
    "it is exactly 76% of the image width and centred left-to-right. It is drawn as bare "
    # Colour was left unspecified here and three Branches cards duly drew the keyline in
    # black, which reads as a different banner object across a fan of cards. Name the ink.
    "kraft paper enclosed by a single fine METALLIC GOLD keyline (never black), sitting "
    "on top of the artwork, and it "
    "is COMPLETELY EMPTY — flat blank paper, no lettering, no ornament, no rule, no "
    "flourish, no device inside it. NOT a ribbon, NOT a scroll, NOT a banderole, NO "
    "curled or rolled ends, NO wavy or draped edges, NO swallowtails, NO scalloped or "
    "lobed or shaped cartouche, NO tapered ends, NO corner ornaments on the banner. A "
    "plain rectangle, every time. "
)

# --- the realm glyph ---------------------------------------------------------------
# It wandered corner to corner and sometimes evaporated. One corner, stated twice.
GLYPH = {
    r: ("REALM GLYPH — ALWAYS PRESENT, ALWAYS IN THE TOP-LEFT CORNER OF THE CARD AND "
        "NOWHERE ELSE: a small carved " + mark + ", about 5% of the card width across, "
        "sitting just inside the frame at the top left. It appears on every card without "
        "exception. Never in the top-right, never at the bottom, never in more than one "
        "corner, never omitted. ")
    for r, mark in {
        "shell": "turtle-shell glyph (it rides inside the top-left corner boss)",
        "roots": "root-knot glyph in a plain circular medallion",
        "trunk": "trunk-ring glyph (concentric growth rings) in a plain circular medallion",
        "branches": "branch-star glyph in a plain circular medallion",
    }.items()
}

# --- the second ink, and the ground value ------------------------------------------
# The undertone is a SECOND spot-colour printed alongside the black and gold — say it that
# way. Naming a colour alone gets ignored: "deep indigo undertone" produced cards
# indistinguishable from the kraft default, while branches' sky-blue happened to survive
# because the subject was already sky. Each realm states the ink, where it goes, and how
# much of the card it should touch.
#
# GROUND VALUE is the same lesson applied to overall darkness, which drifted inside every
# realm in v1 — a night-black Shell card next to a pale one, a Roots card with no indigo
# below the line at all, a Trunk card two stops lighter than its neighbours. So each realm
# now fixes where the horizon sits and how dark the card is allowed to print, in the same
# ink terms.
REALM_TONE = {
    "shell": ("SECOND INK — metallic gold, used lavishly, far more than any other realm: a "
              "full radiant sunburst behind the subject, gilded ornament throughout, gold "
              "rules and nodes running the whole axis. "
              "GROUND VALUE — ONE FIXED VALUE ACROSS ALL TWELVE: the field is warm mid-tan "
              "kraft paper, and the gold sunburst behind the subject covers the middle two "
              "thirds of the image, so every Shell card reads gold-dominant at the same "
              "brightness. The field is NEVER flooded with black and NEVER left as pale "
              "washed-out paper: no night sky, no dark background, no black field. In this "
              "realm the black lives in the frame band and the linework, not in the "
              "field."),
    "roots": ("SECOND INK — deep indigo blue, used heavily and unmistakably: the entire "
              "lower half of the card below the ground line is printed in dark indigo "
              "rather than black, indigo soaking the subterranean cross-hatching, indigo "
              "shadow pooling under the subject. The card must read as blue-black, not "
              "brown. Downward pull; dense underground detail. Gold only as a small "
              "accent. "
              "GROUND VALUE — ONE FIXED VALUE ACROSS ALL TWELVE: the ground line CUTS THE "
              "IMAGE EXACTLY IN HALF. The top half of the card, and only the top half, is "
              "bare warm kraft with light black linework and open pale sky. The bottom "
              "half of the card, all of it, is solid dark indigo at the same density "
              "every time, corner to corner. Not a third, not two thirds — half and half, "
              "on every one of the twelve. NEVER a Roots card that is warm tan below the "
              "line, and never a Roots card whose sky is dark."),
    "trunk": ("SECOND INK — burnt rust-orange ochre, clearly visible: rust in the sky wash, "
              "rust in the horizon band, rust warming the midtones. Balanced, upright, "
              "weighty. "
              "GROUND VALUE — ONE FIXED VALUE ACROSS ALL TWELVE: a strong horizon line "
              "across the full width at 45% of the image height. Above it, the sky is "
              "filled solidly with rust-orange ink at the same saturation on every card — "
              "never pale, never blue, never night. Below it, pale cracked playa in bare "
              "kraft carrying black linework only. The rust sky is the constant that makes "
              "the twelve one realm."),
    "branches": ("SECOND INK — pale sky blue, clearly visible: blue filling the open sky, "
                 "blue in the leaves and small carved stars. Upward reach, airy negative "
                 "space, the lightest of the four realms. "
                 "GROUND VALUE — ONE FIXED VALUE ACROSS ALL TWELVE: pale sky blue fills "
                 "the WHOLE TOP HALF of the image, at the same light value on every card; "
                 "the cracked kraft playa gets the bottom half, and the horizon line "
                 "where they meet crosses at exactly half the image height, corner to "
                 "corner, every time. Whatever the subject is, it stays small against "
                 "that sky, standing in the bottom half — do not raise the horizon above "
                 "the midline to fit it in. The sky is NEVER dark, never night, never "
                 "rust, never black — this realm is always the lightest card on the "
                 "table."),
}

# --- the extras' corner ------------------------------------------------------------
# The two jokers belong to no realm, so there is no realm glyph to draw — but the corner
# still has to speak the deck's language, because the JOKER mark is hung off exactly the
# roundel the rank medallions are hung off (tools/rankmark.py finds it by measurement).
# So they carry the turtle itself in the same plain circular medallion the roots, trunk
# and branches cards use. The frame masters carry no corner mark at all: nothing is
# ranked on them and a stray roundel would sit under the typeset copy.
EXTRA_GLYPH = {
    "turtle": ("DECK GLYPH — ALWAYS PRESENT, ALWAYS IN THE TOP-LEFT CORNER OF THE CARD AND "
               "NOWHERE ELSE: a small carved turtle-shell glyph in a plain circular gold "
               "medallion, about 5% of the card width across, sitting just inside the frame "
               "at the top left. Never in the top-right, never at the bottom, never in more "
               "than one corner, never omitted. "),
}

# No lettering in the generated art: image models misspell, and 48 cards that each
# misspell differently is the fastest way to lose deck cohesion. The title is composited
# into the empty banner by tools/print_prep.py, where the typography is exact and
# identical across the deck.
NO_TEXT = (" Absolutely no letters, words, numerals or signatures anywhere in the image; "
           "the title banner stays blank.")


def auth_headers():
    with open(AUTH) as f:
        a = json.load(f)
    t = a["tokens"]
    return {
        "Authorization": f"Bearer {t['access_token']}",
        "chatgpt-account-id": t["account_id"],
        "Content-Type": "application/json",
        "OpenAI-Beta": "responses=experimental",
        "originator": "codex_cli_rs",
        "session_id": "00000000-0000-0000-0000-0000000000ff",
    }


def build_prompt(card):
    realm = card["realm"]
    # Furniture first, subject last: the fixed deck-wide spec, then the one card.
    return (PREAMBLE
            + (SHELL_FRAME if realm == "shell" else TREE_FRAME)
            + CARTOUCHE
            + GLYPH[realm]
            + f"[{realm.upper()} undertone: {REALM_TONE[realm]}] "
            + "Subject: " + card["image_prompt"].strip() + NO_TEXT)


def build_extra_prompt(art):
    """The same furniture-first rule, for one of the extras' masters.

    `art` is an entry from data/extras.json's "art" list: it may switch off the
    composition and setting clauses (an empty frame master has neither), names its own
    tone in place of a realm's, and takes a glyph from EXTRA_GLYPH or none at all.
    """
    parts = [PREAMBLE_IDIOM]
    if art.get("composition", True):
        parts.append(PREAMBLE_COMPOSITION)
    if art.get("setting", True):
        parts.append(PREAMBLE_SETTING)
    parts.append(SHELL_FRAME if art.get("frame") == "shell" else TREE_FRAME)
    parts.append(CARTOUCHE)
    if art.get("glyph"):
        parts.append(EXTRA_GLYPH[art["glyph"]])
    if art.get("tone"):
        parts.append(f"[{art['tone']}] ")
    parts.append("Subject: " + art["image_prompt"].strip() + NO_TEXT)
    return "".join(parts)


def generate(prompt, headers, timeout=600):
    """Returns PNG bytes, or raises."""
    body = {
        "model": MODEL,
        "instructions": "You generate images. Call the image_generation tool. Do not ask "
                        "clarifying questions; produce the image immediately.",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "tools": [{"type": "image_generation"}],
        "stream": True,
        "store": False,
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers)
    b64, said = None, []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                d = json.loads(line[5:].strip())
            except Exception:
                continue
            if d.get("type", "").startswith("response.image_generation_call") and d.get("result"):
                b64 = d["result"]
            for k in ("partial_image_b64", "b64_json", "image_b64"):
                v = d.get(k)
                if isinstance(v, str) and len(v) > 5000:
                    b64 = v
            if d.get("type") == "response.output_text.delta" and d.get("delta"):
                said.append(d["delta"])
    if not b64:
        raise RuntimeError("no image returned; model said: " + ("".join(said)[:300] or "(nothing)"))
    return base64.b64decode(b64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="card ids, e.g. shell-01")
    ap.add_argument("--realm", help="generate a whole realm")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--extras", nargs="*", default=None, metavar="ART_ID",
                    help="the extras' masters from data/extras.json (all of them if bare)")
    ap.add_argument("--out", default=None, help="default cards/art, or cards/extras")
    ap.add_argument("--force", action="store_true", help="regenerate even if the file exists")
    ap.add_argument("--retries", type=int, default=2)
    args = ap.parse_args()

    if args.extras is not None:
        art = json.load(open(os.path.join(REPO, "data", "extras.json")))["art"]
        by_id = {a["id"]: a for a in art}
        missing = [i for i in args.extras if i not in by_id]
        if missing:
            sys.exit(f"unknown extras art ids: {missing}")
        todo = [by_id[i] for i in args.extras] if args.extras else art
        prompt_of = build_extra_prompt
        default_out = "cards/extras"
    else:
        cards = json.load(open(os.path.join(REPO, "data", "cards.json")))["cards"]
        by_id = {c["id"]: c for c in cards}
        if args.all:
            todo = cards
        elif args.realm:
            todo = [c for c in cards if c["realm"] == args.realm]
        else:
            missing = [i for i in args.ids if i not in by_id]
            if missing:
                sys.exit(f"unknown card ids: {missing}")
            todo = [by_id[i] for i in args.ids]
        prompt_of = build_prompt
        default_out = "cards/art"
    if not todo:
        sys.exit("nothing to generate")

    outdir = os.path.join(REPO, args.out or default_out)
    os.makedirs(outdir, exist_ok=True)
    headers = auth_headers()
    used_path = os.path.join(outdir, "prompts-used.json")
    used = json.load(open(used_path)) if os.path.exists(used_path) else {}

    ok = fail = skip = 0
    for n, card in enumerate(todo, 1):
        dest = os.path.join(outdir, card["id"] + ".png")
        if os.path.exists(dest) and not args.force:
            print(f"[{n}/{len(todo)}] {card['id']}: exists, skipping")
            skip += 1
            continue
        prompt = prompt_of(card)
        for attempt in range(1, args.retries + 2):
            t = time.time()
            try:
                png = generate(prompt, headers)
                with open(dest, "wb") as f:
                    f.write(png)
                # The .png master stays local (gitignored); the committed archive
                # is a q95 4:4:4 JPEG — visually lossless at print size.
                from PIL import Image
                Image.open(dest).convert("RGB").save(
                    dest[:-4] + ".jpg", "JPEG",
                    quality=95, optimize=True, subsampling=0)
                used[card["id"]] = prompt
                with open(used_path, "w") as f:
                    json.dump(used, f, indent=2)
                print(f"[{n}/{len(todo)}] {card['id']}: {len(png)//1024} KB in "
                      f"{time.time()-t:.0f}s  ({card.get('name', card['id'])})")
                ok += 1
                break
            except Exception as e:
                msg = str(e)[:160]
                if attempt > args.retries:
                    print(f"[{n}/{len(todo)}] {card['id']}: FAILED — {msg}")
                    fail += 1
                else:
                    print(f"[{n}/{len(todo)}] {card['id']}: retry {attempt} — {msg}")
                    time.sleep(5 * attempt)

    print(f"\ndone: {ok} generated, {skip} skipped, {fail} failed -> {outdir}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
