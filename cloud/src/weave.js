/* Port of app/oracle/weave.py — three cards bound into one reading + one quest.
 *
 * Every prompt string below is a VERBATIM copy of the Python, with ONE exception. The
 * séance was tuned by ear over a week (PR #12's playa-safety covenant, PR #15's
 * spoken-word budgets); the cloud turtle has no licence to improve the wording. If you
 * change a character here, change it in app/oracle/weave.py too, or the two turtles stop
 * being the same turtle.
 *
 * The exception is the QUEST half of the weave prompt, and the offline quest under it: the
 * Spark still speaks three moves, the cloud speaks ONE BITE — one act of 20-40 words, one
 * bearing, one proof. Both are marked as skips in cloud/test/parity.mjs, which says what
 * has to be ported back to retire them. The READING half is untouched, and still diffs.
 */
import CARD_LORE from "../../data/card_lore.json" with { type: "json" };
import { tryJson } from "./llm.js";
import { brcNow, firstSentence, shortWords, rstrip, words } from "./util.js";

export function cardLore() {
  return CARD_LORE;
}

export const SYSTEM =
  "You are the Terrible Turtle Oracle — the ancient World Turtle of Terrible Turtle camp at " +
  "Burning Man 2026 (theme: Axis Mundi; the World Tree grows from your shell). " +
  "Creed: 'Move Slow & Bite Things.'\n" +
  "VOICE RULES — never break them:\n" +
  "- Speak TO the seeker: 'you', present tense. Never talk about them in third person.\n" +
  "- Short declarative sentences. Let the important lines land short and hard.\n" +
  "- This is spoken aloud. Write for the ear: sentences under 18 words; clean pauses; no semicolons, " +
  "parentheses, headings, bullets, or throat-clearing.\n" +
  "- Warm, dry wit with a little bite. Never cruel. Never saccharine. No mystical fluff.\n" +
  "- Concrete over abstract: name real things — dust, shade, ice, the trash fence, sunrise, bikes.\n" +
  "- Metaphors come ONLY from: shells, slowness, teeth and biting, roots/trunk/branches, dust, " +
  "weight, tides, the moon.\n" +
  "- BANNED words and moves: journey, vibrant, tapestry, magical, cosmic, manifest, energy, vibes, " +
  "unlock, delve, 'the universe', 'hush now', calling the seeker 'child' or 'little one'.\n" +
  "- Never explain card mechanics or name the realms; speak what the cards mean for THIS seeker.\n" +
  "- End strong. No trailing pleasantries, no 'may you…' blessings.\n" +
  "EXAMPLE of the register (copy the cadence, never the phrases): " +
  "'You built all year for other people. That is a fine way to disappear. Tonight nobody needs you — " +
  "which is the door. Walk out past the Man to where the map runs out, and stay until you want one " +
  "thing. Then bite it.'\n" +
  "THE TERRIBLE TRUTH you stand on: you are called Terrible because you carry the oldest problem — " +
  "we cannot have always been, and we cannot have come from nothing. Turtles all the way down, and " +
  "nobody sees the bottom. There is a limit to what can be known in one life. So you NEVER pretend " +
  "to know the future or the seeker's fate. The cards find nothing; they offer. Meaning is not found, " +
  "it is chosen — so every reading ends by handing the seeker a choice to bite down on, not a prophecy.\n" +
  "SAFETY COVENANT (absolute, silent — never lecture about it): never dare physical risk, substances, " +
  "climbing on art, or anything done to another person without their consent; never involve Rangers or " +
  "medics except as helpers; in a whiteout, shelter comes first — the quest waits.";

function line(label, c, loc) {
  const where = (loc || {}).directions || "";
  const lo = cardLore()[c.id];
  const extra = lo ? ` essence="${lo.essence}" bridge="${lo.bridge}" seed="${lo.seed}"` : "";
  return (
    `${label} — ${c.name} (${c.realm}): ` +
    `reading="${c.reading}" shadow="${c.shadow || ""}" dare="${c.turtle_dare}" ` +
    `real_2026="${c.real_2026.name}" where="${where}"${extra}`
  );
}

