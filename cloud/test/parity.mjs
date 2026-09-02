/* Does the cloud turtle still say the same words as the playa turtle?
 *
 *   node cloud/test/parity.mjs        (needs python3 on PATH, as this repo already does)
 *
 * The séance's quality lives in five strings: the SYSTEM voice and the four prompts.
 * They were tuned by ear over a week and they now exist twice — once in app/oracle/,
 * once in cloud/src/. Two copies of a tuned string is exactly the thing that rots.
 *
 * So this builds every prompt on BOTH sides from the SAME fixture and diffs them byte
 * for byte, then repeats the structural checks tools/test_spoken_readings.py makes of
 * the Python (verbatim echo quotes, spoken word budgets, the stub-quest rejection)
 * against the JavaScript. It is not a mock of the port; it runs the port.
 *
 * The only normalisation is the wall clock: both sides stamp the current Black Rock City
 * minute into CONTEXT, and the two processes can straddle a minute boundary.
 */
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { BY_REALM } from "../src/deck.js";
import { locateSpread } from "../src/geo.js";
import { SYSTEM, weaveLlm, weaveFallback, biteRealm, landmarkRealm, standsSomewhere } from "../src/weave.js";
import { __test as S } from "../src/session.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");

let failures = 0;
let skipped = 0;
function check(label, ok, detail = "") {
  console.log((ok ? "  ok   " : "  FAIL ") + label + (ok || !detail ? "" : "\n         " + detail));
  if (!ok) failures++;
}

/* A prompt the cloud has deliberately moved ahead on. NOT a failure and NOT a pass: the
 * two turtles genuinely say different words here, on purpose, and the byte-diff would
 * only ever fail. Every skip names what diverged and what has to happen to retire it. */
function skip(label, why) {
  console.log("  skip " + label + "\n         " + why);
  skipped++;
}
const AHEAD =
  "cloud is ahead of the Spark as of feat/cloud-seance-v2 — port back when the Spark " +
  "is reachable, then restore the byte-diff.";

/** Both sides write "It is Sunday, 4:19 PM in Black Rock City: ..." — pin the minute. */
function normalise(s) {
  return String(s || "").replace(
    /It is [A-Za-z]+, \d{1,2}:\d{2} (AM|PM) in Black Rock City/g,
    "It is <CLOCK> in Black Rock City",
  );
}

function firstDiff(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] !== b[i]) {
      return `at char ${i}:\n         py: ${JSON.stringify(a.slice(Math.max(0, i - 40), i + 60))}\n         js: ${JSON.stringify(b.slice(Math.max(0, i - 40), i + 60))}`;
    }
  }
  return a.length === b.length ? "" : `same prefix, lengths differ py=${a.length} js=${b.length}`;
}

/* ---- the fixture, shared by both sides ------------------------------------------- */

/* Why these three ids. ONE BEARING (the bite says a kind of place, never an address, unless
 * the card stands at one of the four placements nobody can miss) only says anything on a
 * spread with no unmissable landmark in it — and WHICH cards resolve where is data, not a
 * constant: data/playa_2026.json gains addresses every time the BRC directories are
 * re-fetched. So the fixture is a plain draw with no landmark, and the landmark branch of
 * the prompt is checked below against a draw built by hand. The checks read the bite off
 * `located` rather than trust this. */
const CARD_IDS = { roots: "roots-05", trunk: "trunk-13", branches: "branches-10" };
const WEATHER_ID = "thunderhead";
const SHARES = [
  "I keep swallowing… the thing I want to say to my sister, because my friends all think I am " +
    "the calm one and I keep swallowing how angry I actually am about it",
  "I am carrying: Grief, Too Many People.",
  "I secretly want to sing in front of people and I have never done it once",
];
const ADVENTURE =
  "Tonight, one bite. Say the sentence you have been swallowing about your sister out loud, to " +
  "the first stranger who hands you water — no hedging, no laugh at the end. Bring back what " +
  "their face did.";

