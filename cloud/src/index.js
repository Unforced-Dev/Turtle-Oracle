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
import { DEFAULT_WHISPER, transcribe } from "./ears.js";
import { locate } from "./geo.js";
import { WorkersAILLM, DEFAULT_MODEL } from "./llm.js";
import * as lore from "./lore.js";
import { formatReceipt } from "./printer.js";
import * as session from "./session.js";
import { json } from "./util.js";
import { TRYOUT_SPEAKERS, voiceChoice, voiceText } from "./voice.js";

/* wrangler needs the Durable Object class exported from the entry module. The séance
 * state lives here now rather than in KV — sessiondo.js says why. */
export { SessionDO } from "./sessiondo.js";

const DEFAULT_TTS = "@cf/deepgram/aura-1";
const DEFAULT_TTS_SPEAKER = "angus";

/* The kiosk holds a séance across several minutes of talking; two hours is a generous
 * roof that still lets an abandoned session fall off the shelf the same evening. */
const SESSION_TTL = 7200;

/* Every POST /api/* route spends money — whisper, the voice, and the séance itself — so
 * they are limited per client IP. The voice gets its OWN budget: /api/speak is one POST
 * per sentence, ~41 of them in a séance, so sharing the séance's 30/min meant two phones
 * behind one carrier NAT could 429 each other out of a reading. See wrangler.toml. */
const RATE_LIMITED = "the shell needs a moment — too many seekers at once";

/* What a stranger hears when the Worker throws. Never String(err.message): the seeker is
 * standing in the dust looking at a toast, and an internal message tells them nothing and
 * tells everyone else how this is built. The real one goes to console.error. */
const LOST_THREAD = "the Turtle lost the thread — touch it again";

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
 * run two stages — the draw runs weave and echoes side by side — and each stage may also
 * spend half as long again on the fallback model; the weave may roll twice, the second
 * roll only while half its budget is unspent and with half the timeout. Worst case is
 * max(1.5 * 38, 1.5 * 20) = 57s, or 19 + 1.5 * 19 = 48s on the two-roll path, against a
 * ~100s edge timeout. Raising either number buys a 524 instead of a reading. */
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
async function overLimit(binding, request) {
  /* No binding — local `wrangler dev`, or a deploy the account would not take it on —
   * means no limit rather than no séance. */
  if (!binding || typeof binding.limit !== "function") return false;
  try {
    const { success } = await binding.limit({
      key: request.headers.get("cf-connecting-ip") || "no-ip",
    });
    return !success;
  } catch (e) {
    return false;
  }
}

/** Which budget a route spends from. The two routes that bill by the SECOND of media
 *  each have their own: the voice because a séance is ~41 POSTs of it and two phones
 *  behind one carrier NAT were 429ing each other out of a reading, and the ears because
 *  one POST there is up to two minutes of billed Whisper and should not be able to eat a
 *  seeker's séance budget — nor have 30 of them a minute to itself. */
