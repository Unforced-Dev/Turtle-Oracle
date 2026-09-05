/* The Turtle's memory of the city — port of app/oracle/guide.py for a Worker.
 *
 * The Spark reads the 4.3MB BRC dump off its own disk and keeps the whole thing in
 * memory. A Worker has no disk, so it fetches a BUILT artefact — cloud/assets/city.json,
 * made by tools/build_city.py at deploy time — through the ASSETS binding, once per
 * isolate, and holds it in a module-level promise.
 *
 * TWO TIERS, AND THE SPLIT IS THE WHOLE POINT. Measured on this file, node 22, M4:
 *
 *   JSON.parse(city.json) + the occurrence timeline .......  ~32 ms
 *   the token index over every name and description ........ ~100 ms
 *
 * Both are paid ONCE PER ISOLATE, but the first one is paid by whoever asks "what is on
 * tonight" and the second by whoever asks the Turtle a question. Browsing does not need
 * a token index — the window is a slice of an already-sorted list, and filtering a few
 * dozen rows by substring is free — so browsing must not pay 100ms for one. Hence
 * `city()` and `searchIndex()` are separate lazy promises. Nothing re-parses per request;
 * if you ever find yourself calling JSON.parse on the request path, that is the bug.
 *
 * TIME IS NOT THE MACHINE'S TIME. A Worker runs in UTC in whatever datacentre took the
 * request. Everything here is seconds since the epoch, and every wall-clock question
 * ("when does tonight start") is answered through Intl in America/Los_Angeles. The
 * offset is READ, not assumed: during burn week it is always PDT (-07:00), and writing
 * -07:00 in would work this week and quietly break in November.
 */
import { CARDS } from "./deck.js";
import { hookPlace } from "./geo.js";
import { biteRealm, cardLore, standsSomewhere } from "./weave.js";
import { TZ } from "./util.js";

/* ~1500 tokens of context, measured the cheap way — English prose runs near four
 * characters to the token, and place lines run denser, so this is a ceiling. Same
 * number as guide.py's ORACLE_GUIDE_CHARS default. */
const MAX_BLOCK_CHARS = 6000;

/* What one browse response may carry. A phone on playa LTE does not want the city. */
export const MAX_PAGE = 60;
export const DEFAULT_PAGE = 25;

const STOP = new Set(
  `a an and are as at be been being but by can could did do does for from get got
had has have he her here him his how i if in into is it its just me my no not of on or our
out over she should so some such than that the their them then there these they this those
to too us was we were what when where which who whom why will with would you your yours
about after again all any because before between during more most other same up down
tell told know knows want need find give given say says see look looking let ask asked
please thing things something anything someone somewhere near around much many kind
best good great turtle oracle shell camp place places going come coming`.split(/\s+/),
);

/* Words that steer the clock, not the search. "what is happening tonight" must not go
 * hunting for a camp with "tonight" in its name. */
const TIME_WORDS = new Set(
  `now tonight today tomorrow morning afternoon evening night sunrise
sunset later happening going soon next upcoming right currently`.split(/\s+/),
);

/* The one thing the dump does not hold: who is behind the decks. There are no set times,
 * no lineups, no art-car schedules in the API. Never let the Turtle improvise one. */
