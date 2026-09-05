/* The city, the chat, and the four routes that carry them.
 *
 *   node cloud/test/city.mjs      (no network, no Cloudflare, no model)
 *
 * seance.mjs guards the ceremony's shape and parity.mjs guards its words. This guards
 * the three doors the phone grew: "let me just see what's happening", "let me ask about
 * what's happening", and "from the cards, let me look at what's happening".
 *
 * EVERY CLOCK HERE IS PINNED. The whole module under test is about time — tonight,
 * tomorrow, on now, already over — and a test that reads the wall clock passes in the
 * afternoon and fails at midnight. NOW is Saturday 5 September 2026, 21:30 playa time,
 * which is a real hour of the real burn with a real evening in front of it.
 *
 * The city fixture is cloud/assets/city.json when tools/build_city.py has built one, and
 * a small hand-written one when it has not — so this suite passes on a checkout without
 * the gitignored Burning Man dump, which is the state CI and a fresh clone are in.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { registerHooks } from "node:module";

import * as guide from "../src/guide.js";
import * as chat from "../src/chat.js";
import { biteRealm, standsSomewhere } from "../src/weave.js";
import { locate, hookPlace } from "../src/geo.js";
import CARDS_DATA from "../../data/cards.json" with { type: "json" };

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ASSETS = path.join(HERE, "..", "assets");

let failures = 0;
function check(label, ok, detail = "") {
  console.log((ok ? "  ok   " : "  FAIL ") + label + (ok || !detail ? "" : "\n         " + detail));
  if (!ok) failures++;
}
function section(name) {
  console.log("\n" + name + ":");
}

/** Saturday 5 September 2026, 21:30 on the playa. */
const NOW = Math.floor(Date.parse("2026-09-05T21:30:00-07:00") / 1000);
const H = 3600;

/* ---- the fixtures ---------------------------------------------------------------- */

/* A hand-built city, used when assets/city.json has not been generated. It is small on
 * purpose: every row in it exists to be asserted about. Times are written relative to
 * NOW so the windows land where the assertions say they do. */
function tinyCity() {
  const ev = (uid, title, kind, startOffsetH, runH, extra = {}) =>
    Object.assign(
      { uid, title, kind, occ: [[NOW + startOffsetH * H, NOW + (startOffsetH + runH) * H]] },
      extra,
    );
  return {
    fetched_at: "2026-09-01T00:13:37Z",
    year: 2026,
    kinds: ["Music/Party", "Beverages", "Class/Workshop"],
    events: [
      // running now, ends in an hour
      ev("e-now", "Dust Lounge Sound Bath", 0, -1, 2, {
        desc: "A sound bath in the dust.",
        where: "Dust Lounge at C & 7:45",
        at: "camp-dust",
      }),
      // finished an hour ago: must never appear under a window that contains now
      ev("e-over", "Morning Pancake Riot", 2, -8, 4, {
        desc: "Pancakes, loudly.",
        where: "Dust Lounge at C & 7:45",
        at: "camp-dust",
      }),
      // later tonight
      ev("e-late", "Deep Playa Coffee Vigil", 1, 1, 3, {
        desc: "Coffee at the trash fence until it is not night any more.",
        where: "Nowhere in Particular at 2:00 & K",
        at: "camp-nowhere",
      }),
      // tomorrow morning
      ev("e-tmrw", "Sunrise Coffee Service", 1, 10, 2, {
        desc: "Coffee, at sunrise, for anyone still upright.",
        where: "Nowhere in Particular at 2:00 & K",
        at: "camp-nowhere",
      }),
    ],
    camps: [
      {
        uid: "camp-dust",
        kind: "camp",
        name: "Dust Lounge",
        where: "C & 7:45",
        desc: "Shade, water, and a place to sit down.",
        landmark: "the lit antler arch",
        from: "Oakland",
      },
      {
        uid: "camp-nowhere",
        kind: "camp",
        name: "Nowhere in Particular",
        where: "2:00 & K",
        desc: "Coffee and quiet, deep in the residential streets.",
      },
    ],
    art: [
      {
        uid: "art-spire",
        kind: "art",
        name: "The Resonant Spire",
        where: "3:30 2000', Open Playa",
        desc: "A tower that hums when the wind takes it.",
        by: "A. Builder",
      },
    ],
  };
}

const REAL_CITY = path.join(ASSETS, "city.json");
const USING_REAL = fs.existsSync(REAL_CITY);
const CITY_BLOB = USING_REAL
  ? fs.readFileSync(REAL_CITY, "utf8")
  : JSON.stringify(tinyCity());
