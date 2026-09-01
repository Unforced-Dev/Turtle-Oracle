/* Port of app/oracle/deck.py — the deck and the Tree spread.
 *
 * The Python version reads data/cards.json off disk with a retry loop (the art batch
 * may be mid-write). A Worker has no disk: the deck is bundled at build time, so it
 * is always whole and the retry loop disappears.
 */
import CARDS_DATA from "../../data/cards.json" with { type: "json" };
import { rand, choice } from "./util.js";

export const SPREAD_REALMS = ["roots", "trunk", "branches"];

export const SLOT_LABEL = {
  roots: "what to face",
  trunk: "where you stand",
  branches: "what to reach for",
  shell: "the axis speaks",
};

export const DECK = CARDS_DATA;
export const CARDS = CARDS_DATA.cards;

export const BY_REALM = (() => {
  const out = {};
  for (const c of CARDS) (out[c.realm] = out[c.realm] || []).push(c);
  return out;
})();

/** Pure chance, one card per slot. Returns {picks, axisSlot|null}. */
export function drawSpread(byRealm, shellChance) {
  const picks = {};
  for (const slot of SPREAD_REALMS) picks[slot] = choice(byRealm[slot]);
  let axisSlot = null;
  if ((byRealm.shell || []).length && rand() < shellChance) {
    axisSlot = choice(SPREAD_REALMS);
    picks[axisSlot] = choice(byRealm.shell);
  }
  return { picks, axisSlot };
}

/* Every card in cards/web/{med,thumb} is built by tools/webimg.py for the whole deck,
 * and cloud/prepare-assets.sh copies all of them. So unlike the Python server — which
 * stats each file and degrades to /art/*.png — the cloud paths are unconditional. */
export function cardPayload(c, loc) {
  loc = loc || {};
  return {
    id: c.id,
    name: c.name,
    realm: c.realm,
    slot: SLOT_LABEL[c.realm] || "",
    reading: c.reading,
    shadow: c.shadow || "",
    turtle_dare: c.turtle_dare,
    real_2026: c.real_2026.name,
    location: {
      directions: loc.directions || "",
      status: loc.status || "",
      clock: loc.clock === undefined ? null : loc.clock,
    },
    image: `/med/${c.id}.jpg`,
    thumb: `/thumb/${c.id}.jpg`,
  };
}