const LINEUP_RE =
  /\b(dj|djs|line[- ]?up|lineups?|set ?times?|headlin\w*|b2b|playing at|who'?s? (is )?playing|spinning|on the decks|schedule for|art car)\b/i;

const TOKEN_RE = /[a-z0-9][a-z0-9:'&]*/g;

export function tokens(text) {
  const out = [];
  const low = String(text || "").toLowerCase();
  TOKEN_RE.lastIndex = 0;
  let m;
  while ((m = TOKEN_RE.exec(low)) !== null) {
    if (m[0].length > 2 && !STOP.has(m[0])) out.push(m[0]);
  }
  return out;
}

function tokenSet(text) {
  return new Set(tokens(text));
}

/* ---- the playa wall clock -------------------------------------------------------- */

const OFFSET_FMT = new Intl.DateTimeFormat("en-US", { timeZone: TZ, timeZoneName: "longOffset" });

/** Seconds to add to UTC to get playa wall-clock, at that instant. -25200 all burn week. */
function offsetAt(sec) {
  try {
    const part = OFFSET_FMT.formatToParts(new Date(sec * 1000)).find(
      (p) => p.type === "timeZoneName",
    );
    const m = /GMT([+-])(\d{1,2})(?::(\d{2}))?/.exec((part && part.value) || "");
    if (!m) return -7 * 3600;
    return (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 3600 + Number(m[3] || 0) * 60);
  } catch (e) {
    return -7 * 3600;
  }
}

/** The playa's wall-clock fields for an instant. `wd` is 0=Sunday, as Date gives it. */
export function wallOf(sec) {
  const d = new Date((sec + offsetAt(sec)) * 1000);
  return {
    y: d.getUTCFullYear(),
    mo: d.getUTCMonth(),
    d: d.getUTCDate(),
    h: d.getUTCHours(),
    mi: d.getUTCMinutes(),
    wd: d.getUTCDay(),
  };
}

/** The instant when it is h:mi on that playa day. Two passes so a day that straddles a
 *  DST edge lands on the offset that actually applies to the ANSWER, not to the guess. */
function atWall(w, h, mi) {
  const guess = Date.UTC(w.y, w.mo, w.d, h || 0, mi || 0, 0, 0) / 1000;
  return guess - offsetAt(guess - offsetAt(guess));
}

/** The same playa calendar day, n days on. */
function shiftDay(w, n) {
  const d = new Date(Date.UTC(w.y, w.mo, w.d));
  d.setUTCDate(d.getUTCDate() + n);
  return { y: d.getUTCFullYear(), mo: d.getUTCMonth(), d: d.getUTCDate(), wd: d.getUTCDay() };
}

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function hhmm(sec) {
  const w = wallOf(sec);
  return String(w.h).padStart(2, "0") + ":" + String(w.mi).padStart(2, "0");
}

function dayWord(sec, nowSec) {
  const a = wallOf(sec);
  const n = wallOf(nowSec);
  const key = (x) => x.y * 10000 + x.mo * 100 + x.d;
  if (key(a) === key(n)) return "today";
  if (key(a) === key(shiftDay(n, 1))) return "tomorrow";
  if (key(a) === key(shiftDay(n, -1))) return "yesterday";
  return DAYS[a.wd];
}

/** "21:00–23:00 today" — port of guide.py's _when. */
export function whenLine(start, end, nowSec) {
  const s = hhmm(start);
  const e = end ? hhmm(end) : "";
  return (e ? `${s}–${e}` : s) + " " + dayWord(start, nowSec);
}

/** Playa clock string for the chat system prompt: "Saturday 5 September, 9:30 PM". */
export function playaClock(sec) {
  const w = wallOf(sec);
  const h12 = w.h % 12 || 12;
  const month = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "long" }).format(
    new Date(Date.UTC(w.y, w.mo, w.d)),
  );
  return `${DAYS[w.wd]} ${w.d} ${month}, ${h12}:${String(w.mi).padStart(2, "0")} ${
    w.h < 12 ? "AM" : "PM"
  }`;
}

export function nowSec() {
  return Math.floor(Date.now() / 1000);
}

/* ---- time windows ---------------------------------------------------------------- */

/** {start, end, label} in epoch seconds. Default: the next six hours.
 *  Byte-for-byte the same ladder as guide.py's window_for, including the rule that
 *  before 5am the night in progress is still "tonight" — it started yesterday. */