/* ---- the Python side ------------------------------------------------------------- */

const PY = `
import json, sys
sys.path.insert(0, ${JSON.stringify(path.join(REPO, "app"))})
from oracle.deck import load_deck
from oracle.geo import locate_spread
from oracle import weave as W
from oracle import session as S

fx = json.loads(sys.stdin.read())
_, _, by = load_deck()
picks = {r: next(c for c in by[r] if c["id"] == cid) for r, cid in fx["card_ids"].items()}
located = locate_spread(picks)

class Cap:
    def __init__(self): self.p = None
    def available(self): return True
    def generate(self, prompt, system=None, **kw):
        self.p = prompt
        return None

sess = {"id": "fixture", "weather": fx["weather"], "shares": fx["shares"], "stones": [],
        "ground": 0.0, "axis_slot": None, "prior_line": None, "picks": picks,
        "located": located, "adventure": fx["adventure"]}

told = " ".join(S._seeker_words(sess))
ctx = S._context(sess)

cw = Cap(); W.weave_llm(told, picks, cw, located, context=ctx)
ce = Cap(); S._echoes_llm(sess, ce)
cr = Cap(); S._refine_llm(sess, cr)
cs = Cap(); S._seal_llm(sess, cs)

json.dump({
    "system": W.SYSTEM,
    "context": ctx,
    "told": told,
    "seeker_words": S._seeker_words(sess),
    "weave": cw.p, "echoes": ce.p, "refine": cr.p, "seal": cs.p,
    "weave_fallback": W.weave_fallback(told, picks, located),
    "echoes_fallback": S._echoes_fallback(sess),
    "names": [S._extract_name(t) for t in fx["names"]],
    "time_context": S._time_context(),
}, sys.stdout, ensure_ascii=False)
`;

const NAMES = [
  "um, hi there, I'm Wren",
  "they call me BRAMBLEFOOT, and I have returned",
  "hello hello my name is dusty pete the third and more",
  "",
];

const fixture = {
  card_ids: CARD_IDS,
  weather: WEATHER_ID,
  shares: SHARES,
  adventure: ADVENTURE,
  names: NAMES,
};

let py;
try {
  py = JSON.parse(
    execFileSync("python3", ["-c", PY], {
      input: JSON.stringify(fixture),
      encoding: "utf-8",
      maxBuffer: 32 * 1024 * 1024,
    }),
  );
} catch (err) {
  console.error("could not run the Python side:", err.message);
  process.exit(2);
}

/* ---- the JavaScript side --------------------------------------------------------- */

const picks = Object.fromEntries(
  Object.entries(CARD_IDS).map(([r, id]) => [r, BY_REALM[r].find((c) => c.id === id)]),
);
const located = locateSpread(picks);

/* What the 2026 data actually says about THIS spread, read off `located` instead of assumed.
 * The bite is one card, and whether its quest may name a place at all depends on that card
 * standing at one of the four unmissable landmarks. Every bite check below is stated against
 * these rather than against a card id. */
const REALMS = ["roots", "trunk", "branches"];
const SLOT_TITLES = { roots: "FACE", trunk: "STAND", branches: "REACH" };
const BITE = biteRealm(located, picks);
const LANDMARK = landmarkRealm(located);
const spread = () =>
  `the bite is ${SLOT_TITLES[BITE]} (${picks[BITE].name}), landmark: ${LANDMARK || "none"}`;

const sess = {
  id: "fixture",
  weather: WEATHER_ID,
  shares: SHARES,
  stones: [],
  ground: 0.0,
  axis_slot: null,
  prior_line: null,
  picks,
  located,
  adventure: ADVENTURE,
};

class Cap {
  constructor() {
    this.p = null;
  }
  available() {
    return true;
  }
  async generate(prompt) {
    this.p = prompt;
    return null;
  }
}

const told = S.seekerWords(sess).join(" ");
const ctx = S.context(sess);