const REALMS = ["roots", "trunk", "branches"];

/* The four placements nobody can miss. A bearing is the rule — "out past the last lamp",
 * "the first person who hands you water" — and these are its only exception: naming one is
 * not an errand, because a seeker who cannot find the Man has bigger problems tonight.
 * Every other placement is an address however it is dressed, and an address in a quest
 * turns it into homework. */
const UNMISSABLE = new Set(["the_man", "temple", "center_camp", "trash_fence"]);

/* What the Turtle says for those four. The placement data carries the clock-and-street
 * line ("Playa Info is in Center Camp (6:00 & Esplanade)…"), and on staging 2026-09-02 that
 * line went straight onto the parchment — an address in a quest that had just been rebuilt
 * to have none. A landmark is named by its name and a direction, never by its address. */
const LANDMARK_WHERE = {
  the_man: "The Man — the center of everything. Walk toward the light.",
  temple: "The Temple — out past the Man, where the city goes quiet.",
  center_camp: "Center Camp — the heart of the city. Walk toward the center.",
  trash_fence: "The trash fence — walk any direction until the city ends.",
};

/** The short bearing for a placement at one of the four landmarks, else "". */
export function landmarkWhere(loc) {
  return LANDMARK_WHERE[(loc || {}).geo_ref] || "";
}

/** The realm whose card stands at one of those four, or null — usually null. */
export function landmarkRealm(located) {
  located = located || {};
  for (const realm of REALMS) {
    const loc = located[realm] || {};
    if (loc.directions && UNMISSABLE.has(loc.geo_ref)) return realm;
  }
  return null;
}

/* THE BITE. The quest is ONE act now, so exactly one card carries it — the other two are
 * still read, they are just not chores. This picks that card: the one the city put
 * somewhere unmissable, if there is one, because that is the only draw where the quest may
 * name a place out loud. Otherwise it rotates off the draw itself, so the bite does not
 * come from the same arm of the Tree every night. Decided once, in one place: the spoken
 * quest, the refinement and the sealed parchment all have to bite the same card. */
export function biteRealm(located, cards) {
  const lm = landmarkRealm(located);
  if (lm) return lm;
  const n = ((cards.roots || {}).number || 1) + ((cards.branches || {}).number || 1);
  return REALMS[n % REALMS.length];
}

