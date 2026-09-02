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
import { SYSTEM, weaveLlm, weaveFallback } from "../src/weave.js";
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

const CARD_IDS = { roots: "roots-04", trunk: "trunk-13", branches: "branches-10" };
const WEATHER_ID = "thunderhead";
const SHARES = [
  "I keep swallowing… the thing I want to say to my sister, because my friends all think I am " +
    "the calm one and I keep swallowing how angry I actually am about it",
  "I am carrying: Grief, Too Many People.",
  "I secretly want to sing in front of people and I have never done it once",
];
const ADVENTURE =
  "Tonight, an adventure in three moves. First, walk out alone past the Man until the music " +
  "thins, sit in the dust, and say out loud the sentence you have been swallowing for your " +
  "sister — stay until it stops shaking. Second, stand at the Heartwood work of your own camp: " +
  "take one shift nobody wants, the 4am ice run or the last sweep, and stay until the job is " +
  "finished. Third, find one stranger at Center Camp, tell them the thing you make that has no " +
  "use, and give them something small you made. Leave your written word weighted under a stone.";

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
/* The weave prompt's quest rules diverged on feat/cloud-seance-v2: the playa turtle tells
 * the model to name real 2026 places for all three moves, the cloud turtle pins exactly
 * ONE move to a placement and gives the other two a bearing instead of an address. The
 * reading half of the prompt, and every other prompt, still match byte for byte — so the
 * rest of this diff is worth keeping, and only this one string is skipped. */
skip("weave prompt (quest rules: one anchor + two open moves)", AHEAD);
/* The seal prompt diverged for the same reason the weave prompt did, one stage later: the
 * playa turtle tells the model to take every move's `where` from its card, the cloud
 * turtle marks the ONE placed move and forbids an address on the other two, so the sealed
 * parchment says what the spoken quest said. Retire this skip by porting the same
 * paragraph into app/oracle/session.py's _seal_llm. */
skip("seal prompt (one placed move, two bearings)", AHEAD);
for (const [label, a, b] of [
  ["echoes prompt", py.echoes, ce.p],
  ["refine prompt", py.refine, cr.p],
]) {
  const A = normalise(a);
  const B = normalise(b);
  check(label, A === B, firstDiff(A, B));
}
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
check(
  "fallback echoes",
  JSON.stringify(jsEch) === JSON.stringify(py.echoes_fallback),
  `py=${JSON.stringify(py.echoes_fallback)}\n         js=${JSON.stringify(jsEch)}`,
);
const jsWf = weaveFallback(told, picks, located);
check(
  "fallback reading",
  jsWf.reading === py.weave_fallback.reading,
  firstDiff(py.weave_fallback.reading, jsWf.reading),
);
/* Same divergence, offline half: the Python appends "The map says <directions>." to all
 * three moves, the cloud appends it to the anchor move only. The reading above is
 * untouched by that and still diffs. */
skip("fallback quest (anchor move keeps the map line, the other two do not)", AHEAD);

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
  `fallback quest is compact and orally sequenced (${qw}w)`,
  qw <= 175 && ["First.", "Second.", "Third."].every((x) => jsWf.adventure.includes(x)),
);
check(
  "runtime prompt carries spoken word budgets",
  cw.p.includes("90-120 words") && cw.p.includes("75-110 words"),
);
check(
  "system voice bans prose that reads poorly aloud",
  SYSTEM.includes("spoken aloud") && SYSTEM.includes("no semicolons"),
);

/* The two skips above are only safe if SOMETHING still guards the diverged strings. This
 * is that something: the cloud's own rule, checked on the cloud's own side. */
check(
  "quest prompt pins exactly one move to a placement",
  (cw.p.match(/- THE ANCHOR: exactly ONE move/g) || []).length === 1 &&
    cw.p.includes("the REACH move") &&
    cw.p.includes("Terrible Turtle Camp"),
  "the fixture's only non-citywide card is the branches card, at E & 6:15",
);
check(
  "quest prompt tells the other two moves to give a bearing, not an address",
  cw.p.includes("the other two moves name NO address and NO camp") &&
    cw.p.includes("Give them a bearing, not an address."),
);
check(
  "fallback quest carries the map line exactly once",
  (jsWf.adventure.match(/The map says /g) || []).length === 1 &&
    (jsWf.adventure.match(/No address for this one\./g) || []).length === 2,
  jsWf.adventure,
);
check(
  "seal prompt marks the one placed move and forbids an address on the other two",
  (cs.p.match(/<- THE PLACED MOVE/g) || []).length === 1 &&
    cs.p.includes("THE ANCHOR: exactly ONE of the three — the REACH move") &&
    cs.p.includes("must NOT name an address, a clock, a street, or a camp"),
  "the fixture's only placed card is the branches card, at E & 6:15",
);
check(
  "refine prompt preserves the spoken three-move shape",
  cr.p.includes("75-110 words") && cr.p.includes("First, Second, Third"),
);
check(
  "refine prompt excludes UI stems and synthetic stone labels",
  !cr.p.includes("I keep swallowing…") && !cr.p.includes("I am carrying:"),
);

const stub = { available: () => true, generate: async () => JSON.stringify({ say: "That changes it.", adventure: "word ".repeat(20) }) };
check("refine rejects a stub quest", (await S.refineLlm(sess, stub, 1)) === null);
const parrot = {
  available: () => true,
  generate: async () => JSON.stringify({ say: "That changes it.", adventure: ADVENTURE }),
};
check("refine rejects the old quest handed back unchanged", (await S.refineLlm(sess, parrot, 1)) === null);

const tail = skipped ? ` (${skipped} skipped — cloud ahead of the Spark)` : "";
console.log(failures ? `\n${failures} FAILED${tail}` : `\nALL PASS${tail}`);
process.exit(failures ? 1 : 0);