const META_BLOB = JSON.stringify({
  fetched_at: "2026-09-01T00:13:37Z",
  year: 2026,
  built_at: "2026-09-05T20:36:44Z",
  counts: { events: JSON.parse(CITY_BLOB).events.length, camps: 2, art: 1, occurrences: 4 },
  bytes: CITY_BLOB.length,
});

/** The ASSETS binding: the two files guide.js asks for, and 404 for everything else. */
function assetsBinding(present = true) {
  return {
    calls: [],
    async fetch(req) {
      const p = new URL(req.url).pathname;
      this.calls.push(p);
      if (!present) return new Response("not found", { status: 404 });
      if (p === "/city.json") return new Response(CITY_BLOB);
      if (p === "/city.meta.json") return new Response(META_BLOB);
      if (p === "/" || p === "/index.html") return new Response("<html>the kiosk</html>");
      return new Response("not found", { status: 404 });
    },
  };
}

/** A Durable Object namespace that keeps its objects in a Map — same contract as
 *  sessiondo.js (load/save/drop, an `expires` checked on read), no storage. */
function fakeDO() {
  const store = new Map();
  const ns = {
    idFromName: (name) => ({ name, toString: () => name }),
    get: (id) => ({
      async load() {
        const rec = store.get(id.name);
        if (!rec) return null;
        if (rec.expires <= Date.now()) {
          store.delete(id.name);
          return null;
        }
        return rec.sess;
      },
      async save(sess, ttl) {
        if (!sess) return;
        store.set(id.name, { sess, expires: Date.now() + (Number(ttl) || 7200) * 1000 });
      },
      async drop() {
        store.delete(id.name);
      },
    }),
  };
  ns._store = store;
  return ns;
}

function fakeKV() {
  const m = new Map();
  return {
    async get(k, type) {
      const v = m.get(k);
      return v === undefined ? null : type === "json" ? JSON.parse(v) : v;
    },
    async put(k, v) {
      m.set(k, v);
    },
  };
}

function makeEnv(opts = {}) {
  return {
    ASSETS: assetsBinding(opts.city !== false),
    SESSION_DO: opts.sessions || fakeDO(),
    SESSIONS: fakeKV(),
    AI: opts.ai || null,
    ...(opts.vars || {}),
  };
}

/* Every test that swaps the city has to forget the isolate's cache first — the whole
 * point of that cache is that it survives, which is exactly what a second fixture must
 * not inherit. */
function freshEnv(opts) {
  guide.__reset();
  return makeEnv(opts);
}

const CARDS = CARDS_DATA.cards;
const byName = (n) => CARDS.find((c) => c.name === n);

/* ---- 1. the clock and the windows -------------------------------------------------*/
section("1. the playa clock, pinned to Saturday 5 September 21:30");

check(
  "the clock reads playa time, not the machine's",
  guide.playaClock(NOW) === "Saturday 5 September, 9:30 PM",
  guide.playaClock(NOW),
);

const W = (q) => guide.windowFor(q, NOW);
const iso = (sec) => new Date(sec * 1000).toISOString();
const at = (s) => Math.floor(Date.parse(s) / 1000);

check("'now' is the next two hours", W("now").start === NOW && W("now").end === NOW + 2 * H,
  `${iso(W("now").start)} -> ${iso(W("now").end)}`);
check(
  "'tonight' opens at 17:00 playa and closes at 23:59",
  W("tonight").start === at("2026-09-05T17:00:00-07:00") &&
    W("tonight").end === at("2026-09-05T23:59:00-07:00"),
  `${iso(W("tonight").start)} -> ${iso(W("tonight").end)}`,
);
check(
  "'tomorrow' is the whole of Sunday, playa time",
  W("tomorrow").start === at("2026-09-06T00:00:00-07:00") &&
    W("tomorrow").end === at("2026-09-06T23:59:00-07:00"),
  `${iso(W("tomorrow").start)} -> ${iso(W("tomorrow").end)}`,
);
check(
  "'morning' at half past nine at night means TOMORROW morning",
  W("morning").start === at("2026-09-06T06:00:00-07:00"),
  iso(W("morning").start),
);
check(
  "'sunrise' after 8am means tomorrow's sunrise",
  W("sunrise").start === at("2026-09-06T04:30:00-07:00"),
  iso(W("sunrise").start),
);
check("the default window is the next six hours",
  W("").end - W("").start === 6 * H && W("").label === "the next six hours");

