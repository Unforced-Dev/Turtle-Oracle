"""Prototype harness for the rank medallion — renders the 4 sample cards through the
real MPC pipeline in both ink variants, plus corner crops and a comparison sheet.

Not part of any build: this exists so the marks can be LOOKED at before the rule is
wired into export_mpc.py.  python3 tools/proto_rank.py [--sweep]
"""
from PIL import Image, ImageDraw, ImageFont
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cardtitle import set_title
from print_prep import art_src
from export_mpc import TRIM, mpc_ready
from rankmark import detect_corner

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{REPO}/.proto/render"
os.makedirs(OUT, exist_ok=True)

SAMPLES = ["shell-01", "roots-07", "trunk-11", "branches-10"]
VARIANTS = ["gold", "realm"]
CROP = 0.35            # corner crop side, as a fraction of the card width

CARDS = {c["id"]: c for c in json.load(open(f"{REPO}/data/cards.json"))["cards"]}


def height_fit(src):
    """The MPC pipeline's first step: 1024x1536 master -> 1000x1500."""
    im = Image.open(src).convert("RGB")
    return im.resize((int(TRIM[1] * im.size[0] / im.size[1]), TRIM[1]), Image.LANCZOS)


def corner_crops(im, cid, variant):
    W, H = im.size
    s = int(W * CROP)
    out = {}
    for tag, box in (("TL", (0, 0, s, s)), ("BR", (W - s, H - s, W, H))):
        c = im.crop(box).resize((720, 720), Image.LANCZOS)
        p = f"{OUT}/{cid}_{variant}_{tag}.png"
        c.save(p)
        out[tag] = p
    return out


def _label_font(size):
    for p in ("/System/Library/Fonts/Supplemental/Bodoni 72 Smallcaps Book.ttf",
              "/System/Library/Fonts/Supplemental/Georgia.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def compare_sheet(paths):
    cell, gut, side, head = 400, 16, 210, 52
    W = side + len(SAMPLES) * (cell + gut)
    sheet = Image.new("RGB", (W, head + 2 * (cell + gut) + gut), (247, 243, 235))
    d = ImageDraw.Draw(sheet)
    f, fs = _label_font(34), _label_font(26)
    for col, cid in enumerate(SAMPLES):
        d.text((side + col * (cell + gut), head - 38), cid.upper(), font=fs,
               fill=(60, 50, 34))
    for row, variant in enumerate(VARIANTS):
        y = head + row * (cell + gut)
        d.text((gut, y + cell // 2 - 20), f"{variant.upper()}\nINK", font=f,
               fill=(120, 40, 20) if variant == "realm" else (30, 90, 60))
        for col, cid in enumerate(SAMPLES):
            sheet.paste(Image.open(paths[(cid, variant)]["TL"]).resize((cell, cell),
                                                                      Image.LANCZOS),
                        (side + col * (cell + gut), y))
    sheet.save(f"{OUT}/compare.png")
    return f"{OUT}/compare.png"


def sweep():
    """Detection only, all 48 cards, through the same height-fit.

    Also draws a contact sheet of every detection (roundel circle + both mark
    positions) — a table of numbers cannot tell you the circle landed on the roundel.
    """
    rows = []
    cell = 260
    sheet = Image.new("RGB", (cell * 8, cell * 6), (250, 248, 244))
    for n, cid in enumerate(sorted(CARDS)):
        im = height_fit(art_src(cid))
        try:
            g = detect_corner(im)
        except Exception as e:
            rows.append({"id": cid, "ok": False, "why": f"{type(e).__name__}: {e}"})
            continue
        if g is None:
            rows.append({"id": cid, "ok": False, "why": "no roundel"})
            continue
        W, H = im.size
        rows.append({"id": cid, "ok": True,
                     "cx_f": round(g["cx"] / W, 4), "cy_f": round(g["cy"] / H, 4),
                     "r_f": round(g["r"] / W, 4), "score": round(g["score"], 3),
                     "band": None if g["band"] is None else round(g["band"] / W, 4),
                     "mark_r": round(g["mark_r"], 1),
                     "tl": [round(v, 1) for v in g["tl"]],
                     "br": [round(v, 1) for v in g["br"]],
                     "field": g["field"],
                     "br_from": g["br_from"],
                     "br_r_f": None if g["br_r"] is None else round(g["br_r"] / W, 4),
                     "clamped": g["clamped"]})
        vis = im.copy()
        d = ImageDraw.Draw(vis)
        cx, cy, r, mr = g["cx"], g["cy"], g["r"], g["mark_r"]
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(0, 255, 60), width=2)
        for (mxx, myy) in (g["tl"], g["br"]):
            d.ellipse((mxx - mr, myy - mr, mxx + mr, myy + mr),
                      outline=(255, 0, 200), width=2)
        sheet.paste(vis.resize((cell, int(cell * 1.5)), Image.LANCZOS)
                    .crop((0, 0, cell, cell)), ((n % 8) * cell, (n // 8) * cell))
        ImageDraw.Draw(sheet).text(((n % 8) * cell + 4, (n // 8) * cell + 4),
                                   f"{cid} {g['field']}", font=_label_font(15),
                                   fill=(255, 255, 255))
        sys.stderr.write(f"{cid} ")
        sys.stderr.flush()
    sheet.save(f"{OUT}/_sweep_tl.png")
    print(json.dumps(rows, indent=1))


def main():
    paths, geo = {}, {}
    for cid in SAMPLES:
        c = CARDS[cid]
        for variant in VARIANTS:
            rep = {}
            im = mpc_ready(art_src(cid), c["name"], c["number"], c["realm"],
                           variant=variant, report=rep)
            p = f"{OUT}/{cid}_{variant}.png"
            im.save(p)
            paths[(cid, variant)] = corner_crops(im, cid, variant)
            paths[(cid, variant)]["full"] = p
            geo[f"{cid}/{variant}"] = {k: (list(v) if isinstance(v, tuple) else v)
                                       for k, v in rep.items()}
    sheet = compare_sheet(paths)
    print(json.dumps({"geometry": geo, "sheet": sheet}, indent=1, default=str))


if __name__ == "__main__":
    if "--sweep" in sys.argv:
        sweep()
    else:
        main()
