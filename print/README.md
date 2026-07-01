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
- **Fixed-template services** (e.g. MakePlayingCards, The Game Crafter) use set sizes whose aspect (e.g. tarot 2.75×4.75 = 0.58) differs from our 2:3 (0.67). To use one, the art must be padded or slightly cropped to their template. Say the word and I'll re-export `fronts/` to any vendor's exact pixel size + aspect (padding with the deck's kraft/border so nothing important is lost).

## Quantity
~50 decks (one per camp member). Confirm finish (matte recommended for the woodcut look), card stock, and box option with your chosen printer.

## Regenerate
`python3 scratchpad/print_prep.py` (uses `cards/art/*.png` + `cards/back.png`, PIL only). Change `TRIM`/`DPI`/`BLEED` at the top to retarget size.