export function windowFor(question, now) {
  now = now || nowSec();
  const q = String(question || "").toLowerCase();
  const day = wallOf(now);
  const tomorrow = shiftDay(day, 1);

  if (q.includes("sunrise") || q.includes("sunup") || q.includes("dawn")) {
    const t = day.h < 8 ? day : tomorrow;
    return { start: atWall(t, 4, 30), end: atWall(t, 8, 30), label: "around sunrise" };
  }
  if (q.includes("tomorrow")) {
    return { start: atWall(tomorrow, 0, 0), end: atWall(tomorrow, 23, 59), label: "tomorrow" };
  }
  if (q.includes("tonight") || q.includes("this evening")) {
    if (day.h < 5) {
      return { start: atWall(shiftDay(day, -1), 17, 0), end: atWall(day, 5, 0), label: "tonight" };
    }
    return { start: atWall(day, 17, 0), end: atWall(day, 23, 59), label: "tonight" };
  }
  if (q.includes("afternoon")) {
    return { start: atWall(day, 12, 0), end: atWall(day, 17, 0), label: "this afternoon" };
  }
  if (q.includes("morning")) {
    const t = day.h < 12 ? day : tomorrow;
    return { start: atWall(t, 6, 0), end: atWall(t, 12, 0), label: "this morning" };
  }
  if (/\b(right now|now|happening|going on|open now)\b/.test(q)) {
    return { start: now, end: now + 2 * 3600, label: "right now" };
  }
  if (q.includes("today")) {
    return { start: now, end: atWall(day, 23, 59), label: "today" };
  }
  return { start: now, end: now + 6 * 3600, label: "the next six hours" };
}

/* ---- tier 1: the city itself ----------------------------------------------------- */

const EMPTY = {
  have: false,
  fetched_at: null,
  year: null,
  kinds: [],
  events: [],
  camps: [],
  art: [],
  occ: [],
  byUid: new Map(),
};

let _cityPromise = null;
/* Whether THIS isolate holds the parsed city — the flag /api/health reads without
 * forcing the parse. Set on the way out of readCity, never before. */
let _loaded = false;

/* An occurrence with no end runs an hour, the same guess guide.py makes when it decides
 * whether a window overlaps. Written into the timeline once rather than per query. */
const DEFAULT_RUN = 3600;

/* A DIVERGENCE FROM guide.py, ON PURPOSE. The python asks only whether an occurrence
 * overlaps the window. Ask it "what is happening tonight" at half past nine and the
 * window opens at 17:00, so a gym that ran 06:00-18:00 overlaps it — and the top of the
 * answer is four things that finished hours ago. On the Spark that fed a model; here it
 * is a list a seeker reads in the dark and walks to. So every window is also floored at
 * NOW: an event that has already ended is never "what is happening". Worth porting back
 * to app/oracle/guide.py — the model is being told the same untrue thing there. */
function floorAt(win, now) {
  return Math.max(win.start, now);
}

async function readCity(env) {
  if (!env || !env.ASSETS) return EMPTY;
  let raw;
  try {
    /* The ASSETS binding is fetched directly — it does not re-enter this Worker, so the
     * router's 404 on the public /city.json path (see index.js) does not hide the file
     * from us. The hostname is a placeholder; only the path is read. */
    const res = await env.ASSETS.fetch(new Request("https://city.assets.local/city.json"));
    if (!res || !res.ok) return EMPTY;
    raw = await res.json();
  } catch (e) {
    /* No city is a supported state — a checkout without the gitignored snapshot deploys
     * a Turtle that knows the 52 cards and says so. It is never an error. */
    return EMPTY;
  }
  if (!raw || !Array.isArray(raw.events)) return EMPTY;

  const events = raw.events;
  const camps = raw.camps || [];
  const art = raw.art || [];
  const byUid = new Map();
  for (const c of camps) byUid.set(c.uid, c);
  for (const a of art) byUid.set(a.uid, a);
  for (const e of events) byUid.set(e.uid, e);

  /* One flat timeline of [start, end, eventIndex], sorted. build_city.py already sorts
   * the events by their first start, but an event's LATER occurrences interleave with
   * other events' first ones, so the merge still has to happen — 6.5k rows, ~4ms. */
  const occ = [];
  for (let i = 0; i < events.length; i++) {
    for (const o of events[i].occ || []) {
      occ.push([o[0], o.length > 1 && o[1] ? o[1] : o[0] + DEFAULT_RUN, i]);
    }
  }
  occ.sort((a, b) => a[0] - b[0] || a[2] - b[2]);

  _loaded = true;
  return {
    have: true,
    fetched_at: raw.fetched_at || null,
    year: raw.year || null,
    kinds: raw.kinds || [],
    events,
    camps,
    art,
    occ,
    byUid,
  };
}