const cw = new Cap();
await weaveLlm(told, picks, cw, located, ctx, 1);
const ce = new Cap();
await S.echoesLlm(sess, ce, 1);
const cr = new Cap();
await S.refineLlm(sess, cr, 1);
const cs = new Cap();
await S.sealLlm(sess, cs, 1);

/* ---- 1. the five tuned strings must be identical --------------------------------- */

console.log("\nprompt parity with app/oracle (byte for byte):");
check("SYSTEM voice", SYSTEM === py.system, firstDiff(py.system, SYSTEM));
/* The weave prompt's quest half diverged on feat/cloud-seance-v2 and again on
 * fix/seance-smooth: the playa turtle asks for three moves with real 2026 places in them,
 * the cloud turtle asks for ONE act of 20-40 words with a bearing and a proof. The READING
 * half of this prompt is untouched and still says the same words — but the two halves are
 * built as one string, so the byte-diff cannot see that; the structural checks below hold
 * the reading's budget instead. */
skip("weave prompt (quest rules: one bite, one bearing, one proof)", AHEAD);
/* The seal prompt diverged for the same reason the weave prompt did, one stage later: the
 * playa turtle seals three moves, the cloud turtle seals the one bite the seeker heard,
 * with a bearing instead of an address. Retire this skip by porting the same shape into
 * app/oracle/session.py's _seal_llm. */
skip("seal prompt (one bite: act, bearing, proof)", AHEAD);
/* The echoes prompt gained one paragraph the Spark does not have yet: what a quotable
 * phrase IS — a clause with a noun or a verb in it, cut at the seeker's own punctuation.
 * Everything the Spark's version says is still said, in the same words and the same
 * order. Retire this skip by porting that paragraph into app/oracle/session.py. */
skip("echoes prompt (quote a clause, not a word count)", AHEAD);
/* The refine prompt diverged with the two above and for the same reason: the playa turtle
 * rewrites three moves around the new truth, the cloud turtle rewrites the ONE bite the
 * seeker heard. Retire this skip by porting the one-bite quest into app/oracle. */
skip("refine prompt (rewrite the one bite, not three moves)", AHEAD);
check("CONTEXT block", normalise(py.context) === normalise(ctx), firstDiff(normalise(py.context), normalise(ctx)));
check(
  "time-of-day phrasing",
  normalise(py.time_context) === normalise(S.timeContext()),
  firstDiff(normalise(py.time_context), normalise(S.timeContext())),
);

/* ---- 2. deterministic helpers must agree ----------------------------------------- */

console.log("\ndeterministic helpers agree with the Python:");
check(
  "seeker words (UI stem and stone labels stripped)",
  JSON.stringify(S.seekerWords(sess)) === JSON.stringify(py.seeker_words),
  `py=${JSON.stringify(py.seeker_words)}\n         js=${JSON.stringify(S.seekerWords(sess))}`,
);
check(
  "name extraction",
  JSON.stringify(NAMES.map(S.extractName)) === JSON.stringify(py.names),
  `py=${JSON.stringify(py.names)}\n         js=${JSON.stringify(NAMES.map(S.extractName))}`,
);
const jsEch = S.echoesFallback(sess);
/* The same divergence, in the offline half: the Python cuts fixed seven-word windows out
 * of what the seeker said, the cloud cuts at their punctuation and trims the edges back to
 * real words ("out to the trash fence alone and" is what the fixed window gives on a
 * two-minute story). Both are verbatim and 3-8 words — the structural checks below still
 * run on the cloud's — but the phrases chosen differ, so the byte-diff cannot. */
