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

## The companion booklet
The booklet is built twice, from one deck and one shared module (`tools/bookkit.py`):

- **`python3 tools/booklet.py` → `print/booklet.pdf`** — half-letter (5.5×8.5 in @ 200 DPI), 40 pages, saddle-stitch ready (a multiple of 4). Two cards to a page. This is the **fallback**, for printing outside the deck order at Mixam / FedEx Office / at home.
- **`python3 tools/booklet_mpc.py` → `print/mpc-booklet/`** (gitignored, ~63 MB) — MPC's **in-order perfect-bound booklet**, packed with every deck. One card to a side, **72 sides**. `--sides 96` for the fallback count, `--pdf` for a proof to flip through.

### MPC booklet template, as measured
MPC's live `/dl/booklet-template/` links 404 as of Aug 2026; these were measured off the templates recovered from the Wayback Machine and cross-checked against MPC's [booklet spec table](https://www.makeplayingcards.com/pops/booklet-guide.html).

| | upload (full bleed) | trim | safe |
|---|---|---|---|
| Inside page | **1125 × 1575** (3.75×5.25 in) | 1050 × 1500 | 897 × 1428 |
| Cover, 72 sides | **2238 × 1575** (7.46×5.25 in) | 2160 × 1500 | per panel 897 × 1428 |

Bleed is ⅛ in (37.5 px) per edge. **The safe area is not centred:** the inset from the trim is ~117 px on the binding edge and ~37.5 px on the outer edge, and it *mirrors* — recto gutters left, verso gutters right. `booklet_mpc.py` lays every side into a gutter-aware box for exactly this reason.

Upload is **one raster per side** dragged into MPC's page grid — PNG/JPEG/TIFF, RGB, 300 DPI. **MPC does not accept a PDF for booklets** (they'll convert one at $2/page, $30 min — export PNGs instead). Files are named `NN-slug.png` so a filename sort *is* the page order.

**Open question, not settled:** MPC does not publish whether "72 sides" counts the cover faces. Their table lists *"Cover page **for** 72 pages"* as a separate artwork item at its own size and ships no inside-front/inside-back template, so the defensible reading is 72 interior faces **plus** a separate cover. The tool emits both — 72 numbered sides and `cover/cover-spread.png` — so either reading is covered. Worth one email to MPC before ordering.

## Sending to a printer
These files suit any printer that accepts a **3.5×5.25 in, 300 DPI, ⅛ in bleed** card with no crop marks (most online/offset card printers and print-on-demand services).

- **Best fit:** a service/shop that accepts a **custom 2:3 card size** (offset printers, or POD that allows custom dimensions). Upload `fronts/` as the fronts and `back.png` as the shared back.
- **Fixed-template services** use set sizes whose aspect differs from our 2:3 (0.67), so the art has to be adapted to their template. Two are already written, each a single command, each writing a gitignored directory (the output is ~73 MB; the upload zip ships as a GitHub release, not in git):
  - `python3 tools/export_mpc.py` → `print/mpc/` — **MakePlayingCards jumbo**, 3.5×5 in (0.70), upload 1125×1575. Fitted by height, side edges extended outward to reach the trim width. **This is the 63-card package** (see below).
  - `python3 tools/export_tgc.py` → `print/tgc/` — **The Game Crafter Jumbo Deck**, 3.5×5.5 in (0.636), upload 1125×1725, RGB only (they reject CMYK). Taller than our art rather than shorter, so there is nothing to extend into: the master is resized onto the trim, a 4.76% vertical stretch, which keeps the engraved frame running to all four edges.
  - Both typeset the title **after** the resize, through `tools/cardtitle.py`, so the name sits in its banner by the same relative rule as the house card. Any other vendor is a new `TRIM`/`FULL` pair away.

## The 63-card deck (MPC package, v6)
MakePlayingCards charges the same for any deck **up to 63 cards**, so the vendor package
is 52 oracle cards plus **eleven extras** — data in `data/extras.json`, art masters in
`cards/extras/`, every word on them typeset by `tools/extracard.py`:

| | |
|---|---|
| 2 | **jokers** — the Terrible Turtle radiant and shadow, with `JOKER` set in the rank medallion's own gold-on-dark language, top-left and mirrored bottom-right |
| 1 | **title card** — deck name, camp + address, and the oracle's URL |
| 2 | **reference cards** — how to read the oracle · how to deal the deck |
| 4 | **realm cards** — one per suit: the realm's own glyph, large, and its 1→13 arc in a line |
| 2 | **blanks** — frame, empty aged centre, empty banner: draw your own at camp |

Nine of the eleven are neither oracle nor playing cards; lift them out and the deck is
52 + 2 jokers. Nothing about the 52 changed in v6 — the fronts are byte-identical to v5.

**Filename order is deck order.** Fronts are named `<NN>-<slug>.jpg` (`01-title.jpg`,
`05-shell-01.jpg`, `60-joker-radiant.jpg`…), so a plain filename sort is the order a
fresh deck should arrive in: title, the two reference cards, then each realm behind its
own realm card (Ace→King), then the jokers, then the blanks. Drag them into MPC's
designer in that order.

## Quantity
~50 decks (one per camp member); the standing MPC order is 60. Confirm finish (matte
recommended for the woodcut look), card stock, and box option with your chosen printer.

## Regenerate
`python3 tools/print_prep.py` (uses the committed `cards/art/*.jpg` archive + `cards/back.png`, PIL only). Card names are typeset onto the empty banner at build time by `tools/cardtitle.py` — the same rule the web images use. Change `TRIM`/`DPI`/`BLEED` at the top to retarget size.