/* The one rule in window_for that is easy to lose in a port, and the one a seeker at the
 * shell at 2am depends on: the night in progress started YESTERDAY. */
const LATE = Math.floor(Date.parse("2026-09-06T02:00:00-07:00") / 1000);
const late = guide.windowFor("tonight", LATE);
check(
  "at 2am, 'tonight' is the night in progress — it opened yesterday at 17:00",
  late.start === at("2026-09-05T17:00:00-07:00") && late.end === at("2026-09-06T05:00:00-07:00"),
  `${iso(late.start)} -> ${iso(late.end)}`,
);

check(
  "a time word steers the clock and not the search",
  guide.tokens("what is happening tonight").every((t) => t !== "the"),
  guide.tokens("what is happening tonight").join(","),
);

/* ---- 2. what is happening --------------------------------------------------------- */
section("2. what is happening — the browse view");

const env = freshEnv();
const tonight = await guide.happening(env, { window: "tonight", now: NOW });

check("the city loads through the ASSETS binding", tonight.have === true,
  `assets asked for: ${env.ASSETS.calls.join(", ")}`);
check("it is fetched, not re-fetched", env.ASSETS.calls.filter((p) => p === "/city.json").length === 1,
  env.ASSETS.calls.join(", "));
check("tonight has something in it", tonight.items.length > 0, `total ${tonight.total}`);
check("the window is labelled for the phone to print", tonight.label === "tonight");

check(
  "NOTHING that has already finished is 'happening'",
  tonight.items.every((i) => !i.over && i.end > NOW),
  (tonight.items.find((i) => i.over) || {}).title || "",
);
check(
  "what is on right now is badged on_now, and only that",
  tonight.items.every((i) => i.on_now === (i.start <= NOW && NOW < i.end)),
);
check("the rows are in time order", tonight.items.every((i, n, a) => !n || a[n - 1].start <= i.start));
check(
  "every row carries what a list row needs and a uid to open it with",
  tonight.items.every((i) => i.uid && i.title && i.type && i.when && i.kind === "event"),
);

const kinds = tonight.kinds;
check("the kind filter's own vocabulary comes back with the page", Array.isArray(kinds) && kinds.length > 0,
  kinds.join(" · "));

const oneKind = kinds.find((k) => tonight.items.some((i) => i.type === k)) || kinds[0];
const filtered = await guide.happening(env, { window: "tonight", kind: oneKind, now: NOW });
check(
  `the kind filter keeps only ${JSON.stringify(oneKind)}`,
  filtered.items.length > 0 && filtered.items.every((i) => i.type === oneKind),
  filtered.items.map((i) => i.type).join(","),
);
check("and it is a filter, not a different question", filtered.total <= tonight.total);

const searchInWindow = await guide.happening(env, { window: "tonight", q: "coffee", now: NOW });
check(
  "the browse search matches inside the window and nowhere else",
  searchInWindow.items.every(
    (i) => i.end > NOW && `${i.title} ${i.where}`.toLowerCase().includes("coffee"),
  ) || searchInWindow.items.length === 0,
  searchInWindow.items.map((i) => i.title).join(" | "),
);

const page1 = await guide.happening(env, { window: "tonight", limit: 2, now: NOW });
const page2 = await guide.happening(env, { window: "tonight", limit: 2, offset: 2, now: NOW });
check("a page is a page", page1.items.length <= 2 && page1.total === tonight.total);
check(
  "and the next page is the next rows, not the same ones",
  page2.items.length === 0 || page1.items[0].uid !== page2.items[0].uid,
);
check(
  "an absurd limit is clamped rather than obeyed",
  (await guide.happening(env, { window: "tonight", limit: 99999, now: NOW })).items.length <=
    guide.MAX_PAGE,
);

const tomorrow = await guide.happening(env, { window: "tomorrow", now: NOW });
check(
  "tomorrow is tomorrow — every row starts after tonight ends",
  tomorrow.items.every((i) => i.end > W("tomorrow").start && i.start < W("tomorrow").end),
  tomorrow.items.slice(0, 2).map((i) => i.when).join(" | "),
);
check(
  "an unknown window name is the six-hour default, not an error",
  (await guide.happening(env, { window: "beltane", now: NOW })).label === "the next six hours",
);

/* ---- 3. search -------------------------------------------------------------------- */
section("3. search — the whole city, any time");

