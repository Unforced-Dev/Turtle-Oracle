/* Does the séance still walk both doors, end to end?
 *
 *   node cloud/test/seance.mjs      (no network, no python, no Cloudflare)
 *
 * parity.mjs guards the WORDS. This guards the SHAPE: every stage the kiosk can be in,
 * every body the kiosk can post, and the two paths through them —
 *
 *   naming → door → talk  → listening → asking → proposed → accepted
 *   naming → door → touch → weather → stones → wanting → asking → proposed → accepted
 *
 * It runs the real session.js against a fake LLM, so a stage that stops existing, an
 * `expects` that changes, or a body key the server quietly ignores fails here rather than
 * on a phone in the dust. The fake model is deliberately switchable: a séance that only
 * works when the model answers is a séance that does not work on the playa.
 *
 * Sections 9-12 are the ones that came out of the v2 review, and they are about the
 * séance being answered by a phone rather than by a test: every stage against every body
 * shape (an event the kiosk cannot draw is the whole bug), a client one stage behind the
 * server, the caps that truncate rather than refuse, and src/ears.js against a fake AI
 * binding — the only route here that talks to Workers AI without a séance in its body.
 */
import { start, hear, accept, replayable, __test as S } from "../src/session.js";
import { transcribe, toBase64, MAX_AUDIO_BYTES } from "../src/ears.js";

let failures = 0;
function check(label, ok, detail = "") {
  console.log((ok ? "  ok   " : "  FAIL ") + label + (ok || !detail ? "" : "\n         " + detail));
  if (!ok) failures++;
}
function section(name) {
  console.log("\n" + name + ":");
}

/* ---- the fakes ------------------------------------------------------------------- */

/** A model that answers every stage with something well-formed. */
function goodLlm(overrides = {}) {
  const answers = {
    ask: JSON.stringify({
      question: "The shell wants to know: what did you put down to get here?",
      chips: ["My phone", "A whole year", "Nothing yet"],
    }),
    weave: JSON.stringify({
      reading: "You came a long way to sit still. " + "word ".repeat(96),
      adventure: "Tonight, three moves. First. Second. Third. " + "word ".repeat(80),
    }),
    echoes: JSON.stringify({ roots: "no quote", trunk: "no quote", branches: "no quote" }),
    seal: JSON.stringify({
      moves: [
        { task: "Sit alone until it stops shaking.", where: "past the last lamp", proof: "one word" },
        { task: "Take the shift nobody wants.", where: "your own camp", proof: "a name" },
        { task: "Tell one stranger.", where: "wherever they are thickest", proof: "their name", leave: "a written word" },
      ],
    }),
    ...overrides,
  };
  return {
    seen: [],
    available: () => true,
    async generate(prompt, opts = {}) {
      this.seen.push(opts.stage || "");
      return answers[opts.stage] === undefined ? null : answers[opts.stage];
    },
  };
}

/** A model that is simply not there — every stage must still complete on templates. */
const deadLlm = { available: () => false, async generate() { return null; } };

function ctxWith(llm) {
  return { kv: null, sessions: null, llm, shellChance: 0, tShort: 1, tLong: 1 };
}

/* ---- the two walks ---------------------------------------------------------------- */

async function walk(door, { llm, answer }) {
  const trace = [];
  const { sess, event } = start("seek");
  const ctx = ctxWith(llm);
  trace.push(event);
  const say = async (body) => {
    const e = await hear(sess, body, ctx);
    trace.push(e);
    return e;
  };
  await say({ text: "um, hi there, I'm Wren" }); // naming -> door
  await say({ door }); // door -> listening | weather
  if (door === "talk") {
    await say({
      text:
        "I got here Tuesday and I have not slept and I keep telling everyone I am fine. " +
        "I am not fine. I have not said the thing I came out here to say.",
    });
  } else {
    await say({ weather: "thunderhead" });
    await say({ stones: ["grief", "secret", "not-a-stone"] });
    await say({ wanting: "lost" });
  }
  const proposed = await say(answer); // asking -> proposed
  const sealed = await accept(sess, ctx);
  trace.push(sealed);
  return { sess, trace, proposed, sealed };
}

const stages = (trace) => trace.map((e) => e.stage);

/* ---- 1. the talk door ------------------------------------------------------------- */

