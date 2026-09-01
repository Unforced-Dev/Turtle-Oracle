/* The cloud turtle — app/oracle/server.py as a single Cloudflare Worker.
 *
 * Same API surface the kiosk already speaks, so cloud/assets/index.html is
 * app/web/kiosk.html with two lines changed (see cloud/README.md). Static assets (the
 * kiosk, the card art) are served by the [assets] binding; this script only ever sees
 * /api/* and a couple of redirects.
 *
 * What the playa server has and this does not, on purpose:
 *   - the legacy single-question flow (/api/reading, app/web/index.html). The kiosk
 *     never calls it and the cloud turtle is the kiosk.
 *   - a real printer. /api/print formats the receipt and says "preview".
 *   - a warm-keeper thread. Workers AI has no cold model to keep resident.
 */
import { DECK, CARDS, cardPayload } from "./deck.js";
import { locate } from "./geo.js";
import { WorkersAILLM, DEFAULT_MODEL } from "./llm.js";
import * as lore from "./lore.js";
import { formatReceipt } from "./printer.js";
import * as session from "./session.js";
import { json } from "./util.js";

/* wrangler needs the Durable Object class exported from the entry module. The séance
 * state lives here now rather than in KV — sessiondo.js says why. */
export { SessionDO } from "./sessiondo.js";

const DEFAULT_WHISPER = "@cf/openai/whisper-large-v3-turbo";
const DEFAULT_TTS = "@cf/deepgram/aura-1";
const DEFAULT_TTS_SPEAKER = "angus";

/* The kiosk holds a séance across several minutes of talking; two hours is a generous
 * roof that still lets an abandoned session fall off the shelf the same evening. */
const SESSION_TTL = 7200;

/* Whisper is billed by audio; the kiosk's own recorder caps at 60s, which is ~240KB of
 * webm/opus on Android and ~1MB of mp4/aac on iOS. Anything past 1.5MB is not a seeker,
 * it is a mistake or an attack. */
const MAX_AUDIO_BYTES = 1.5 * 1024 * 1024;

/* Every POST /api/* route spends money — whisper, the voice, and the séance itself —
 * so they are all limited together, per client IP. See the binding in wrangler.toml. */
const RATE_LIMITED = "the shell needs a moment — too many seekers at once";

/* The kiosk is one HTML file with an inline <style>, an inline <script> and one inline
 * onerror handler, its grain texture is a data: SVG, and the Turtle's spoken lines play
 * from a blob: URL — hence unsafe-inline, data: and blob:. Everything else is same-origin.
 * Tightening this means changing assets/index.html first, which is a copy of the playa
 * kiosk and is meant to stay one. */
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "media-src 'self' blob:",
  "connect-src 'self'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
].join("; ");

const REALM_ORDER = { shell: 0, roots: 1, trunk: 2, branches: 3 };

/* T_SHORT/T_LONG are patience before dropping to the offline template. One request can
 * chain two stages — the draw runs weave then echoes — and each stage may also spend half
 * as long again on the fallback model, so the worst case is 1.5 * (38 + 20) = 87s against
 * a ~100s edge timeout. Raising either number buys a 524 instead of a reading. */
function makeCtx(env) {
  return {
    // the Tale-Book and the tiers counter; the séance itself is in ctx.sessions
    kv: env.SESSIONS,
    sessions: env.SESSION_DO,
    llm: new WorkersAILLM(env),
    shellChance: parseFloat(env.SHELL_CHANCE || "0.10"),
    tShort: parseFloat(env.T_SHORT || "20"),
    tLong: parseFloat(env.T_LONG || "38"),
  };
}

/** True when this IP has had its share of the shell for the minute. */
async function overLimit(env, request) {
  /* No binding — local `wrangler dev`, or a deploy the account would not take it on —
   * means no limit rather than no séance. */
  if (!env.RL || typeof env.RL.limit !== "function") return false;
  try {
    const { success } = await env.RL.limit({ key: request.headers.get("cf-connecting-ip") || "no-ip" });
    return !success;
  } catch (e) {
    return false;
  }
}

