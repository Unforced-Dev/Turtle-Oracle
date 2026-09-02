/* Port of app/oracle/weave.py — three cards bound into one reading + one quest.
 *
 * Every prompt string below is a VERBATIM copy of the Python. The séance was tuned by
 * ear over a week (PR #12's playa-safety covenant, PR #15's spoken-word budgets); the
 * cloud turtle has no licence to improve the wording. If you change a character here,
 * change it in app/oracle/weave.py too, or the two turtles stop being the same turtle.
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

const SLOT_TITLES = { roots: "FACE", trunk: "STAND", branches: "REACH" };

/* THE ANCHOR. A quest with three street addresses in it is a errand list, and it is the
 * burn — half of what is on the map moved, burned, or was never where the guide said. So
 * exactly ONE move gets pinned to a real 2026 placement and the other two get a
 * direction and a quality. This picks the pin: the card whose live_hook actually
 * resolved to a placed thing (geo.locate gives status "citywide" when it did not), and
 * best of all one with a real address or clock behind it. */
export function anchorRealm(located) {
  const rank = (realm) => {
    const loc = located[realm] || {};
    if (!loc.directions) return 0;
    if (loc.status === "citywide") return 1; // "wherever you stand" is not a placement
    // a surveyed landmark, or a camp whose address the 2026 gates data actually knows
    if (loc.status === "fixed" || loc.clock != null || loc.street != null) return 3;
    return 2; // placed, but the placement is still pending the BRC API
  };
  let best = "trunk";
  for (const realm of ["trunk", "roots", "branches"]) {
    if (rank(realm) > rank(best)) best = realm;
  }
  return best;
}

export async function weaveLlm(question, cards, llm, located, context, timeout) {
  located = located || {};
  const anchor = anchorRealm(located);
  const anchorCard = cards[anchor];
  const anchorWhere = rstrip((located[anchor] || {}).directions || "", " .");
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
    "Then give ONE concrete quest at Burning Man in 75-110 words (use the cards' seed lines as raw " +
    "material). It will also be spoken aloud: one short opening, then exactly three compact moves " +
    "introduced as First, Second, Third. No headings or bullets. Build it on these rules:\n" +
    "- THE CROSSING: find the thing the seeker confessed they avoid, don't do, or secretly want — " +
    "the heart of the quest makes them do exactly that. Not visit it. Do it.\n" +
    "- THE ARC: the FACE move is done alone and involves a hard truth; the STAND move is a presence " +
    "practice at a real place; the REACH move must involve another human — tell, ask, give, or witness.\n" +
    "- THE SACRIFICE: exactly one move has them leave something behind (a written word, an object, " +
    "a habit named out loud) — left, not kept.\n" +
    "- THE SHAPE: every move pairs a concrete anchor (a named place + a physical action) with an " +
    "open interior door ('stay until…', 'leave when you have…', 'ask until someone…') — specific " +
    "on the outside, open on the inside. That openness is where the seeker finds themselves.\n" +
    "- Fit the quest to the hour given in CONTEXT (heat, dark, sunrise). If CONTEXT says they are here " +
    "with a partner or friends, this is NOT optional: write the quest for them together, and it MUST " +
    "include one move done apart and one moment reunited. If it is their first burn, keep it simple " +
    "and kind.\n" +
    `- THE ANCHOR: exactly ONE move — the ${SLOT_TITLES[anchor]} move — is pinned to a real place ` +
    `in Black Rock City 2026: ${anchorCard.real_2026.name}` +
    (anchorWhere ? `, ${anchorWhere}` : "") +
    ". Name it and give simple directions (the city is a clock plus a street grid, the Man at " +
    "center, deep playa past him).\n" +
    "- THE OPEN TWO: the other two moves name NO address and NO camp. Their 'where' is a " +
    "direction, a kind of place, a kind of person, or a time of day — 'out past the last lamp', " +
    "'wherever the music is worst', 'the first person who hands you water', 'before the sun is " +
    "up'. It is the burn: what is on the map moved, and finding it is half the quest. Give them " +
    "a bearing, not an address.\n\n" +
    'Return JSON only: {"reading": "...", "adventure": "..."}';

  /* Two rolls, one budget. A reading that was the example and nothing else (1 in 5 on
   * staging, 2026-09-02), or JSON that max_tokens cut mid-word (llm.js's most common
   * weave failure), is worth one more roll of the model before the template — but only
   * while half the stage budget is still unspent, and the second roll gets half the
   * timeout, so the draw stays inside the edge timeout the budget in wrangler.toml was
   * sized against (first roll up to timeout + timeout/2 on the model fallback; the second
   * only starts before timeout/2 has passed and gets timeout/2). */
  const started = Date.now();
  for (let attempt = 0; attempt < 2; attempt++) {
    const t = attempt ? Math.floor(timeout / 2) : timeout;
    /* The second roll says why it is happening. On production 2026-09-02 the first roll
     * came back as the example and nothing else in 3 of 10 séances; a bare re-roll of
     * the same prompt is the same dice. This line is an ADDITION, only ever sent on the
     * retry, so the parity-locked first prompt is untouched. */
    const p = attempt ? prompt + RETRY_NOTE : prompt;
    const resp = await llm.generate(p, { system: SYSTEM, asJson: true, timeout: t, stage: "weave" });
    const out = tryJson(resp);
    if (out && typeof out === "object" && out.reading && out.adventure) {
      const reading = unquoteExample(String(out.reading).trim());
      const adventure = String(out.adventure).trim();
      if (reading && !QUEST_EXAMPLE_RE.test(adventure)) return { reading, adventure };
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
  if (h >= 5 && h < 12) return "Today, before the heat wins, an adventure in three moves.";
  if (h >= 12 && h < 17)
    return "This afternoon — move through shade and ice, save the far playa for dark. Three moves.";
  if (h >= 17 && h < 21) return "As the light goes gold, an adventure in three moves.";
  if ((h >= 21 && h < 24) || h < 2) return "Tonight, an adventure in three moves.";
  return "In the deep night, three moves — and if your legs hold, end it facing the sunrise.";
}

/* The offline half of THE ANCHOR: what the two unpinned moves say instead of an address.
 * A bearing and a quality, in the Turtle's mouth — never a street. Exported because the
 * seal has to say the same thing on the parchment that the quest said out loud. */
export const OPEN_WHERE = {
  roots: "No address for this one. Walk until the sound thins and you can hear your own feet.",
  trunk: "No address for this one. It is wherever you already stand — your camp, your street, your hour.",
  branches:
    "No address for this one. Go where the strangers are thickest, at whatever hour you are bravest.",
};

export function weaveFallback(question, cards, located) {
  located = located || {};
  const anchor = anchorRealm(located);
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

  const move = (ordinal, c, realm) => {
    if (realm === anchor) {
      const where = ((located[realm] || {}).directions || "").replace(/&/g, "and");
      const tail = where ? ` The map says ${where}.` : "";
      return `${ordinal}. ${c.turtle_dare.trim()}${tail}`;
    }
    return `${ordinal}. ${c.turtle_dare.trim()} ${OPEN_WHERE[realm]}`;
  };

  const adventure =
    opener() +
    " " +
    move("First", r, "roots") +
    " " +
    move("Second", t, "trunk") +
    " " +
    move("Third", b, "branches");
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
