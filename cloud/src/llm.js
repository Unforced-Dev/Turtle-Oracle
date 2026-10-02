/* The cloud turtle's voice: Workers AI, standing in for app/oracle/llm.py.
 *
 * Same interface as the Python adapters — available() / generate() / .model — so the
 * ported séance code reads the same. Any failure returns null and the caller drops to
 * the offline template, exactly as on the playa Spark.
 *
 * Three facts about Workers AI shape this file. All were measured against this account
 * on 2026-08-23 with the app's own four prompts, not assumed:
 *
 * 1. Qwen3 reasoning does NOT leak into the answer. Workers AI splits the scratchpad
 *    into choices[0].message.reasoning and hands back clean content. So the failure the
 *    Python CloudLLM guards against (a <think> block landing outside the JSON and
 *    breaking json.loads) does not happen here. The strip stays anyway — it is three
 *    lines, and it is the exact class of bug that reappears when a model is swapped.
 *    (`chat_template_kwargs: {enable_thinking:false}` DOES break it: the whole answer
 *    arrives in `reasoning` and `content` comes back null. Do not use that route.)
 *
 * 2. Qwen3's `/no_think` soft switch works, and it is not a free win — it helps two of
 *    the séance's prompts and ruins the third. n=8 per cell, same prompt each time:
 *
 *      WEAVE  (the reading + quest, 6.9k chars of instruction)
 *        /no_think : 4/8 answers were the SYSTEM prompt's own EXAMPLE, copied verbatim
 *                    and handed to the seeker as their reading. 1/8 hit the 90-120 word
 *                    budget. Median 1.2s.
 *        thinking  : 0/8 example-copies, 5/8 in budget, the rest 80-88w. Median 4.6s.
 *      REFINE (rewrite the quest around a new confession)
 *        /no_think : 4/4 in the 60-140 word gate. Median 1.1s.
 *        thinking  : 1/4 — it spends the budget deliberating and then writes a stub,
 *                    and one run hit max_tokens mid-JSON and returned nothing at all.
 *      ECHOES, SEAL: 4/4 either way; /no_think is 3-11x faster, so they skip it.
 *      TALE (the honour line spoken when a seeker returns with their story)
 *        /no_think : 3/3 answers put the two sentences on two LINES, and _clean_line
 *                    keeps only the first — which silently drops the half that tells
 *                    the human turtle to hand over the gift. That is the whole point
 *                    of the stage.
 *        thinking  : 3/3 one line, both sentences, gift instruction intact.
 *
 *    So thinking is per-stage, not global (THINK_STAGES in wrangler.toml), which is a
 *    deliberate divergence from llm.py — it sets think=False for every qwen3 call
 *    because Ollama on one playa GPU cannot afford 700 reasoning tokens a stage.
 *    Four seconds of thinking on the one call the whole séance is judged by is the
 *    trade the cloud can make and the Spark cannot.
 *
 * 3. max_tokens is a ceiling, not a target, and the ceiling is what truncates a
 *    reasoning model mid-JSON — which surfaces as "bad JSON" rather than "ran out of
 *    room" and drops the seeker to a template. 4096, for the same reason llm.py says so.
 */

export const DEFAULT_MODEL = "@cf/qwen/qwen3-30b-a3b-fp8";

/* Model families that emit a scratchpad unless told not to. Same list as llm.py. */
const NO_THINK = ["qwen3", "deepseek", "gpt-oss", "magistral"];

/* Only Qwen understands the /no_think marker; the others are listed so a future swap
 * is a one-line change rather than a rediscovery. */
const NO_THINK_MARKER = " /no_think";

const THINK_RE = /<(think|thinking|reasoning)>[\s\S]*?<\/\1>/gi;
/* A cap hit can truncate mid-scratchpad, leaving an opening tag and no close. */
const THINK_OPEN_RE = /<(think|thinking|reasoning)>[\s\S]*$/i;
const FENCE_RE = /^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$/;

/** Undo the ways a chat model ruins otherwise-valid JSON. Port of _clean_json_ish. */
export function cleanJsonIsh(text) {
  let out = (text || "").replace(THINK_RE, "").replace(THINK_OPEN_RE, "").trim();
  const m = FENCE_RE.exec(out);
  return (m ? m[1] : out).trim();
}

function wantsNoThink(model) {
  const m = (model || "").toLowerCase();
  return NO_THINK.some((k) => m.includes(k));
}