section("the talk door: naming → door → listening → asking → proposed → accepted");
{
  const llm = goodLlm();
  const { sess, trace, sealed } = await walk("talk", { llm, answer: { text: "I put down being the calm one." } });
  check(
    "walks the stages in order",
    JSON.stringify(stages(trace)) ===
      JSON.stringify(["naming", "door", "listening", "asking", "proposed", "accepted"]),
    JSON.stringify(stages(trace)),
  );
  const [, door, listening, asking, proposed] = trace;
  check("the name is heard and spoken back", sess.name === "Wren" && door.say.startsWith("Wren."));
  check(
    "the door offers exactly talk and touch",
    JSON.stringify(door.doors.map((d) => d.id)) === JSON.stringify(["talk", "touch"]) &&
      door.expects === "door" &&
      door.doors.every((d) => d.label),
  );
  check("the talk door invites a story", listening.expects === "story" && /burn/i.test(listening.say));
  check(
    "the cards are revealed at the asking, not at the reading",
    asking.expects === "answer" &&
      ["roots", "trunk", "branches"].every((r) => asking.cards[r] && asking.cards[r].thumb) &&
      proposed.cards.roots.id === asking.cards.roots.id,
  );
  check(
    "the asking carries a question and three short chips",
    Boolean(asking.question) && asking.chips.length === 3 && asking.chips.every((c) => c.split(/\s+/).length <= 6),
    JSON.stringify(asking.chips),
  );
  check("the model's question is used when it answers", asking.modes.ask === "llm");
  check(
    "the story and the answer both reach the shares",
    sess.shares.length === 2 && sess.shares[1] === "I put down being the calm one.",
    JSON.stringify(sess.shares),
  );
  check(
    "the reading, the quest and the decision arrive together",
    proposed.reading && proposed.adventure && proposed.ask && proposed.expects === "decision",
  );
  check("the echoes quote the seeker, or name the card", ["roots", "trunk", "branches"].every((r) => proposed.echoes[r]));
  check("the seal produces three moves and a vow", sealed.quest.moves.length === 3 && Boolean(sealed.quest.vow));
  check("the sealed quest is stamped with the name", sealed.quest.for === "Wren");
  check(
    "every stage that spends a model call asked for one",
    llm.seen.includes("ask") && llm.seen.includes("weave") && llm.seen.includes("seal"),
    JSON.stringify(llm.seen),
  );
}

/* ---- 2. the touch door ------------------------------------------------------------ */

section("the touch door: naming → door → weather → stones → wanting → asking → proposed → accepted");
{
  const llm = goodLlm();
  const { sess, trace, proposed, sealed } = await walk("touch", {
    llm,
    answer: { chip: "A whole year" },
  });
  check(
    "walks the stages in order",
    JSON.stringify(stages(trace)) ===
      JSON.stringify([
        "naming", "door", "weather", "stones", "wanting", "asking", "proposed", "accepted",
      ]),
    JSON.stringify(stages(trace)),
  );
  const [, , weather, stones, wanting, asking] = trace;
  check("the weather screen offers six skies with tiles", weather.weathers.length === 6 && weather.weathers.every((w) => w.tile));
  check("the stones screen offers six stones", stones.stones.length === 6 && stones.expects === "stones");
  check("the stones ask is the one about carrying", /Touch what you are carrying/.test(stones.say));
  check(
    "the wanting screen offers six tiles, each with a line",
    wanting.wantings.length === 6 && wanting.wantings.every((w) => w.id && w.name && w.line) && wanting.expects === "wanting",
  );
  check("an unknown stone id is dropped, the known ones kept", JSON.stringify(sess.stones) === JSON.stringify(["grief", "secret"]));
  check(
    "every tap became a share the model can read",
    sess.shares.length === 4 &&
      /the weather in me is The Thunderhead/.test(sess.shares[0]) &&
      sess.shares[1].startsWith("I am carrying:") &&
      /I came out here for a lost thing/.test(sess.shares[2]) &&
      sess.shares[3] === "A whole year",
    JSON.stringify(sess.shares),
  );
  check(
    "a tapped tile is never quotable as something the seeker said",
    JSON.stringify(S.seekerWords(sess)) === JSON.stringify(["A whole year"]),
    JSON.stringify(S.seekerWords(sess)),
  );
  check(
    "…but it does reach the weave",
    /the weather in me is The Thunderhead/.test(S.toldFrom(sess)) && /a lost thing/.test(S.toldFrom(sess)),
    S.toldFrom(sess),
  );
  check("the chip answer was taken", asking.expects === "answer" && proposed.stage === "proposed");
  check("a wordless séance still seals", sealed.quest.moves.length === 3);
}

/* ---- 3. refusing to answer -------------------------------------------------------- */

