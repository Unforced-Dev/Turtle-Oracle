# Print — The Terrible Turtle Oracle

Print-ready assets for the physical deck (~50 copies). **Full-art fronts + one uniform turtle back.**

## Specs
- **Card size:** 3.5 × 5.25 in (exact **2:3** — matches the generated art, so nothing is cropped).
- **Resolution:** 300 DPI.
- **Bleed:** ⅛ in on every edge, already baked in (added by extending edge pixels *outward* — no card's gold border is ever trimmed).
- **Full image incl. bleed:** 1124 × 1649 px. **Trim:** 1050 × 1575 px. Keep text/important art ~⅛ in inside the trim (already true of the woodcut borders).

## Files
- `fronts/<id>.png` — 48 card fronts, bleed included, upload-ready. (`<id>` = `shell-01` … `branches-12`.)
- `back.png` — the single shared card back, bleed included.
- `proof.pdf` — 50-page flip-through for **review only** (cover + 48 fronts + back, with captions). Not for the printer.

## Sending to a printer
These files suit any printer that accepts a **3.5×5.25 in, 300 DPI, ⅛ in bleed** card with no crop marks (most online/offset card printers and print-on-demand services).

- **Best fit:** a service/shop that accepts a **custom 2:3 card size** (offset printers, or POD that allows custom dimensions). Upload `fronts/` as the fronts and `back.png` as the shared back.
- **Fixed-template services** use set sizes whose aspect differs from our 2:3 (0.67), so the art has to be adapted to their template. Two are already written, each a single command, each writing a gitignored directory (the output is ~73 MB; the upload zip ships as a GitHub release, not in git):
  - `python3 tools/export_mpc.py` → `print/mpc/` — **MakePlayingCards jumbo**, 3.5×5 in (0.70), upload 1125×1575. Fitted by height, side edges extended outward to reach the trim width.
  - `python3 tools/export_tgc.py` → `print/tgc/` — **The Game Crafter Jumbo Deck**, 3.5×5.5 in (0.636), upload 1125×1725, RGB only (they reject CMYK). Taller than our art rather than shorter, so there is nothing to extend into: the master is resized onto the trim, a 4.76% vertical stretch, which keeps the engraved frame running to all four edges.
  - Both typeset the title **after** the resize, through `tools/cardtitle.py`, so the name sits in its banner by the same relative rule as the house card. Any other vendor is a new `TRIM`/`FULL` pair away.

## Quantity
~50 decks (one per camp member). Confirm finish (matte recommended for the woodcut look), card stock, and box option with your chosen printer.

## Regenerate
`python3 tools/print_prep.py` (uses the committed `cards/art/*.jpg` archive + `cards/back.png`, PIL only). Card names are typeset onto the empty banner at build time by `tools/cardtitle.py` — the same rule the web images use. Change `TRIM`/`DPI`/`BLEED` at the top to retarget size.