skip("fallback echoes (clause-shaped windows, not fixed-width ones)", AHEAD);
console.log("         cloud picks: " + JSON.stringify(Object.values(jsEch).map((l) => l.split("“")[1].split("”")[0])));
const jsWf = weaveFallback(told, picks, located);
check(
  "fallback reading",
  jsWf.reading === py.weave_fallback.reading,
  firstDiff(py.weave_fallback.reading, jsWf.reading),
);
/* Same divergence, offline half: the Python stitches three dares into First/Second/Third,
 * the cloud speaks one dare with a bearing and a proof. The reading above is untouched by
 * that and still diffs. */
skip("fallback quest (one bite, not First/Second/Third)", AHEAD);

/* ---- 3. the structural guarantees tools/test_spoken_readings.py makes ------------ */

console.log("\nstructural guarantees (mirrors tools/test_spoken_readings.py):");
const spoken = S.seekerWords(sess);
const quotes = Object.values(jsEch).map((l) => l.split("“")[1].split("”")[0]);
check("fallback chooses three distinct seeker phrases", new Set(quotes).size === 3);
check(
  "every fallback quote is verbatim and 3-8 words",
  Object.values(jsEch).every((l) => S.validEcho(l, spoken)),
);
check(
  "fallback echoes stay short enough to speak on a card turn",
  Object.values(jsEch).every((l) => l.split(/\s+/).length <= 22),
);

const echoLlm = {
  available: () => true,
  generate: async () =>
    JSON.stringify({
      roots: "You said “words I invented here” — no.",
      trunk: "You said “I am the calm one and I” — the trunk can hold that.",
      branches: "The future is bright.",
    }),
};
const mixed = await S.echoesLlm(sess, echoLlm, 1);
check("valid model echo survives", mixed.trunk.startsWith("You said “I am the calm one and I”"), mixed.trunk);
check(
  "invented and unquoted model echoes fall back",
  mixed.roots === jsEch.roots && mixed.branches === jsEch.branches,
);
const stonesOnly = { ...sess, shares: ["I am carrying: Grief, Too Many People."] };
check(
  "stone taps are never fabricated into spoken quotes",
  (await S.echoesLlm(stonesOnly, echoLlm, 1)) === null &&
    Object.values(S.echoesFallback(stonesOnly)).every((l) => !l.includes("“")),
);

const rw = jsWf.reading.split(/\s+/).length;
const qw = jsWf.adventure.split(/\s+/).length;
check(`fallback reading fits a spoken-length budget (${rw}w)`, rw >= 70 && rw <= 125);
check(
  `fallback quest is one bite — act, bearing, proof (${qw}w)`,
  qw <= 90 &&
    !/\b(First|Second|Third)[.,]/.test(jsWf.adventure) &&
    /Bring back /.test(jsWf.adventure),
  jsWf.adventure,
);
check(
  "runtime prompt carries spoken word budgets",
  cw.p.includes("90-120 words") && cw.p.includes("20-40 words"),
);
check(
  "system voice bans prose that reads poorly aloud",
  SYSTEM.includes("spoken aloud") && SYSTEM.includes("no semicolons"),
);

/* The skips above are only safe if SOMETHING still guards the diverged strings. This is
 * that something: the cloud's own rule, checked on the cloud's own side. */
/* Guard the guard: if a data refresh ever puts this fixture's bite at a landmark, the
 * bearing checks would go quietly vacuous, so fail here first and say to repick CARD_IDS. */
check(
  "the fixture is still a draw with no unmissable landmark in it",
  LANDMARK === null,
  spread() + " — repick CARD_IDS above; the bearing rule needs a draw without one.",
);
check(
  "quest prompt asks for ONE act, built from ONE named card",
  (cw.p.match(/ONE BITE, not an errand list/g) || []).length === 1 &&
    cw.p.includes("in 20-40 words") &&
    cw.p.includes(`built from the “${picks[BITE].name}” card`) &&
    cw.p.includes("- THE BITE: one act, and only one.") &&
    !cw.p.includes("THE ANCHOR") &&
    !cw.p.includes("First, Second, Third"),
  spread(),
);
check(
  "quest prompt keeps THE CROSSING and folds THE SACRIFICE in",
  cw.p.includes("- THE CROSSING: the act is the thing the seeker confessed they avoid") &&
    cw.p.includes("- THE SACRIFICE, when it falls out of that on its own"),
);
/* ONE BEARING opened up on feat/pull-first: the bite may name the place ITS OWN card
 * stands at, with a rough direction, or stay metaphorical — the model chooses, and about
 * half should point at the real place. Two things did not move: the address, and the
 * thirteen cards that hook onto a PRINCIPLE rather than a place. This fixture's bite is
 * one of those thirteen, so it is the control for the closed half of the rule; the two
 * open ones are built by hand below. */
