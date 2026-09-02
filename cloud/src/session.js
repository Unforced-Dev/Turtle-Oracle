/* Port of app/oracle/session.py — the séance state machine.
 *
 * Structure, stage names, spoken lines and prompts are carried over verbatim. Three
 * things had to change shape for a Worker, and only three:
 *
 *   1. State. Python keeps a module-level SESSIONS dict and garbage-collects it. Every
 *      Worker request may land in a different isolate in a different city, so the
 *      session is loaded at the top of a request and written back at the end, with an
 *      expiry instead of _gc(). It lives in a Durable Object — one per séance, see
 *      sessiondo.js for why KV could not hold it. The session OBJECT is identical —
 *      same keys, same values — so the ported logic mutates `sess` exactly as the
 *      Python does.
 *   2. Async. Every LLM touch is awaited, so hear/accept/_draw and friends are async.
 *   3. The Tale-Book is KV rather than a JSONL file (see lore.js).
 *
 * Everything else — including which failures fall back to a template, and the order in
 * which the fallbacks are tried — is the Python's judgment, not this file's.
 */
import WEATHER from "../../data/weather.json" with { type: "json" };
import { BY_REALM, SPREAD_REALMS, drawSpread, cardPayload } from "./deck.js";
import { selectFallback, tokens } from "./select.js";
import { weave, weaveFallback, SYSTEM, cardLore } from "./weave.js";
import { locateSpread, directionsLines, COMPASS_ROSE } from "./geo.js";
import { tryJson } from "./llm.js";
import * as lore from "./lore.js";
import { randRange, choice, words, rstrip, brcNow, brcClockString } from "./util.js";

const WEATHERS = Object.fromEntries(WEATHER.weathers.map((w) => [w.id, w]));
const STONES = WEATHER.stones;
const WEATHER_ASK = WEATHER.meta.ask;

const NAME_ASKS = [
  "Ah. A traveler. Come closer — the shell is warm. First things first: what do they call you out here?",
  "Welcome, dusty one. Before any card moves, the Turtle takes names. What name do you carry tonight?",
  "Mm. The Tree said someone was coming. Sit. Tell me the name you go by in this city.",
];

/* THE DOOR — the one branch the whole séance turns on. A seeker deep in their burn is
 * not going to complete the sentence "I want to keep…", and the old flow made them.
 * So: talk, or touch. Nobody has to type to be read. */
const DOOR_ASK_TAIL = "Now: will you talk to the Turtle, or touch?";
const DOORS = [
  { id: "talk", label: "Talk — tell the Turtle about your burn" },
  { id: "touch", label: "Touch — no words needed" },
];
const DOOR_RETRY = "One or the other, traveler. Talk, or touch.";

const LISTEN_INVITES = [
  "Tell the Turtle about your burn so far. Whatever comes — the good, the strange, " +
    "the thing you have not said yet. Take your time.",
  "Then talk. Your burn so far, out loud — the good, the strange, the thing you have " +
    "not told anyone. The shell has all night.",
];

const STONES_ASK =
  "Words are hard tonight. No matter — the shell reads weight. " +
  "Touch what you are carrying. Leave the rest in the dust.";

/* The third touch screen. Weather is how they arrived, stones are what they carry, and
 * this is what they are out here FOR — the one thing a quest can actually aim at. Six
 * tiles, no text box; `line` is what the tile says under its name and also what the
 * shell hands the model, so a wordless séance still has words in it. */
const WANTING_ASK = "Last touch. What did you come out here for tonight?";
const WANTINGS = [
  { id: "person", name: "A person", line: "someone out here, or someone who is not" },
  { id: "fire", name: "A fire", line: "something loud enough to burn the year off" },
  { id: "quiet", name: "Quiet", line: "less city, fewer voices, more dust" },
  { id: "lost", name: "A lost thing", line: "something I had and put down somewhere" },
  { id: "dance", name: "A dance", line: "to move until my legs stop arguing" },
  { id: "unknown", name: "Nothing yet", line: "I came out here to find out" },
];
const WANTING_RETRY = "Touch one, traveler. Even “nothing yet” is an answer.";

const DRAWN_LINES = [
  "Enough. The Turtle has heard you. Watch — the Tree is choosing.",
  "The shell hums. Three cards rise for you: what to face, where you stand, what to reach for.",
  "Good. That is enough truth to pull on. The Tree is choosing your three.",
];

/* Spoken when the reading finally arrives. The cards were already turned at `asking`,
 * so the old DRAWN_LINES cannot do this job twice. */
const WOVEN_LINES = [
  "Mm. Now the Turtle can see it. Hear what the three of them say together.",
  "Enough. The shell has what it needs. This is what rose for you.",
  "Good. That is the shape of it. Hear it whole.",
];

const ASK_RETRY = "The Turtle heard only wind. Say it again, or let it be.";

// Spoken instead of the usual line when a Shell card substitutes into a slot — roughly
// one séance in ten. The Turtle interrupting its own format is the whole point.
const AXIS_LINE =
  "The shell goes quiet. Mm. That is not a card from the Tree — that is the " +
  "Tree's own spine. “{card}” has come up for you, and the Turtle does not " +
  "choose when that happens. Sit with it.";

const REFINE_ACKS = [
  "Mm. That changes the shape of it. The Tree bends — hear your quest again.",
  "Good. More truth makes a better quest. Listen.",
  "The Turtle chews on that. Slowly. Yes — the quest turns like this.",
];

const DECISION_ASK = "Do you accept this quest? Or shall the Turtle hear more before it is sealed?";

const ACCEPT_LINES = [
  "So be it. The quest is sealed. Move slow, bite things, and bring your proofs back to the shell.",
  "Sealed. The Tree will be watching, and trees see everything slowly. Go — and come back with the tale.",
];

const TALE_NAME_ASKS = [
  "You came back. The shell felt your steps. First — the name you carry.",
  "A returner. Good. The Turtle keeps its ledger by name — what is yours?",
];

const TALE_INVITES = [
  "Now. A turtle of the shell must stand beside you — the tale is told to a living creature, " +
    "not a machine. Tell them the tale aloud, and let the shell listen too. Speak when ready.",
];

const TALE_THANKS = [
  "So it happened, and now it is story. The shell keeps it in the Tale-Book. " +
    "Turtle who witnessed: this one has earned the gift.",
  "That is a true tale — the Turtle can taste the dust in it. It joins the Tale-Book. " +
    "Witness: give this one their gift.",
];