/** The kiosk and the card art, with the headers a public deployment wants. */
async function serveAsset(request, env) {
  const res = await env.ASSETS.fetch(request);
  const out = new Response(res.body, res);
  out.headers.set("content-security-policy", CSP);
  out.headers.set("x-content-type-options", "nosniff");
  return out;
}

/* server.py's TIERS counter: if fallback_pct is climbing, the Turtle has gone dumb and
 * is hiding it behind a very convincing template. Kept in KV, best-effort. */
async function noteTiers(kv, modes) {
  if (!kv || !modes) return;
  const seen = [modes.weave, modes.refine, modes.seal].filter(
    (m) => m === "llm" || m === "fallback",
  );
  if (!seen.length) return;
  try {
    const t = (await kv.get("tiers", "json")) || { llm: 0, fallback: 0 };
    for (const m of seen) t[m] = (t[m] || 0) + 1;
    await kv.put("tiers", JSON.stringify(t));
  } catch (e) {
    /* ops telemetry never blocks a séance */
  }
}

function allCardsPayload() {
  const ordered = [...CARDS].sort(
    (a, b) => REALM_ORDER[a.realm] - REALM_ORDER[b.realm] || a.number - b.number,
  );
  return ordered.map((c) => cardPayload(c, locate(c)));
}

async function readJsonBody(req) {
  try {
    return (await req.json()) || {};
  } catch (e) {
    return {};
  }
}

function toBase64(bytes) {
  let s = "";
  const CH = 0x8000;
  for (let i = 0; i < bytes.length; i += CH) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  }
  return btoa(s);
}

/* ---- ears: app/oracle/ears.py, whisper.cpp -> Workers AI whisper ------------------ */
async function transcribe(req, env) {
  const buf = await req.arrayBuffer();
  if (!buf.byteLength) return json({ error: "no audio" }, 400);
  if (buf.byteLength > MAX_AUDIO_BYTES) return json({ error: "that is too much audio" }, 413);
  const model = env.WHISPER_MODEL || DEFAULT_WHISPER;
  /* The kiosk posts the raw MediaRecorder blob with its own Content-Type — webm/opus on
   * Android and Chrome, mp4/aac on iOS. Both were round-tripped through this model on
   * 2026-08-23 and both transcribed; unlike the playa path there is no ffmpeg step. */
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
    return json(
      { error: "the Turtle has no ears on this machine", detail: String(err && err.message) },
      501,
    );
  }
}

/* ---- voice: app/oracle/voice.py, kokoro -> Workers AI TTS ------------------------- */
async function speak(req, env) {
  const body = await readJsonBody(req);
  const text = String(body.text || "")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
  if (!text) return json({ error: "no text" }, 400);
  if (text.length > 600) return json({ error: "speech line is too long" }, 400);
  const model = (env.TTS_MODEL || DEFAULT_TTS).trim();
  if (!model || model === "off") {
    return json({ error: "the Turtle's deeper voice is unavailable" }, 503);
  }
  try {
    const out = await env.AI.run(model, {
      text,
      speaker: env.TTS_SPEAKER || DEFAULT_TTS_SPEAKER,
    });
    const stream = out instanceof ReadableStream ? out : out && out.audio ? out.audio : null;
    if (!stream) return json({ error: "the Turtle's deeper voice is unavailable" }, 503);
    return new Response(stream, {
      headers: {
        "content-type": "audio/mpeg",
        // Readings contain the seeker's words; never let a browser or proxy retain them.
        "cache-control": "no-store",
      },
    });
  } catch (err) {
    return json({ error: "the Turtle's deeper voice is unavailable" }, 503);
  }
}