check(
  "the fixture's bite is still a card that stands nowhere in the city",
  standsSomewhere(located[BITE]) === false,
  spread() + " — the bearing checks below need a citywide bite; repick CARD_IDS.",
);
check(
  "a bite on a card that stands nowhere gets the open bearing, and no place to name",
  cw.p.includes("This card does not stand anywhere in the city") &&
    cw.p.includes("NO address, NO clock, NO street, NO camp name.") &&
    !cw.p.includes("NAME THE PLACE"),
  spread(),
);
check(
  "quest prompt still asks for one proof and no interior door",
  cw.p.includes("- ONE PROOF: end on the single thing they carry back to the Turtle") &&
    cw.p.includes("no 'stay until…'"),
);
/* A bite the city DID put somewhere, and not at one of the four unmissable landmarks: the
 * two ways are offered, and only the landmark case is told how to phrase it. */
const fxPicks = { ...picks, roots: BY_REALM.roots.find((c) => c.id === "roots-02") };
const fxLocated = locateSpread(fxPicks);
const fxCap = new Cap();
await weaveLlm(told, fxPicks, fxCap, fxLocated, ctx, 1);
const FXBITE = biteRealm(fxLocated, fxPicks);
check(
  "a placed bite is offered both bearings — its own place, or an open one",
  standsSomewhere(fxLocated[FXBITE]) &&
    fxCap.p.includes("- ONE BEARING: say where, in one short phrase, and you have two ways") &&
    fxCap.p.includes(
      `NAME THE PLACE this card stands at in this year's city — ${fxPicks[FXBITE].real_2026.name} —`,
    ) &&
    fxCap.p.includes("Or give an OPEN BEARING: a kind of place, a kind of person, or a time of day") &&
    fxCap.p.includes("take the real place about half the time") &&
    fxCap.p.includes(`no camp but ${fxPicks[FXBITE].real_2026.name}`) &&
    fxCap.p.includes("NO address, NO clock time, NO lettered street, NO Esplanade") &&
    !fxCap.p.includes("said like this:"),
  `placed draw bites ${FXBITE} (${fxPicks[FXBITE].name} at ${fxPicks[FXBITE].real_2026.name})`,
);
/* The control for the check above: every bite may now name its own place, but a bite at
 * one of the four UNMISSABLE landmarks is the one that is also told HOW to say it — by its
 * name and a direction, never by its clock-and-street line. A draw that stands at one is
 * built by hand, because which cards resolve where is data, not a constant. */
const lmPicks = { ...picks, trunk: BY_REALM.trunk.find((c) => c.id === "trunk-05") };
const lmLocated = locateSpread(lmPicks);
const lmCap = new Cap();
await weaveLlm(told, lmPicks, lmCap, lmLocated, ctx, 1);
check(
  "a bite at a landmark is told to name it by its name and a direction",
  landmarkRealm(lmLocated) === "trunk" &&
    biteRealm(lmLocated, lmPicks) === "trunk" &&
    lmCap.p.includes(
      "NAME THE PLACE this card stands at in this year's city — Center Camp — with a rough " +
        "direction and nothing else pinned to it, said like this: Center Camp — the heart of " +
        "the city. Walk toward the center.",
    ) &&
    // the card's own data line still carries the clock-and-street address; the BEARING
    // the Turtle is told to speak must not, which is the whole point of LANDMARK_WHERE
    !lmCap.p.slice(lmCap.p.indexOf("- ONE BEARING")).includes("Esplanade)") &&
    !cw.p.includes("said like this:"),
  `landmark draw bites ${biteRealm(lmLocated, lmPicks)}`,
);
/* The pull: a séance where the seeker said nothing must still get a real reading and a
 * real bite, and the prompt must never treat the silence as a refusal. */