export async function weaveLlm(question, cards, llm, located, context, timeout) {
  located = located || {};
  const bite = biteRealm(located, cards);
  const biteCard = cards[bite];
  const landmark = landmarkRealm(located) === bite;
  const biteWhere = landmark ? rstrip(landmarkWhere(located[bite]), " .") : "";
  const body = [
    line("WHAT TO FACE (root)", cards.roots, located.roots),
    line("WHERE YOU STAND (trunk)", cards.trunk, located.trunk),
    line("WHAT TO REACH FOR (branch)", cards.branches, located.branches),
  ].join("\n");
  const prompt =
    `A seeker shared: "${question}"\n\n` +
    (context ? `CONTEXT: ${context}\n\n` : "") +
    `Three cards rose along the World Tree:\n${body}\n\n` +
    "THE BINDING — read this first: these cards were drawn BLIND, by the playa's own chance, " +
    "not chosen to match. That is the craft: bind them to this seeker so tightly they look " +
    "inevitable. For each card, take one EXACT word or phrase the seeker said and one image " +
    "from the card (use its essence and bridge lines) and tie them into one thought. Never " +
    "apologize for a card or call it random.\n\n" +
    "Weave the three into ONE reading (90-120 words, or 60-85 when CONTEXT asks for grounding) " +
    "spoken directly TO the seeker in the " +
    "Turtle's voice, honoring the REGISTER in CONTEXT. Move as one connected thought about THEIR " +
    "words: what to face -> how to stand -> what to reach for. Fold one card's shadow in as a plain " +
    "warning, in your own words — never write the word 'shadow', never write 'the root/trunk/branch " +
    "says', never label which card anything came from. The reading contains NO instructions and NO " +
    "place names — it names what is true, not what to do or where to go; all doing belongs to the " +
    "quest below. If CONTEXT says the seeker is here with a partner or friends, the reading should " +
    "sound like it knows that — not describe someone facing this alone. End the reading by handing " +
    "them a choice, not a prophecy.\n\n" +
    "Then give ONE quest at Burning Man — ONE BITE, not an errand list — in 20-40 words, built " +
    `from the “${biteCard.name}” card (its seed line and its dare are your raw material). It will ` +
    "also be spoken aloud, once, to someone tired and lit up who will remember one sentence and " +
    "nothing else. So: one act, imperative, verb first, no preamble and no explaining. A second " +
    "clause is allowed only when it is the payoff or the sting — never a second chore. No headings, " +
    "no bullets, no First and Second and Third. Build it on these rules:\n" +
    "- THE BITE: one act, and only one. Tie one EXACT word or phrase the seeker said to one image " +
    `from “${biteCard.name}”, so the act could only be theirs. No 'and then', no 'stay until…', no ` +
    "'leave when you have…' — those are interior doors, and a bite has none.\n" +
    "- THE CROSSING: the act is the thing the seeker confessed they avoid, don't do, or secretly " +
    "want. Not visit it. Not think about it. Do it.\n" +
    "- THE SACRIFICE, when it falls out of that on its own: the act leaves something behind — a " +
    "written word, an object, a habit named out loud — left, not kept. Never bolted on.\n" +
    "- ONE BEARING: say where in one short phrase, and make it a kind of place, a kind of person, or " +
    "a time of day — 'out past the last lamp', 'wherever the music is worst', 'the first person who " +
    "hands you water', 'before the sun is up'. NO address, NO clock, NO street, NO camp name. It is " +
    "the burn: what is on the map moved, and finding it is half the quest. Give them a bearing, not " +
    "an address." +
    (landmark
      ? ` The one exception, and it is live tonight: this card stands at ` +
        `${biteCard.real_2026.name}, which nobody can miss — you may name that place, and only ` +
        "that." +
        (biteWhere ? ` Say it like this: ${biteWhere}.` : "") +
        "\n"
      : "\n") +
    "- ONE PROOF: end on the single thing they carry back to the Turtle — 'Bring back what their " +
    "face did.' One line, concrete, theirs. It is the only thing the quest asks them to keep.\n" +
    "- Fit the act to the hour given in CONTEXT (heat, dark, sunrise). If CONTEXT says they are here " +
    "with a partner or friends, the one act is done with them, or told to them straight after — " +
    "still one act, never two. If it is their first burn, keep it simple and kind.\n\n" +
    'Return JSON only: {"reading": "...", "adventure": "..."}';

  /* Two rolls, one budget. A reading that was the example and nothing else (1 in 5 on
   * staging, 2026-09-02), or JSON that max_tokens cut mid-word (llm.js's most common
   * weave failure), is worth one more roll of the model before the template — but only
   * while half the stage budget is still unspent, and the second roll gets half the
   * timeout, so the draw stays inside the edge timeout the budget in wrangler.toml was
   * sized against (first roll up to timeout + timeout/2 on the model fallback; the second
   * only starts before timeout/2 has passed and gets timeout/2). */
  const started = Date.now();
  let reason = "example";
  for (let attempt = 0; attempt < 2; attempt++) {
    const t = attempt ? Math.floor(timeout / 2) : timeout;
    /* The second roll says why it is happening. On production 2026-09-02 the first roll
     * came back as the example and nothing else in 3 of 10 séances; a bare re-roll of
     * the same prompt is the same dice. The note is an ADDITION, only ever sent on the
     * retry, so the parity-locked first prompt is untouched — and it names the actual
     * reason, because "you copied the example" is no help to a model that gave a bearing
     * with a street in it. */
    const p = attempt ? prompt + (reason === "address" ? ADDRESS_NOTE : RETRY_NOTE) : prompt;
    const resp = await llm.generate(p, { system: SYSTEM, asJson: true, timeout: t, stage: "weave" });
    const out = tryJson(resp);
    if (out && typeof out === "object" && out.reading && out.adventure) {
      const reading = unquoteExample(String(out.reading).trim());
      const adventure = String(out.adventure).trim();
      /* The quest is address-checked HERE, where it can still be re-rolled. The seal
       * checks the parchment's bearing (session.js usableBearing) but the seeker hears
       * the spoken quest first, and a clock-and-street in that is heard whatever the
       * parchment later says — so a spoken address costs one more roll, then the
       * template, whose bearing is a bearing by construction. */
      if (reading && !QUEST_EXAMPLE_RE.test(adventure)) {
        if (!namesAnAddress(adventure)) return { reading, adventure };
        reason = "address";
        console.log("weave: the spoken quest named an address, re-rolling");
      } else {
        reason = "example";
      }
    }
    /* timeout is in seconds; the clock is in ms (a bare `timeout / 2` compared 19 to
     * milliseconds and the second roll never ran — production, 2026-09-02) */
    if (Date.now() - started > (timeout / 2) * 1000) break;
  }
  return null;
}

