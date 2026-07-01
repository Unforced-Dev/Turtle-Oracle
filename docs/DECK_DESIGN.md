# The Terrible Turtle Oracle
### *Black Rock City MMXXVI · "Move Slow & Bite Things"*

An AI-powered oracle deck for **Terrible Turtle** camp, built on the synchronicity between the camp's mascot and Burning Man 2026's theme.

> Working titles: **The Terrible Turtle Oracle** · *The Shell Oracle* · *Turtles All the Way Down*

---

## 1. The synchronicity (why this deck exists)

Burning Man 2026's theme is **Axis Mundi** — the **World Tree** that runs through nearly every human cosmology (Norse Yggdrasil, Maya Ceiba, Lakota cottonwood, the Bodhi tree): **roots** in the underworld, **trunk** in the middle world, **branches** in the heavens; the column that connects us to powers greater than ourselves. Of 75 funded 2026 art pieces, 41 proposals were trees.

In many of those same cosmologies, the World Tree grows from the back of the **World Turtle** — "Turtle Island," *turtles all the way down.* The turtle is what *carries* the axis.

**So Terrible Turtle's mascot is the foundation the entire 2026 theme stands on.** "Move Slow & Bite Things" is the turtle who patiently carries the cosmos. That image is the deck's spine.

```
        ✦ BRANCHES   →  the heavens / what you reach for
        │
        │ TRUNK      →  the middle world / where you stand now
        │
       ╱│╲ ROOTS     →  the underworld / what's beneath & buried
     ~~~~🐢~~~~       →  THE WORLD TURTLE: what carries it all
```

---

## 2. Format: an Oracle with a tree for a skeleton

Not strict tarot (its Swords/Cups/Wands structure would feel like a costume on the playa), but not a shapeless oracle either. The **World Tree gives structural power without tarot's baggage.**

**48 cards = 4 realms × 12.**

| Realm | Cosmic layer | Domain | Spread position |
|---|---|---|---|
| **Shell** (12) | the Turtle beneath | major archetypes; load-bearing life truths | *wild / the axis speaks* |
| **Roots** (12) | underworld | shadow, grief, the buried, ancestry, release | ***what to face*** |
| **Trunk** (12) | middle world | body, presence, endurance, "move slow," survival | ***where you stand*** |
| **Branches** (12) | heavens | connection, ecstasy, aspiration, the sunrise, reaching | ***what to grow toward*** |

### The core spread — "The Tree" (3 cards)
Pull one **Root**, one **Trunk**, one **Branch**:
- Root = *what's beneath you / what to face or release*
- Trunk = *where you stand / how to hold the present*
- Branch = *what you're growing toward / where to reach*

The three are **woven into one arc**, not read as three separate horoscopes. If a **Shell** card is drawn (it can substitute into any position), the axis itself is speaking — the reading centers on that archetype.

---

## 3. Two tracks: a timeless print deck + a live 2026 app

The deck lives in two forms, joined by the `live_hook` field on every card:

**🃏 The Print Deck (timeless, ~50 physical copies).** Recurring Burning Man + Terrible Turtle. The card *meanings* (Reading, Turtle Dare) are universal life-wisdom, so they're timeless as-is; we keep the woodcut art. Each card's **anchor is its timeless BM pattern** (the Man burns every year, the sunrise sound camp, the Temple, the deep-playa wander), not a single-year installation. A deck every camper carries, pulls, and shares for years.

**📱 The App (2026-sourced, live).** The *same 48 archetypes*, but at read-time the app overlays **this year's real specifics + locations** via `data/playa_2026.json`, keyed by each card's `live_hook`: which real camps/art/events match, *where they are* on the BRC clock-grid, and wayfinding for the adventure. Built now from public data, then **refreshed from the Burning Man API in August** (see `data/README.md`).

Cards still record a `real_2026` reference with a **confidence**; that specificity now feeds the *app overlay*, while the printed card stays archetypal. We are honest about confidence rather than inventing.

---

## 4. Card anatomy

Printed on the card:
- **Name** + realm glyph
- **Art**
- **The Reading** — the life-wisdom (2-4 sentences; the honest, non-saccharine insight)
- **The Turtle Dare** — one concrete adventure into the burn tied to the card

Data-only (drives the app, not necessarily printed):
- `keywords`, `shadow` (optional counter-reading), `real_2026` reference + confidence
- `live_hook` — a tag the digital oracle uses to bind the card to live/current event data (e.g. tonight's sets, this afternoon's workshops)
- `image_prompt`

See `data/card.schema.json` for the exact structure.

---

## 5. The digital oracle

```
voice question  →  transcribe  →  LLM (full deck + pre-loaded 2026 event data)
   →  pull 1 Root + 1 Trunk + 1 Branch resonant to the question
   →  weave ONE reading across the three (face / stand / reach)
   →  hand over ONE doable adventure into the burn tonight
   →  (optional) speak it back in the Turtle's slow voice
```

The magic is the **weave** — a single arc landing on one real quest, not three fortunes.

### Hard constraint: no internet on playa
The app must be **fully self-contained**: a local model (or pre-generated readings) + the 2026 What/Where/When event data loaded **before** leaving for the desert. Runs on a laptop/mini-PC inside the shell — the "live" 2026 data is a static snapshot, not a network call.

---

## 6. Build order

1. **Deck content** — write all 48 cards (names, readings, Turtle Dares, realms, real_2026 refs). ← *current phase*
2. **Art** — image prompts → generate card art (codex image gen), lock a visual style.
3. **Print** — layout for a physical deck.
4. **App** — voice in → weave → adventure out; self-contained for playa.

---

## 7. Research inputs

Card material is seeded from live research into real BRC 2026 elements (see `docs/research/` — funded honoraria art, sound camps & art cars, Temple/Man & rituals, recurring theme camps & workshops, Terrible Turtle's own plans). Each seed = a real thing + the life-theme it evokes + best realm + a candidate Turtle Dare.
