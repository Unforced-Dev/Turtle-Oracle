"""Local LLM adapter (Ollama over stdlib urllib). Any failure -> None, so callers fall back."""
import json
import os
import urllib.request


class LLM:
    def __init__(self, model=None, host=None):
        self.model = model or os.environ.get("ORACLE_MODEL", "qwen2.5")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self._available = None

    def available(self):
        if self._available is None:
            try:
                with urllib.request.urlopen(self.host + "/api/tags", timeout=1.5) as r:
                    self._available = r.status == 200
            except Exception:
                self._available = False
        return self._available

    def generate(self, prompt, system=None, timeout=90, as_json=False):
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.8},
        }
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