section("the seeker refuses the question (pass), with no model at all");
{
  const { sess, trace, proposed, sealed } = await walk("touch", { llm: deadLlm, answer: { pass: true } });
  check(
    "a pass still walks to a sealed quest",
    stages(trace).join(",") === "naming,door,weather,stones,wanting,asking,proposed,accepted" &&
      Boolean(sealed.quest),
  );
  check("a pass adds nothing to the shares", sess.shares.length === 3, JSON.stringify(sess.shares));
  check("nothing the seeker never said is quoted back", S.seekerWords(sess).length === 0);
  check(
    "the fallback echoes name the cards instead of inventing a quote",
    ["roots", "trunk", "branches"].every((r) => proposed.echoes[r] && !proposed.echoes[r].includes("“")),
    JSON.stringify(proposed.echoes),
  );
  check("the template reading and quest arrive anyway", Boolean(proposed.reading) && Boolean(proposed.adventure));
  check("and the template is honest about being one", proposed.modes.weave === "fallback");
}

/* ---- 4. the template question ----------------------------------------------------- */

section("the template question, when the model will not ask one");
{
  const { trace } = await walk("talk", { llm: deadLlm, answer: { text: "A whole year of it." } });
  const asking = trace[3];
  const names = ["roots", "trunk", "branches"].map((r) => asking.cards[r].name);
  check("there is still a question", Boolean(asking.question) && asking.modes.ask === "fallback");
  check(
    "it names one of the three cards that were just turned",
    names.some((n) => asking.question.includes(n)),
    asking.question + "\n         cards: " + names.join(" / "),
  );
  check("it is open, not a yes/no", /^(what|who|where|when|how)\b/i.test(asking.question.split(/[.?!] /).pop()));
  check("there are still three chips", asking.chips.length === 3, JSON.stringify(asking.chips));
}
{
  // a model that answers, but with chips nobody would tap
  const llm = goodLlm({
    ask: JSON.stringify({
      question: "What did you put down to get here?",
      chips: ["a chip that runs on and on well past six words", "", null],
    }),
  });
  const { trace } = await walk("talk", { llm, answer: { text: "Everything." } });
  check(
    "a good question with bad chips keeps the question and swaps the chips",
    trace[3].question === "What did you put down to get here?" && trace[3].chips.length === 3,
    JSON.stringify(trace[3].chips),
  );
  check(
    "an over-long chip never reaches the phone",
    trace[3].chips.every((c) => c.split(/\s+/).length <= 6),
  );
}

/* ---- 5. the guards ---------------------------------------------------------------- */

section("what the séance refuses");
{
  const ctx = ctxWith(deadLlm);
  const { sess } = start("seek");
  await hear(sess, { text: "Wren" }, ctx);
  const bad = await hear(sess, { door: "shrug" }, ctx);
  check("an unknown door re-asks rather than advancing", bad.stage === "door" && bad.expects === "door");
  await hear(sess, { door: "touch" }, ctx);
  const noSky = await hear(sess, { weather: "sideways" }, ctx);
  check("an unknown sky re-asks with the six", noSky.stage === "weather" && noSky.weathers.length === 6);
  await hear(sess, { weather: "fog" }, ctx);
  await hear(sess, { stones: [] }, ctx);
  const noWant = await hear(sess, { wanting: "" }, ctx);
  check("an unknown wanting re-asks with the six", noWant.stage === "wanting" && noWant.wantings.length === 6);
  await hear(sess, { wanting: "quiet" }, ctx);
  const silent = await hear(sess, {}, ctx);
  check(
    "an empty answer at the asking re-asks the same question",
    silent.stage === "asking" && silent.question === sess.question && silent.chips.length === 3,
  );
  const answered = await hear(sess, { text: "ok then" }, ctx);
  check("and answering it moves on", answered.stage === "proposed");
}
{
  const ctx = ctxWith(deadLlm);
  const { sess } = start("seek");
  await hear(sess, { text: "Wren" }, ctx);
  await hear(sess, { door: "talk" }, ctx);
  const long = "word ".repeat(900);
  await hear(sess, { text: long }, ctx);
  check(
    "a two-minute transcript is kept at 2000 characters, not 1000",
    sess.shares[0].length === 2000,
    String(sess.shares[0].length),
  );
}
{
  const ctx = ctxWith(deadLlm);
  const { sess } = start("seek");
  const gone = await hear(null, { text: "hello" }, ctx);
  check("a séance that has aged out says so", gone.stage === "gone" && Boolean(gone.error));
  await hear(sess, { text: "Wren" }, ctx);
  await hear(sess, { door: "talk" }, ctx);
  await hear(sess, { text: "the whole thing" }, ctx);
  await hear(sess, { pass: true }, ctx);
  for (let i = 0; i < 3; i++) await hear(sess, { text: "one more thing " + i }, ctx);
  const settled = await hear(sess, { text: "and another" }, ctx);
  check("the fourth refinement is refused, gently", settled.modes.refine === "settled" && /settled/i.test(settled.say));
  const first = await accept(sess, ctx);
  const again = await accept(sess, ctx);
  check(
    "a second accept replays the sealed quest rather than resealing it",
    JSON.stringify(first.quest) === JSON.stringify(again.quest) && first.say === again.say,
  );
}