/* ---- the séance ------------------------------------------------------------------ */
async function seance(action, req, env, exec) {
  const ctx = makeCtx(env);
  const body = await readJsonBody(req);

  if (action === "start") {
    const mode = String(body.mode || "seek").trim();
    const { sess, event } = session.start(mode);
    await session.saveSession(ctx.sessions, sess, SESSION_TTL);
    return json(event);
  }

  const sid = String(body.session || "").trim();
  const sess = await session.loadSession(ctx.sessions, sid);

  if (action === "say") {
    const event = await session.hear(sess, body, ctx);
    if (sess) await session.saveSession(ctx.sessions, sess, SESSION_TTL);
    exec(noteTiers(ctx.kv, event.modes));
    return json(event);
  }
  if (action === "accept") {
    // The sealed quest stays on the session; /api/print reads it back by session id.
    const event = await session.accept(sess, ctx);
    if (sess) await session.saveSession(ctx.sessions, sess, SESSION_TTL);
    exec(noteTiers(ctx.kv, event.modes));
    return json(event);
  }
  return json({ error: "unknown séance action" }, 404);
}

/* ---- the printer that is not there ----------------------------------------------- */
async function print(req, env) {
  const body = await readJsonBody(req);
  const sid = String(body.session || "").trim();
  if (!sid) return json({ error: "no reading to print yet" }, 400);
  const sess = await session.loadSession(env.SESSION_DO, sid);
  if (!sess || !sess.picks) return json({ error: "no such séance to print" }, 400);
  const receipt = formatReceipt(
    {
      question: sess.shares.join(" / "),
      reading: sess.reading,
      adventure: sess.adventure,
      name: sess.name,
    },
    sess.picks,
    sess.located,
    sess.quest,
  );
  return json({
    status: "preview",
    // the kiosk's own copy hides the print button; this stays so a camp turtle can
    // curl the receipt out of a cloud séance and print it by hand at the shell
    note: "the cloud turtle has no printer — this is the paper it would have cut",
    receipt,
    kiosk: String(body.kiosk || ""),
  });
}

/* ---- router ---------------------------------------------------------------------- */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const exec = (p) => (ctx && ctx.waitUntil ? ctx.waitUntil(p) : p);

    if (request.method === "GET") {
      // the cloud turtle IS the kiosk: there is no marketing page to sit at /
      if (path === "/kiosk" || path === "/kiosk.html" || path === "/oracle" || path === "/app") {
        return Response.redirect(new URL("/", url).toString(), 302);
      }
      if (path === "/api/deck") {
        return json({
          title: DECK.deck.title,
          subtitle: DECK.deck.subtitle,
          count: CARDS.length,
          llm: Boolean(env.AI),
        });
      }
      if (path === "/api/cards") return json(allCardsPayload());
      if (path === "/api/lore") return json(await lore.counts(env.SESSIONS));
      if (path === "/api/health") {
        const tiers = (await env.SESSIONS.get("tiers", "json")) || { llm: 0, fallback: 0 };
        const total = tiers.llm + tiers.fallback;
        return json({
          llm_reachable: Boolean(env.AI),
          backend: "workers-ai",
          model: env.MODEL || DEFAULT_MODEL,
          model_fallback: env.MODEL_FALLBACK || null,
          ears: env.WHISPER_MODEL || DEFAULT_WHISPER,
          voice: {
            backend: (env.TTS_MODEL || DEFAULT_TTS) === "off" ? "browser" : "workers-ai",
            model: env.TTS_MODEL || DEFAULT_TTS,
            speaker: env.TTS_SPEAKER || DEFAULT_TTS_SPEAKER,
          },
          readings: tiers,
          // the number to look at: if this is climbing, the Turtle has gone dumb
          fallback_pct: total ? Math.round((1000.0 * tiers.fallback) / total) / 10 : null,
          sessions: "durable-object",
          printer: "none — cloud turtle",
        });
      }
    }

    if (request.method === "POST" && path.startsWith("/api/")) {
      if (await overLimit(env, request)) return json({ error: RATE_LIMITED }, 429);
      if (path === "/api/transcribe") return await transcribe(request, env);
      if (path === "/api/speak") return await speak(request, env);
      if (path === "/api/print") return await print(request, env);
      if (path.startsWith("/api/session/")) {
        const action = path.split("/").pop();
        try {
          return await seance(action, request, env, exec);
        } catch (err) {
          return json({ error: String((err && err.message) || err) }, 500);
        }
      }
    }

    if (path.startsWith("/api/")) return json({ error: "not found" }, 404);
    if (env.ASSETS) return await serveAsset(request, env);
    return json({ error: "not found" }, 404);
  },
};