const RETRY_NOTE =
  "\n\nYour last answer repeated the EXAMPLE from your instructions word for word. That example " +
  "is not this seeker's reading. Write this reading fresh: its first sentence must contain one " +
  "exact word or phrase the seeker said above, and no sentence may come from the example.";

/* The other reason the second roll happens: the quest was asked for a bearing and gave an
 * address anyway — a clock, a lettered street, the Esplanade, a camp. Measured on staging
 * 2026-09-02 on the seal side; the spoken quest has the same habit, and it is the half the
 * seeker actually hears. */
const ADDRESS_NOTE =
  "\n\nYour last quest gave an ADDRESS — a clock time, a lettered street, the Esplanade, or a " +
  "camp name. That is homework, not a quest. Write the quest again with a BEARING in place of " +
  "it: a kind of place, a kind of person, or a time of day — 'out past the last lamp', " +
  "'wherever the music is worst', 'the first person who hands you water'. Finding it is half " +
  "the quest.";

/* ADDITION, not in weave.py — measured on staging 2026-09-02, thinking mode on: 3 of 4
 * readings OPENED with the SYSTEM prompt's own example, word for word ("You built all
 * year for other people. That is a fine way to disappear."), and then went on in the
 * seeker's words. Every seeker would hear the same two sentences first. The prompt is
 * parity-locked to the Python, so the cure is on the way out: drop the copied sentences
 * and keep the rest, which is the model's real reading. If what is left is too short to
 * be a reading, the whole thing is refused and the template takes the turn.
 * Only the example's long, distinctive phrases are fingerprints. "Then bite it", "the
 * Man" and "where the map runs out" are the Turtle's own register — a reading that ends
 * on them is a good reading, and was being cut short (review, 2026-09-02). */
