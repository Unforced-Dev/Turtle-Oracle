"""LLM adapters (stdlib urllib only). Any failure -> None, so callers fall back to templates.

Two backends, one interface (``.available()`` / ``.generate()`` / ``.model``):

- ``LLM``      — Ollama on the LAN. The playa Spark. No internet, no bill.
- ``CloudLLM`` — any OpenAI-chat-completions-compatible host (Groq, OpenAI, Together,
                 Fireworks, DeepInfra, Cerebras, OpenRouter…). For the public instance
                 at oracle.terribleturtle.camp, where there is no GPU to lean on.

Pick with ``ORACLE_LLM_BACKEND=ollama|cloud|auto`` (default ``auto``: cloud if an API
key is in the environment, else Ollama). Nothing else in the app changes.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

# Models that emit a <think> preamble unless told not to. The Turtle has no use for one.
NO_THINK = ("qwen3", "deepseek", "gpt-oss", "magistral")

# How long a probe result is trusted. Short enough that Ollama coming up late (a power blip
# on playa reorders systemd units) heals on its own within a seeker or two; long enough that
# we don't probe on every LLM touch.
PROBE_TTL = float(os.environ.get("ORACLE_PROBE_TTL", "30"))


class LLM:
    def __init__(self, model=None, host=None):
        self.model = model or os.environ.get("ORACLE_MODEL", "qwen2.5")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self._available = None
        self._probed_at = 0.0

    def available(self):
        """Probe Ollama, re-probing after PROBE_TTL.

        Never cache the answer for the life of the process: if Ollama is down when the
        oracle starts and comes up later, a permanently-cached False leaves the Turtle in
        template mode until a human restarts it — and on playa nobody is at a keyboard.
        """
        now = time.monotonic()
        if self._available is None or (now - self._probed_at) > PROBE_TTL:
            try:
                with urllib.request.urlopen(self.host + "/api/tags", timeout=1.5) as r:
                    self._available = r.status == 200
            except Exception:
                self._available = False
            self._probed_at = now
        return self._available

    def generate(self, prompt, system=None, timeout=90, as_json=False):
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.75},
            "keep_alive": -1,  # stay resident: no 20s reload between seekers
        }
        if self.model.startswith(NO_THINK):
            body["think"] = False
        if system:
            body["system"] = system
        if as_json:
            body["format"] = "json"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.host + "/api/generate", data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read().decode("utf-8"))
            return out.get("response")
        except Exception:
            return None


# --- cloud backend ------------------------------------------------------------------

# Where the key is read from, in order. Never hardcode one; never commit one.
KEY_VARS = ("ORACLE_CLOUD_KEY", "GROQ_API_KEY", "OPENAI_API_KEY")

# Escape hatch for provider-specific knobs without a code change, e.g.
# ORACLE_CLOUD_EXTRA='{"reasoning_format":"hidden"}'. Merged last, so it wins.
try:
    EXTRA = json.loads(os.environ.get("ORACLE_CLOUD_EXTRA") or "{}")
    if not isinstance(EXTRA, dict):
        EXTRA = {}
except Exception:
    EXTRA = {}

# Reasoning models wrap their scratchpad in <think>…</think> and will happily put it
# *outside* the JSON, which json.loads then chokes on — a silent slide into template
# mode. Strip it, and ask for as little of it as the model will accept (below).
THINK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)
FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


def _reasoning_knob(model):
    """Per-family knob to keep the scratchpad short. Reasoning tokens are billed as
    output and cost latency, and the Turtle needs judgment, not deliberation.

    The values are not interchangeable: Groq documents `reasoning_effort` as low/medium/
    high for gpt-oss and none/default for qwen3 — sending "none" to gpt-oss is a 400.
    Anything unrecognised gets nothing, and `generate()` retries bare on a 400 anyway,
    so a wrong guess costs one round trip, not the reading.
    """
    m = (model or "").lower()
    if "gpt-oss" in m:
        return {"reasoning_effort": "low"}
    if any(k in m for k in ("qwen3", "deepseek", "magistral")):
        return {"reasoning_effort": "none"}
    return {}


def _clean_json_ish(text):
    """Undo the two ways a chat model ruins otherwise-valid JSON."""
    text = THINK_RE.sub("", text or "").strip()
    m = FENCE_RE.match(text)
    return (m.group(1) if m else text).strip()


class CloudLLM:
    """OpenAI-compatible /chat/completions client.

    Fails closed: with no API key in the environment ``available()`` is False and the
    séance runs on templates, exactly as it does when Ollama is down. It never touches
    the network to discover that, so a keyless box costs nothing and stalls nobody.
    """

    def __init__(self, model=None, base=None, key=None):
        # Groq's gpt-oss-20b: $0.075/$0.30 per Mtok, ~900 tok/s, and one of only two
        # models there with guaranteed-schema JSON. Roughly a tenth of a cent a séance.
        self.model = model or os.environ.get("ORACLE_CLOUD_MODEL", "openai/gpt-oss-20b")
        self.base = (base or os.environ.get("ORACLE_CLOUD_BASE",
                                            "https://api.groq.com/openai/v1")).rstrip("/")
        self.key = key or next((os.environ[v] for v in KEY_VARS if os.environ.get(v)), None)
        # Room for the weave (~450 tokens of JSON) plus whatever scratchpad a reasoning
        # model spends getting there — that counts against the same cap. Set generously:
        # you are billed for tokens generated, not for the ceiling, and a cap hit truncates
        # the object mid-string, which surfaces as "bad JSON" rather than "ran out of room".
        self.max_tokens = int(os.environ.get("ORACLE_CLOUD_MAX_TOKENS", "2048"))
        self._available = None
        self._probed_at = 0.0

    def _headers(self):
        return {"Content-Type": "application/json", "Authorization": "Bearer " + self.key}

    def available(self):
        """No key -> False, immediately and always. With a key, probe GET /models.

        Re-probes after PROBE_TTL for the same reason Ollama does: a provider blip or an
        expired key should heal (or be noticed in /api/health) without a restart. A 401 or
        403 means the key is wrong — that is genuinely unavailable. Anything else that
        answered at all counts as up, because not every provider serves /models and a
        404 there is no reason to put the Turtle in template mode.
        """
        if not self.key:
            return False
        now = time.monotonic()
        if self._available is None or (now - self._probed_at) > PROBE_TTL:
            req = urllib.request.Request(self.base + "/models", headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=4.0) as r:
                    self._available = r.status < 400
            except urllib.error.HTTPError as e:
                self._available = e.code not in (401, 403)
            except Exception:
                self._available = False
            self._probed_at = now
        return self._available

    def generate(self, prompt, system=None, timeout=90, as_json=False):
        if not self.key:
            return None
        messages = ([{"role": "system", "content": system}] if system else []) \
            + [{"role": "user", "content": prompt}]
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.75,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if as_json:
            # Every JSON-shaped prompt in this app already says "Return JSON only",
            # which is what OpenAI-style json_object mode requires of the messages.
            body["response_format"] = {"type": "json_object"}
        extras = dict(_reasoning_knob(self.model))
        extras.update(EXTRA)
        body.update(extras)

        # One retry at most. A free/hobby tier answers 429 under a queue of seekers and
        # one backoff is far cheaper than dropping to a template; a 400 usually means a
        # parameter this provider doesn't know, so we drop the extras and ask again plain
        # rather than leaving the Turtle mysteriously dumb on an unfamiliar host.
        for attempt in (0, 1):
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(self.base + "/chat/completions", data=data,
                                         headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    out = json.loads(r.read().decode("utf-8"))
                text = (out.get("choices") or [{}])[0].get("message", {}).get("content")
                return _clean_json_ish(text) if as_json else ((text or "").strip() or None)
            except urllib.error.HTTPError as e:
                if attempt:
                    return None          # one retry only, whatever the reason
                if e.code == 400 and extras:
                    for k in extras:     # a knob this provider doesn't know: drop and retry
                        body.pop(k, None)
                    continue
                if e.code in (408, 429, 500, 502, 503, 529):
                    time.sleep(1.5)
                    continue
                return None              # 401/403/404 and friends: no point asking twice
            except Exception:
                return None
        return None


def make_llm():
    """The one place the app decides which shell the voice comes out of."""
    choice = os.environ.get("ORACLE_LLM_BACKEND", "auto").strip().lower()
    if choice == "cloud":
        return CloudLLM()
    if choice in ("ollama", "local"):
        return LLM()
    if any(os.environ.get(v) for v in KEY_VARS):   # auto
        return CloudLLM()
    return LLM()