function limiterFor(env, path) {
  if (path === "/api/speak") return env.RL_SPEAK;
  if (path === "/api/transcribe") return env.RL_EARS;
  return env.RL;
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

/* ---- voice: app/oracle/voice.py, kokoro -> Workers AI TTS ------------------------- */
async function speak(req, env) {
  const body = await readJsonBody(req);
  const line = String(body.text || "")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
  if (!line) return json({ error: "no text" }, 400);
  if (line.length > 600) return json({ error: "speech line is too long" }, 400);
  /* The kiosk posts one SENTENCE per request, so the Turtle's "Mm." arrives here alone
   * and comes back as a groan. Strip the throat-clearing before spending the call; if
   * that is all the line was, answer 204 and let the kiosk move to the next part. The
   * screen still shows every word — this is the voice, not the text. */
  const text = voiceText(line);
  if (!text) return new Response(null, { status: 204 });
  const { model, speaker } = voiceChoice(env, body, {
    model: DEFAULT_TTS,
    speaker: DEFAULT_TTS_SPEAKER,
  });
  if (!model || model === "off") {
    return json({ error: "the Turtle's deeper voice is unavailable" }, 503);
  }
  try {
    const out = await env.AI.run(model, { text, speaker });
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

  if (action !== "say" && action !== "accept") {
    return json({ error: "unknown séance action" }, 404);
  }

  const sid = String(body.session || "").trim();
  const sess = await session.loadSession(ctx.sessions, sid);
  const stageIn = sess ? sess.stage : null;

  let event;
  try {
    // The sealed quest stays on the session; /api/print reads it back by session id.
    event = action === "say" ? await session.hear(sess, body, ctx) : await session.accept(sess, ctx);
  } catch (err) {
    /* The seeker gets a line in the Turtle's voice and a 200, because the kiosk toasts
     * `error` and keeps their screen; the real message goes to the log, where it belongs.
     * It used to be handed to the phone as a 500 with String(err.message) in it. */
    console.error(`séance ${action} failed at ${stageIn}:`, (err && err.stack) || String(err));
    /* hear() mutates `sess` and THEN awaits the model, and saveSession only ran when the
     * request finished — so a throw anywhere after the draw threw the spread away and the
     * seeker's retry paid for a second one. Save it, but only when the stage both moved
     * and finished arriving: replayable() is false for a stage that was entered and never
     * filled in (an `asking` with no question yet), and saving one of those would land
     * the retry in a stage whose reveal the seeker never saw. An unfinished stage is
     * cheaper to redo than a broken séance is to sit in. */
    if (sess && sess.stage !== stageIn && session.replayable(sess)) {
      try {
        await session.saveSession(ctx.sessions, sess, SESSION_TTL);
      } catch (e) {
        /* the séance is already lost; do not lose the reply too */
      }
    }
    return json({ error: LOST_THREAD, stage: (sess && sess.stage) || "gone" });
  }
  if (sess) await session.saveSession(ctx.sessions, sess, SESSION_TTL);
  exec(noteTiers(ctx.kv, event.modes));
  return json(event);
}

/* ---- the printer that is not there ----------------------------------------------- */
async function print(req, env) {
  const body = await readJsonBody(req);
  const sid = String(body.session || "").trim();
  if (!sid) return json({ error: "no reading to print yet" }, 400);
  const sess = await session.loadSession(env.SESSION_DO, sid);
  if (!sess || !sess.picks) return json({ error: "no such séance to print" }, 400);
  /* The receipt is the paper the shell would have cut, and app/oracle/printer.py opens it
   * with YOU TOLD THE TURTLE and the seeker's own shares — a confession, on the paper, by
   * design, because on the playa the paper goes straight into the hand of the person who
   * said it. Here it comes back over the open internet to whoever posts the id, so it is
   * gated on a SEALED séance: an accepted quest is a thing the seeker asked for and can
   * hand on, and everything before it is a session mid-confession. The shares stay in the
   * receipt because removing them would leave the playa's own format with a heading and
   * nothing under it, and this text has to stay the paper. */
  if (sess.stage !== "accepted" || !sess.quest) {
    return json({ error: "there is no sealed quest on this séance yet" }, 400);
  }
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
            // staging only: /api/speak will take a speaker and a model off the body
            tryouts: String(env.VOICE_TRYOUTS || "") === "1" ? TRYOUT_SPEAKERS : null,
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
      if (await overLimit(limiterFor(env, path), request)) return json({ error: RATE_LIMITED }, 429);
      if (path === "/api/transcribe") return await transcribe(request, env, url);
      if (path === "/api/speak") return await speak(request, env);
      if (path === "/api/print") return await print(request, env);
      if (path.startsWith("/api/session/")) {
        const action = path.split("/").pop();
        try {
          return await seance(action, request, env, exec);
        } catch (err) {
          /* seance() catches everything the séance itself can throw and answers in the
           * Turtle's voice; this is the outer net for the rest — a body that would not
           * parse, a Durable Object that would not answer. Same shape, same silence. */
          console.error(`/api/session/${action} failed:`, (err && err.stack) || String(err));
          return json({ error: LOST_THREAD, stage: null });
        }
      }
    }

    if (path.startsWith("/api/")) return json({ error: "not found" }, 404);
    if (env.ASSETS) return await serveAsset(request, env);
    return json({ error: "not found" }, 404);
  },
};