/** The city, parsed once per isolate. Never throws; a missing file is a smaller Turtle. */
export function city(env) {
  if (!_cityPromise) {
    _cityPromise = readCity(env).catch(() => EMPTY);
  }
  return _cityPromise;
}

/** Only for tests: forget the isolate's cache so a fixture can be swapped in. */
export function __reset() {
  _cityPromise = null;
  _indexPromise = null;
  _metaPromise = null;
  _loaded = false;
}

/* ---- tier 2: the token index ----------------------------------------------------- */

let _indexPromise = null;

/** name tokens and all tokens per record, for the scorer. ~100ms once, for search and
 *  for the model's retrieval — never for browsing. */
async function buildIndex(env) {
  const c = await city(env);
  const mk = (rec, name, rest) => ({
    rec,
    name: tokenSet(name),
    all: tokenSet(name + " " + rest),
  });
  return {
    events: c.events.map((e) =>
      mk(e, e.title, [e.desc || "", e.where || "", c.kinds[e.kind] || ""].join(" ")),
    ),
    camps: c.camps.map((p) => mk(p, p.name, [p.desc || "", p.landmark || "", p.from || ""].join(" "))),
    art: c.art.map((p) => mk(p, p.name, [p.desc || "", p.by || ""].join(" "))),
  };
}

function searchIndex(env) {
  if (!_indexPromise) {
    _indexPromise = buildIndex(env).catch(() => ({ events: [], camps: [], art: [] }));
  }
  return _indexPromise;
}

/** guide.py's _score: a hit in the name counts for more than a hit in the blurb. */
function score(entry, qtok, nameWeight = 3) {
  if (!qtok.size) return 0;
  let n = 0;
  let a = 0;
  for (const t of qtok) {
    if (entry.name.has(t)) n++;
    if (entry.all.has(t)) a++;
  }
  return nameWeight * n + a;
}

/* ---- what the phone draws -------------------------------------------------------- */

/** One row in a list: enough to draw it, and the uid to open it with. */
function eventRow(c, e, start, end, now) {
  return {
    uid: e.uid,
    kind: "event",
    type: c.kinds[e.kind] || "Other",
    title: e.title,
    when: whenLine(start, end, now),
    start,
    end,
    /* "on right now" is the one thing a phone in the dust actually wants to know, and
     * it is a fact about the row, not a thing the client should recompute against a
     * clock that may be hours off — a phone with no signal since Tuesday has drifted. */
    on_now: start <= now && now < end,
    /* A search can land on an event whose last night was Thursday. Saying so is honest;
     * saying "00:00–12:00 yesterday" and leaving the phone to work it out is not. */
    over: end <= now,
    where: e.where || "",
    at: e.at || "",
  };
}

function placeRow(p) {
  return {
    uid: p.uid,
    kind: p.kind,
    type: p.kind === "camp" ? "Camp" : "Art",
    title: p.name,
    when: "",
    where: p.where || "",
  };
}

/** Cheap substring filter over a window's worth of rows. No token index: the candidate
 *  set here is tens of rows, not five thousand. */
function matches(hay, needle) {
  return !needle || hay.toLowerCase().includes(needle);
}

/**
 * WHAT IS HAPPENING — the browse view.
 * @param {object} opts {window, kind, q, limit, offset, now}
 * @returns {{window, label, start, end, total, items, have}}
 */
