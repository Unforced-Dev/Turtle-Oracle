# Visual Style Guide — The Terrible Turtle Oracle

**Chosen direction: Mythic Woodcut + Gold.** All 48 cards must read as one deck.

This guide is the shared contract, and `tools/gen_art.py` is its executable copy — the
`PREAMBLE`, `TREE_FRAME`, `SHELL_FRAME`, `CARTOUCHE`, `GLYPH` and `REALM_TONE` constants
there say exactly what is written below. **If you change one, change the other in the
same commit.** A guide that disagrees with the generator is worse than no guide.

## What went wrong the first time (and why this doc is now specific)

The v1 deck came back as 48 individually decent cards rather than one deck. Every fault
was in the *furniture*, never the subject:

1. The Shell twelve ran **two different frame systems** — half ornate gold-on-black with
   corner medallions, half a plain thin keyline on pale kraft.
2. The title banner took **three different shapes** — plain rectangle, ornate shaped
   cartouche, and a wavy ribbon scroll with rolled ends that had taken over most of the
   Branches row.
3. **Ground value drifted inside a single realm** — a night-black Shell card beside a
   pale one, a Roots card with no indigo below the line at all.
4. The **realm glyph wandered** between corners, or vanished.
5. A few cards **left the woodcut idiom** and read as soft illustration (*Center Camp*,
   *Playa Info & the Rangers*).

The fix is the same in all five cases: **specify the furniture the way a printer would —
which ink, exactly where, how much of the card it covers — never as an adjective.**
Adjectives are what drifted. "Ornate frame" and "bottom cartouche" are adjectives.

## Core aesthetic

- **Medium look:** hand-carved woodblock / letterpress relief print. Every tone is built
  from carved marks — parallel hatching, cross-hatch, stipple, chatter, and white gouges
  where the block was cut away. Flat opaque ink, hard edges, strong figure–ground.
- **This is a relief print, not a drawing of one.** No airbrush, no soft or blended
  shading, no gradients, no painterly light, no rendered skin/cloth/metal, no 3D, no
  photography, no pencil sketch, no comic inking, no storybook warmth. Faces and hands
  are carved exactly like rock and cloth: blunt, angular, hatched, never modelled. If a
  passage could pass for a soft digital illustration, it is wrong.
- **Exactly three inks** touch the paper — black, metallic gold, and the realm's second
  ink — with no blends in between. Stock is warm desert-tan kraft with visible grain.
- **Composition:** mythic and heraldic, centred, symmetrical, iconic, with calm breathing
  space; a subtle vertical World-Tree axis motif somewhere on every card.
- **Setting, always:** the Black Rock Desert — flat pale alkali playa, cracked dust,
  distant barren mountains, enormous sky. No trees but the World Tree itself.

## The frame — two frames in the deck, on purpose, and exactly two

The Shell twelve are the axis, surfaced by the séance about one card in ten, and they are
meant to be identifiable from across a dusty tent before anyone reads the name. Their
heavier furniture **is** the design. What was never the design was half of them printing
the plain frame.

**Roots · Trunk · Branches — one identical plain frame:**
a plain rectangular double keyline in gold and nothing else. Outer rule inset **3% of the
card width** from the edge; inner rule **1.5% further in**; both hairline weight, bare
kraft showing between them; square mitred corners. **No** corner bosses, medallions,
rosettes, filigree, engraved band, black frame ground, or third rule.

**Shell — one identical ornate frame:**
gold-on-black. A solid black band inset **2% of the card width**, running the full
perimeter at **6% of the card width** (~8× a plain rule), filled edge to edge with a
repeating engraved gold vine/dot/lozenge ornament and bounded by a fine gold hairline on
both edges. A **circular gold boss at each of the four corners**, the full width of the
band, carrying a rosette — except the **top-left boss, which carries the turtle-shell
glyph**. Never a plain keyline on a Shell card.

## The title banner — one shape for all 48

One **plain rectangular banner, square corners, flat and horizontal**:

| | |
|---|---|
| top edge | 84.5% down the image |
| bottom edge | 93% down the image |
| width | 76% of the image width, centred |
| contents | **empty** — bare kraft inside a single fine keyline |

**Not** a ribbon, scroll or banderole. No curled or rolled ends, wavy or draped edges,
swallowtails, scallops, lobes, tapers, or corner ornaments.

The banner is left blank on purpose: image models misspell, and 48 cards each misspelling
differently is the fastest way to lose deck cohesion. `tools/print_prep.py` composites the
name in one face at one size rule across the whole deck.