const coffee = await guide.search(env, "coffee", { now: NOW });
check("coffee finds coffee", coffee.items.length > 0, `${coffee.total} hits`);
check(
  "every hit says what it is",
  coffee.items.every((i) => ["event", "camp", "art"].includes(i.kind) && i.uid && i.title),
);
const coffeeEvents = coffee.items.filter((i) => i.kind === "event");
check(
  "what is still standing outranks what is over",
  coffeeEvents.every((i, n, a) => !n || Number(a[n - 1].over || false) <= Number(i.over || false)),
  coffeeEvents.map((i) => (i.over ? "over" : "live")).join(","),
);
/* A page that is all events is a page that has buried every camp that pours coffee all
 * week under eight one-hour workshops. The places get a third of it. */
const roomy = await guide.search(env, "coffee", { limit: 24, now: NOW });
check(
  "and a page holds room for the places, not only the events",
  roomy.items.some((i) => i.kind !== "event") || roomy.items.length < 24,
  roomy.items.map((i) => i.kind).join(","),
);
check("an empty search is empty, not everything", (await guide.search(env, "  ")).items.length === 0);
check(
  "a search that matches nothing says so quietly",
  (await guide.search(env, "zzzzqqqxx", { now: NOW })).items.length === 0,
);

/* ---- 4. one thing, in full -------------------------------------------------------- */
section("4. the detail sheet");

const first = tonight.items[0];
const sheet = await guide.item(env, first.uid, { now: NOW });
check("an event opens", sheet && sheet.uid === first.uid && sheet.kind === "event", JSON.stringify(first));
check("with the fields the sheet draws", Boolean(sheet.title && sheet.when && sheet.type));
check(
  "and only times it can still be walked to",
  sheet.times.length > 0 && (sheet.times.every((t) => !t.over) || sheet.times.length === 1),
  sheet.times.map((t) => t.when + (t.over ? " (over)" : "")).join(" | "),
);
if (first.at) {
  check(
    "an event knows the place it hangs off, by uid",
    sheet.host && sheet.host.uid === first.at && Boolean(sheet.host.title),
    JSON.stringify(sheet.host),
  );
}

const anyCamp = (await guide.search(env, "coffee", { now: NOW })).items.find((i) => i.kind === "camp");
const campUid = (anyCamp && anyCamp.uid) || first.at;
if (campUid) {
  const place = await guide.item(env, campUid, { now: NOW });
  check("a camp or an art piece opens too", Boolean(place && place.title), JSON.stringify(place || {}).slice(0, 120));
  check(
    "and it says what is on there next, never what was on there last",
    (place.events || []).every((e) => e.end > NOW),
    (place.events || []).map((e) => e.when).join(" | "),
  );
}
check("a uid nobody has is null, not an empty sheet", (await guide.item(env, "no-such-uid")) === null);
check("and neither is an empty uid", (await guide.item(env, "")) === null);

/* ---- 5. from the cards to the city ------------------------------------------------ */
section("5. from the cards to the city");

/* A card the city really put somewhere, and a card that hooks onto a PRINCIPLE. The
 * second one is the whole test: weave.js refuses to name a citywide placement in a
 * quest, and this must refuse to put a map pin on one. */
const placed = CARDS.filter((c) => standsSomewhere(locate(c)) && hookPlace(c));
const citywide = CARDS.filter((c) => !standsSomewhere(locate(c)));
check("the deck has cards the city really placed", placed.length > 0, `${placed.length} of ${CARDS.length}`);
check("and cards that hook onto a principle", citywide.length > 0, `${citywide.length} of ${CARDS.length}`);

/** Build a spread whose bite lands on `want`, by trying every pairing of the other two. */
function spreadBiting(want, pool) {
  const realms = ["roots", "trunk", "branches"];
  for (const a of pool.slice(0, 24)) {
    for (const b of pool.slice(0, 24)) {
      for (const target of realms) {
        const picks = {};
        const others = realms.filter((r) => r !== target);
        picks[target] = want;
        picks[others[0]] = a;
        picks[others[1]] = b;
        const located = {};
        for (const r of realms) located[r] = locate(picks[r]);
        if (biteRealm(located, picks) === target) return { picks, located, bite: target };
      }
    }
  }
  return null;
}