const pullCap = new Cap();
await weaveLlm("The seeker could not put it into words.", picks, pullCap, located, ctx, 1, {
  pulled: true,
  look: "Three cards, one thread, and none of them is asking you a question yet.",
});
check(
  "the weave knows when the seeker let the cards speak",
  pullCap.p.startsWith("A seeker gave their name and asked for nothing else.") &&
    pullCap.p.includes("That is an answer, not a refusal") &&
    !pullCap.p.includes("A seeker shared:") &&
    pullCap.p.includes("60-120 words") &&
    pullCap.p.includes("You know nothing about this seeker") &&
    !pullCap.p.includes("take one EXACT word or phrase the seeker said"),
);
check(
  "the weave continues the look it already gave, rather than starting over",
  pullCap.p.includes("YOU HAVE ALREADY SPOKEN ONCE.") &&
    pullCap.p.includes("Three cards, one thread, and none of them is asking you a question yet.") &&
    pullCap.p.includes("never start the reading over") &&
    !cw.p.includes("YOU HAVE ALREADY SPOKEN ONCE."),
);
check(
  "fallback quest gives a bearing, not an address",
  jsWf.adventure.includes(S.openWhere(BITE, located[BITE])) &&
    !jsWf.adventure.includes("The map says ") &&
    !S.namesAnAddress(jsWf.adventure),
  jsWf.adventure,
);
check(
  "echoes prompt asks for a clause the seeker would recognise, not a word count",
  ce.p.includes("Quote a whole clause the seeker would recognise as their own") &&
    ce.p.includes("never a fragment that begins mid-clause") &&
    ce.p.includes("3-8 words"),
);
check(
  "seal prompt seals the one bite it was bitten from, with a bearing",
  cs.p.includes("Seal this quest into ONE BITE: one act, one bearing, one proof.") &&
    cs.p.includes(`card="${picks[BITE].name}"`) &&
    !cs.p.includes(picks[BITE === "roots" ? "trunk" : "roots"].name) &&
    cs.p.includes("THE BEARING: KEEP the one the quest above already spoke") &&
    cs.p.includes("This card does not stand anywhere in the city, so there is no place to name") &&
    cs.p.includes('{"move": {"task":"","where":"","proof":"","leave":""}}'),
  spread(),
);
check(
  "refine prompt rewrites the one bite, in the shape it was spoken",
  cr.p.includes("Rewrite the ONE BITE around that new truth") &&
    cr.p.includes("20-40 words, one act, imperative, verb first") &&
    cr.p.includes("no First and Second and Third"),
);
check(
  "refine prompt excludes UI stems and synthetic stone labels",
  !cr.p.includes("I keep swallowing…") && !cr.p.includes("I am carrying:"),
);

const stub = { available: () => true, generate: async () => JSON.stringify({ say: "That changes it.", adventure: "word ".repeat(6) }) };
check("refine rejects a stub quest", (await S.refineLlm(sess, stub, 1)) === null);
const parrot = {
  available: () => true,
  generate: async () => JSON.stringify({ say: "That changes it.", adventure: ADVENTURE }),
};
check("refine rejects the old quest handed back unchanged", (await S.refineLlm(sess, parrot, 1)) === null);

const tail = skipped ? ` (${skipped} skipped — cloud ahead of the Spark)` : "";
console.log(failures ? `\n${failures} FAILED${tail}` : `\nALL PASS${tail}`);
process.exit(failures ? 1 : 0);