// Proof-of-quest tokens, one flavor per realm (rotated by card number so quests differ).
const PROOFS = {
  roots: [
    "Bring back the hardest true sentence spoken there — yours or a stranger's.",
    "Bring back the name of what you almost didn't face.",
    "Bring back one word for what you left behind in the dust there.",
    "Bring back the thing you understood there that you didn't before.",
  ],
  trunk: [
    "Bring back the name of a stranger who stood beside you.",
    "Bring back one thing you only noticed because you stayed still.",
    "Bring back the story of who was there, and why they had come.",
    "Bring back a description of the ground you stood on — exactly as it was.",
  ],
  branches: [
    "Bring back something given to you freely — a word, a bead, a taste, a promise.",
    "Bring back the wish you said out loud there.",
    "Bring back proof of one small brave thing: what it was, and how it felt.",
    "Bring back the name of the first person you told about it.",
  ],
};

const LEAVES = [
  "Write one word on a scrap and leave it there, weighted with a stone.",
  "Leave behind something small you have been carrying — and mean it.",
  "Say the name of a habit out loud there, once, and walk away from it.",
];

const VOW =
  "When your three moves are made, return to the Terrible Turtle shell. Find a turtle. " +
  "Tell the tale aloud, to their face — your proofs are the witnesses. Those who return and tell " +
  "receive a gift from the shell — and while the shell still holds them, that gift " +
  "is a deck of this very oracle.";
const VOW_WHERE =
  "Camp placement posts in August — until then, ask any turtle where the shell is parked.";
const CHOSEN = "Meaning is not found. It is chosen. Bite down.";

const SLOT_TITLES = { roots: "FACE", trunk: "STAND", branches: "REACH" };

/* Bounds the playa server never needed, because there the seeker was standing in front of
 * a turtle and the GPU was ours. Here every share is re-sent to a metered model. */
const MAX_TEXT = 1000; // one spoken confession; nobody says more into a shell
/* …except at `listening`, which is the whole point of the talk door: two minutes of
 * voice, transcribed. Whisper gives back ~300 words a minute, so 2000 leaves room. */
const MAX_STORY_TEXT = 2000;
const MAX_SHARES = 12; // the seal prompt quotes them all back
const MAX_REFINES = 3; // each refinement is a fresh LLM call on an already-good quest

/* Touch-path shares carry this marker. They are things the seeker PRESSED, not things
 * they said, so they must reach the weave (a wordless séance still needs words) without
 * ever becoming a quoted echo — the same rule "I am carrying:" already enforces for the
 * stones. seekerWords() drops them; toldFrom() and context() keep them. */
const TAP_PREFIX = "The shell reads: ";

const SETTLED_LINE =
  "The Turtle has heard enough. The Tree has settled — it will not turn again tonight. " +
  "Accept this quest as it stands, or walk away and leave it in the dust.";

export { STONES, WEATHER };

/* ---- session storage ------------------------------------------------------------- */