const placedSpread = spreadBiting(placed[0], CARDS);
if (placedSpread) {
  const sess = {
    id: "aaaaaaaaaaaa",
    picks: placedSpread.picks,
    located: placedSpread.located,
    reading: "You have been carrying the whole camp on your back. Put it down for one hour.",
  };
  const out = await guide.forSeance(env, sess, { now: NOW });
  check(
    "the bite card is the one marked, and it is the one weave.js would bite",
    (out.cards.find((c) => c.bite) || {}).name === placedSpread.picks[placedSpread.bite].name,
    JSON.stringify(out.cards),
  );
  if (USING_REAL) {
    check(
      "a card the city really placed is pinned to the dump's own record",
      Boolean(out.pinned && out.pinned.uid === hookPlace(placedSpread.picks[placedSpread.bite]).uid),
      JSON.stringify(out.pinned),
    );
    check(
      "and the pin says which card sent them there",
      Boolean(out.pinned && out.pinned.card === placedSpread.picks[placedSpread.bite].name),
      JSON.stringify(out.pinned),
    );
  }
  check(
    "what is out there for the reading is out there in the next six hours",
    out.items.every((i) => i.end > NOW && i.start < NOW + 6 * H),
    out.items.map((i) => i.when).join(" | "),
  );
  check("and it never offers more than a screenful", out.items.length <= 8);
}

const principleSpread = spreadBiting(citywide[0], CARDS);
if (principleSpread) {
  const out = await guide.forSeance(
    env,
    { id: "bbbbbbbbbbbb", picks: principleSpread.picks, located: principleSpread.located },
    { now: NOW },
  );
  check(
    "A PRINCIPLE IS NEVER PINNED — a seeker is not sent to walk to an idea",
    out.pinned === null,
    JSON.stringify(out.pinned),
  );
}

check(
  "a séance with no cards yet is an empty answer, not a crash",
  (await guide.forSeance(env, { id: "cccccccccccc", picks: null, located: null }, { now: NOW }))
    .items.length === 0,
);
check("and neither is no séance at all", (await guide.forSeance(env, null, { now: NOW })).items.length === 0);

/* ---- 6. ask the turtle ------------------------------------------------------------ */
section("6. ask the turtle — the envelope, the guard, the template");

check(
  "the spoken line comes out of the JSON envelope",
  chat.said('{"say": "The shell is open. Ask."}') === "The shell is open. Ask.",
);
check(
  "even when the model wraps it in a fence and a paragraph",
  chat.said('Sure!\n```json\n{"say": "Coffee is at Joyism."}\n```') === "Coffee is at Joyism.",
);
check(
  "a model that forgot the envelope is still answered from",
  chat.said("Coffee is at Joyism, from seven.") === "Coffee is at Joyism, from seven.",
);
check(
  "a scratchpad in tags never reaches the speaker",
  chat.said('<think>the seeker wants coffee</think>{"say": "Joyism, from seven."}') ===
    "Joyism, from seven.",
);

const narrated = chat.clean(
  "Hmm, the seeker is asking about coffee. Let me check the Shell Holds. " +
    "Joyism pours from seven. Walk to E and 4:15.",
);
check(
  "THE NARRATION GUARD drops the scratchpad sentences and keeps the speech",
  narrated.say === "Joyism pours from seven. Walk to E and 4:15." && narrated.narrated === true,
  JSON.stringify(narrated),
);
check(
  "an answer that is ALL scratchpad comes back empty, so the caller can re-roll",
  chat.clean("Hmm, the seeker is asking about coffee. Let me check the Shell Holds.").say === "",
);
check(
  "markdown never reaches a speaker",
  chat.clean("## Coffee\n- **Joyism** pours from seven.").say === "Coffee Joyism pours from seven.",
  JSON.stringify(chat.clean("## Coffee\n- **Joyism** pours from seven.").say),
);
check(
  "and no answer runs past five sentences",
  chat.clean("One. Two. Three. Four. Five. Six. Seven.").say === "One. Two. Three. Four. Five.",
  chat.clean("One. Two. Three. Four. Five. Six. Seven.").say,
);

const ctxLineup = await guide.retrieve(env, "who is playing at Mayan Warrior tonight", { now: NOW });
check("a lineup question is recognised as one", ctxLineup.lineup === true);
const refusal = chat.fallback(ctxLineup, "who is playing at Mayan Warrior tonight", null);
check(
  "AND THE TEMPLATE REFUSES IT FIRST, before anything friendlier",
  /^The Turtle does not know that\. No lineups live in this shell/.test(refusal),
  refusal,
);

const ctxCard = await guide.retrieve(env, "tell me about the Taproot card", { now: NOW });
check("a named card is found in the question", ctxCard.card === "The Taproot", String(ctxCard.card));
check(
  "and with no model the Turtle still says what it means",
  chat.fallback(ctxCard, "tell me about the Taproot card", null).startsWith("The Taproot."),
  chat.fallback(ctxCard, "tell me about the Taproot card", null).slice(0, 90),
);