export async function happening(env, opts = {}) {
  const c = await city(env);
  const now = opts.now || nowSec();
  const name = String(opts.window || "now").trim().toLowerCase();
  const win = windowFor(name, now);
  const kind = String(opts.kind || "").trim().toLowerCase();
  const q = String(opts.q || "").trim().toLowerCase().slice(0, 80);
  const limit = Math.min(Math.max(parseInt(opts.limit, 10) || DEFAULT_PAGE, 1), MAX_PAGE);
  const offset = Math.min(Math.max(parseInt(opts.offset, 10) || 0, 0), 5000);

  /* The timeline is sorted by start, so everything that could overlap the window starts
   * before win.end — walk until then and keep what has not already finished. An event
   * with several occurrences in one window shows once, at the earliest of them. */
  const seen = new Map();
  const floor = floorAt(win, now);
  for (const [s, e, i] of c.occ) {
    if (s >= win.end) break;
    if (e <= floor) continue;
    const ev = c.events[i];
    const type = c.kinds[ev.kind] || "Other";
    if (kind && type.toLowerCase() !== kind) continue;
    if (q && !matches(ev.title + " " + (ev.desc || "") + " " + (ev.where || ""), q)) continue;
    const prev = seen.get(ev.uid);
    if (prev && prev[0] <= s) continue;
    seen.set(ev.uid, [s, e, i]);
  }
  const rows = [...seen.values()].sort((a, b) => a[0] - b[0]);
  return {
    have: c.have,
    window: name,
    label: win.label,
    start: win.start,
    end: win.end,
    total: rows.length,
    kinds: c.kinds,
    items: rows.slice(offset, offset + limit).map(([s, e, i]) => eventRow(c, c.events[i], s, e, now)),
  };
}

/**
 * SEARCH — the whole city, any time. Events first, then camps, then art, each ranked by
 * what the question actually said.
 */
export async function search(env, q, opts = {}) {
  const c = await city(env);
  const now = opts.now || nowSec();
  const text = String(q || "").trim().slice(0, 120);
  const limit = Math.min(Math.max(parseInt(opts.limit, 10) || DEFAULT_PAGE, 1), MAX_PAGE);
  if (!text) return { have: c.have, q: "", total: 0, items: [] };

  const idx = await searchIndex(env);
  const qtok = new Set(tokens(text).filter((t) => !TIME_WORDS.has(t)));
  const items = [];

  const ranked = (entries, weight) =>
    entries
      .map((entry) => [score(entry, qtok, weight), entry.rec])
      .filter(([s]) => s > 0)
      .sort((a, b) => b[0] - a[0]);

  /* An event is ranked by the question and then shown at its NEXT occurrence — a search
   * result the seeker cannot act on ("that was Tuesday") is noise. An event whose last
   * night has been and gone still appears, because "was there a coffee thing" is a real
   * question, but it appears BELOW everything still standing: a top hit the seeker
   * cannot walk to reads as the search being broken. Its last time is kept, and `over`
   * says plainly what it is. */
  const evHits = ranked(idx.events, 3).map(([sc, e]) => {
    const flat = (e.occ || []).map((o) => [o[0], o.length > 1 && o[1] ? o[1] : o[0] + DEFAULT_RUN]);
    const next = flat.find((o) => o[1] > now) || flat[flat.length - 1] || [now, now];
    return { sc, e, next, over: next[1] <= now };
  });
  evHits.sort((a, b) => Number(a.over) - Number(b.over) || b.sc - a.sc || a.next[0] - b.next[0]);
  for (const h of evHits.slice(0, limit)) {
    items.push(eventRow(c, h.e, h.next[0], h.next[1], now));
  }
  for (const [, p] of ranked(idx.camps, 5).slice(0, Math.max(0, limit - items.length))) {
    items.push(placeRow(p));
  }
  for (const [, p] of ranked(idx.art, 5).slice(0, Math.max(0, limit - items.length))) {
    items.push(placeRow(p));
  }
  return { have: c.have, q: text, total: items.length, items: items.slice(0, limit) };
}

/**
 * ONE THING, in full — the detail sheet. An event carries the place it hangs off; a camp
 * or an art piece carries what is on there next.
 */
