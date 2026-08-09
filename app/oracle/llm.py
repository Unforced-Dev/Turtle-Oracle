"""Local LLM adapter (Ollama over stdlib urllib). Any failure -> None, so callers fall back."""
import json
import os
import time
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