const noCityEnv = freshEnv({ city: false });
const ctxNoCity = await guide.retrieve(noCityEnv, "what is happening tonight", { now: NOW });
check("with no city file the guide says it has no city", ctxNoCity.have === false);
check(
  "the block tells the model so in as many words",
  ctxNoCity.block.startsWith("THE CITY IS NOT IN THE SHELL"),
  ctxNoCity.block.slice(0, 60),
);
check(
  "and the template says so to the seeker, without inventing a single place",
  /The city is not in this shell tonight/.test(chat.fallback(ctxNoCity, "what is happening tonight", null)),
  chat.fallback(ctxNoCity, "what is happening tonight", null),
);
check("a missing city is never an error", ctxNoCity.hits.length === 0);
guide.__reset();

/* ---- 6b. one turn, end to end ----------------------------------------------------- */
section("6b. one turn of the conversation");

const cityEnv = freshEnv();
await guide.happening(cityEnv, { window: "now", now: NOW }); // warm, as a real isolate would be

const deadLlm = { available: () => false, async generate() { return null; } };
const goodLlm = {
  seen: [],
  available: () => true,
  async generate(prompt, opts = {}) {
    this.seen.push(opts);
    return '{"say": "Coffee pours at Joyism from seven. Walk to E and 4:15."}';
  },
};
const narratingLlm = {
  rolls: 0,
  available: () => true,
  async generate() {
    this.rolls++;
    return this.rolls === 1
      ? '{"say": "Hmm, the seeker is asking about coffee. Let me check the Shell Holds."}'
      : '{"say": "Joyism pours from seven."}';
  },
};
const uselessLlm = {
  available: () => true,
  async generate() { return '{"say": "Let me check the Shell Holds."}'; },
};
const brokenLlm = { available: () => true, async generate() { throw new Error("workers ai is down"); } };

const t1 = await chat.ask(cityEnv, { text: "where is coffee tonight" }, goodLlm, { now: NOW });
check("a turn comes back with a chat id, an answer and its hits", Boolean(t1.chat_id && t1.say), JSON.stringify(t1).slice(0, 140));
check("the answer is the model's, and it is marked so", t1.mode === "llm" && /Joyism/.test(t1.say), t1.say);
check("the chat id is our own shape, so it can name a Durable Object", /^c[0-9a-f]{12}$/.test(t1.chat_id), t1.chat_id);
check(
  "the model is asked for JSON, with no scratchpad and a ceiling on the answer",
  goodLlm.seen[0].asJson === true && goodLlm.seen[0].stage === "chat" && goodLlm.seen[0].maxTokens > 0,
  JSON.stringify({ ...goodLlm.seen[0], system: "…", }),
);
check(
  "the system prompt is the Turtle's own voice plus the shell, never a second turtle",
  goodLlm.seen[0].system.startsWith("You are the Terrible Turtle Oracle") &&
    goodLlm.seen[0].system.includes("THE SHELL HOLDS") &&
    goodLlm.seen[0].system.includes("Saturday 5 September, 9:30 PM"),
);

const t2 = await chat.ask(cityEnv, { text: "and tomorrow?", chat_id: t1.chat_id }, goodLlm, { now: NOW });
check("the same chat id comes back", t2.chat_id === t1.chat_id);
check(
  "and the conversation is remembered across the turn",
  goodLlm.seen[1].system !== undefined &&
    (await cityEnv.SESSION_DO.get(cityEnv.SESSION_DO.idFromName("chat:" + t1.chat_id)).load())
      .history.length === 4,
);

const t3 = await chat.ask(cityEnv, { text: "where is coffee" }, narratingLlm, { now: NOW });
check("a narrating model is rolled exactly once more", narratingLlm.rolls === 2);
check("and the second roll is the answer", t3.mode === "llm" && t3.say === "Joyism pours from seven.", t3.say);

const t4 = await chat.ask(cityEnv, { text: "what is happening tonight" }, uselessLlm, { now: NOW });
check("a model that only ever narrates drops to the template", t4.mode === "fallback", t4.say);
const t5 = await chat.ask(cityEnv, { text: "what is happening tonight" }, deadLlm, { now: NOW });
check("no model at all drops to the template too", t5.mode === "fallback" && t5.say.length > 0, t5.say);
const t6 = await chat.ask(cityEnv, { text: "what is happening tonight" }, brokenLlm, { now: NOW });
check("and a model that throws is a template, never a 500", t6.mode === "fallback" && t6.say.length > 0, t6.say);

