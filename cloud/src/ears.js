/* The Turtle's ears — app/oracle/ears.py, whisper.cpp -> Workers AI whisper.
 *
 * Its own file for two reasons. It is the one paid route that carries no séance in its
 * body, so the tie back to a live séance lives here rather than in the router; and
 * index.js cannot be imported outside the Workers runtime (it re-exports the Durable
 * Object class, which needs `cloudflare:workers`), so a test could not otherwise reach
 * this at all. cloud/test/seance.mjs drives it against a fake AI binding.
 */
import { loadSession } from "./session.js";
import { json } from "./util.js";

/* Also read by /api/health in index.js, which reports which ears are live. */
export const DEFAULT_WHISPER = "@cf/openai/whisper-large-v3-turbo";

/* Whisper is billed by audio. The talk door asks a seeker to tell the Turtle about their
 * burn and gives them two minutes to do it, which is ~480KB of webm/opus on Android and
 * ~2MB of iOS mp4/aac (iOS records AAC at ~128kbps and does not let us ask for less), so
 * the roof is 4MB. Anything past that is not a seeker, it is a mistake or an attack.
 * The kiosk's own recorder still stops itself at 120s — this is the second wall. */
export const MAX_AUDIO_BYTES = 4 * 1024 * 1024;

/* The stages where somebody is actually being asked to speak. The other six are taps —
 * the door, the three touch screens, a sealed quest, a told tale — and a séance sitting
 * on one of them has no use for a transcript.
 *
 * Without this gate the route was a free Whisper endpoint: no séance, no session, just an
 * IP and a 4MB body, which is 120MB of billed audio a minute inside the shared 30/min
 * limit. Now it costs a live séance in a listening stage, and it spends from its own
 * ratelimit binding (RL_EARS in wrangler.toml) rather than from the séance's. */
const EARS_OPEN = new Set([
  "naming",
  "listening",
  "asking",
  "proposed",
  "tale_naming",
  "tale_listening",
]);

/* Séance-shaped, and a 200: the kiosk toasts `error` and keeps the seeker's screen. A
 * 4xx here would be read by whyLost() as the Turtle speaking, which it is not. */
const NO_SEANCE = "the shell is not listening — touch it to begin";
const NOT_LISTENING = "the Turtle is not listening for words just now";

/* Whisper takes base64. Build it in 48KB slices — a multiple of 3, so each slice encodes
 * independently and the pieces concatenate — and join once at the end. The old version
 * grew one string by `+=` for the whole 4MB and then based64'd it, which is a ~5.4MB
 * string on top of a 4MB one in a 128MB isolate. */
export function toBase64(bytes) {
  const SLICE = 48 * 1024; // 49152 = 3 * 16384
  const parts = [];
  for (let i = 0; i < bytes.length; i += SLICE) {
    const slice = bytes.subarray(i, i + SLICE);
    let s = "";
    for (let j = 0; j < slice.length; j += 0x2000) {
      s += String.fromCharCode.apply(null, slice.subarray(j, j + 0x2000));
    }
    parts.push(btoa(s));
  }
  return parts.join("");
}

/** POST /api/transcribe — the séance id in `?session=` or the `x-seance-session` header,
 *  the raw MediaRecorder blob as the body. */
export async function transcribe(req, env, url) {
  /* The séance is checked BEFORE the body is read: an unknown caller should never get
   * as far as making this isolate hold 4MB of their audio. */
  const sid = String(
    (url && url.searchParams && url.searchParams.get("session")) ||
      req.headers.get("x-seance-session") ||
      "",
  ).trim();
  if (!sid) return json({ error: NO_SEANCE });
  const sess = await loadSession(env.SESSION_DO, sid);
  if (!sess) return json({ error: NO_SEANCE });
  if (!EARS_OPEN.has(sess.stage)) return json({ error: NOT_LISTENING, stage: sess.stage });

  const buf = await req.arrayBuffer();
  if (!buf.byteLength) return json({ error: "no audio" }, 400);
  if (buf.byteLength > MAX_AUDIO_BYTES) return json({ error: "that is too much audio" }, 413);
  const model = env.WHISPER_MODEL || DEFAULT_WHISPER;
  /* The kiosk posts the raw MediaRecorder blob with its own Content-Type — webm/opus on
   * Android and Chrome, mp4/aac on iOS. Both were round-tripped through this model on
   * 2026-08-23 and both transcribed; unlike the playa path there is no ffmpeg step.
   *
   * The 60s/1.5MB roof was measured; this 120s/4MB one is NOT — nobody has round-tripped
   * a real two-minute recording through whisper-large-v3-turbo on this account. Verify it
   * on staging with an actual long share before trusting it, and check the TAIL of the
   * transcript, not just that a transcript came back: a truncated answer looks like a
   * quiet seeker, not like an error. If it truncates, slice client-side and post the
   * pieces — do not raise anything here. */
  try {
    const out = await env.AI.run(model, { audio: toBase64(new Uint8Array(buf)) });
    const text = String((out && (out.text || out.transcription)) || "")
      .split(/\s+/)
      .filter(Boolean)
      .join(" ")
      .trim();
    if (!text) return json({ error: "the Turtle has no ears on this machine" }, 501);
    return json({ text });
  } catch (err) {
    console.error("whisper failed:", String((err && err.message) || err));
    return json({ error: "the Turtle has no ears on this machine" }, 501);
  }
}