export async function item(env, uid, opts = {}) {
  const c = await city(env);
  const now = opts.now || nowSec();
  const rec = c.byUid.get(String(uid || ""));
  if (!rec) return null;

  if (rec.title !== undefined) {
    const flat = (rec.occ || []).map((o) => [
      o[0],
      o.length > 1 && o[1] ? o[1] : o[0] + DEFAULT_RUN,
    ]);
    const next = flat.find((o) => o[1] > now) || flat[flat.length - 1] || [now, now];
    const host = rec.at ? c.byUid.get(rec.at) : null;
    return {
      uid: rec.uid,
      kind: "event",
      type: c.kinds[rec.kind] || "Other",
      title: rec.title,
      desc: rec.desc || "",
      where: rec.where || "",
      when: whenLine(next[0], next[1], now),
      on_now: next[0] <= now && now < next[1],
      all_day: Boolean(rec.all_day),
      /* The nights it still runs. A list that opens with three days that already
       * happened is a list nobody reads to the end of. */
      times: (flat.filter((o) => o[1] > now).length ? flat.filter((o) => o[1] > now) : flat.slice(-1))
        .slice(0, 12)
        .map(([s, e]) => ({ when: whenLine(s, e, now), start: s, end: e, over: e <= now })),
      host: host ? { uid: host.uid, kind: host.kind, title: host.name, where: host.where || "" } : null,
    };
  }

  /* A camp or an art piece: what is on there in the next 24 hours, so the sheet answers
   * "should I walk over" and not only "what is this". */
  const soon = [];
  for (const [s, e, i] of c.occ) {
    if (s > now + 86400) break;
    if (e <= now) continue;
    const ev = c.events[i];
    if (ev.at !== rec.uid) continue;
    soon.push(eventRow(c, ev, s, e, now));
    if (soon.length >= 8) break;
  }
  return {
    uid: rec.uid,
    kind: rec.kind,
    type: rec.kind === "camp" ? "Camp" : "Art",
    title: rec.name,
    desc: rec.desc || "",
    where: rec.where || "",
    by: rec.by || "",
    from: rec.from || "",
    landmark: rec.landmark || "",
    events: soon,
  };
}

/* ---- the cards --------------------------------------------------------------------*/

function normName(s) {
  return String(s || "")
    .replace(/\(.*?\)/g, " ")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^the /, "");
}

/** The card a question names, if it names one. Longest name first, so a short title
 *  inside a longer one never wins. Port of guide.py's find_card. */
