/* The Turtle's spoken voice — the two decisions /api/speak makes before it spends a
 * Workers AI call. Its own module because index.js re-exports the Durable Object class
 * and so cannot be imported outside the Workers runtime; cloud/test/seance.mjs drives
 * these directly, the same reason src/ears.js lives on its own.
 */

/* THE TURTLE SAYS "Mm." A LOT, and it should: on the page it is the shell thinking, a
 * beat before the sentence that matters. Through a synthesised voice it is a groan —
 * Aaron heard it on production, 2026-09-02 — and there is no prosody to rescue it,
 * because the kiosk posts ONE SENTENCE PER REQUEST, so "Mm." arrives at the model alone.
 * So the voice skips it. Only the voice: the screen still says what it always said.
 *
 * The family is deliberately small — the m and h hums, and "ah" — and every one of them
 * has to be followed by its own punctuation, so "Ah yes" is a sentence and "Ah." is a
 * noise. Stripping repeats, because "Mm. Ah. Good." is three of them in a row. */
const INTERJECTION = /^\s*(?:m+m|h+m+|a+h+)\s*[.,…!?—–-]+\s*/i;

/** What is worth saying aloud, or "" when the whole line was the Turtle clearing its
 *  throat. Never used for anything the seeker reads. */
export function voiceText(text) {
  let s = String(text == null ? "" : text).trim();
  for (;;) {
    const next = s.replace(INTERJECTION, "");
    if (next === s) break;
    s = next;
  }
  return s.trim();
}

/* VOICE TRYOUTS, staging only. Picking a voice by ear needs a way to ask the same two
 * sentences of several of them, and the alternative is redeploying between each. So when
 * VOICE_TRYOUTS is "1" — set in [env.staging.vars] and nowhere else — /api/speak takes an
 * optional speaker and model from the body. Both are allowlists, not free text: the route
 * is public and unauthenticated, and `model` reaching env.AI.run() unchecked would be an
 * open door onto every model on the account. Anything outside them is ignored in silence
 * and the environment's own voice answers, which is exactly what production always does. */
export const TRYOUT_SPEAKERS = [
  "pluto",
  "draco",
  "mars",
  "odysseus",
  "atlas",
  "orion",
  "zeus",
  "arcas",
];
export const TRYOUT_MODELS = ["@cf/deepgram/aura-2-en", "@cf/deepgram/aura-1"];

const SPEAKER_SET = new Set(TRYOUT_SPEAKERS);
const MODEL_SET = new Set(TRYOUT_MODELS);

/** Which voice this request gets: the environment's, unless tryouts are on AND the body
 *  named one of the few this build will speak in. */
export function voiceChoice(env, body, fallback) {
  env = env || {};
  body = body && typeof body === "object" ? body : {};
  fallback = fallback || {};
  const out = {
    model: String(env.TTS_MODEL || fallback.model || "").trim(),
    speaker: String(env.TTS_SPEAKER || fallback.speaker || "").trim(),
    tryout: false,
  };
  if (String(env.VOICE_TRYOUTS || "") !== "1") return out;
  const model = String(body.model || "").trim();
  const speaker = String(body.speaker || "").trim().toLowerCase();
  if (MODEL_SET.has(model)) {
    out.model = model;
    out.tryout = true;
  }
  if (SPEAKER_SET.has(speaker)) {
    out.speaker = speaker;
    out.tryout = true;
  }
  return out;
}
