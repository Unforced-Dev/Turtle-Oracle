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
import { biteRealm, landmarkRealm, landmarkWhere } from "../src/weave.js";
import { formatReceipt } from "../src/printer.js";
import { transcribe, toBase64, MAX_AUDIO_BYTES } from "../src/ears.js";
import CARDS from "../../data/cards.json" with { type: "json" };
import { voiceText, voiceChoice, TRYOUT_SPEAKERS, TRYOUT_MODELS } from "../src/voice.js";

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
      look:
        "Three cards, one thread. The Taproot came up first: the low place that grows you " +
        "while it feels like burying you — your Tuesday with no sleep. Under it the Heartwood, " +
        "what holds from the inside; you have been that for everyone, telling them you are fine. " +
        "And reaching, the Lantern: the thing you have not said yet, and it is already lit.",
      question: "The shell wants to know: what did you put down to get here?",
      chips: ["My phone", "A whole year", "Nothing yet"],
    }),
    weave: JSON.stringify({
      reading: "You came a long way to sit still. " + "word ".repeat(96),
      adventure:
        "Say the sentence you have been swallowing, out loud, to the first face that stops for " +
        "you tonight. Out past the last lamp. Bring back what their face did.",
    }),
    echoes: JSON.stringify({ roots: "no quote", trunk: "no quote", branches: "no quote" }),
    seal: JSON.stringify({
      move: {
        task: "Say the sentence you have been swallowing, out loud, to one face.",
        where: "out past the last lamp",
        proof: "what their face did",
        leave: "",
      },
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

/* ---- the walks --------------------------------------------------------------------- */

const STORY =
  "I got here Tuesday and I have not slept and I keep telling everyone I am fine. " +
  "I am not fine. I have not said the thing I came out here to say.";

/** THE PULL: the only way in now. A name, and then three cards.
 *  `door` is "pull" for that, or "talk"/"touch" for an OLD SESSION — one written by the
 *  build before this one and still sitting in a Durable Object at stage `door`. Nothing
 *  routes there any more, so those two are rewound by hand; they must still finish. */
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
  if (door === "pull") {
    await say({ text: "um, hi there, I'm Wren" }); // naming -> asking, in one move
  } else {
    rewindToDoor(sess);
    await say({}); // the door, offered again to a phone that came back to it
    await say({ door }); // door -> listening | weather
    if (door === "talk") {
      await say({ text: STORY });
    } else {
      await say({ weather: "thunderhead" });
      await say({ stones: ["grief", "secret", "not-a-stone"] });
      await say({ wanting: "lost" });
    }
  }
  const proposed = await say(answer); // asking -> proposed
  const sealed = await accept(sess, ctx);
  trace.push(sealed);
  return { sess, trace, proposed, sealed };
}

const stages = (trace) => trace.map((e) => e.stage);

/** A séance parked at the OLD door: what a Durable Object written by the build before
 *  this one still holds. nameStep will not go there any more, so the stages that only a
 *  legacy session can reach are rewound by hand — they must all still answer. */
function rewindToDoor(sess, name = "Wren") {
  sess.name = name;
  sess.stage = "door";
  sess.door = null;
  sess.picks = null;
  sess.located = null;
  sess.bite = null;
  sess.look = null;
  sess.question = null;
  sess.chips = null;
  return sess;
}

/* ---- 1. the pull: a name, and then the cards --------------------------------------- */

section("the pull: naming → asking → proposed → accepted, on the cards alone");
{
  const llm = goodLlm();
  const { sess, trace, proposed, sealed } = await walk("pull", { llm, answer: { pass: true } });
  check(
    "walks the stages in order — no door, no touch screens",
    JSON.stringify(stages(trace)) === JSON.stringify(["naming", "asking", "proposed", "accepted"]),
    JSON.stringify(stages(trace)),
  );
  const [, asking] = trace;
  check(
    "the name is heard and said back, and the draw follows in the same breath",
    sess.name === "Wren" && asking.say.startsWith("Wren.") && asking.say.length > 30,
    asking.say,
  );
  check("the séance knows it pulled first", sess.door === "pull");
  check("nothing offers a door any more", !asking.doors && !asking.weathers && !asking.wantings);
  check(
    "the cards are on the table at the asking, with a gloss each",
    asking.expects === "answer" &&
      ["roots", "trunk", "branches"].every((r) => asking.cards[r] && asking.cards[r].thumb) &&
      ["roots", "trunk", "branches"].every(
        (r) => typeof asking.cards[r].gloss === "string" && asking.cards[r].gloss.length > 8,
      ),
    JSON.stringify(["roots", "trunk", "branches"].map((r) => asking.cards[r].gloss)),
  );
  /* THE LOOK IS THE READING NOW. Most seekers will let the cards speak and never add a
     word, so what the Turtle says over the spread has to stand on its own: whole spoken
     sentences, no question inside it, no place names. */
  check(
    "the look is a reading of the spread, not a caption",
    typeof asking.look === "string" &&
      asking.look.split(/\s+/).length >= 45 &&
      asking.look.split(/\s+/).length <= 130 &&
      !/\?\s*$/.test(asking.look),
    String(asking.look),
  );
  check("the model's look is used when it gives one", /one thread/.test(asking.look) && asking.modes.look === "llm");
  check(
    "one open question, and three chips nobody has to tap",
    Boolean(asking.question) &&
      asking.question.split(/\s+/).length < 30 &&
      asking.chips.length === 3 &&
      asking.chips.every((c) => c.split(/\s+/).length <= 6),
    JSON.stringify(asking.chips),
  );
  check("the seeker has said nothing, and nothing was invented for them", sess.shares.length === 0);
  check(
    "letting the cards speak still yields a reading and a quest",
    Boolean(proposed.reading) && Boolean(proposed.adventure) && proposed.expects === "decision",
  );
  check("and the event says the reading came off the cards alone", proposed.modes.told === "cards");
  check(
    "the fallback echoes name the cards rather than invent a quote",
    ["roots", "trunk", "branches"].every((r) => proposed.echoes[r] && !proposed.echoes[r].includes("“")),
    JSON.stringify(proposed.echoes),
  );
  check(
    "the seal produces ONE bite — act, bearing, proof — and the vow",
    sealed.quest.moves.length === 1 &&
      ["card", "task", "where", "proof"].every((k) => sealed.quest.moves[0][k]) &&
      Boolean(sealed.quest.vow),
    JSON.stringify(sealed.quest.moves),
  );
  check("the sealed quest is stamped with the name", sealed.quest.for === "Wren");
  check(
    "every stage that spends a model call asked for one",
    llm.seen.includes("ask") && llm.seen.includes("weave") && llm.seen.includes("seal"),
    JSON.stringify(llm.seen),
  );
}

/* The pass path with NO model at all: the templates have to carry a whole séance, because
   a seeker who says nothing is the ordinary case and the offline turtle still has to read. */
{
  const { sess, trace, proposed, sealed } = await walk("pull", { llm: deadLlm, answer: { pass: true } });
  const [, asking] = trace;
  check(
    "with no model, the pull still walks to a sealed quest",
    stages(trace).join(",") === "naming,asking,proposed,accepted" && Boolean(sealed.quest),
  );
  check(
    "the template look names all three cards and what they mean",
    ["roots", "trunk", "branches"].every(
      (r) => asking.look.includes(asking.cards[r].name) && asking.look.includes(asking.cards[r].gloss),
    ),
    String(asking.look),
  );
  check("the template question is still open", /\?\s*$/.test(asking.question) && asking.modes.ask === "fallback");
  check(
    "the template reading does not call the silent seeker mute",
    Boolean(proposed.reading) && !/could not put it into words/.test(proposed.reading),
    proposed.reading,
  );
  check("and the template is honest about being one", proposed.modes.weave === "fallback");
  check("a pass adds nothing to the shares", sess.shares.length === 0);
}

/* Context is OPTIONAL, not gone: whatever the seeker adds is a share and the weave uses it. */
{
  const llm = goodLlm();
  const { sess, trace, proposed } = await walk("pull", {
    llm,
    answer: { text: "I put down being the calm one." },
  });
  check(
    "an answer at the asking becomes the one share the weave reads",
    sess.shares.length === 1 && sess.shares[0] === "I put down being the calm one.",
    JSON.stringify(sess.shares),
  );
  check("and the event says the seeker fed something in", proposed.modes.told === "told");
  check(
    "the reading and the quest arrive as before",
    Boolean(proposed.reading) && Boolean(proposed.adventure) && Boolean(proposed.ask),
  );
  check("the echoes may quote them now", ["roots", "trunk", "branches"].every((r) => proposed.echoes[r]));
  check("a chip is an answer too", trace[1].chips.length === 3);
}
{
  const llm = goodLlm();
  const { sess } = await walk("pull", { llm, answer: { chip: "A whole year" } });
  check("a tapped chip reaches the shares as the seeker's own words", JSON.stringify(sess.shares) === JSON.stringify(["A whole year"]));
}

/* ---- 1b. an old session, still at the talk door ------------------------------------ */

section("an old session at the talk door: door → listening → asking → proposed → accepted");
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
  check(
    "the door still offers exactly talk and touch",
    JSON.stringify(door.doors.map((d) => d.id)) === JSON.stringify(["talk", "touch"]) &&
      door.expects === "door" &&
      door.doors.every((d) => d.label),
  );
  check("the talk door still invites a story", listening.expects === "story" && /burn/i.test(listening.say));
  check(
    "the cards are revealed at the asking, not at the reading",
    asking.expects === "answer" &&
      ["roots", "trunk", "branches"].every((r) => asking.cards[r] && asking.cards[r].thumb) &&
      proposed.cards.roots.id === asking.cards.roots.id,
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
  check("an old session still seals one bite", sealed.quest.moves.length === 1 && Boolean(sealed.quest.vow));
}

/* ---- 2. an old session, still at the touch door ------------------------------------ */

section("an old session at the touch door: door → weather → stones → wanting → asking → …");
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
  check("a wordless séance still seals", sealed.quest.moves.length === 1);
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
    "and still a look at the table that names all three cards with their meaning",
    typeof asking.look === "string" && names.every((n) => asking.look.includes(n)) &&
      ["roots", "trunk", "branches"].every((r) => asking.look.includes(asking.cards[r].gloss)),
    String(asking.look),
  );
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
  rewindToDoor(sess);
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
  rewindToDoor(sess);
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
  rewindToDoor(sess);
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
  rewindToDoor(sess);
  await hear(sess, { door: "touch" }, ctx);
  const after = await hear(sess, { weather: "whiteout" }, ctx);
  check("the weather leads to the stones, never to a sentence to finish", after.stage === "stones" && !after.stem);
  check("no event on either path carries a stem", after.expects === "stones");
}