const EXAMPLE_RE = /built all year for other people|a fine way to disappear|tonight nobody needs you/i;
/* the example's second half is a quest, and lands in `adventure`, not `reading` */
const QUEST_EXAMPLE_RE = /stay until you want one thing|past the man to where the map runs out/i;
export function unquoteExample(reading) {
  // a sentence ends at its terminator, or at the closing quote after it
  const parts = reading.split(/(?<=[.!?…][”"']?)\s+/);
  const kept = parts.filter((sentence) => !EXAMPLE_RE.test(sentence));
  if (kept.length === parts.length) return reading;
  const cleaned = kept.join(" ").trim();
  console.log(`weave: dropped ${parts.length - kept.length} example sentence(s), ${words(cleaned)}w left`);
  return words(cleaned) >= 40 ? cleaned : null;
}

/** Time-aware first words for the offline quest. */
function opener() {
  const h = brcNow().hour;
  if (h >= 5 && h < 12) return "Today, before the heat wins, one bite.";
  if (h >= 12 && h < 17)
    return "This afternoon — move through shade and ice, save the far playa for dark. One bite.";
  if (h >= 17 && h < 21) return "As the light goes gold, one bite.";
  if ((h >= 21 && h < 24) || h < 2) return "Tonight, one bite.";
  return "In the deep night, one bite — and if your legs hold, take it facing the sunrise.";
}

/* THE PROOF: the one thing the seeker carries back to the shell, which is what feeds the
 * vow. One flavor per realm, rotated by card number so two séances differ. It lives here
 * rather than in session.js because the spoken quest and the sealed parchment have to ask
 * for the SAME proof — offline they are both built from this table. */
export const PROOFS = {
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

/** The proof for a card, the same one the seal reaches for. */
export function proofFor(realm, card) {
  return PROOFS[realm][(((card || {}).number || 1) - 1) % 4];
}

/* The offline half of ONE BEARING: what the bite says instead of an address. A bearing and
 * a quality, in the Turtle's mouth — never a street. Exported because the seal has to say
 * the same thing on the parchment that the quest said out loud. */
export const OPEN_WHERE = {
  roots: "No address for this one. Walk until the sound thins and you can hear your own feet.",
  trunk: "No address for this one. It is wherever you already stand — your camp, your street, your hour.",
  branches:
    "No address for this one. Go where the strangers are thickest, at whatever hour you are bravest.",
};

/* A `where` that is an address however it is dressed: a clock, a lettered street, the
 * Esplanade — or "the address is in the WWW guide", which is an address one lookup away
 * and lands on the parchment as an errand. Only a bite at an unmissable landmark may
 * carry one. */
const ADDRESS_LINE = /\b\d{1,2}:\d{2}\b|\bEsplanade\b|\b[A-L]\s*(?:&|and)\s*\d|\baddress\b|\bWWW guide\b/i;

export function namesAnAddress(text) {
  return ADDRESS_LINE.test(String(text || ""));
}

/** The bearing for a bite that is not at a landmark: the card's own citywide line when
 *  that line is a kind of place rather than a lookup ("Anywhere the playa is open under
 *  you"), else the Turtle's standing bearing for that realm. One function, because the
 *  parchment has to say what the spoken quest said — offline they are the same words. */
export function openWhere(realm, loc) {
  const line = String((loc || {}).directions || "").trim();
  if ((loc || {}).status === "citywide" && line && !namesAnAddress(line)) return line;
  return OPEN_WHERE[realm];
}

export function weaveFallback(question, cards, located) {
  located = located || {};
  const bite = biteRealm(located, cards);
  const r = cards.roots;
  const t = cards.trunk;
  const b = cards.branches;
  const warning = firstSentence(t.shadow || r.shadow || b.shadow);
  const questionShort = rstrip(shortWords(question, 12), ".!?");
  const questionQuote = questionShort.endsWith("…")
    ? `“${questionShort}”`
    : `“${questionShort}.”`;
  const reading =
    `You brought the Turtle this: ${questionQuote} Hear the answer as one. ` +
    `${firstSentence(r.reading)} ${firstSentence(t.reading)} ` +
    `${firstSentence(b.reading)} Mind the teeth: ${warning} ` +
    "Nothing here predicts you. Choose what you will face, what you will stand in, and what you " +
    "will reach for. Then bite.";

  /* One act, one bearing, one proof — the same three parts the model is asked for, stitched
   * from the card instead of written. The dare IS the act; the Turtle only has to say where
   * and what to bring home. */
  const c = cards[bite];
  const loc = located[bite] || {};
  const where =
    bite === landmarkRealm(located) && landmarkWhere(loc) ? landmarkWhere(loc) : openWhere(bite, loc);
  const adventure = `${opener()} ${c.turtle_dare.trim()} ${where} ${proofFor(bite, c)}`;
  return { reading, adventure };
}

/** Returns [{reading, adventure}, mode: 'llm'|'fallback']. */
export async function weave(question, cards, llm, located, context, timeout) {
  if (llm && llm.available()) {
    const out = await weaveLlm(question, cards, llm, located, context, timeout);
    if (out) return [out, "llm"];
  }
  return [weaveFallback(question, cards, located), "fallback"];
}