function newId() {
  const b = new Uint8Array(6);
  crypto.getRandomValues(b);
  return [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
}

/* `store` is the SESSION_DO namespace binding, not KV. The séance id IS the object's
 * name, so there is no lookup: the same id always reaches the same object, in one
 * place, and a save is visible to the very next request. See sessiondo.js. */
export async function loadSession(store, sid) {
  if (!store || !sid) return null;
  try {
    return await store.get(store.idFromName(sid)).load();
  } catch (e) {
    return null;
  }
}

export async function saveSession(store, sess, ttl) {
  if (!store || !sess) return;
  await store.get(store.idFromName(sess.id)).save(sess, ttl);
}

/** Keep the seeker's words, but only the last few and only so long. */
function pushShare(sess, text) {
  sess.shares.push(text);
  if (sess.shares.length > MAX_SHARES) sess.shares = sess.shares.slice(-MAX_SHARES);
}

/* ---- text helpers (ports of the module-level Python helpers) ---------------------- */

/** Sanitize an LLM one-liner: strip quotes/labels, keep it one short line. */
function cleanLine(s, maxWords = 40) {
  s = (s || "").trim();
  s = rstrip(s, '"');
  while (s.startsWith('"')) s = s.slice(1);
  s = rstrip(s, "'");
  while (s.startsWith("'")) s = s.slice(1);
  s = s.trim();
  s = s.replace(/^(question|follow-?up|oracle|turtle)\s*[:\-]\s*/i, "").trim();
  s = s ? s.split(/\r\n|\r|\n/)[0].trim() : "";
  if (!s || words(s) > maxWords) return null;
  return s;
}

function extractName(text) {
  // Filler words can stack ("um, hi there, I'm Wren") — strip repeatedly, not once,
  // or a second filler word left behind gets read as the name itself.
  let t = (text || "").trim();
  const filler = /^(hi|hey|hello|hiya|there|um|uh|er|well|ok|okay|so|yeah)[,!. ]+/i;
  for (;;) {
    const stripped = t.replace(filler, "");
    if (stripped === t) break;
    t = stripped;
  }
  t = t.replace(
    /^(i am|i'm|im|they call me|people call me|my name is|my name's|call me|it's|its|the name is|name's|this is)\s+/i,
    "",
  );
  t = t.split(/[,.!?;\n]| and | but /)[0].trim();
  const name = t
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
  return (name || "Traveler").slice(0, 28);
}

function timeContext() {
  const { hour, minute } = brcNow();
  let pod;
  const h = hour + minute / 60;
  if (h >= 5 && h < 8) pod = "dawn — sunrise is near or happening; if the quest can, it ends facing the sun";
  else if (h >= 8 && h < 12) pod = "morning — the city wakes slowly; heat is coming";
  else if (h >= 12 && h < 17)
    pod =
      "the hot afternoon — route through shade, ice at Arctica, misters; " +
      "save the far playa for after dark";
  else if (h >= 17 && h < 20) pod = "golden hour into sunset — the playa softens, art is close and kind";
  else if (h >= 20 && h < 24) pod = "night — the city is fully lit; deep playa and sound camps are alive";
  else pod = "deep night — the quiet hours; the strongest ending is sunrise, near 6:20am";
  return `It is ${brcClockString()} in Black Rock City: ${pod}.`;
}

function company(shares) {
  const t = shares.join(" ").toLowerCase();
  if (
    /\b(my partner|my wife|my husband|my boyfriend|my girlfriend|my friend|my friends|my crew|my campmates|both of us|the two of us|we came|we keep|we are|we're)\b/.test(
      t,
    )
  ) {
    return (
      "The seeker is clearly here WITH someone (they speak as 'we'). Write the quest " +
      "for them together — shared moves, and one done apart, reunited with something to tell."
    );
  }
  return "";
}

function context(sess) {
  const parts = [timeContext()];
  const w = WEATHERS[sess.weather];
  if (w) {
    parts.push(
      `The seeker named their inner weather "${w.name}". ` +
        `REGISTER: ${w.register} QUEST TILT: ${w.quest_tilt}`,
    );
  }
  if (sess.stones && sess.stones.length) {
    const names = STONES.filter((s) => sess.stones.includes(s.id)).map((s) => s.name);
    parts.push(
      "When words were hard, they touched what they carry, instead of speaking: " +
        names.join(", ") +
        ". These are weight felt, not words said — never write " +
        "'you said' or quote a stone's name back to them as if they spoke it.",
    );
  }
  /* Only ever present on the touch path, so a talking séance builds the same CONTEXT the
   * Spark does — which is what cloud/test/parity.mjs diffs. */
  const taps = tapPhrases(sess);
  if (taps.length) {
    parts.push(
      "They came in by touch, not by talking. What they pressed: " +
        taps.join(" ") +
        " These are tiles they chose, not sentences they spoke — never write 'you said' " +
        "about them and never read one back as a quotation.",
    );
  }
  if ((sess.ground || 0) >= 0.5) {
    parts.push(
      "IMPORTANT — the seeker is far from shore tonight (altered, exhausted, or " +
        "unmoored). Keep the reading SHORT (60-90 words), warm, concrete. The quest " +
        "stays small-radius, physical, gentle. Grounding is the gift; no mysteries.",
    );
  }
  const c = company(sess.shares);
  if (c) parts.push(c);
  if (sess.axis_slot) {
    parts.push(
      "THE AXIS HAS SPOKEN: one of the three is not a Tree card but a Shell " +
        "card — the World Turtle's own axis, which surfaces for roughly one " +
        "seeker in ten. Name that this is rare, once, without ceremony or " +
        "flattery, and let it carry more weight in the reading than the " +
        "other two.",
    );
  }
  if (sess.prior_line) parts.push(sess.prior_line);
  return parts.join(" ");
}

/** Passive groundedness inference: weather + latency + speech shape. 0..1-ish. */
function groundSignals(sess, text, meta) {
  let g = (WEATHERS[sess.weather] || {}).grounding || 0.0;
  meta = meta || {};
  try {
    if (parseFloat(meta.ms || 0) > 25000) g += 0.2;
    const secs = parseFloat(meta.audio_secs || 0);
    const n = ((text || "").match(/\S+/g) || []).length;
    if (secs > 1 && meta.input === "voice") {
      const rate = n / secs;
      if (rate < 1.2 || rate > 4.5) g += 0.3;
    }
  } catch (e) {
    /* a malformed meta block never costs the seeker their séance */
  }
  sess.ground = Math.max(sess.ground || 0.0, g);
}

/* ---- the ceremony ---------------------------------------------------------------- */

/** Open a séance (mode 'seek') or a tale-telling (mode 'tale'). */
export function start(mode = "seek") {
  const sid = newId();
  const tale = mode === "tale";
  const sess = {
    id: sid,
    stage: tale ? "tale_naming" : "naming",
    name: null,
    prior_line: null,
    shares: [],
    door: null,
    weather: null,
    stones: [],
    wanting: null,
    question: null,
    chips: null,
    ground: 0.0,
    picks: null,
    located: null,
    reading: null,
    adventure: null,
    axis_slot: null,
    quest: null,
    echoes: null,
    refines: 0,
    created: Date.now() / 1000,
  };
  const say = choice(tale ? TALE_NAME_ASKS : NAME_ASKS);
  return { sess, event: { session: sid, stage: sess.stage, say, expects: "name" } };
}

/** The words the seeker actually SAID — the only text an echo may quote. */
function seekerWords(sess) {
  /* The cloud flow has no stem stage any more, but app/oracle/session.py still does and
   * this function is diffed against it. Keep the strip: it costs one line, it makes a
   * session started before v2 read correctly, and removing it breaks parity for nothing. */
  const stem = ((WEATHERS[sess.weather] || {}).stem || "").trim();
  const spoken = [];
  for (const share of sess.shares || []) {
    let text = (share || "").trim();
    if (text.startsWith("I am carrying:")) continue;
    if (text.startsWith(TAP_PREFIX)) continue;
    if (stem && text.startsWith(stem)) text = text.slice(stem.length).trim();
    if (text) spoken.push(text);
  }
  return spoken;
}

/** What the seeker TOUCHED, without the marker — never quotable, always readable. */
function tapPhrases(sess) {
  return (sess.shares || [])
    .map((s) => String(s || "").trim())
    .filter((s) => s.startsWith(TAP_PREFIX))
    .map((s) => s.slice(TAP_PREFIX.length).trim())
    .filter(Boolean);
}

/** Everything the Turtle has to go on, spoken and tapped, as one line for the weave. */
function toldFrom(sess) {
  const parts = [...tapPhrases(sess), ...seekerWords(sess)];
  return parts.join(" ") || "The seeker could not put it into words.";
}

function quoteTokens(text) {
  return (text || "").match(/[\p{L}\p{N}_’'-]+/gu) || [];
}

/** Make up to three distinct, natural 3-8-word quote candidates per answer. */
function quoteWindows(spoken) {
  const windows = [];
  for (const answer of spoken) {
    const w = quoteTokens(answer);
    if (w.length < 3) continue;
    const width = Math.min(7, w.length);
    const starts = [0, Math.max(0, Math.floor((w.length - width) / 2)), Math.max(0, w.length - width)];
    for (const start of starts) {
      const phrase = w.slice(start, start + width).join(" ");
      if (!windows.includes(phrase)) windows.push(phrase);
    }
  }
  return windows;
}

function validEcho(line, spoken) {
  const quotes = [...String(line || "").matchAll(/“([^”]+)”/g)].map((m) => m[1]);
  if (quotes.length !== 1) return false;
  const qt = quoteTokens(quotes[0]);
  if (qt.length < 3 || qt.length > 8) return false;
  const phrase = qt.map((w) => w.toLowerCase()).join(" ");
  return spoken.some((source) =>
    quoteTokens(source)
      .map((w) => w.toLowerCase())
      .join(" ")
      .includes(phrase),
  );
}

async function echoesLlm(sess, llm, tShort) {
  const picks = sess.picks;
  const cl = cardLore();
  const spoken = seekerWords(sess);
  if (!quoteWindows(spoken).length) return null;
  const lines = ["roots", "trunk", "branches"]
    .map(
      (r) =>
        `${r}: ${picks[r].name} — essence: ${(cl[picks[r].id] || {}).essence || ""}; ` +
        `bridge: ${(cl[picks[r].id] || {}).bridge || ""}`,
    )
    .join("\n");
  const prompt =
    "SEEKER'S ACTUAL WORDS (the only source you may quote from):\n" +
    spoken.map((s) => `- ${s}`).join("\n") +
    `\n\nCARD NOTES (for meaning only — NEVER quote these):\n${lines}\n\n` +
    "For each card, write ONE line (under 22 words) the Turtle speaks as that card turns over. " +
    "Each line quotes exactly ONE phrase of 3-8 words copied verbatim from SEEKER'S WORDS inside " +
    "curly quotation marks — never words from CARD NOTES — then ties that phrase to the card in plain " +
    "speech. No card mechanics, no fortune-telling.\n" +
    "Example shape: You said “yes to everyone” — and the tide kept none of it for you.\n" +
    'Return JSON only: {"roots": "...", "trunk": "...", "branches": "..."}';
  const resp = await llm.generate(prompt, { system: SYSTEM, asJson: true, timeout: tShort, stage: "echoes" });
  const out = tryJson(resp);
  if (out && typeof out === "object" && ["roots", "trunk", "branches"].every((r) => out[r])) {
    // structural guarantee: every echo must carry a quoted seeker phrase, else that
    // card's echo falls back to the deterministic quote-builder
    const fb = echoesFallback(sess);
    const result = {};
    for (const r of ["roots", "trunk", "branches"]) {
      const line = cleanLine(out[r], 22);
      result[r] = line && validEcho(line, spoken) ? line : fb[r];
    }
    return result;
  }
  return null;
}

function echoesFallback(sess) {
  const spoken = seekerWords(sess);
  const windows = quoteWindows(spoken);
  const out = {};
  const used = new Set();
  for (const realm of ["roots", "trunk", "branches"]) {
    const c = sess.picks[realm];
    const kw = tokens((c.keywords || []).join(" ") + " " + (c.reading || ""));
    const ranked = windows
      .map((phrase, i) => ({ phrase, i, hits: overlapCount(tokens(phrase), kw) }))
      .sort((a, b) => b.hits - a.hits || a.i - b.i);
    const hit = ranked.find((x) => !used.has(x.phrase));
    const frag = hit ? hit.phrase : "";
    if (frag) used.add(frag);
    const essence = (cardLore()[c.id] || {}).essence || c.reading || "";
    const essenceWords = essence.split(/\s+/).filter(Boolean);
    let bite = rstrip(essenceWords.slice(0, 10).join(" "), " ,;:—-");
    if (essenceWords.length > 10) bite += "…";
    else if (bite && !".!?".includes(bite[bite.length - 1])) bite += ".";
    out[realm] = frag ? `You said “${frag}” — ${bite}` : `${c.name} rose. ${bite}`;
  }
  return out;
}

function overlapCount(a, b) {
  let n = 0;
  for (const t of a) if (b.has(t)) n++;
  return n;
}

/* ---- the asking: cards first, then one open question ------------------------------ */

/* An oracle turns the cards and then asks you something. Doing it in that order is the
 * difference between an intake form and a reading — the cards are on the table, they are
 * strange, and the question the Turtle asks about them is the one a seeker will actually
 * answer. So the spread is revealed HERE, before any reading exists, and the answer goes
 * into the weave with everything else. */

/** One open question per realm, built from the card's own name and a keyword. */
const ASK_FALLBACKS = {
  roots: (c, kw) =>
    `“${c.name}” rose for what you have to face, and it carries ${kw}. ` +
    "What have you been walking around out here?",
  trunk: (c, kw) =>
    `“${c.name}” is where you are standing tonight, and it carries ${kw}. ` +
    "What has been holding you up this week?",
  branches: (c, kw) =>
    `“${c.name}” is what you are reaching for, and it carries ${kw}. ` +
    "What do you want before this city comes down?",
};

const ASK_CHIPS = {
  roots: ["Something I keep avoiding", "A person, mostly", "I honestly do not know"],
  trunk: ["My camp", "Strangers, so far", "Nothing solid yet"],
  branches: ["To be seen once", "Rest", "Something I cannot name"],
};

/** Which card the Turtle asks about. The axis, if it spoke; otherwise it rotates. */
function askRealm(sess) {
  if (sess.axis_slot) return sess.axis_slot;
  const n = (sess.picks.roots.number || 1) + (sess.picks.branches.number || 1);
  return SPREAD_REALMS[n % SPREAD_REALMS.length];
}

function askFallback(sess) {
  const realm = askRealm(sess);
  const card = sess.picks[realm];
  const kw = (card.keywords || [])[0] || "weight";
  return { question: ASK_FALLBACKS[realm](card, kw), chips: ASK_CHIPS[realm], mode: "fallback" };
}

/** Clean the model's three chips: their words, six words each, or none of them. */
function cleanChips(raw) {
  if (!Array.isArray(raw)) return null;
  const out = [];
  for (const c of raw) {
    const s = String(c == null ? "" : c)
      .replace(/^[\s"'“”\-•]+|[\s"'“”]+$/g, "")
      .trim();
    if (!s || words(s) > 6 || s.length > 48) continue;
    if (!out.includes(s)) out.push(s);
    if (out.length === 3) break;
  }
  return out.length === 3 ? out : null;
}

async function askLlm(sess, llm, tShort) {
  const picks = sess.picks;
  const cl = cardLore();
  const heard = seekerWords(sess);
  const taps = tapPhrases(sess);
  const lines = SPREAD_REALMS.map(
    (r) =>
      `${SLOT_TITLES[r]} — ${picks[r].name}: keywords=${(picks[r].keywords || []).join(", ")}; ` +
      `essence="${(cl[picks[r].id] || {}).essence || picks[r].reading || ""}"`,
  ).join("\n");
  const prompt =
    "Three cards are face up on the table. The seeker has NOT heard their reading yet — " +
    "you are about to ask them one thing, and their answer becomes part of it.\n\n" +
    `The cards:\n${lines}\n\n` +
    (heard.length
      ? "What the seeker has already told you:\n" + heard.map((s) => `- ${s}`).join("\n")
      : "The seeker has said nothing tonight. They only touched what the shell offered:\n" +
        taps.map((s) => `- ${s}`).join("\n")) +
    "\n\nAsk ONE open question in the Turtle's voice, under 25 words. Name one of the cards " +
    "by name and let it put the question in your mouth. It must be answerable out loud in a " +
    "sentence, must NOT be answerable yes or no, must not predict anything, and must make them " +
    "say something they have not said yet. Then give three answers a seeker might actually give " +
    "— in THEIR words, not yours, under six words each.\n" +
    'Return JSON only: {"question": "...", "chips": ["...", "...", "..."]}';
  const resp = await llm.generate(prompt, {
    system: SYSTEM,
    asJson: true,
    timeout: tShort,
    stage: "ask",
  });
  const out = tryJson(resp);
  if (!out || typeof out !== "object") return null;
  const question = cleanLine(out.question, 30);
  if (!question) return null;
  return { question, chips: cleanChips(out.chips) || askFallback(sess).chips, mode: "llm" };
}

/** THE PLAYA PULLS: pure chance, one card per realm. The AI's craft is the binding,
 *  not the choosing — meaning is made, not matched. The cards are revealed now. */
async function drawStep(sess, ctx) {
  const { picks, axisSlot } = drawSpread(BY_REALM, ctx.shellChance);
  const located = locateSpread(picks);
  sess.picks = picks;
  sess.located = located;
  sess.axis_slot = axisSlot;
  sess.stage = "asking";
  const ask =
    (ctx.llm && ctx.llm.available() ? await askLlm(sess, ctx.llm, ctx.tShort) : null) ||
    askFallback(sess);
  sess.question = ask.question;
  sess.chips = ask.chips;
  let say = choice(DRAWN_LINES);
  if (axisSlot) say = AXIS_LINE.replace("{card}", picks[axisSlot].name);
  return {
    session: sess.id,
    stage: "asking",
    say,
    cards: Object.fromEntries(
      SPREAD_REALMS.map((r) => [r, cardPayload(picks[r], located[r])]),
    ),
    // which slot, if any, the Turtle's own axis spoke into — the kiosk marks it
    axis_slot: axisSlot,
    map: COMPASS_ROSE,
    directions: directionsLines(picks, located),
    question: ask.question,
    chips: ask.chips,
    expects: "answer",
    modes: { ask: ask.mode },
  };
}

/** The reading and the quest, from the cards already on the table plus every share. */
async function weaveStep(sess, ctx) {
  const told = toldFrom(sess);
  const picks = sess.picks;
  const located = sess.located;
  const [out, weaveMode] = await weave(told, picks, ctx.llm, located, context(sess), ctx.tLong);
  const echoes =
    (ctx.llm && ctx.llm.available() ? await echoesLlm(sess, ctx.llm, ctx.tShort) : null) ||
    echoesFallback(sess);
  sess.reading = out.reading;
  sess.adventure = out.adventure;
  sess.echoes = echoes;
  sess.stage = "proposed";
  return {
    session: sess.id,
    stage: "proposed",
    say: choice(WOVEN_LINES),
    cards: Object.fromEntries(
      SPREAD_REALMS.map((r) => [r, cardPayload(picks[r], located[r])]),
    ),
    echoes,
    axis_slot: sess.axis_slot,
    reading: out.reading,
    adventure: out.adventure,
    map: COMPASS_ROSE,
    directions: directionsLines(picks, located),
    ask: DECISION_ASK,
    expects: "decision",
    modes: { select: "playa", weave: weaveMode },
  };
}

async function refineLlm(sess, llm, tLong) {
  const picks = sess.picks;
  const located = sess.located;
  const spoken = seekerWords(sess);
  const earlier = spoken.slice(0, -1);
  const newest = spoken.length ? spoken[spoken.length - 1] : "";
  const lines = [];
  for (const realm of ["roots", "trunk", "branches"]) {
    const c = picks[realm];
    const loc = located[realm] || {};
    lines.push(
      `${SLOT_TITLES[realm]} — ${c.name}: dare="${c.turtle_dare}" ` +
        `real_2026="${c.real_2026.name}" where="${loc.directions || ""}"`,
    );
  }
  const prompt =
    "The seeker has heard their reading and wants the quest tuned before accepting.\n" +
    "What they shared earlier:\n" +
    earlier.map((s) => `- ${s}`).join("\n") +
    `\n\nWhat they JUST added — the new truth the rewritten quest MUST visibly use:\n"${newest}"\n` +
    `\nCONTEXT: ${context(sess)}\n` +
    "\nThe drawn cards (KEEP these, do not swap):\n" +
    lines.join("\n") +
    `\n\nThe current quest:\n${sess.adventure}\n\n` +
    "Rewrite the quest around that new truth — same three cards, same three real places, but the " +
    "tasks should now put what they just confessed at the center (if they said they secretly sing, " +
    "the quest makes them sing). At least ONE of the three moves must be REPLACED, not reworded — " +
    "put the new truth in its own words, don't just gesture at it. If the new truth is something " +
    "they are keeping secret, the REACH move should be telling one person. Keep the arc: FACE alone " +
    "with a hard truth, STAND as presence at a place, REACH involving another human; keep one " +
    "leave-something-behind. Concrete, doable, with directions, and as detailed as the quest you are " +
    "replacing — this is a rewrite, not a summary. Keep it fit for speech: 75-110 words, one short " +
    "opening, then exactly three compact moves introduced as First, Second, Third. No headings or " +
    "bullets. Also write one short acknowledgement line (under 20 words) the Turtle says first, " +
    "naming the new truth.\n" +
    'Return JSON only: {"say": "...", "adventure": "..."}';
  const resp = await llm.generate(prompt, {
    system: SYSTEM,
    asJson: true,
    timeout: tLong,
    stage: "refine",
  });
  const out = tryJson(resp);
  if (out && typeof out === "object" && out.adventure) {
    const adventure = String(out.adventure).trim();
    // Reject a summary or a ramble: this whole passage is spoken while the seeker waits.
    const n = words(adventure);
    if (n < 60 || n > 140) return null;
    // ADDITION, not in session.py — measured on staging 2026-08-23: asked to rewrite a
    // short quest, the model handed back the SAME quest, word for word, in 2 of 5 runs.
    // It passes the length gate, so the seeker hears "That changes the shape of it" and
    // then their unchanged quest read back at them — a visible lie from the Turtle. The
    // prompt already demands "At least ONE of the three moves must be REPLACED"; this
    // enforces it, the same way _valid_echo enforces the quoted phrase. A rejected
    // rewrite falls to refineFallback, which genuinely re-scores the cards.
    // Worth back-porting to app/oracle/session.py.
    if (isSameQuest(adventure, sess.adventure)) return null;
    return { say: cleanLine(out.say, 30) || choice(REFINE_ACKS), adventure };
  }
  return null;
}

/** True when a "rewrite" is the old quest with at most cosmetic edits. */
function isSameQuest(next, prev) {
  const norm = (s) =>
    String(s || "")
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter(Boolean);
  const a = norm(next);
  const b = norm(prev);
  if (!a.length || !b.length) return false;
  if (a.join(" ") === b.join(" ")) return true;
  const bag = new Set(b);
  const shared = a.filter((w) => bag.has(w)).length;
  return shared / a.length >= 0.95;
}

/** No LLM: re-score the realms against the fuller share; the Tree may reconsider a card. */
function refineFallback(sess) {
  const told = toldFrom(sess);
  const picks = selectFallback(told, BY_REALM);
  // select_fallback only knows the three Tree realms, so a re-score would quietly swap
  // out an axis card the seeker has already been shown. The Turtle does not take that
  // back — once the spine has spoken, it stays on the table.
  const axisSlot = sess.axis_slot;
  if (axisSlot && sess.picks) picks[axisSlot] = sess.picks[axisSlot];
  const located = locateSpread(picks);
  const out = weaveFallback(told, picks, located);
  sess.picks = picks;
  sess.located = located;
  sess.reading = out.reading;
  sess.echoes = echoesFallback(sess);
  return { say: choice(REFINE_ACKS), adventure: out.adventure, reading: out.reading };
}

/** The seeker gives their name; the Turtle checks its ledger. */
async function nameStep(sess, text, tale, ctx) {
  sess.name = extractName(text);
  const name = sess.name;
  const priorQ = await lore.lastQuest(ctx.kv, name);
  const priorT = await lore.lastTale(ctx.kv, name);
  if (tale) {
    const recall = priorQ ? `The ledger shows your quest: “${priorQ.title}.” ` : "";
    sess.stage = "tale_listening";
    return {
      session: sess.id,
      stage: "tale_listening",
      say: `${name}. ${recall}${choice(TALE_INVITES)}`,
      expects: "tale",
    };
  }
  sess.stage = "door";
  let say;
  if (priorQ) {
    sess.prior_line =
      `This seeker has quested with the Turtle before. Their last quest: “${priorQ.title}”.` +
      (priorT ? ` The tale they told of it: "${String(priorT.tale).slice(0, 300)}"` : "") +
      " Build tonight on top of that — acknowledge it once, never repeat it.";
    say =
      `${name}. The Turtle remembers you — you carried “${priorQ.title}.” ` +
      (priorT ? "Your tale is in the book. " : "The book still waits for that tale. ") +
      DOOR_ASK_TAIL;
  } else {
    say = `${name}. Good — a name the dust can hold. ${DOOR_ASK_TAIL}`;
  }
  return { session: sess.id, stage: "door", say, doors: DOORS, expects: "door" };
}

/** The six skies, as the kiosk wants them. */
function weatherEvent(sess, say) {
  return {
    session: sess.id,
    stage: "weather",
    say,
    weathers: WEATHER.weathers.map((w) => ({
      id: w.id,
      name: w.name,
      tile: `/tiles/${w.id}.jpg`,
    })),
    expects: "weather",
  };
}

function wantingEvent(sess, say) {
  return {
    session: sess.id,
    stage: "wanting",
    say,
    wantings: WANTINGS.map((w) => ({ id: w.id, name: w.name, line: w.line })),
    expects: "wanting",
  };
}

/** The tale, told aloud to a human turtle, recorded by the shell. */
async function taleStep(sess, text, ctx) {
  const priorQ = await lore.lastQuest(ctx.kv, sess.name);
  await lore.append(ctx.kv, {
    type: "tale",
    name: sess.name,
    tale: text,
    quest_title: (priorQ || {}).title || "",
  });
  sess.stage = "tale_told";
  let say = null;
  if (ctx.llm && ctx.llm.available()) {
    say = cleanLine(
      await ctx.llm.generate(
        `A seeker named ${sess.name} returned to the shell and told this tale of their quest` +
          (priorQ ? ` “${priorQ.title}”` : "") +
          `:\n"${text}"\n\n` +
          "In the Turtle's voice, honor the tale in TWO sentences (under 40 words): first name one " +
          "specific detail from the tale itself, then address the human turtle who witnessed it, " +
          "telling THEM to hand this seeker their gift. Return the lines only.",
        { system: SYSTEM, timeout: ctx.tShort, stage: "tale" },
      ),
      50,
    );
  }
  return {
    session: sess.id,
    stage: "tale_told",
    say: say || choice(TALE_THANKS),
    gift: true,
    expects: "done",
  };
}

/** The seeker speaks or taps. Routes on the session's stage; returns the next event. */
export async function hear(sess, body, ctx) {
  if (!sess) {
    return { error: "no such séance — touch the shell to begin again", stage: "gone" };
  }
  body = body && typeof body === "object" ? body : { text: body };
  // truncate rather than refuse: a real seeker never notices, and a séance should not
  // fail on the one thing the seeker was brave enough to say. The talk door gets a
  // bigger cap because two minutes of transcribed voice lands there in one piece.
  const cap = sess.stage === "listening" ? MAX_STORY_TEXT : MAX_TEXT;
  const text = String(body.text || "").trim().slice(0, cap);
  const meta = body.meta || {};
  const sid = sess.id;

  /* The wordless stages come first: a tap carries no text, so none of them may fall
   * through the "the Turtle heard only wind" guard below. */
  if (sess.stage === "door") {
    const d = String(body.door || "").trim().toLowerCase();
    if (d === "talk") {
      sess.door = "talk";
      sess.stage = "listening";
      return { session: sid, stage: "listening", say: choice(LISTEN_INVITES), expects: "story" };
    }
    if (d === "touch") {
      sess.door = "touch";
      sess.stage = "weather";
      return weatherEvent(sess, WEATHER_ASK);
    }
    return { session: sid, stage: "door", say: DOOR_RETRY, doors: DOORS, expects: "door" };
  }
  if (sess.stage === "weather") {
    const w = WEATHERS[String(body.weather || "").trim()];
    if (!w) return weatherEvent(sess, "Touch one of the six skies, traveler.");
    sess.weather = w.id;
    sess.ground = Math.max(sess.ground, w.grounding || 0.0);
    pushShare(sess, `${TAP_PREFIX}the weather in me is ${w.name}.`);
    sess.stage = "stones";
    return {
      session: sid,
      stage: "stones",
      say: `${w.name}. ${STONES_ASK}`,
      stones: STONES,
      expects: "stones",
    };
  }
  if (sess.stage === "stones") {
    const valid = new Set(STONES.map((x) => x.id));
    sess.stones = (Array.isArray(body.stones) ? body.stones : []).filter((s) => valid.has(s));
    const names = STONES.filter((x) => sess.stones.includes(x.id)).map((x) => x.name);
    pushShare(
      sess,
      "I am carrying: " + (names.length ? names.join(", ") : "nothing I can name") + ".",
    );
    sess.stage = "wanting";
    return wantingEvent(sess, WANTING_ASK);
  }
  if (sess.stage === "wanting") {
    const want = WANTINGS.find((w) => w.id === String(body.wanting || "").trim());
    if (!want) return wantingEvent(sess, WANTING_RETRY);
    sess.wanting = want.id;
    pushShare(sess, `${TAP_PREFIX}I came out here for ${want.name.toLowerCase()} — ${want.line}.`);
    return await drawStep(sess, ctx);
  }
  if (sess.stage === "asking") {
    // three ways to answer: say it, tap one of the Turtle's own guesses, or refuse
    const chip = String(body.chip || "").trim().slice(0, 120);
    if (body.pass === true || body.pass === "true") {
      /* A refusal is an answer. Nothing is pushed — the weave runs on what it already
       * has, and echoesFallback names the cards instead of quoting words that
       * were never said. */
    } else if (chip) {
      pushShare(sess, chip);
    } else if (text) {
      groundSignals(sess, text, meta);
      pushShare(sess, text);
    } else {
      return {
        session: sid,
        stage: "asking",
        say: ASK_RETRY,
        question: sess.question,
        chips: sess.chips,
        expects: "answer",
      };
    }
    return await weaveStep(sess, ctx);
  }
  if (!text) {
    return {
      session: sid,
      stage: sess.stage,
      say: "The Turtle heard only wind. Try again, slower.",
      expects: "share",
    };
  }
  if (sess.stage === "naming") return await nameStep(sess, text, false, ctx);
  if (sess.stage === "tale_naming") return await nameStep(sess, text, true, ctx);
  if (sess.stage === "tale_listening") return await taleStep(sess, text, ctx);
  if (sess.stage === "tale_told") {
    return {
      session: sid,
      stage: "tale_told",
      gift: true,
      say: "The tale is kept. Go get your gift, and let the next traveler in.",
      expects: "done",
    };
  }
  /* The talk door: one long share, however long it took to say. No stem, no rescue —
   * a seeker who chose to talk has already been given the whole night. */
  if (sess.stage === "listening") {
    groundSignals(sess, text, meta);
    pushShare(sess, text);
    return await drawStep(sess, ctx);
  }
  if (sess.stage === "proposed") {
    pushShare(sess, text);
    const event = {
      session: sid,
      stage: "proposed",
      map: COMPASS_ROSE,
      ask: DECISION_ASK,
      expects: "decision",
    };
    // A quest can be tuned a few times and then it is the quest. Past that the Turtle
    // says so and spends nothing — the seeker's choice is now accept or walk away.
    if ((sess.refines || 0) >= MAX_REFINES) {
      Object.assign(event, {
        say: SETTLED_LINE,
        adventure: sess.adventure,
        reading: sess.reading,
        modes: { refine: "settled" },
      });
      event.cards = Object.fromEntries(
        SPREAD_REALMS.map((r) => [r, cardPayload(sess.picks[r], sess.located[r])]),
      );
      event.echoes = sess.echoes;
      event.directions = directionsLines(sess.picks, sess.located);
      return event;
    }
    sess.refines = (sess.refines || 0) + 1;
    const ref = ctx.llm && ctx.llm.available() ? await refineLlm(sess, ctx.llm, ctx.tLong) : null;
    if (ref) {
      sess.adventure = ref.adventure;
      Object.assign(event, {
        say: ref.say,
        adventure: ref.adventure,
        reading: sess.reading,
        modes: { refine: "llm" },
      });
    } else {
      const fb = refineFallback(sess);
      sess.adventure = fb.adventure;
      Object.assign(event, {
        say: fb.say,
        adventure: fb.adventure,
        reading: fb.reading,
        modes: { refine: "fallback" },
      });
    }
    const picks = sess.picks;
    const located = sess.located;
    event.cards = Object.fromEntries(
      SPREAD_REALMS.map((r) => [r, cardPayload(picks[r], located[r])]),
    );
    event.echoes = sess.echoes;
    event.directions = directionsLines(picks, located);
    return event;
  }
  if (sess.stage === "accepted") {
    return {
      session: sid,
      stage: "accepted",
      quest: sess.quest,
      say: "The quest is already sealed, traveler. Go live it — the shell will wait.",
      expects: "done",
    };
  }
  return { error: "the Turtle is confused", stage: sess.stage };
}

/** Personalize the three sealed moves (task/where/proof + one leave) from the final quest. */
async function sealLlm(sess, llm, tLong) {
  const picks = sess.picks;
  const located = sess.located;
  const lines = [];
  for (const realm of ["roots", "trunk", "branches"]) {
    const c = picks[realm];
    const loc = located[realm] || {};
    lines.push(
      `${SLOT_TITLES[realm]}: card="${c.name}" at="${c.real_2026.name}" ` +
        `where="${loc.directions || ""}"`,
    );
  }
  const prompt =
    "Seal this quest into exactly three moves, in order FACE, STAND, REACH.\n" +
    "The seeker's words:\n" +
    sess.shares.map((s) => `- ${s}`).join("\n") +
    `\n\nThe accepted quest:\n${sess.adventure}\n\nThe cards:\n` +
    lines.join("\n") +
    "\n\nFor each move give: task (1-2 concrete sentences drawn from the quest; EVERY task must " +
    "pair a physical action with an open interior door — 'stay until…', 'leave when you have…', " +
    "'ask until someone…' — specific on the outside, open on the inside, since that openness is " +
    "where the seeker finds themselves), where (short, from the card's where), proof (ONE specific " +
    "thing to bring back to the shell, personal to their words). EXACTLY ONE move also gets leave: " +
    "one small thing left behind there. FACE is done alone with a hard truth; STAND is presence at " +
    "a place; REACH involves another human. Nothing risky, nothing without consent.\n" +
    'Return JSON only: {"moves": [{"task":"","where":"","proof":"","leave":""}, {...}, {...}]}';
  const resp = await llm.generate(prompt, {
    system: SYSTEM,
    asJson: true,
    timeout: tLong,
    stage: "seal",
  });
  const parsed = tryJson(resp);
  const moves = parsed && typeof parsed === "object" ? parsed.moves : null;
  if (
    !(
      Array.isArray(moves) &&
      moves.length === 3 &&
      moves.every((m) => m && typeof m === "object" && m.task)
    )
  ) {
    return null;
  }
  return moves;
}

/** Seal the quest: three moves with places + proofs (+ one sacrifice), the vow, the map. */
export async function accept(sess, ctx) {
  if (!sess) {
    return { error: "no such séance — touch the shell to begin again", stage: "gone" };
  }
  /* Replay, never reseal. A double-tap on the kiosk, a retried POST or two isolates
   * racing each other must all get back the quest that was sealed — same words, same
   * moves, no second LLM call. Two overlapping accepts can still both find no quest and
   * both run the seal (the object serialises the reads and writes, not the LLM call
   * between them); the loser's write is overwritten and every later request replays the
   * one stored answer, which is what makes the race harmless rather than merely rare. */
  if (sess.quest) {
    return {
      session: sess.id,
      stage: "accepted",
      say: sess.accept_say || choice(ACCEPT_LINES),
      quest: sess.quest,
      expects: "done",
    };
  }
  if (sess.stage !== "proposed") {
    return { error: "no quest to accept yet", stage: sess.stage };
  }
  const picks = sess.picks;
  const located = sess.located;
  const r = picks.roots;
  const t = picks.trunk;
  const b = picks.branches;
  const sealed = ctx.llm && ctx.llm.available() ? await sealLlm(sess, ctx.llm, ctx.tLong) : null;
  const sealMode = sealed ? "llm" : "fallback";
  const moves = [];
  const leaveAt = randRange(3);
  const realms = ["roots", "trunk", "branches"];
  realms.forEach((realm, i) => {
    const c = picks[realm];
    const loc = located[realm] || {};
    const where = loc.directions || "Somewhere out there — ask Playa Info.";
    if (sealed) {
      const m = sealed[i];
      // Real BRC geo wins over whatever the model invented; its guess only
      // rides along as a suffix, and only when it actually adds something.
      const mWhere = String(m.where || "").trim();
      const mergedWhere =
        mWhere && mWhere.toLowerCase() !== where.toLowerCase() ? `${where} — ${mWhere}` : where;
      moves.push({
        slot: SLOT_TITLES[realm],
        card: c.name,
        task: String(m.task).trim(),
        where: mergedWhere,
        at: c.real_2026.name,
        proof: String(m.proof || PROOFS[realm][((c.number || 1) - 1) % 4]).trim(),
        leave: String(m.leave || "").trim(),
      });
    } else {
      moves.push({
        slot: SLOT_TITLES[realm],
        card: c.name,
        task: c.turtle_dare,
        where,
        at: c.real_2026.name,
        proof: PROOFS[realm][((c.number || 1) - 1) % 4],
        leave: i === leaveAt ? LEAVES[(c.number || 1) % LEAVES.length] : "",
      });
    }
  });
  // THE SACRIFICE demands exactly one move leave something behind — the model isn't
  // trustworthy on the count, so enforce it here rather than in the prompt alone.
  let leaveIdx = moves.findIndex((mv) => mv.leave);
  if (leaveIdx === -1) {
    leaveIdx = leaveAt;
    const c = picks[realms[leaveIdx]];
    moves[leaveIdx].leave = LEAVES[(c.number || 1) % LEAVES.length];
  } else {
    moves.forEach((mv, i) => {
      if (i !== leaveIdx) mv.leave = "";
    });
  }
  sess.quest = {
    title: `The Quest of ${b.name}`,
    for: sess.name || "Traveler",
    charge:
      `Face “${r.name}.” Stand in “${t.name}.” Reach for “${b.name}.” ` +
      "Three moves, made slow — then home to the shell.",
    adventure: sess.adventure,
    moves,
    vow: VOW,
    vow_where: VOW_WHERE,
    chosen: CHOSEN,
    map: COMPASS_ROSE,
  };
  sess.stage = "accepted";
  // The spoken line is stored, not re-rolled, so a replayed accept is the same event.
  sess.accept_say = choice(ACCEPT_LINES);
  /* The Tale-Book is read back by NAME, by whoever next gives that name — that is the
   * point of it, and it is also its whole blast radius. So it keeps the title and the
   * three cards and nothing the seeker said: a quest title is a card name, but a share
   * is a confession. lore.append stamps the time. */
  await lore.append(ctx.kv, {
    type: "quest",
    name: sess.quest.for,
    title: sess.quest.title,
    cards: SPREAD_REALMS.map((x) => picks[x].id),
  });
  return {
    session: sess.id,
    stage: "accepted",
    say: sess.accept_say,
    quest: sess.quest,
    expects: "done",
    modes: { seal: sealMode },
  };
}

/* Exported only for cloud/test/parity.mjs, which builds each prompt on both sides of
 * the port and diffs them byte for byte. Nothing in the Worker imports these. */
export const __test = {
  cleanLine,
  extractName,
  seekerWords,
  tapPhrases,
  toldFrom,
  askLlm,
  askFallback,
  cleanChips,
  WANTINGS,
  DOORS,
  quoteWindows,
  validEcho,
  echoesFallback,
  echoesLlm,
  refineLlm,
  sealLlm,
  timeContext,
  context,
  isSameQuest,
};