/* ---- 7. the sealed quest: one bite, one bearing, one proof ----------------------- */

/* The quest is ONE act now (weave.js: THE BITE / ONE BEARING / ONE PROOF). The parchment
 * used to seal three moves with a street address on one of them; it now seals the single
 * act the seeker heard, and its `where` is a bearing — a kind of place, a kind of person,
 * an hour — unless the card happens to stand at one of the four placements nobody can miss.
 * These walk real random draws, because the spread is drawn blind. */

section("the sealed quest is one bite, with a bearing and a proof");
{
  /* A clock, a lettered street, the Esplanade, or a pointer at the WWW guide, which is an
   * address one lookup away. Deliberately NOT the bare word "address" — the Turtle's own
   * bearing says "No address for this one" out loud, and that is the opposite of one. */
  const ADDRESSY = /\d{1,2}:\d{2}|Esplanade|\b[A-L]\s*(?:&|and)\s*\d|WWW guide/i;
  let oneBite = 0;
  let bitTheRightCard = 0;
  let woreABearing = 0;
  let carriedAProof = 0;
  let landmarks = 0;
  const runs = [];
  for (let i = 0; i < 12; i++) {
    const llm = i % 4 === 0 ? goodLlm() : deadLlm;
    const { sess, sealed } = await walk(i % 2 ? "talk" : "touch", {
      llm,
      answer: { text: "I have not said the thing I came here to say." },
    });
    const moves = sealed.quest.moves;
    const m = moves[0];
    if (moves.length === 1) oneBite++;
    if (m.card === sess.picks[sess.bite].name) bitTheRightCard++;
    if (m.proof && m.task) carriedAProof++;
    if (landmarkRealm(sess.located) === sess.bite) {
      landmarks++;
      // the one draw where a place may be named: by its name and a direction, never by
      // the placement data's clock-and-street line (that leaked onto staging 2026-09-02)
      const lm = landmarkWhere(sess.located[sess.bite]);
      if (m.where && !ADDRESSY.test(m.where) && (llm === deadLlm ? m.where === lm : true)) woreABearing++;
    } else if (m.where && !ADDRESSY.test(m.where)) {
      woreABearing++;
    }
    runs.push({ card: m.card, where: m.where });
  }
  check("every sealed quest carries exactly one move", oneBite === 12, JSON.stringify(runs));
  check(
    "and it is the card the spoken quest was bitten from",
    bitTheRightCard === 12,
    JSON.stringify(runs),
  );
  check(
    `the where is a bearing, never an address (${12 - landmarks} bearings, ${landmarks} landmarks)`,
    woreABearing === 12,
    JSON.stringify(runs),
  );
  check("and the bite always asks for something back", carriedAProof === 12, JSON.stringify(runs));
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
  check("a placed card's line is never handed to an open bite", /^No address for this one\./.test(placed), placed);
}
{
  /* The model's own bearing is the one the seeker HEARD, so it is worth sealing — but only
   * when it is a bearing. It was told not to name a camp and it names camps anyway. */
  const keep = [
    "out past the last lamp",
    "wherever the music is worst",
    "the first person who hands you water",
    "before the sun is up",
    "Somewhere quiet on the open playa",
    // an hour on its own is a TIME OF DAY, which is one of the three things a bearing may
    // be — the flat address rule was reading the clock and throwing the bearing away
    "before 6:00, when the light is grey",
    // the city capitalizes some common nouns; none of these is a camp
    "out where the Deep Playa goes dark",
    "the first Ranger you see",
    // two sentences: the capital that starts the SECOND one is forced too
    "wherever the music is worst. Before the sun is up",
    "Center Camp",
  ];
  const drop = [
    "Camp Questionmark, 7:30 & E",
    "the Esplanade at 3:00",
    "Ashram Galactica — ask at the desk",
    "",
    // one word, and it is a camp: there is no sentence to forgive the capital
    "Kidsville",
    "Camp Questionmark at 7:30 & E",
    "out past the last lamp, and then keep walking until you reach the place where the music " +
      "finally gives up on you",
  ];
  check("a real bearing is kept", keep.every(S.usableBearing), JSON.stringify(keep.filter((w) => !S.usableBearing(w))));
  check(
    "an address or a camp name in a bearing is not",
    drop.every((w) => !S.usableBearing(w)),
    JSON.stringify(drop.filter(S.usableBearing)),
  );
  /* End to end, on real draws: the model's clean bearing is the one sealed, and the camp
   * address it invented instead is thrown away for the Turtle's own line — at a landmark
   * draw too, where the Turtle's line is the landmark's name and a direction. */
  const camped = () =>
    goodLlm({
      seal: JSON.stringify({
        move: { task: "Say it to one face.", where: "Camp Questionmark at 7:30 & E", proof: "their face" },
      }),
    });
  let sealedBearing = 0;
  let refusedCamp = 0;
  for (let i = 0; i < 6; i++) {
    const a = await walk("talk", { llm: goodLlm(), answer: { text: "I have not said it yet." } });
    const b = await walk("talk", { llm: camped(), answer: { text: "I have not said it yet." } });
    const aWhere = a.sealed.quest.moves[0].where;
    const bWhere = b.sealed.quest.moves[0].where;
    if (aWhere === "out past the last lamp") sealedBearing++;
    // the Turtle's own "No address for this one." must not trip an address check here
    if (!/Camp Questionmark|7:30|\d{1,2}:\d{2}|Esplanade|\b[A-L]\s*(?:&|and)\s*\d/.test(bWhere)) refusedCamp++;
  }
  check("the model's bearing reaches the parchment when it is one", sealedBearing === 6, String(sealedBearing));
  check("and a camp address it invented never does", refusedCamp === 6, String(refusedCamp));
}
{
  /* THE QUEST OPENED UP. A bite may now say where by naming the place ITS OWN card stands
     at — the quest prompt offers that as half of what a bearing may be — so the parchment
     has to accept the same thing the seeker just heard. Every OTHER camp is still a
     placement in disguise, and an address is still an address. */
  check(
    "the bite card's own place is a bearing",
    S.usableBearing("Fractal Nation — walk toward the loud edge", "Fractal Nation") &&
      S.usableBearing("Kidsville, at the quiet end of the city", "Kidsville") &&
      S.usableBearing("out past the last lamp", "Fractal Nation"),
  );
  check(
    "another camp's name still is not, however the card is placed",
    !S.usableBearing("Camp Questionmark, past the loud edge", "Fractal Nation") &&
      !S.usableBearing("Ashram Galactica — ask at the desk", "Fractal Nation") &&
      !S.usableBearing("Kidsville", "Fractal Nation"),
  );
  check(
    "and the card's own place with an address on it is still an address",
    !S.usableBearing("Fractal Nation at 7:30 & E", "Fractal Nation") &&
      !S.usableBearing("Fractal Nation, 3:00 & Esplanade", "Fractal Nation"),
  );
  /* End to end on real draws: the fake model reads the bite card's place out of the seal
     prompt itself, so this works whatever the Tree happens to choose. */
  const sealsWhere = (build) => {
    const base = goodLlm();
    return {
      seen: base.seen,
      available: () => true,
      async generate(prompt, opts = {}) {
        if (opts.stage === "seal") {
          const at = (prompt.match(/at="([^"]*)"/) || [])[1] || "";
          return JSON.stringify({
            move: { task: "Say it to one face.", where: build(at), proof: "what their face did" },
          });
        }
        return base.generate(prompt, opts);
      },
    };
  };
  let namedItsOwn = 0;
  let refusedAnother = 0;
  for (let i = 0; i < 8; i++) {
    const own = await walk("pull", {
      llm: sealsWhere((at) => `${at} — walk toward it`),
      answer: { pass: true },
    });
    const other = await walk("pull", {
      llm: sealsWhere(() => "Camp Questionmark — ask at the desk"),
      answer: { pass: true },
    });
    const at = own.sess.picks[own.sess.bite].real_2026.name;
    if (own.sealed.quest.moves[0].where === `${at} — walk toward it`) namedItsOwn++;
    if (!/Questionmark/.test(other.sealed.quest.moves[0].where)) refusedAnother++;
  }
  /* The 8 draws above are random, so they cannot prove this — and the first version of
     the rule quietly refused three of the deck's own places, because it reduced the
     bearing's words one way and the place's words another ("Self-Reliance",
     "Sunrise/Sunset", "El Pulpo Mecánico"). Every card in the deck, every time. */
  const refused = CARDS.cards.filter(
    (c) => !S.usableBearing(`${c.real_2026.name} — walk toward it`, c.real_2026.name),
  );
  check(
    `every card in the deck may name its own place (${CARDS.cards.length} cards)`,
    refused.length === 0,
    JSON.stringify(refused.map((c) => c.real_2026.name)),
  );
  /* …and it opens the door to that ONE place. Said mid-bearing, where no capital is
     forced, another card's place is still a placement in disguise. */
  const strangers = ["El Pulpo Mecánico", "Mebuyan Pulse", "Barbie Death Village"];
  check(
    "and only to that one — another card's place is still refused",
    strangers.every((n) => !S.usableBearing(`walk toward ${n}`, "Kidsville")) &&
      strangers.every((n) => S.usableBearing(`walk toward ${n}`, n)),
  );
  check("a bearing that names the bite card's own place is sealed", namedItsOwn === 8, String(namedItsOwn));
  check("a bearing that names any other camp is not", refusedAnother === 8, String(refusedAnother));
}
{
  /* The offline quest is the same three parts, stitched from the card: one act, one
   * bearing, one proof — and nothing that reads as an itinerary. */
  const { sess, proposed } = await walk("touch", { llm: deadLlm, answer: { pass: true } });
  const n = proposed.adventure.split(/\s+/).length;
  check(`the template quest stays one bite (${n}w)`, n <= 90, proposed.adventure);
  check(
    "and never speaks in First, Second, Third",
    !/\b(First|Second|Third)[.,]/.test(proposed.adventure),
    proposed.adventure,
  );
  /* the bearing it speaks is the one the parchment will seal — the card's own citywide
     line when that is a kind of place, the Turtle's standing line when it is not, and the
     landmark's name and direction on the rare draw that stands at one */
  const bearing =
    landmarkRealm(sess.located) === sess.bite
      ? landmarkWhere(sess.located[sess.bite])
      : S.openWhere(sess.bite, sess.located[sess.bite]);
  check(
    "it says where, and what to bring back",
    proposed.adventure.includes(bearing) && /Bring back /.test(proposed.adventure),
    proposed.adventure + "\n         bearing: " + bearing,
  );
}
{
  /* A rewrite that is a shrug never reaches the seeker: the refinement falls to the
   * template, which genuinely re-scores the cards. */
  const stub = goodLlm({ refine: JSON.stringify({ say: "That changes it.", adventure: "do a thing" }) });
  const sess = await seanceAt("proposed", ctxWith(stub));
  const out = await hear(sess, { text: "I have never told anyone I sing." }, ctxWith(stub));
  check(
    "a stub rewrite is refused and the template answers instead",
    (out.modes || {}).refine === "fallback" && Boolean(out.adventure),
    JSON.stringify(out.modes),
  );
  const long = goodLlm({
    refine: JSON.stringify({ say: "That changes it.", adventure: "word ".repeat(120) }),
  });
  const s2 = await seanceAt("proposed", ctxWith(long));
  const out2 = await hear(s2, { text: "I have never told anyone I sing." }, ctxWith(long));
  check("a rambling rewrite is refused too", (out2.modes || {}).refine === "fallback", JSON.stringify(out2.modes));
}