/* ---- 6. no stem anywhere ---------------------------------------------------------- */

section("the stem stage is gone");
{
  const ctx = ctxWith(deadLlm);
  const { sess } = start("seek");
  await hear(sess, { text: "Wren" }, ctx);
  await hear(sess, { door: "touch" }, ctx);
  const after = await hear(sess, { weather: "whiteout" }, ctx);
  check("the weather leads to the stones, never to a sentence to finish", after.stage === "stones" && !after.stem);
  check("no event on either path carries a stem", after.expects === "stones");
}

/* ---- 7. the sealed parchment: one address, two bearings --------------------------- */

/* The quest is spoken with ONE move pinned to a real 2026 placement and two given a
 * bearing (weave.js: THE ANCHOR / THE OPEN TWO). The parchment used to put the card's
 * directions on all three, so a move that said "lie flat somewhere quiet" sealed with a
 * street address. These walk real random draws — the spread is drawn blind, so this runs
 * enough séances to hit citywide, pending and fixed cards. */

section("the sealed parchment carries one address and two bearings");
{
  const REALMS = ["roots", "trunk", "branches"];
  /* A clock, a lettered street, the Esplanade, or a pointer at the WWW guide, which is an
   * address one lookup away. Deliberately NOT the bare word "address" — the Turtle's own
   * bearing says "No address for this one" out loud, and that is the opposite of one. */
  const ADDRESSY = /\d{1,2}:\d{2}|Esplanade|\b[A-L]\s*(?:&|and)\s*\d|WWW guide/i;
  let pinnedRight = 0;
  let bearingsClean = 0;
  let atMostOneAddress = 0;
  let sawAnchorLine = 0;
  const runs = [];
  for (let i = 0; i < 12; i++) {
    const llm = i % 4 === 0 ? goodLlm() : deadLlm;
    const { sess, sealed } = await walk(i % 2 ? "talk" : "touch", {
      llm,
      answer: { text: "I have not said the thing I came here to say." },
    });
    const ai = REALMS.indexOf(sess.anchor);
    const anchorLine = sess.located[sess.anchor].directions || "Somewhere out there";
    const wheres = sealed.quest.moves.map((m) => m.where);
    const open = wheres.filter((_, j) => j !== ai);
    if (ai >= 0 && wheres[ai].startsWith(anchorLine)) pinnedRight++;
    if (open.every((w) => w && !ADDRESSY.test(w))) bearingsClean++;
    if (wheres.filter((w) => ADDRESSY.test(w)).length <= 1) atMostOneAddress++;
    if (wheres.filter((w) => anchorLine && w.startsWith(anchorLine)).length === 1) sawAnchorLine++;
    runs.push(wheres);
  }
  check("the placed move seals with its own card's directions", pinnedRight === 12, JSON.stringify(runs[0]));
  check("exactly one move carries the anchor's directions line", sawAnchorLine === 12, JSON.stringify(runs));
  check("the other two seal with a bearing, never an address", bearingsClean === 12, JSON.stringify(runs));
  check("no sealed quest carries more than one address", atMostOneAddress === 12, JSON.stringify(runs));
}
{
  // the bearing itself: the card's own citywide line when that line is a kind of place,
  // and the Turtle's standing bearing when it is a lookup
  const clean = S.openWhere("roots", {
    status: "citywide",
    directions: "Anywhere the playa is open under you — lie down and let it mark you.",
  });
  const lookup = S.openWhere("roots", {
    status: "citywide",
    directions: "Dozens run daily citywide — check the WWW guide for a time and place near you.",
  });
  const placed = S.openWhere("branches", { status: "fixed", directions: "E & 6:15 (mid-block facing man)." });
  check("a citywide line that is a kind of place becomes the bearing", /^Anywhere the playa is open/.test(clean), clean);
  check("a citywide line that is really a lookup does not", /^No address for this one\./.test(lookup), lookup);
  check("a placed card's line is never handed to an open move", /^No address for this one\./.test(placed), placed);
}

/* ---- 8. the echoes: a clause, not a word count ------------------------------------ */

/* Two minutes of voice used to be cut into fixed seven-word windows, which land wherever
 * they land: You said “I got here Sunday and I have”. The windows are now cut at the
 * seeker's own punctuation and trimmed back to words that carry weight. */