check("an empty question is no turn at all", (await chat.ask(cityEnv, { text: "   " }, goodLlm, { now: NOW })) === null);
check(
  "a chat id off the wire that is not ours is replaced, never used",
  /^c[0-9a-f]{12}$/.test(
    (await chat.ask(cityEnv, { text: "hello", chat_id: "../../etc/passwd" }, goodLlm, { now: NOW })).chat_id,
  ),
);
const longQ = await chat.ask(cityEnv, { text: "coffee ".repeat(400) }, goodLlm, { now: NOW });
check("a stuck mic is truncated, not refused", Boolean(longQ && longQ.say));

/* The seeker's own draw, read back — the answer to "what did my cards mean" when there
 * is no model, and the one place a chat is allowed to know about a séance. */
const mineSess = {
  id: "dddddddddddd",
  name: "Ash",
  picks: { roots: byName("The Taproot") || CARDS[0], trunk: CARDS[1], branches: CARDS[2] },
  reading: "You came a long way to sit still. That is not nothing.",
};
const mine = chat.fallback(
  await guide.retrieve(cityEnv, "what did my cards mean", { now: NOW }),
  "what did my cards mean",
  mineSess,
);
check("with no model, 'what did my cards mean' is answered from the seeker's own draw",
  mine.startsWith("The Tree gave you ") && mine.includes("sit still"), mine);
check(
  "and the séance block hands the model the cards without re-weaving them",
  chat.seanceBlock(mineSess).includes("do not re-weave") && chat.seanceBlock(mineSess).includes("name: Ash"),
);
check("no séance, no block", chat.seanceBlock(null) === "");
check(
  "the seeker's own quest is a second source the Turtle may name places from",
  chat.ADDENDUM.includes("or from the\n  seeker's own cards and reading when those are given"),
  chat.ADDENDUM.split("\n").find((l) => l.includes("must come from")) || "",
);

/* The prompt shows the model the shape of the envelope, and qwen3 hands the example
 * straight back often enough that llm.js measured it. */
check(
  "the prompt's own shape example is never the answer",
  chat.unexample("It is a little past ten in the morning, playa time. The shell is open. Ask.") === "",
);
check(
  "but a real answer that happens to end 'Ask.' keeps its words",
  chat.unexample("Joyism pours from seven. The shell is open. Ask.") === "Joyism pours from seven.",
  chat.unexample("Joyism pours from seven. The shell is open. Ask."),
);

/* ---- 7. the routes ---------------------------------------------------------------- */
section("7. the routes the phone actually calls");

/* src/index.js imports cloudflare:workers for the Durable Object base class, which plain
 * node cannot resolve. One resolution hook stands a two-line class in for it, and the
 * rest of the Worker — the router, the rate-limit gate, the JSON — is the real thing. */
registerHooks({
  resolve(spec, ctx, next) {
    if (spec === "cloudflare:workers") {
      return {
        url: "data:text/javascript," +
          encodeURIComponent("export class DurableObject{constructor(c,e){this.ctx=c;this.env=e;}}"),
        shortCircuit: true,
      };
    }
    return next(spec, ctx);
  },
});
const worker = (await import("../src/index.js")).default;

/* The routes have no `now` parameter — a query string that moves the clock would be a
 * production surface built for a test. So the clock is moved instead, for this section
 * only, and put back after it. */
const realNow = Date.now;
Date.now = () => NOW * 1000;

const routeEnv = freshEnv();
const call = async (p) => {
  const res = await worker.fetch(new Request("https://turtle.test" + p), routeEnv, {
    waitUntil: () => {},
  });
  let body = null;
  try {
    body = await res.clone().json();
  } catch (e) {
    body = await res.text();
  }
  return { status: res.status, body };
};

const rHappening = await call("/api/city/happening?window=tonight");
check("GET /api/city/happening answers", rHappening.status === 200 && rHappening.body.have === true,
  JSON.stringify(rHappening).slice(0, 160));
check("with the window it was asked for", rHappening.body.label === "tonight");
check("and nothing that has already finished", (rHappening.body.items || []).every((i) => !i.over));

const rSearch = await call("/api/city/search?q=coffee");
check("GET /api/city/search answers", rSearch.status === 200 && rSearch.body.items.length > 0,
  `${(rSearch.body.items || []).length} hits`);