{
  /* THE SPOKEN quest is address-checked too. The seal's bearing has been guarded since the
   * rebuild, but the seeker HEARS the quest before any parchment exists — a clock and a
   * lettered street in that is heard whatever the parchment later says. So a spoken address
   * costs one more roll of the model, and then the template, whose bearing is a bearing by
   * construction. */
  const CLEAN = JSON.stringify({
    reading: "You came a long way to sit still. " + "word ".repeat(96),
    adventure:
      "Say the sentence you have been swallowing, out loud, to the first face that stops for " +
      "you tonight. Out past the last lamp. Bring back what their face did.",
  });
  const ADDRESSED = JSON.stringify({
    reading: "You came a long way to sit still. " + "word ".repeat(96),
    adventure:
      "Go to Camp Questionmark at 7:30 & E before 9:00 and say the thing you have not said. " +
      "Bring back what their face did.",
  });
  /** goodLlm, but the weave answers a different thing on each roll. */
  function weaver(...rolls) {
    const base = goodLlm();
    let i = 0;
    return {
      seen: base.seen,
      available: () => true,
      async generate(p, opts = {}) {
        if (opts.stage !== "weave") return base.generate(p, opts);
        base.seen.push("weave");
        return rolls[Math.min(i++, rolls.length - 1)];
      },
    };
  }
  const second = weaver(ADDRESSED, CLEAN);
  const { proposed: reRolled } = await walk("talk", { llm: second, answer: { text: "I have not said it yet." } });
  check(
    "a spoken quest with an address is re-rolled, and the clean roll is what is spoken",
    (reRolled.modes || {}).weave === "llm" && /Out past the last lamp/.test(reRolled.adventure) &&
      !/7:30/.test(reRolled.adventure) &&
      second.seen.filter((s) => s === "weave").length === 2,
    reRolled.adventure,
  );
  const never = weaver(ADDRESSED);
  const { proposed: templated } = await walk("talk", { llm: never, answer: { text: "I have not said it yet." } });
  check(
    "and a model that only ever gives an address loses the turn to the template",
    (templated.modes || {}).weave === "fallback" && !/7:30|Camp Questionmark/.test(templated.adventure),
    templated.adventure,
  );
}
{
  /* THE SEAL THAT DID NOT ANSWER. When sealLlm comes back null the parchment used to fall
   * to the card's canned dare — which is right offline, where the spoken quest was stitched
   * from that dare, and wrong on the model path, where the seeker heard a quest written for
   * them and then read a stock errand off the parchment. Two quests in one séance. */
  const mute = () => goodLlm({ seal: "not json at all" });
  let fromTheSpokenQuest = 0;
  let notTheDare = 0;
  for (let i = 0; i < 6; i++) {
    const { sess, sealed } = await walk("talk", {
      llm: mute(),
      answer: { text: "I have not said it yet." },
    });
    const m = sealed.quest.moves[0];
    const dare = sess.picks[sess.bite].turtle_dare;
    if (m.task === "Say the sentence you have been swallowing, out loud, to the first face " +
      "that stops for you tonight.") fromTheSpokenQuest++;
    if (m.task !== dare && m.proof === "Bring back what their face did.") notTheDare++;
  }
  check(
    "a model quest with no seal still prints the quest the seeker HEARD",
    fromTheSpokenQuest === 6,
    String(fromTheSpokenQuest),
  );
  check(
    "and its proof is the one the quest asked for out loud, not the card's",
    notTheDare === 6,
    String(notTheDare),
  );
  // the offline quest is built FROM the dare, so there the dare is what they heard
  const { sess: os, sealed: oq } = await walk("touch", { llm: deadLlm, answer: { pass: true } });
  check(
    "the template quest still seals its own dare",
    oq.quest.moves[0].task === os.picks[os.bite].turtle_dare,
    oq.quest.moves[0].task,
  );
}
{
  /* The model answers the seal in the shape it was asked for for a year — {"moves": [...]}
   * — often enough that dropping it cost a good seal. One move in a list of one is a seal. */
  const listy = goodLlm({
    seal: JSON.stringify({
      moves: [{ task: "Sing the one you never sing, once, to one stranger.", where: "wherever the music is worst", proof: "what they said back", leave: "" }],
    }),
  });
  const { sealed } = await walk("talk", { llm: listy, answer: { text: "I have not said it yet." } });
  check(
    "a seal answered as moves[] is still a seal",
    (sealed.modes || {}).seal === "llm" &&
      sealed.quest.moves[0].task === "Sing the one you never sing, once, to one stranger." &&
      sealed.quest.moves[0].where === "wherever the music is worst",
    JSON.stringify(sealed.quest.moves[0]),
  );
}
{
  /* A REAL rewrite, all the way through: the 15-60 word gate and the isSameQuest guard only
   * ever ran on rewrites they refused, so a genuine short rewrite had no test at all. */
  const rewrite =
    "Sing the song you have never sung for anyone, out loud, to the first stranger who stops " +
    "walking. Wherever the music is worst. Bring back the face they made.";
  const singer = goodLlm({ refine: JSON.stringify({ say: "So you sing.", adventure: rewrite }) });
  const sess = await seanceAt("proposed", ctxWith(singer));
  const before = sess.adventure;
  const out = await hear(sess, { text: "I have never told anyone I sing." }, ctxWith(singer));
  const n = rewrite.split(/\s+/).length;
  check(
    `a genuine ${n}-word rewrite is taken, and it is what the seeker now hears`,
    (out.modes || {}).refine === "llm" &&
      out.adventure === rewrite &&
      sess.adventure === rewrite &&
      before !== rewrite &&
      out.say === "So you sing.",
    JSON.stringify(out.modes) + " " + out.adventure,
  );
  // …and it is the rewritten quest that gets sealed, not the one it replaced
  const sealedAfter = await accept(sess, ctxWith(singer));
  check(
    "and the parchment seals the rewritten quest",
    sealedAfter.quest.adventure === rewrite,
    sealedAfter.quest.adventure,
  );
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
  if (stage === "tale_listening") {
    await hear(sess, { text: "Wren" }, ctx);
    return sess;
  }
  if (stage === "tale_told") {
    await hear(sess, { text: "Wren" }, ctx);
    await hear(sess, { text: "I walked out to the fence and I came back changed." }, ctx);
    return sess;
  }
  /* The five stages only an OLD session can be sitting in. They are still answered, so
     they are still probed — the matrix below is the whole point of keeping them alive. */
  if (["door", "weather", "stones", "wanting", "listening"].includes(stage)) {
    rewindToDoor(sess);
    if (stage === "door") return sess;
    if (stage === "listening") {
      await hear(sess, { door: "talk" }, ctx);
      return sess;
    }
    await hear(sess, { door: "touch" }, ctx);
    if (stage === "weather") return sess;
    await hear(sess, { weather: "fog" }, ctx);
    if (stage === "stones") return sess;
    await hear(sess, { stones: ["grief"] }, ctx);
    return sess;
  }
  // everything from the asking on comes off the pull, which is how a séance runs now
  await hear(sess, { text: "Wren" }, ctx);
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
    drawable(after) && after.stage === "accepted" && after.quest.moves.length === 1,
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
    sealed.stage === "accepted" && sealed.quest.moves.length === 1 && !sealed.error,
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
    "an answer plus three refines and a settled fourth stays inside the twelve-share roof",
    sess.shares.length <= 12 && sess.shares.length === 5,
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

/* ---- 11b. the reading has a roof --------------------------------------------------- */

/* A reading anchored in the seeker's own words runs out on its own. Asked to read three
 * cards for a seeker who said nothing, the model came back from staging with 426 words of
 * one thought in twenty metaphors — spoken aloud, at one /api/speak call per sentence. */

section("a runaway reading is re-rolled, then given up on");
{
  const runaway = "The shell is not a wall. It is a womb. ".repeat(30);
  const good =
    "You came a long way to sit still. The weight you carry is not yours to carry alone. " +
    "word ".repeat(70);
  const quest = "Say it to the first face that stops. Out past the last lamp. Bring back what their face did.";
  let rolls = 0;
  const notes = [];
  const rambler = {
    available: () => true,
    async generate(prompt, opts = {}) {
      if (opts.stage !== "weave") return goodLlm().generate(prompt, opts);
      rolls++;
      notes.push(prompt.includes("ran far too long"));
      return JSON.stringify({ reading: rolls === 1 ? runaway : good, adventure: quest });
    },
  };
  const { sess } = start("seek");
  const e = await hear(sess, { text: "Wren" }, ctxWith(rambler));
  const p2 = await hear(sess, { pass: true }, ctxWith(rambler));
  check(
    "a 400-word reading is thrown back once, with the reason",
    rolls === 2 && notes[0] === false && notes[1] === true,
    `rolls=${rolls} notes=${JSON.stringify(notes)}`,
  );
  check(
    "and the second, sane one is what the seeker hears",
    p2.stage === "proposed" &&
      p2.modes.weave === "llm" &&
      p2.reading.split(/\s+/).length < 170 &&
      !/is not a wall/.test(p2.reading),
    String(p2.reading || "").slice(0, 120),
  );
  check("the asking before it was a real one", e.stage === "asking" && Boolean(e.look));
}
{
  // a model that will not stop rambling: the template takes the turn rather than the ramble
  const runaway = "The shell is not a wall. It is a womb. ".repeat(30);
  const always = {
    available: () => true,
    async generate(prompt, opts = {}) {
      if (opts.stage !== "weave") return goodLlm().generate(prompt, opts);
      return JSON.stringify({
        reading: runaway,
        adventure: "Say it to the first face. Out past the last lamp. Bring back what their face did.",
      });
    },
  };
  const { sess } = start("seek");
  await hear(sess, { text: "Wren" }, ctxWith(always));
  const p2 = await hear(sess, { pass: true }, ctxWith(always));
  check(
    "a model that only rambles falls to the template, and says so",
    p2.modes.weave === "fallback" && p2.reading.split(/\s+/).length < 170,
    `${p2.modes.weave} ${p2.reading.split(/\s+/).length}w`,
  );
}

/* ---- 12b. the voice: what is worth saying aloud ----------------------------------- */

/* The kiosk posts ONE SENTENCE per /api/speak call, so the Turtle's "Mm." reaches the
 * model on its own and comes back as a groan. src/voice.js is its own module for the same
 * reason src/ears.js is: index.js re-exports the Durable Object class and cannot be
 * imported outside the Workers runtime. */

section("the voice skips the Turtle's throat-clearing");
{
  const gone = ["Mm.", "Mmm.", "Hm.", "Hmm.", "Ah.", "Ahh.", "mm,", "  Mm…  ", "Mm. Ah. Hmm."];
  check(
    "a line that is only a hum is nothing to say aloud",
    gone.every((t) => voiceText(t) === ""),
    JSON.stringify(gone.filter((t) => voiceText(t) !== "")),
  );
  check(
    "a leading hum is stripped and the sentence survives",
    voiceText("Mm. Now the Turtle can see it.") === "Now the Turtle can see it." &&
      voiceText("Mm, that changes the shape of it.") === "that changes the shape of it." &&
      voiceText("Ah. A traveler. Come closer.") === "A traveler. Come closer.",
    JSON.stringify(voiceText("Mm. Now the Turtle can see it.")),
  );
  check(
    "a real sentence is never touched",
    ["The shell hums.", "Ah yes, the shell hums.", "Move slow and bite things.",
      "Mmhm is not a word the Turtle says."].every((t) => voiceText(t) === t),
  );
  check("and nothing at all is still nothing", voiceText("") === "" && voiceText(null) === "");
}
{
  /* The tryouts are staging-only, and they are an ALLOWLIST because /api/speak is public
     and unauthenticated: a `model` reaching env.AI.run() unchecked is an open door onto
     every model on the account. */
  const prod = { TTS_MODEL: "@cf/deepgram/aura-1", TTS_SPEAKER: "angus" };
  const stg = { ...prod, TTS_MODEL: "@cf/deepgram/aura-2-en", TTS_SPEAKER: "pluto", VOICE_TRYOUTS: "1" };
  const body = { speaker: "draco", model: "@cf/deepgram/aura-1" };
  check(
    "with no tryouts, the environment's own voice answers whatever the body asks",
    JSON.stringify(voiceChoice(prod, body)) ===
      JSON.stringify({ model: "@cf/deepgram/aura-1", speaker: "angus", tryout: false }),
    JSON.stringify(voiceChoice(prod, body)),
  );
  check(
    "with tryouts on, an allowed speaker and model are taken",
    JSON.stringify(voiceChoice(stg, body)) ===
      JSON.stringify({ model: "@cf/deepgram/aura-1", speaker: "draco", tryout: true }),
    JSON.stringify(voiceChoice(stg, body)),
  );
  check(
    "every allowlisted speaker is reachable, and only those",
    TRYOUT_SPEAKERS.every((sp) => voiceChoice(stg, { speaker: sp }).speaker === sp) &&
      TRYOUT_MODELS.every((m) => voiceChoice(stg, { model: m }).model === m),
  );
  const bad = [
    { model: "@cf/meta/llama-3.3-70b-instruct-fp8-fast" },
    { model: "../../etc/passwd" },
    { speaker: "angus2" },
    { speaker: "PLUTO; drop" },
    { model: null, speaker: [] },
  ];
  check(
    "anything outside the allowlists is ignored in silence",
    bad.every((b) => {
      const v = voiceChoice(stg, b);
      return v.model === "@cf/deepgram/aura-2-en" && v.speaker === "pluto" && v.tryout === false;
    }),
    JSON.stringify(bad.map((b) => voiceChoice(stg, b))),
  );
  check(
    "a body that is not an object never reaches the model name",
    voiceChoice(stg, "pluto").model === "@cf/deepgram/aura-2-en" &&
      voiceChoice(stg, null).speaker === "pluto",
  );
}

/* ---- 13. a séance sealed before the rebuild --------------------------------------- */

/* The quest became ONE bite on fix/seance-smooth. Sessions older than that are still out
 * there — in a phone's localStorage, and in a Durable Object that has not expired — and
 * they carry the old shape: an `anchor` instead of a `bite`, and three moves on the
 * parchment. None of that may throw, and none of it may be relabelled into a lie: three
 * moves headed "the one bite" three times is a lie the seeker can read. */

section("a quest sealed before the rebuild still reads, and still says three");
{
  const ctx = ctxWith(deadLlm);
  // an unsealed legacy session: the old field is there, the new one is not
  const sess = await seanceAt("proposed", ctx);
  delete sess.bite;
  sess.anchor = "roots";
  let sealed;
  let threw = "";
  try {
    sealed = await accept(sess, ctx);
  } catch (e) {
    threw = String(e && e.stack ? e.stack : e);
  }
  check(
    "a session with an anchor and no bite still seals, and seals one bite",
    !threw && sealed && sealed.quest && sealed.quest.moves.length === 1 &&
      sealed.quest.moves[0].card === sess.picks[biteRealm(sess.located, sess.picks)].name,
    threw || JSON.stringify(sealed && sealed.quest && sealed.quest.moves),
  );

  // …and the same session with a THREE-move parchment already on it, as a restore finds it
  const legacy = await seanceAt("proposed", ctx);
  const bite = legacy.bite;
  delete legacy.bite;
  legacy.anchor = "roots";
  legacy.stage = "accepted";
  legacy.quest = {
    title: "The Quest of the Old Shape",
    for: "Wren",
    charge: "Three moves, as the Turtle used to ask.",
    adventure: legacy.adventure,
    moves: ["roots", "trunk", "branches"].map((realm, i) => ({
      slot: ["FACE", "STAND", "REACH"][i],
      card: legacy.picks[realm].name,
      task: legacy.picks[realm].turtle_dare,
      where: "out past the last lamp",
      at: legacy.picks[realm].real_2026.name,
      proof: "Bring back what you found there.",
      leave: "",
    })),
    vow: "I will bring it back.",
    vow_where: "at the shell",
    chosen: "you chose this",
    map: legacy.quest ? legacy.quest.map : "",
  };
  check("the legacy fixture is the old shape", legacy.quest.moves.length === 3 && !legacy.bite && Boolean(bite));
  check("a legacy accepted session is replayable", replayable(legacy));
  const replayed = await accept(legacy, ctx);
  const heard = await hear(legacy, { pass: true }, ctx);
  const tapped = await hear(legacy, { text: "one more thing" }, ctx);
  check(
    "accept replays the three moves it was sealed with, and never reseals",
    replayed.stage === "accepted" && replayed.quest.moves.length === 3 &&
      replayed.quest.moves[0].card === legacy.picks.roots.name,
    JSON.stringify(replayed.quest && replayed.quest.moves.map((m) => m.card)),
  );
  check(
    "and a phone that taps or talks at it gets the same parchment back",
    heard.stage === "accepted" && tapped.stage === "accepted" &&
      JSON.stringify(heard.quest) === JSON.stringify(replayed.quest) &&
      JSON.stringify(tapped.quest) === JSON.stringify(replayed.quest),
    JSON.stringify([heard.stage, tapped.stage]),
  );

  /* THE HEADING, which is the one the client mirrors. assets/index.html renderQuest and
   * questText cannot be imported here — they live inside the HTML — so the rule is tested
   * where it also lives on the server, and index.html's moveHead() points back at this
   * test by name. Change one, change the other. */
  const payload = { question: "a question", reading: legacy.reading, adventure: legacy.adventure };
  const three = formatReceipt(payload, legacy.picks, legacy.located, legacy.quest);
  check(
    "the receipt heads a legacy three-move quest as MOVE 1..3",
    /MOVE 1 \[FACE\]/.test(three) && /MOVE 2 \[STAND\]/.test(three) && /MOVE 3 \[REACH\]/.test(three) &&
      !/THE ONE BITE/.test(three),
    three.split("\n").filter((l) => /MOVE|ONE BITE/.test(l)).join(" | "),
  );
  const one = formatReceipt(payload, legacy.picks, legacy.located, {
    ...legacy.quest,
    moves: legacy.quest.moves.slice(0, 1),
  });
  check(
    "and a one-bite quest is headed the one bite, never MOVE 1",
    /THE ONE BITE \[FACE\]/.test(one) && !/MOVE 1/.test(one),
    one.split("\n").filter((l) => /MOVE|ONE BITE/.test(l)).join(" | "),
  );
}

console.log(failures ? `\n${failures} FAILED` : "\nALL PASS");
process.exit(failures ? 1 : 0);