section("the echoes quote a clause the seeker would recognise");
{
  const STORY =
    "I got here Sunday and I have not slept, and I keep telling everyone I am fine. " +
    "I am not fine. I have not said the thing I came out here to say, and last night " +
    "I walked out to the trash fence alone and stood there for an hour.";
  const flat = STORY.toLowerCase().match(/[\p{L}\p{N}_’'-]+/gu).join(" ");
  const windows = S.quoteWindows([STORY]);
  const OPENERS = /^(and|i have|the|to|of|that|but|so|my|i)\b/i;
  const ENDERS = /\b(and|i|have|the|to|of|that|but|so|my|is|was)$/i;
  check("a long story still yields quote candidates", windows.length >= 3, JSON.stringify(windows));
  check("every window is 3-8 words", windows.every((w) => {
    const n = w.split(/\s+/).length;
    return n >= 3 && n <= 8;
  }), JSON.stringify(windows));
  check(
    "no window starts mid-clause on a joining word",
    windows.every((w) => !OPENERS.test(w)),
    JSON.stringify(windows),
  );
  check("no window trails off on one either", windows.every((w) => !ENDERS.test(w)), JSON.stringify(windows));
  check(
    "every window is verbatim in what the seeker said",
    windows.every((w) => flat.includes(w.toLowerCase())) &&
      windows.every((w) => S.validEcho(`You said “${w}” — mm.`, [STORY])),
    JSON.stringify(windows),
  );
  check(
    "the windows are spread across the story, not all cut from its opening",
    flat.indexOf(windows[windows.length - 1].toLowerCase()) > flat.length / 2,
    JSON.stringify(windows),
  );
}
{
  // and the template echoes are cut from exactly those windows, one card each
  const { sess, proposed } = await walk("talk", {
    llm: deadLlm,
    answer: { text: "I put down being the calm one." },
  });
  const cut = S.quoteWindows(S.seekerWords(sess));
  const quoted = ["roots", "trunk", "branches"]
    .map((r) => (proposed.echoes[r].match(/“([^”]+)”/) || [])[1])
    .filter(Boolean);
  check(
    "the template echoes are cut from those windows, one card each",
    quoted.length === 3 && new Set(quoted).size === 3 && quoted.every((q) => cut.includes(q)),
    JSON.stringify(quoted) + "\n         windows: " + JSON.stringify(cut),
  );
}
{
  // and the event says which of the two wrote them
  const quoting = goodLlm({
    echoes: JSON.stringify({
      roots: "You said “keep telling everyone I am fine” — the dust heard that one.",
      trunk: "You said “I have not slept” — so stand still first.",
      branches: "You said “the thing I came out here to say” — say it to a face.",
    }),
  });
  const { proposed } = await walk("talk", { llm: quoting, answer: { text: "I put down being the calm one." } });
  check(
    "a model echo that quotes the seeker is reported as llm",
    proposed.modes.echoes === "llm" && proposed.echoes.trunk.includes("“I have not slept”"),
    JSON.stringify(proposed.modes) + " " + JSON.stringify(proposed.echoes),
  );
  check(
    "the other modes keys are still there",
    proposed.modes.select === "playa" && Boolean(proposed.modes.weave),
    JSON.stringify(proposed.modes),
  );
  const { proposed: templated } = await walk("talk", {
    llm: goodLlm(), // its echoes quote nothing the seeker said
    answer: { text: "I put down being the calm one." },
  });
  check(
    "echoes that quote nothing the seeker said are reported as fallback",
    templated.modes.echoes === "fallback" && templated.modes.weave === "llm",
    JSON.stringify(templated.modes),
  );
  const { proposed: dead } = await walk("touch", { llm: deadLlm, answer: { pass: true } });
  check("no model at all is reported as fallback too", dead.modes.echoes === "fallback", JSON.stringify(dead.modes));
}


/* ---- 9. every stage, every body the phone can post -------------------------------- */

/* The blast radius of a partial event is the whole séance: the kiosk persists the last
 * step it was handed, and a `proposed` event with no cards makes its renderer throw on
 * every render AND on every reload afterwards, because a phone has no idle wipe to clear
 * the saved copy. So this walks the whole matrix — twelve stages against every body shape
 * the kiosk has ever posted, plus the shapes a confused client can post — and asks the
 * one question that matters: could this be drawn?
 *
 * `drawable` is assets/index.html's own renderable(), restated. Keep the two in step. */

const REALMS3 = ["roots", "trunk", "branches"];
function drawable(e) {
  if (!e || typeof e !== "object" || !e.stage) return false;
  if (e.error) return true; // an error-marked event is a toast, not a screen
  const dealt = e.cards && REALMS3.every((r) => e.cards[r] && e.cards[r].id);
  if (e.stage === "asking") return Boolean(dealt && e.question);
  if (e.stage === "proposed") return Boolean(dealt && e.adventure);
  if (e.stage === "accepted") return Boolean(e.quest && e.quest.moves);
  return Boolean(e.say || e.doors || e.weathers || e.stones || e.wantings);
}

/** A fresh séance parked at `stage`, so one probe can never contaminate the next. */
async function seanceAt(stage, ctx) {
  const { sess } = start(stage.startsWith("tale") ? "tale" : "seek");
  if (stage === "naming" || stage === "tale_naming") return sess;
  await hear(sess, { text: "Wren" }, ctx);
  if (stage === "door" || stage === "tale_listening") return sess;
  if (stage === "tale_told") {
    await hear(sess, { text: "I walked out to the fence and I came back changed." }, ctx);
    return sess;
  }
  if (["weather", "stones", "wanting"].includes(stage)) {
    await hear(sess, { door: "touch" }, ctx);
    if (stage === "weather") return sess;
    await hear(sess, { weather: "fog" }, ctx);
    if (stage === "stones") return sess;
    await hear(sess, { stones: ["grief"] }, ctx);
    return sess;
  }
  await hear(sess, { door: "talk" }, ctx);
  if (stage === "listening") return sess;
  await hear(sess, { text: "I got here Tuesday and I have not slept, and I keep saying I am fine." }, ctx);
  if (stage === "asking") return sess;
  await hear(sess, { text: "I put down being the calm one." }, ctx);
  if (stage === "proposed") return sess;
  await accept(sess, ctx);
  return sess;
}

section("every stage answers every body with something the phone can draw");
{
  const ctx = ctxWith(deadLlm);
  const STAGES = [
    "naming", "door", "listening", "weather", "stones", "wanting",
    "asking", "proposed", "accepted", "tale_naming", "tale_listening", "tale_told",
  ];
  /* Every body the kiosk posts, plus the ones a client that has fallen a stage behind
   * posts by accident — which is the real bug: the reply was lost on LTE after the
   * Durable Object had already moved on, and the seeker taps the screen they still see. */
  const BODIES = [
    ["nothing at all", {}],
    ["a refusal", { pass: true }],
    ["a refusal as a string", { pass: "true" }],
    ["a tapped chip", { chip: "A whole year" }],
    ["a door", { door: "talk" }],
    ["a sky", { weather: "fog" }],
    ["stones", { stones: ["grief"] }],
    ["a wanting", { wanting: "quiet" }],
    ["words", { text: "here is a thing I have not said" }],
    ["empty words", { text: "" }],
    ["only meta", { meta: { ms: 900, input: "voice" } }],
    ["an unknown key", { shrug: true }],
    ["a bare string", "just a string"],
    ["null", null],
  ];
  let drew = 0;
  let missed = [];
  let visited = new Set();
  for (const stage of STAGES) {
    for (const [label, body] of BODIES) {
      const sess = await seanceAt(stage, ctx);
      visited.add(sess.stage);
      if (sess.stage !== stage) { missed.push(`${stage}: parked at ${sess.stage}`); continue; }
      const e = await hear(sess, body, ctx);
      if (drawable(e)) drew++;
      else missed.push(`${stage} + ${label} -> ${JSON.stringify(e).slice(0, 160)}`);
    }
  }
  // the control: if the walker silently failed to reach a stage, the matrix proves nothing
  check(
    "the matrix actually visits all twelve stages",
    STAGES.every((st) => visited.has(st)),
    STAGES.filter((st) => !visited.has(st)).join(", "),
  );
  check(
    `every stage × body pair is renderable (${drew}/${STAGES.length * BODIES.length})`,
    missed.length === 0,
    missed.slice(0, 6).join("\n         "),
  );
}
{
  // and the two that were actually blowing up the phone, named
  const ctx = ctxWith(deadLlm);
  for (const body of [{ pass: true }, { chip: "A whole year" }, {}, { stones: ["grief"] }]) {
    const sess = await seanceAt("proposed", ctx);
    const e = await hear(sess, body, ctx);
    check(
      "a standing decision answered with " + JSON.stringify(body) + " re-offers the whole quest",
      drawable(e) && e.stage === "proposed" && !e.error &&
        Boolean(e.reading && e.ask && e.echoes && e.map),
      JSON.stringify(Object.keys(e)),
    );
  }
  const asking = await seanceAt("asking", ctx);
  const retry = await hear(asking, {}, ctx);
  check(
    "an empty answer at the asking still carries the cards it is asking about",
    drawable(retry) && retry.stage === "asking" && retry.retry === true &&
      retry.question === asking.question && Boolean(retry.map && retry.directions),
    JSON.stringify(Object.keys(retry)),
  );
  const sealed = await seanceAt("accepted", ctx);
  const after = await hear(sealed, { pass: true }, ctx);
  check(
    "a sealed séance replays the parchment rather than saying it heard wind",
    drawable(after) && after.stage === "accepted" && after.quest.moves.length === 3,
    JSON.stringify(Object.keys(after)),
  );
}
{
  // replayable(): what index.js saves when a request throws half-way through
  const ctx = ctxWith(deadLlm);
  const asking = await seanceAt("asking", ctx);
  const half = { ...asking, question: null };
  check("a finished asking is worth saving", replayable(asking) === true);
  check("an asking with no question yet is not", replayable(half) === false);
  const proposed = await seanceAt("proposed", ctx);
  check("a proposed with a quest on it is", replayable(proposed) === true);
  check("a proposed with no quest is not", replayable({ ...proposed, adventure: null }) === false);
  const sealed = await seanceAt("accepted", ctx);
  check("a sealed séance is", replayable(sealed) === true && replayable({ ...sealed, quest: null }) === false);
  check("and the stages with nothing to half-build always are", replayable({ stage: "door" }) === true);
}

/* ---- 10. the phone a stage behind the server -------------------------------------- */

/* The real sequence: the séance answers, the reply dies on LTE, the Durable Object has
 * already saved `proposed`, the seeker reloads onto the `asking` screen it last saw and
 * taps "let it be". Every one of those stale bodies has to land somewhere sane, and the
 * séance still has to end with a sealed quest. */

section("a phone one stage behind the server still reaches a sealed quest");
{
  const ctx = ctxWith(deadLlm);
  const sess = await seanceAt("proposed", ctx);
  const first = sess.adventure;
  const stale1 = await hear(sess, { pass: true }, ctx);
  const stale2 = await hear(sess, { chip: "A whole year" }, ctx);
  check(
    "the stale pass and the stale chip both come back as the standing decision",
    drawable(stale1) && drawable(stale2) &&
      (stale1.modes || {}).refine === "standing" && (stale2.modes || {}).refine === "standing",
    JSON.stringify([stale1.modes, stale2.modes]),
  );
  check("neither spent a refinement", sess.refines === 0, String(sess.refines));
  check("neither changed the quest under the seeker", sess.adventure === first);
  check(
    "neither became a share the Turtle will quote back",
    !sess.shares.includes("A whole year"),
    JSON.stringify(sess.shares),
  );
  const sealed = await accept(sess, ctx);
  check(
    "and the séance still seals",
    sealed.stage === "accepted" && sealed.quest.moves.length === 3 && !sealed.error,
  );
  // …and the same walk with a REAL refinement in the middle of the stale ones
  const s2 = await seanceAt("proposed", ctx);
  await hear(s2, {}, ctx);
  const refined = await hear(s2, { text: "I have not told my sister I am here." }, ctx);
  await hear(s2, { pass: true }, ctx);
  check(
    "a real refinement between two stale bodies is still taken",
    (refined.modes || {}).refine === "fallback" && s2.refines === 1 && Boolean(refined.adventure),
    JSON.stringify(refined.modes) + " refines=" + s2.refines,
  );
  check("and a sealed quest still comes out of it", Boolean((await accept(s2, ctx)).quest));
}

/* ---- 11. the caps: two minutes of voice, twelve shares ---------------------------- */

section("the caps hold, and truncate rather than refuse");
{
  const ctx = ctxWith(deadLlm);
  const sess = await seanceAt("listening", ctx);
  const story = "I came out here to say a thing and I have not said it yet. ".repeat(90); // ~5300
  check("the fixture is longer than the cap", story.length > 5000, String(story.length));
  const e = await hear(sess, story, ctx);
  check(
    "a 5000-character transcript is truncated, not refused",
    e.stage === "asking" && !e.error && sess.shares.length === 1 && sess.shares[0].length === 2000,
    e.stage + " share=" + (sess.shares[0] || "").length,
  );
  check(
    "and the truncated story still reaches what the weave is given",
    S.toldFrom(sess).startsWith("I came out here to say a thing") &&
      S.toldFrom(sess).length >= 2000,
    String(S.toldFrom(sess).length),
  );
  check(
    "the 2000 is the listening cap only — a share elsewhere is still cut at 1000",
    (await (async () => {
      const other = await seanceAt("asking", ctx);
      await hear(other, { text: story }, ctx);
      return other.shares[other.shares.length - 1].length;
    })()) === 1000,
  );
}
{
  const ctx = ctxWith(deadLlm);
  const sess = await seanceAt("proposed", ctx);
  for (let i = 0; i < 3; i++) await hear(sess, { text: "one more true thing, number " + i }, ctx);
  const settled = await hear(sess, { text: "and one more after that" }, ctx);
  check(
    "three refinements, then the Tree has settled — and the settled event is still whole",
    (settled.modes || {}).refine === "settled" && drawable(settled) &&
      Boolean(settled.reading && settled.echoes),
    JSON.stringify(settled.modes),
  );
  check(
    "a full story plus three refines stays inside the twelve-share roof",
    sess.shares.length <= 12 && sess.shares.length === 6,
    String(sess.shares.length),
  );
  // the roof itself: a séance cannot reach twelve through the API, so push it there
  sess.shares = Array.from({ length: 12 }, (_, i) => "share " + i);
  sess.refines = 0;
  await hear(sess, { text: "the thirteenth thing" }, ctx);
  check(
    "the thirteenth share pushes the first one off the shelf",
    sess.shares.length === 12 && sess.shares[11] === "the thirteenth thing" && sess.shares[0] === "share 1",
    JSON.stringify(sess.shares.slice(0, 2)) + " … " + JSON.stringify(sess.shares.slice(-1)),
  );
}

/* ---- 12. the ears: a séance, or nothing ------------------------------------------- */

/* /api/transcribe used to be a free Whisper endpoint — no séance, no session, 4MB a POST.
 * src/ears.js is its own module partly so this can run: index.js re-exports the Durable
 * Object class and cannot be imported outside the Workers runtime. */

section("the ears will not open without a séance");
{
  const store = new Map();
  const fakeStore = {
    idFromName: (n) => n,
    get: (id) => ({
      async load() { return store.get(id) || null; },
      async save(sess) { store.set(id, sess); },
    }),
  };
  const heard = [];
  const env = {
    SESSION_DO: fakeStore,
    WHISPER_MODEL: "test-whisper",
    AI: {
      async run(model, inputs) { heard.push({ model, bytes: (inputs.audio || "").length }); return { text: "  the   transcript  " }; },
    },
  };
  const ears = (sid, bytes) => {
    const u = new URL("https://turtle.example/api/transcribe");
    const req = new Request(u, {
      method: "POST",
      body: bytes || new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]),
      headers: sid ? { "x-seance-session": sid } : {},
    });
    return transcribe(req, env, u);
  };

  const live = await seanceAt("listening", ctxWith(deadLlm));
  store.set(live.id, live);
  const tapping = await seanceAt("weather", ctxWith(deadLlm));
  store.set(tapping.id, tapping);

  const nobody = await (await ears("")).json();
  check("no session id, no whisper", Boolean(nobody.error) && heard.length === 0, JSON.stringify(nobody));
  const stranger = await (await ears("deadbeefdead")).json();
  check("an id that is not a séance, no whisper", Boolean(stranger.error) && heard.length === 0, JSON.stringify(stranger));
  const tapStage = await (await ears(tapping.id)).json();
  check(
    "a séance on a tap screen is not listening for words",
    Boolean(tapStage.error) && tapStage.stage === "weather" && heard.length === 0,
    JSON.stringify(tapStage),
  );
  const rejected = await ears("");
  check("and every refusal is a séance-shaped 200, not a status the phone will parrot", rejected.status === 200);

  const ok = await ears(live.id);
  const got = await ok.json();
  check(
    "a live séance at the talk door is heard, and the transcript comes back squeezed",
    ok.status === 200 && got.text === "the transcript" && heard.length === 1 && heard[0].model === "test-whisper",
    JSON.stringify(got) + " " + JSON.stringify(heard),
  );

  const tooMuch = await ears(live.id, new Uint8Array(MAX_AUDIO_BYTES + 1));
  check(
    "more than four megabytes is refused with a 413, unheard",
    tooMuch.status === 413 && heard.length === 1,
    String(tooMuch.status) + " calls=" + heard.length,
  );
  const empty = await ears(live.id, new Uint8Array(0));
  check("and an empty body never reaches the model either", empty.status === 400 && heard.length === 1);
}
{
  // the base64 the model is handed, built in slices — the join has to be byte-exact
  const bytes = new Uint8Array(200000);
  for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 7 + (i >> 5)) & 0xff;
  check(
    "the sliced base64 is the same string one btoa would have made",
    toBase64(bytes) === Buffer.from(bytes).toString("base64"),
  );
  check(
    "including at the lengths that do not divide by three",
    [0, 1, 2, 3, 47, 49151, 49152, 49153].every(
      (n) => toBase64(bytes.subarray(0, n)) === Buffer.from(bytes.subarray(0, n)).toString("base64"),
    ),
  );
}

console.log(failures ? `\n${failures} FAILED` : "\nALL PASS");
process.exit(failures ? 1 : 0);
