/* Port of app/oracle/select.py — keyword scoring.
 *
 * Only the fallback half is carried over: the séance draws BLIND (deck.drawSpread),
 * and select_llm() is used solely by the legacy /api/reading flow, which the cloud
 * turtle does not serve. selectFallback is still needed — session.refineFallback
 * re-scores the realms when the model declines to rewrite a quest.
 */
import { rand } from "./util.js";

const STOP = new Set(
  ("the a an and or but of to in on for with i im i'm my me you your it its is am are was " +
    "be do dont don't should would could can cant can't what how why when if about at as this " +
    "that these those we our us they them he she his her").split(" "),
);

export function tokens(s) {
  const out = new Set();
  for (const t of ((s || "").toLowerCase().match(/[a-z']+/g) || [])) {
    if (!STOP.has(t) && t.length > 2) out.add(t);
  }
  return out;
}

function overlap(a, b) {
  let n = 0;
  for (const t of a) if (b.has(t)) n++;
  return n;
}

function score(qt, card) {
  const kw = tokens((card.keywords || []).join(" "));
  const body = tokens((card.reading || "") + " " + (card.shadow || ""));
  return 4 * overlap(qt, kw) + overlap(qt, body);
}

export function selectFallback(question, byRealm) {
  const qt = tokens(question);
  const out = {};
  for (const realm of ["roots", "trunk", "branches"]) {
    const ranked = byRealm[realm]
      .map((c) => ({ c, s: score(qt, c), r: rand() }))
      .sort((a, b) => b.s - a.s || b.r - a.r);
    out[realm] = ranked[0].c;
  }
  return out;
}