const someUid = (rHappening.body.items[0] || {}).uid;
const rItem = await call("/api/city/item?uid=" + encodeURIComponent(someUid));
check("GET /api/city/item opens one thing", rItem.status === 200 && rItem.body.uid === someUid);
check("and 404s a uid the shell does not hold", (await call("/api/city/item?uid=nope")).status === 404);

check("GET /api/city/for without a real séance id is a 404, not a Durable Object",
  (await call("/api/city/for?session=" + encodeURIComponent("../../evil"))).status === 404);
check("and a well-shaped id with no séance behind it is a 404 too",
  (await call("/api/city/for?session=0123456789ab")).status === 404);

const rHealth = await call("/api/health");
check("GET /api/health reports the city without parsing it", rHealth.status === 200 && rHealth.body.city === true,
  JSON.stringify(rHealth.body).slice(0, 200));
check("with the counts the meta file carries", Boolean(rHealth.body.city_counts && rHealth.body.city_counts.events > 0),
  JSON.stringify(rHealth.body.city_counts));

/* The public door on the 1.4MB file. It is an asset so the binding can reach it, and the
 * binding does not come back through here — so this 404 costs the guide nothing. */
const rCity = await call("/city.json");
check("GET /city.json is 404 — the dump is answered FROM, never served", rCity.status === 404,
  JSON.stringify(rCity).slice(0, 120));
const warmed = await guide.happening(routeEnv, { window: "now", now: NOW });
check("and the guide can still read it through the binding", warmed.have === true);

const post = async (p, body, extra = {}) => {
  const res = await worker.fetch(
    new Request("https://turtle.test" + p, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
    { ...routeEnv, ...extra },
    { waitUntil: () => {} },
  );
  return { status: res.status, body: await res.json() };
};

const rChat = await post("/api/chat", { text: "what is happening tonight" });
check("POST /api/chat answers with no AI binding at all — on the template",
  rChat.status === 200 && rChat.body.mode === "fallback" && rChat.body.say.length > 0,
  JSON.stringify(rChat.body).slice(0, 200));
check("and hands the phone the places to draw under it", Array.isArray(rChat.body.hits));
check("an empty question is a 400", (await post("/api/chat", { text: "" })).status === 400);

/* The gate, not the budget: a limiter that says no must stop the route before it spends
 * anything. RL_CHAT is its own binding for exactly this reason. */
const deny = { limit: async () => ({ success: false }) };
check("POST /api/chat has its own rate-limit budget, and honours it",
  (await post("/api/chat", { text: "hello" }, { RL_CHAT: deny })).status === 429);
check("and the séance's budget is NOT the one it spends",
  (await post("/api/chat", { text: "hello" }, { RL: deny })).status === 200);

/* THE EARS. A chat is the other thing a seeker speaks into, and the gate on /api/transcribe
 * has to know that without becoming a free Whisper endpoint. */
const opened = await post("/api/chat/open", {});
check("POST /api/chat/open mints an empty chat for the mic to be gated on",
  opened.status === 200 && /^c[0-9a-f]{12}$/.test(opened.body.chat_id), JSON.stringify(opened.body));
check("and it spends from the chat's budget, not the séance's",
  (await post("/api/chat/open", {}, { RL_CHAT: deny })).status === 429);

const { transcribe } = await import("../src/ears.js");
const hear = async (headers) => {
  const res = await transcribe(
    new Request("https://turtle.test/api/transcribe", {
      method: "POST", headers, body: new Uint8Array([1, 2, 3]),
    }),
    { ...routeEnv, AI: { async run() { return { text: "where is the coffee" }; } } },
    new URL("https://turtle.test/api/transcribe"),
  );
  return await res.json();
};
check("the ears open for a live chat", (await hear({ "x-turtle-chat": opened.body.chat_id })).text ===
  "where is the coffee");
check("and stay shut for a chat id nobody minted",
  Boolean((await hear({ "x-turtle-chat": "c000000000000" })).error));
check("and for no caller at all", Boolean((await hear({})).error));

const denyRes = await worker.fetch(
  new Request("https://turtle.test/api/city/happening"),
  { ...routeEnv, RL_CITY: deny },
  { waitUntil: () => {} },
);
check("GET /api/city/* has one too", denyRes.status === 429);

Date.now = realNow;

console.log(
  USING_REAL
    ? "\n(ran against the real assets/city.json)"
    : "\n(ran against the built-in fixture — assets/city.json was not generated)",
);
console.log(failures ? `\n${failures} FAILED` : "\nALL PASS");
process.exit(failures ? 1 : 0);
