/* Port of app/oracle/geo.py — a card's live_hook resolved to a real BRC 2026 place. */
import GEO from "../../data/brc_geo.json" with { type: "json" };
import PLAYA from "../../data/playa_2026.json" with { type: "json" };

const HOOKS = PLAYA.hooks;
const LANDMARKS = GEO.landmarks;
const ZONES = GEO.zones;

export const COMPASS_ROSE = [
  "      12  Temple / deep playa",
  "            \\   |   /",
  "  10 --------(MAN)-------- 2",
  "            /   |   \\",
  "       7   Center Camp   5",
  "               6",
].join("\n");

export function locate(card) {
  const hook = card.live_hook;
  const h = (hook && HOOKS[hook]) || {};
  const geoRef = h.geo_ref;
  const lm = geoRef ? LANDMARKS[geoRef] || ZONES[geoRef] || null : null;
  const directions = h.directions || (lm ? lm.directions : "") || "";
  return {
    instances: h.instances || [(card.real_2026 || {}).name || card.name],
    directions,
    status: h.status || "citywide",
    clock: lm ? (lm.clock === undefined ? null : lm.clock) : null,
    street: lm ? (lm.street === undefined ? null : lm.street) : null,
    geo_ref: geoRef === undefined ? null : geoRef,
  };
}

export function locateSpread(picks) {
  const out = {};
  for (const [realm, card] of Object.entries(picks)) out[realm] = locate(card);
  return out;
}

export function directionsLines(picks, located) {
  return ["roots", "trunk", "branches"].map((realm) => {
    const c = picks[realm];
    const where = located[realm].directions || "Somewhere out there — ask Playa Info.";
    return `${c.name}: ${where}`;
  });
}
