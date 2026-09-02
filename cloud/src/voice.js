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