> **The geometry is load-bearing.** `print_prep.py` centres the title baseline at
> `TITLE_Y = 0.888` of card height and shrinks the face until the tracked line fits
> `TITLE_MAX_W = 0.66` of card width. The band above is centred on 0.888 and is 0.76 wide,
> clearing the longest name with margin. Move one, move the other.

## The realm glyph — always present, always top-left

A small carved mark, **~5% of the card width**, just inside the frame at the **top-left
corner and nowhere else**, on every card without exception:

| Realm | Glyph |
|---|---|
| Shell | turtle-shell glyph — it rides inside the top-left corner boss |
| Roots | root-knot, in a plain circular medallion |
| Trunk | trunk-ring (concentric growth rings), in a plain circular medallion |
| Branches | branch-star, in a plain circular medallion |

## Second ink and ground value — one fixed value per realm

The undertone is a **second spot colour printed alongside the black and gold**, and must
be described that way. Naming a colour alone gets ignored: "deep indigo undertone"
produced cards indistinguishable from the kraft default. **Ground value** is the same
lesson applied to overall darkness — it fixes where the horizon sits and how dark the card
is allowed to print.

| Realm | Second ink — where it goes | Ground value — fixed across all twelve |
|---|---|---|
| **Shell** | Metallic gold, lavishly: full radiant sunburst behind the subject, gilded ornament throughout, gold rules and nodes along the axis. | Warm mid-tan kraft field; the sunburst covers the middle two-thirds. Gold-dominant at the same brightness every time. **Never** a black-flooded field, night sky, or washed-out pale card — the black lives in the frame band and the linework. |
| **Roots** | Deep indigo: the entire lower half below the ground line prints indigo instead of black, soaking the subterranean cross-hatching. Reads blue-black, not brown. Gold only as a small accent. | The ground line **cuts the image exactly in half** — not a third, not two thirds. Top half: bare warm kraft, light linework, open pale sky. Bottom half: solid dark indigo at one density, corner to corner. **Never** warm tan below the line; never a dark sky. |
| **Trunk** | Burnt rust-orange ochre: rust in the sky wash, the horizon band, and the midtones. Balanced, upright, weighty. | Horizon across the full width at **45% of image height**. Above: sky solidly rust-orange at one saturation. Below: pale cracked playa, bare kraft, black linework only. **Never** pale, blue, or night. |
| **Branches** | Pale sky blue: filling the open sky, in the leaves and small carved stars. Upward reach, airy negative space. | Pale sky blue fills the whole **top half**; the cracked playa gets the bottom half, horizon crossing at exactly half the image height, corner to corner. The subject stays small in that bottom half rather than pushing the horizon up. **Never** dark, night, rust or black — always the lightest card on the table. |

> **Horizon numbers are the softest part of this spec.** In the v2 sample row the model
> honoured the frame, banner, glyph and ink assignments exactly, but treated horizon
> percentages as suggestions: Branches' horizon came back at ~30% of the height when the
> spec said 68%, and only moved to ~half once the clause was rewritten as *"pale sky blue
> fills the WHOLE TOP TWO THIRDS … the subject stays small in the bottom third, do not
> raise the horizon to fit it in."* Roots' "cuts the image exactly in half" landed first
> try. Prefer plain fractions and an explicit instruction about what to do with the
> subject; expect the horizon to land within a band rather than on the number.
>
> **Resolution (approved 2026-08-11): Branches is specified at half.** The model
> reliably delivered ~half no matter how the two-thirds clause was worded, so the spec
> was restated to the value it actually hits — a rule the model obeys beats a prettier
> rule it fuzzes differently on each card. The sample card (`branches-09`) was generated
> under the old two-thirds wording, which rendered as half; its archived prompt in
> `cards/art-v2/prompts-used.json` therefore predates this clause.

## Format

Portrait **2:3** — generated at 1024×1536, printed at 3.5 × 5.25 in @ 300 DPI with 1/8"
bleed added by extending edge pixels outward, so no gold border is ever trimmed.

## Consistency checklist (per generated card)

1. Correct frame for the realm, and *only* that frame.
2. Plain rectangular banner at the fixed geometry, empty.
3. Realm glyph present, top-left, nowhere else.
4. Realm ground value matched — horizon in the right place, correct darkness.
5. Only black + gold + the realm's second ink.
6. Carved marks everywhere; no soft rendering, especially on faces and hands.
7. Axis motif present; subject centred with breathing room; setting is the playa.

## Cover / box

Likely **The World Turtle** or **The Resonant Spire** as the box art (the spire literally
turns voices into light — the oracle as sculpture). Full-gold treatment.
