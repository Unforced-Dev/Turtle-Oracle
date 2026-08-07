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

Writes <out>/<id>.png at 1024x1536 (exactly the deck's 2:3), and records the
prompt actually used in <out>/prompts-used.json so a run is reproducible.
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
PREAMBLE = (
    "Hand-carved woodblock print / letterpress relief illustration, bold black ink "
    "linework with visible carving texture, cross-hatch and stipple shading, printed on "
    "warm desert-tan kraft paper with subtle paper grain, sparing metallic gold accents. "
    "Flat printed ink — no 3D render, no photography, no gradients, no digital smoothness. "
    "Mythic and heraldic. Centered, symmetrical, iconic composition with calm breathing "
    "space. Thin double gold border just inside the card edge. A subtle vertical World-Tree "
    "axis motif somewhere in the composition — the spine of the deck. "
)

# The undertone is a SECOND spot-colour printed alongside the black and gold — say it that
# way. Naming a colour alone gets ignored: "deep indigo undertone" produced cards
# indistinguishable from the kraft default, while branches' sky-blue happened to survive
# because the subject was already sky. Each realm now states the ink, where it goes, and
# how much of the card it should touch.
REALM_TONE = {
    "shell": ("SECOND INK — metallic gold, used generously: a radiant sunburst behind the "
              "subject, gilded ornament, gold rules and nodes down the axis. The most "
              "ornamented realm of the four. Small carved turtle-shell glyph in a top corner."),
    "roots": ("SECOND INK — deep indigo blue, used heavily and unmistakably: the entire "
              "lower half of the card below the ground line is printed in dark indigo "
              "rather than black, indigo soaking the subterranean cross-hatching, indigo "
              "shadow pooling under the subject. The card must read as blue-black, not "
              "brown. Downward pull; dense underground detail. Gold only as a small accent. "
              "Small carved root-knot glyph in a top corner."),
    "trunk": ("SECOND INK — burnt rust-orange ochre, clearly visible: rust in the sky wash, "
              "rust in the horizon band, rust warming the midtones. A strong grounded "
              "horizon line across the full width. Balanced, upright, weighty. "
              "Small carved trunk-ring glyph in a top corner."),
    "branches": ("SECOND INK — pale sky blue, clearly visible: blue filling the open sky, "
                 "blue in the leaves and small carved stars. Upward reach, airy negative "
                 "space, the lightest of the four. Small carved branch-star glyph in a "
                 "top corner."),
}

# No lettering in the generated art: image models misspell, and 48 cards that each
# misspell differently is the fastest way to lose deck cohesion. The title cartouche
# is composited in tools/print_prep.py, where the typography is exact and identical.
NO_TEXT = (" Leave a clean empty banner cartouche across the bottom sixth of the image for "
           "a title to be printed later. Absolutely no letters, words, numerals or "
           "signatures anywhere in the image.")


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
    return (PREAMBLE + f"[{card['realm'].upper()} undertone: {REALM_TONE[card['realm']]}] "
            + "Subject: " + card["image_prompt"].strip() + NO_TEXT)


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
    ap.add_argument("--out", default="cards/art")
    ap.add_argument("--force", action="store_true", help="regenerate even if the file exists")
    ap.add_argument("--retries", type=int, default=2)
    args = ap.parse_args()

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
    if not todo:
        sys.exit("nothing to generate")

    outdir = os.path.join(REPO, args.out)
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
        prompt = build_prompt(card)
        for attempt in range(1, args.retries + 2):
            t = time.time()
            try:
                png = generate(prompt, headers)
                with open(dest, "wb") as f:
                    f.write(png)
                used[card["id"]] = prompt
                with open(used_path, "w") as f:
                    json.dump(used, f, indent=2)
                print(f"[{n}/{len(todo)}] {card['id']}: {len(png)//1024} KB in "
                      f"{time.time()-t:.0f}s  ({card['name']})")
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
