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
 */
import { start, hear, accept, __test as S } from "../src/session.js";

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

console.log(failures ? `\n${failures} FAILED` : "\nALL PASS");
process.exit(failures ? 1 : 0);
