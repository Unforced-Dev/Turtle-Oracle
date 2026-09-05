/* ASK THE TURTLE — open talk, grounded in the city dump and the cards.
 *
 * Port of app/oracle/chat.py. The séance is a ceremony with an order; this is not. It is
 * the thing a seeker actually does at 2am: lean on the shell and ask where the coffee is.
 * Same voice (weave.SYSTEM, never forked), same cards, but the Turtle answers from
 * guide.retrieve and from nothing else — and says so when the shell does not hold it.
 *
 * TWO THINGS WERE HARD-WON ON THE SPARK, 2026-09-05, AND BOTH ARE LOAD-BEARING:
 *
 * 1. The model must answer as JSON. qwen3 with thinking OFF still reasons out loud when
 *    the prompt reads like a transcript — "Hmm, the seeker is asking about…", "Let me
 *    check the Shell Holds…" — 4 answers in 5 on the Spark. Wrapping the answer in
 *    {"say": "..."} gives the scratchpad nowhere to go, and it stopped.
 * 2. The narration guard stays anyway, with one re-roll behind it. A model that ignores
 *    the envelope produces a whole answer of scratchpad, and shipping that to a speaker
 *    is worse than shipping the offline template.
 *
 * WHERE THE HISTORY LIVES. chat.py keeps an in-memory OrderedDict, because the Spark is
 * one process on one machine. A Worker is not: two turns of the same conversation land
 * in different isolates, often in different datacentres, and an in-memory map would drop
 * the thread most of the time. So a chat is a Durable Object addressed by its id, for
 * exactly the reason cloud/src/sessiondo.js gives for the séance. It is the same class —
 * a chat is a small record with an expiry, which is all SessionDO ever stored.
 */
import * as guide from "./guide.js";
import * as session from "./session.js";
import { SYSTEM } from "./weave.js";

/* A question, not an essay — anything longer is a stuck mic. */
const MAX_TEXT = 600;
/* Seeker+Turtle pairs kept per chat. */
const MAX_TURNS = 12;
/* An hour of standing at the shell. A chat is a conversation, not a record; when the
 * phone goes back in the pocket it is gone, exactly as chat.py intends. */
const CHAT_TTL = 3600;

/* A spoken answer is 2-5 sentences. chat.py caps at 220 tokens against a serialised GPU;
 * Workers AI is faster, so the cap here is a guard against a runaway rather than a pacing
 * control, and it is loose enough that the JSON envelope cannot be the thing that
 * truncates. A truncated answer surfaces as bad JSON and drops the seeker to a template,
 * which is the failure llm.js's header warns about — do not tighten this without
 * measuring the fallback rate. */
const DEFAULT_CHAT_TOKENS = 320;
/* Patience before the offline template. The séance's T_SHORT is 20s for a stage that is
 * one of several in a request; a chat turn is the whole request. */
const DEFAULT_T_CHAT = 30;

const BULLET_RE = /^[ \t]*(?:[-*•–]|\d+[.)])\s+/gm;
const HEADING_RE = /^[ \t]*#{1,6}\s*/gm;
const THINK_RE = /<(think|thinking|reasoning)>[\s\S]*?<\/\1>/gi;

export const ADDENDUM = `
YOU ARE ANSWERING A QUESTION AT THE SHELL, not weaving a reading. Rules, absolute:
- Answer in 2 to 5 sentences. Spoken aloud, so no bullets, no headings, no lists, no
  markdown, no emoji. Plain sentences.
- Every place, time and name you say must come from THE SHELL HOLDS below. Never invent a
  camp, an address, a time, or an event.
- If the answer is not in THE SHELL HOLDS, say "the Turtle does not know that" and say what
  you do know instead. The shell has NO DJ lineups, NO set times, NO art-car schedules and
  NO who-is-playing — never guess one, not even a likely one.
- If you offer a quest, it is ONE BITE: one act, one bearing, one proof. You may name a camp,
  an art piece or an event from below by NAME. Never put an address block in a quest.
- Never lecture about safety; never dare physical risk, substances, climbing on art, or
  anything done to another person without their consent.
`;

/* The openers of a scratchpad sentence. A sentence that starts this way is the model
 * thinking, not the Turtle speaking. Same list as chat.py. */