export function findCard(question) {
  const q = " " + normName(question) + " ";
  const byLength = [...CARDS].sort((a, b) => b.name.length - a.name.length);
  for (const c of byLength) {
    const n = String(c.name || "")
      .toLowerCase()
      .replace(/[^a-z0-9 ]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    const bare = n.replace(/^the /, "");
    for (const probe of [n, bare]) {
      if (probe.length >= 4 && q.includes(" " + probe + " ")) return c;
    }
  }
  return null;
}

/** One block about a card — meaning, shadow, the dare, the lore. Null if no such card. */
export function describeCard(name) {
  let card = null;
  const want = normName(name);
  if (want) {
    for (const c of CARDS) {
      const cn = normName(c.name);
      if (cn === want || want.includes(cn) || cn.includes(want)) {
        card = c;
        break;
      }
    }
  }
  if (!card) card = findCard(name);
  if (!card) return null;
  const lore = cardLore()[card.id] || {};
  const parts = [
    `CARD: ${card.name} (${card.realm} · ${(card.keywords || []).join(", ")})`,
    `meaning: ${card.reading || ""}`,
  ];
  if (card.shadow) parts.push(`the bite: ${card.shadow}`);
  if (lore.essence) parts.push(`essence: ${lore.essence}`);
  if (card.turtle_dare) parts.push(`the dare it carries: ${card.turtle_dare}`);
  return { card, block: parts.join("\n") };
}

/* ---- retrieval: everything the model is allowed to know about one question -------- */

function hitLine(h) {
  return [h.title, h.type, h.when, h.where].filter(Boolean).join(" — ");
}

/**
 * Port of guide.py's retrieve. Returns {block, hits, window, have, card, card_meaning,
 * lineup} — `block` is what the model may speak from, `hits` is what the phone draws
 * under the answer.
 */
export async function retrieve(env, question, opts = {}) {
  const c = await city(env);
  const now = opts.now || nowSec();
  const k = opts.k || 6;
  const win = windowFor(question, now);
  const qtok = new Set(tokens(question).filter((t) => !TIME_WORDS.has(t)));

  const hits = [];
  let lines = [];

  if (c.have) {
    const idx = await searchIndex(env);
    const byIdx = new Map();
    for (const entry of idx.events) byIdx.set(entry.rec.uid, entry);

    /* Everything inside the window, ranked by what the question said and then by the
     * earliest start — the python sorts (-score, -(-timestamp)), which is score down,
     * start up. Same order here, spelled the way a reader can check it. */
    const scored = [];
    const floor = floorAt(win, now);
    for (const [s, e, i] of c.occ) {
      if (s >= win.end) break;
      if (e <= floor) continue;
      const ev = c.events[i];
      const entry = byIdx.get(ev.uid);
      scored.push([entry ? score(entry, qtok, 3) : 0, s, e, ev]);
    }
    scored.sort((a, b) => b[0] - a[0] || a[1] - b[1]);

    const seen = new Set();
    for (const [, s, e, ev] of scored) {
      if (seen.has(ev.title)) continue;
      seen.add(ev.title);
      hits.push(eventRow(c, ev, s, e, now));
      if (hits.length >= k) break;
    }

    if (hits.length) {
      lines.push(`EVENTS (${win.label}):`);
      for (const h of hits) lines.push("- " + hitLine(h));
    } else {
      lines.push(`EVENTS (${win.label}): the shell holds none in that window.`);
    }

    for (const [label, entries, cap] of [
      ["CAMPS", idx.camps, 4],
      ["ART", idx.art, 3],
    ]) {
      const keep = entries
        .map((entry) => [score(entry, qtok, 5), entry.rec])
        .filter(([s]) => s > 0)
        .sort((a, b) => b[0] - a[0])
        .slice(0, cap);
      if (!keep.length) continue;
      lines.push(label + ":");
      for (const [, p] of keep) {
        const desc = String(p.desc || "").slice(0, 180);
        lines.push(
          `- ${p.name}` + (p.where ? ` at ${p.where}` : "") + (desc ? ` — ${desc}` : ""),
        );
        hits.push(placeRow(p));
      }
    }
  }

  const found = findCard(question);
  const described = found ? describeCard(found.name) : null;
  if (described) lines.push(described.block);

  if (!c.have) {
    lines = [
      "THE CITY IS NOT IN THE SHELL: the camp/art/event dump is not on this machine, so " +
        "you know nothing about placements or what is on. Say so plainly if you are " +
        "asked. You still know the 52 cards.",
    ].concat(described ? [described.block] : []);
  }

  let block = lines.join("\n");
  if (block.length > MAX_BLOCK_CHARS) {
    block = block.slice(0, MAX_BLOCK_CHARS).replace(/\n[^\n]*$/, "") + "\n(…the rest is dust.)";
  }
  return {
    block,
    hits,
    window: win.label,
    have: c.have,
    card: found ? found.name : null,
    card_meaning: found ? found.reading || null : null,
    lineup: LINEUP_RE.test(String(question || "")),
  };
}

/* ---- from the cards to the city -------------------------------------------------- */

/**
 * WHAT IS OUT THERE FOR THIS READING. The bridge from the séance to the city:
 *
 *  - the BITE card's real 2026 placement, pinned to the actual camp or art piece in the
 *    dump — but only when the city really put it somewhere. Thirteen of the fifty-two
 *    cards hook onto a PRINCIPLE (Communal Effort, the Sunrise Howl) and those have
 *    status "citywide"; weave.js already refuses to name one out loud in a quest, and
 *    sending a seeker to walk to an idea would be the same mistake with a map on it.
 *  - what is on in the next six hours that rhymes with the draw — scored on the cards'
 *    own keywords and names and on the reading the Turtle already spoke.
 */
export async function forSeance(env, sess, opts = {}) {
  const c = await city(env);
  const now = opts.now || nowSec();
  const out = { have: c.have, window: "", pinned: null, items: [], cards: [] };
  if (!sess || !sess.picks || !sess.located) return out;

  const realms = ["roots", "trunk", "branches"];
  const bite = biteRealm(sess.located, sess.picks);
  out.cards = realms.map((r) => ({
    realm: r,
    name: (sess.picks[r] || {}).name || "",
    bite: r === bite,
  }));

  const biteCard = sess.picks[bite];
  if (biteCard && standsSomewhere(sess.located[bite])) {
    const place = hookPlace(biteCard);
    /* The hook carries the BRC uid of the real camp or art, so the pin is the dump's own
     * record and not a name lookup that could land on a different camp with a similar
     * name. Nineteen of the thirty-nine hooks carry one; the rest fall back to nothing,
     * which is honest — the reading still has its bearing. */
    const rec = place && place.uid ? c.byUid.get(place.uid) : null;
    if (rec && rec.name) {
      out.pinned = {
        uid: rec.uid,
        kind: rec.kind,
        type: rec.kind === "camp" ? "Camp" : "Art",
        title: rec.name,
        where: rec.where || "",
        desc: rec.desc || "",
        card: biteCard.name,
        real_2026: (biteCard.real_2026 || {}).name || "",
      };
    }
  }

  if (!c.have) return out;

  /* The seeker's own draw, as a query: the card names, their keywords, and the reading
   * the Turtle spoke. Not the seeker's confession — that is theirs, and it never leaves
   * the séance to go shopping for events. */
  const words = [];
  for (const r of realms) {
    const card = sess.picks[r];
    if (!card) continue;
    words.push(card.name, ...(card.keywords || []));
  }
  if (sess.reading) words.push(sess.reading);
  const qtok = new Set(tokens(words.join(" ")).filter((t) => !TIME_WORDS.has(t)));

  const idx = await searchIndex(env);
  const byIdx = new Map();
  for (const entry of idx.events) byIdx.set(entry.rec.uid, entry);

  const win = windowFor("", now); // the next six hours
  out.window = win.label;
  const scored = [];
  const floor = floorAt(win, now);
  for (const [s, e, i] of c.occ) {
    if (s >= win.end) break;
    if (e <= floor) continue;
    const ev = c.events[i];
    const entry = byIdx.get(ev.uid);
    scored.push([entry ? score(entry, qtok, 3) : 0, s, e, ev]);
  }
  scored.sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  const seen = new Set();
  for (const [sc, s, e, ev] of scored) {
    if (seen.has(ev.title)) continue;
    seen.add(ev.title);
    out.items.push(Object.assign(eventRow(c, ev, s, e, now), { echoes: sc > 0 }));
    if (out.items.length >= 8) break;
  }
  return out;
}

/* ---- health ---------------------------------------------------------------------- */

let _metaPromise = null;

/** What is in the city, without reading the city.
 *
 * /api/health must never be the request that spends 30ms parsing 1.4MB — an uptime
 * check hitting a cold isolate every minute would pay for it forever, and the answer it
 * wants ("is there a city in this deployment") is 200 bytes. tools/build_city.py writes
 * those 200 bytes next to the big file for exactly this. `loaded` says whether THIS
 * isolate has the real thing in memory yet, which is the other half of the picture.
 */
export async function cityMeta(env) {
  if (!_metaPromise) {
    _metaPromise = (async () => {
      if (!env || !env.ASSETS) return null;
      try {
        const res = await env.ASSETS.fetch(new Request("https://city.assets.local/city.meta.json"));
        if (!res || !res.ok) return null;
        return await res.json();
      } catch (e) {
        return null;
      }
    })().catch(() => null);
  }
  return _metaPromise;
}

/** True once THIS isolate holds the parsed city. Never forces the parse. */
export function loaded() {
  return _loaded;
}