/** Parse a Workers AI text-generation reply into a plain string, or null. */
function extractText(out) {
  if (out == null) return null;
  if (typeof out === "string") return out;
  const msg = out.choices && out.choices[0] && out.choices[0].message;
  if (msg && typeof msg.content === "string" && msg.content.trim()) return msg.content;
  const r = out.response;
  if (typeof r === "string" && r.trim()) return r;
  /* Workers AI helpfully pre-parses a JSON answer into an object on `response`.
   * Stringify it back rather than dropping the reading on the floor. */
  if (r && typeof r === "object") return JSON.stringify(r);
  return null;
}

export class WorkersAILLM {
  constructor(env) {
    this.ai = env.AI;
    this.model = (env.MODEL || DEFAULT_MODEL).trim();
    /* A second model tried once if the first errors. Empty string disables it. */
    this.fallbackModel = (env.MODEL_FALLBACK || "").trim();
    this.maxTokens = parseInt(env.MAX_TOKENS || "4096", 10) || 4096;
    this.temperature = parseFloat(env.TEMPERATURE || "0.75");
    /* Which séance stages are worth a scratchpad. See the measurements at the top. */
    this.thinkStages = new Set(
      (env.THINK_STAGES === undefined ? "weave,tale" : env.THINK_STAGES)
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    );
    /* Ops counters for /api/health, mirroring server.py's TIERS. */
    this.calls = 0;
    this.errors = 0;
    this.lastError = null;
  }

  /** The binding is either there or the Worker would not have booted. */
  available() {
    return Boolean(this.ai);
  }

  /**
   * @param {string} prompt
   * @param {{system?: string, asJson?: boolean, timeout?: number, stage?: string,
   *          maxTokens?: number}} opts
   *   stage names the séance step ("weave", "echoes", "refine", "seal", "tale") and
   *   decides only one thing: whether this call gets a scratchpad.
   *   maxTokens overrides the ceiling for ONE call. The séance never passes it — every
   *   stage of it wants the full 4096, for the reason in note 3 above. Ask the Turtle
   *   does: a chat answer is 2-5 spoken sentences and an unbounded one is a model that
   *   has started writing an essay into a speaker.
   * @returns {Promise<string|null>}
   */
  async generate(prompt, opts = {}) {
    if (!this.ai) return null;
    const { system, asJson = false, timeout = 38, stage = "", maxTokens } = opts;
    const cap = parseInt(maxTokens, 10) > 0 ? parseInt(maxTokens, 10) : this.maxTokens;
    const mayThink = this.thinkStages.has(stage);

    const models = [this.model];
    if (this.fallbackModel && this.fallbackModel !== this.model) models.push(this.fallbackModel);

    for (let attempt = 0; attempt < models.length; attempt++) {
      const model = models[attempt];
      /* The understudy gets half the patience the primary had. A hung primary has
       * already spent the stage's whole budget, and a request can chain two stages, so
       * primary + full fallback twice over would blow through Cloudflare's edge timeout
       * and hand the seeker a 524 instead of the template the fallback exists to reach. */
      const budget = attempt === 0 ? timeout : timeout / 2;
      let sys = system || "";
      if (!mayThink && wantsNoThink(model)) {
        sys = (sys ? sys : "Answer directly.") + NO_THINK_MARKER;
      }

      const messages = [];
      if (sys) messages.push({ role: "system", content: sys });
      messages.push({ role: "user", content: prompt });

      const inputs = {
        messages,
        temperature: this.temperature,
        max_tokens: cap,
      };
      if (asJson) {
        /* Every JSON-shaped prompt in this app already says "Return JSON only",
         * which is what json_object mode requires of the messages. */
        inputs.response_format = { type: "json_object" };
      }

      this.calls++;
      try {
        const out = await this._race(this.ai.run(model, inputs), budget);
        if (out === undefined) {
          this.errors++;
          this.lastError = `timeout after ${budget}s on ${model}`;
          continue; // a hung model: try the understudy, then give up to the template
        }
        const text = extractText(out);
        if (text == null) {
          this.errors++;
          this.lastError = `empty reply from ${model}`;
          continue;
        }
        const cleaned = asJson ? cleanJsonIsh(text) : cleanJsonIsh(text).trim();
        return cleaned || null;
      } catch (err) {
        this.errors++;
        this.lastError = `${model}: ${String((err && err.message) || err)}`.slice(0, 300);
        // fall through to the next model, if any
      }
    }
    return null;
  }

  /** Resolve to `undefined` if the model has not answered in `secs` seconds. */
  _race(promise, secs) {
    let timer;
    const guard = new Promise((resolve) => {
      timer = setTimeout(() => resolve(undefined), secs * 1000);
    });
    return Promise.race([promise, guard]).finally(() => clearTimeout(timer));
  }
}

/** Parse JSON the way the Python does: any failure means "no answer", never a crash. */
export function tryJson(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (e) {
    return null;
  }
}