const NARRATION_RE =
  /^\s*(hmm+|okay|ok|alright|well|so|first|now|wait|the seeker|the user|we (must|are|need|should|have)|let me|let's|i need to|i should|i will|i'll|looking at|checking|based on|according to the shell|the shell holds|the question is|they are asking|they're asking|the answer (must|should|needs))\b/i;

const SPEAK_NOW =
  "Speak now as the Turtle, straight to the seeker, first spoken sentence first. " +
  "No preamble, no notes to yourself, no describing what you are checking or which " +
  'rule applies. Only the words the seeker hears go in "say". ' +
  "Shape (about a different seeker, never quote it): " +
  '{"say": "It is a little past ten in the morning, playa time. The shell is open. Ask."}';

/* "what did my cards mean", "read my quest again" — with no model, the honest answer is
 * the seeker's own draw read back, not a list of whatever is on this hour. */
const MINE_RE = /\bmy (cards?|reading|quest|draw|spread)\b|\b(this|the) (reading|quest)\b/i;

/** Split into sentences the way chat.py does, keeping the terminator. */
function sentences(t) {
  return (t.replace(/\n/g, " ").match(/[^.!?…]+[.!?…]+['"”]?|[^.!?…]+$/g) || [])
    .map((p) => p.trim())
    .filter(Boolean);
}

/** Drop leading scratchpad sentences. Returns {parts, narrated}. */
function unnarrate(parts) {
  let narrated = false;
  while (parts.length && NARRATION_RE.test(parts[0])) {
    parts = parts.slice(1);
    narrated = true;
  }
  return { parts, narrated };
}

/** A spoken answer: no scratchpad, no markdown, no more than five sentences. */
export function clean(text) {
  let t = String(text || "").replace(THINK_RE, "").trim();
  t = t.replace(/^```.*?$|^```$/gm, "");
  t = t.replace(HEADING_RE, "");
  t = t.replace(BULLET_RE, "");
  t = t.replace(/\*\*|\*|__|`/g, "");
  t = t.replace(/^\s*(turtle|oracle|answer)\s*[:\-]\s*/i, "");
  t = t.replace(/[ \t]+/g, " ").replace(/\n{2,}/g, "\n").trim();
  const { parts, narrated } = unnarrate(sentences(t));
  return { say: parts.slice(0, 5).join(" ").trim(), narrated };
}

/** The spoken string out of the model's JSON; the raw text if it forgot the envelope. */
export function said(raw) {
  const t = String(raw || "").replace(THINK_RE, "").trim();
  const m = /\{[\s\S]*\}/.exec(t);
  if (m) {
    try {
      const obj = JSON.parse(m[0]);
      if (obj && typeof obj === "object" && typeof obj.say === "string") return obj.say;
    } catch (e) {
      /* the model forgot the envelope; the raw text is still an answer */
    }
  }
  return t;
}

/** The seeker's own cards and reading, verbatim, when this chat hangs off a live séance. */
export function seanceBlock(sess) {
  if (!sess || !sess.picks) return "";
  const lines = [
    "THE SEEKER'S CARDS AND READING TONIGHT (yours, already spoken — do not re-weave " +
      "them, but you may lean on them):",
  ];
  if (sess.name) lines.push(`name: ${sess.name}`);
  for (const realm of ["roots", "trunk", "branches"]) {
    const card = (sess.picks || {})[realm];
    if (card) lines.push(`${realm}: ${card.name}`);
  }
  if (sess.reading) lines.push(`the reading: ${sess.reading}`);
  if (sess.adventure) lines.push(`the quest offered: ${sess.adventure}`);
  const quest = sess.quest;
  if (quest && quest.moves && quest.moves.length) {
    const m = quest.moves[0];
    lines.push(
      "the sealed quest: " +
        ["task", "where", "proof"].map((f) => String(m[f] || "")).join(" ").trim(),
    );
  }
  return lines.join("\n");
}

function systemFor(ctx, sess, now) {
  /* Our own placement is the ONE address the Turtle may hand out — it is the camp's own,
   * and a seeker who cannot find the shell cannot come back to it. */
  const head =
    `IT IS ${guide.playaClock(now)} in Black Rock City (playa time). ` +
    "Terrible Turtle Camp is at E & 6:15.";
  const seance = seanceBlock(sess);
  return [
    SYSTEM,
    "",
    ADDENDUM,
    "",
    head,
    "",
    "THE SHELL HOLDS (everything you are allowed to say about the city):",
    ctx.block,
  ]
    .concat(seance ? ["", seance] : [])
    .join("\n");
}

function promptFor(history, text) {
  const lines = [];
  for (const [role, saidText] of history.slice(-(MAX_TURNS * 2))) {
    lines.push((role === "seeker" ? "Seeker: " : "Turtle: ") + saidText);
  }
  lines.push("Seeker: " + text);
  lines.push("");
  lines.push(SPEAK_NOW);
  lines.push('Return JSON only: {"say": "<what the Turtle says aloud, 2 to 5 sentences>"}');
  return lines.join("\n");
}

/** No model, or a model that only produced scratchpad. Say what the shell plainly holds,
 *  and never more than that. Port of chat.py's fallback, refusal order included. */
export function fallback(ctx, text, sess) {
  const hits = (ctx.hits || []).filter((h) => h.when).slice(0, 3);

  if (sess && MINE_RE.test(String(text || ""))) {
    const names = ["roots", "trunk", "branches"]
      .map((r) => (sess.picks || {})[r])
      .filter(Boolean)
      .map((c) => c.name);
    if (names.length) {
      const first = sentences(String(sess.reading || "")).slice(0, 2).join(" ");
      const line = ("The Tree gave you " + names.join(", ") + ". " + first).trim();
      if (line) return line;
    }
  }

  /* A lineup question is answered by the refusal FIRST, whatever else the shell holds.
   * It is the one thing the dump has none of, and the one thing a model would happily
   * improvise, so the offline answer must not bury it behind anything friendlier. */
  const lead = ctx.lineup
    ? "The Turtle does not know that. No lineups live in this shell — no names, " +
      "no set times, no art car schedules. "
    : "";

  /* A named card is answerable with or without the city, and is the one thing the Turtle
   * always knows — so it wins over a list of whatever happens to be on. */
  if (ctx.card_meaning) {
    const said3 = sentences(ctx.card_meaning).slice(0, 3).join(" ");
    return (lead + `${ctx.card}. ` + said3).trim();
  }
  if (!ctx.have) {
    return (
      (lead || "The Turtle does not know that. ") +
      "The city is not in this shell tonight. Ask it about a card instead, or ask a " +
      "turtle with legs."
    );
  }
  if (!hits.length) {
    return (
      (lead || "The Turtle does not know that. ") +
      `Nothing is written in the shell for ${ctx.window}. Walk out and let the city tell you.`
    );
  }
  const body = hits
    .map((h) => `${h.title}, ${h.when}` + (h.where ? `, at ${h.where}` : "") + ".")
    .join(" ");
  return (lead + `Here is what the shell holds for ${ctx.window}. ` + body).trim();
}

/* ---- where a chat is kept -------------------------------------------------------- */

const ID_BYTES = 6;

function newChatId() {
  const b = new Uint8Array(ID_BYTES);
  crypto.getRandomValues(b);
  return "c" + [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
}

/* A chat id off the wire addresses a Durable Object by name, so it is validated like one:
 * our own alphabet, our own length, nothing else. An unbounded string here would let a
 * stranger name — and pay us to spin up — any object they liked. */
const CHAT_ID_RE = /^c[0-9a-f]{12}$/;

/* A séance id, the shape session.js newId() makes them. Same reasoning as CHAT_ID_RE:
 * this route hands the id to idFromName, and an id off the wire that is not one of ours
 * is a stranger naming Durable Objects on our account. */
const SESSION_ID_RE = /^[0-9a-f]{12}$/;

function chatStub(store, chatId) {
  if (!store || !CHAT_ID_RE.test(chatId)) return null;
  try {
    return store.get(store.idFromName("chat:" + chatId));
  } catch (e) {
    return null;
  }
}

async function loadChat(store, chatId) {
  const stub = chatStub(store, chatId);
  if (!stub) return null;
  try {
    return await stub.load();
  } catch (e) {
    return null;
  }
}

async function saveChat(store, chatId, rec) {
  const stub = chatStub(store, chatId);
  if (!stub) return;
  try {
    await stub.save(rec, CHAT_TTL);
  } catch (e) {
    /* a lost turn of history is a duller answer, never a failed one */
  }
}

/**
 * Open an empty chat, so a seeker can SPEAK into it before they have typed anything.
 *
 * The ears are gated on a live conversation (src/ears.js says why: without a gate the
 * transcribe route is a free Whisper endpoint). A cold "Ask the Turtle" has no séance
 * behind it and no chat id until the first answer comes back, so without this the mic on
 * that screen could never open — and a seeker at 2am with dusty hands is exactly who the
 * mic is for. One cheap POST when the door opens, on the chat's own rate-limit budget.
 */
export async function open(env) {
  const chatId = newChatId();
  await saveChat(env.SESSION_DO, chatId, { history: [], created: guide.nowSec() });
  return { chat_id: chatId };
}

/** Does this id name a chat that exists? The ears ask before they spend anything. */
export async function exists(env, chatId) {
  const id = String(chatId || "").trim();
  if (!CHAT_ID_RE.test(id)) return false;
  return Boolean(await loadChat(env.SESSION_DO, id));
}

/* ---- one turn -------------------------------------------------------------------- */

/**
 * @param {object} env the Worker env (ASSETS, SESSION_DO, AI, vars)
 * @param {object} body {text, chat_id?, session?}
 * @param {object} llm  a WorkersAILLM, or anything with available()/generate()
 * @param {object} opts {now} — pinned by the tests
 * @returns {Promise<object|null>} {chat_id, say, hits, mode, grounded} — null for no text
 */
export async function ask(env, body, llm, opts = {}) {
  const text = String((body && body.text) || "").trim().slice(0, MAX_TEXT);
  if (!text) return null;
  const now = opts.now || guide.nowSec();

  const raw = String((body && body.session) || "").trim();
  const sid = SESSION_ID_RE.test(raw) ? raw : "";
  /* A chat may hang off a live séance. The id is the seeker's own — the same id their
   * phone already holds — and it only ever READS the séance; a chat can no more move the
   * ceremony's state machine than the printer can. */
  let sess = null;
  if (sid) {
    try {
      sess = await session.loadSession(env.SESSION_DO, sid);
    } catch (e) {
      sess = null;
    }
  }

  const asked = String((body && body.chat_id) || "").trim();
  const chatId = CHAT_ID_RE.test(asked) ? asked : newChatId();
  const rec = (asked === chatId ? await loadChat(env.SESSION_DO, chatId) : null) || {
    history: [],
    created: now,
  };
  const history = Array.isArray(rec.history) ? rec.history : [];

  const ctx = await guide.retrieve(env, text, { now });

  let say = "";
  let mode = "fallback";
  try {
    if (llm && llm.available()) {
      const prompt = promptFor(history, text);
      const system = systemFor(ctx, sess, now);
      const tokens = parseInt(env.CHAT_TOKENS || "", 10) || DEFAULT_CHAT_TOKENS;
      const timeout = parseFloat(env.T_CHAT || "") || DEFAULT_T_CHAT;
      const one = clean(said(await llm.generate(prompt, {
        system, asJson: true, timeout, stage: "chat", maxTokens: tokens,
      })));
      say = one.say;
      if (!say) {
        /* Every sentence was scratchpad. One more roll, told plainly, half the clock —
         * the same second chance the Spark takes, and for the same reason: the answer is
         * usually in there, behind a preamble the model could not help writing. */
        const two = clean(said(await llm.generate(
          prompt + " Answer only, in the Turtle's voice.",
          { system, asJson: true, timeout: timeout / 2, stage: "chat", maxTokens: tokens },
        )));
        say = two.say;
      }
      if (say) mode = "llm";
    }
  } catch (e) {
    console.error("chat: the model failed:", (e && e.stack) || String(e));
    say = "";
  }
  if (!say) say = fallback(ctx, text, sess);

  history.push(["seeker", text], ["turtle", say]);
  await saveChat(env.SESSION_DO, chatId, {
    history: history.slice(-(MAX_TURNS * 2)),
    created: rec.created || now,
  });

  return {
    chat_id: chatId,
    say,
    hits: (ctx.hits || []).slice(0, 8),
    mode,
    grounded: ctx.have,
    window: ctx.window,
  };
}
