#!/usr/bin/env python3
"""Exercise the LLM backends against a fake OpenAI-compatible server. No key, no bill.

    PYTHONPATH=app python3 tools/test_llm_backends.py

Covers the two things that actually bite: the keyless box must fail closed (template
mode, no network, no hang), and a model that wraps its JSON in a think-block or a code
fence must still parse — otherwise fallback_pct climbs and nobody knows why.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from oracle.llm import LLM, CloudLLM, make_llm, _clean_json_ish  # noqa: E402

REPLY = None      # what the fake server puts in message.content
STATUS = [200]    # queue of status codes to hand back, one per request
SEEN = []         # request bodies the server received


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer test-key":
            return self._json(401, {"error": "bad key"})
        self._json(200, {"data": [{"id": "fake-model"}]})

    def do_POST(self):
        SEEN.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        code = STATUS.pop(0) if STATUS else 200
        if code != 200:
            return self._json(code, {"error": "try again"})
        self._json(200, {"choices": [{"message": {"content": REPLY}}]})


def check(name, got, want):
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else f"\n         got {got!r}\n         want {want!r}"))
    return ok


def main():
    for v in ("ORACLE_CLOUD_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "ORACLE_LLM_BACKEND"):
        os.environ.pop(v, None)
    global REPLY
    fails = 0

    print("fail closed with no key (must not touch the network):")
    cold = CloudLLM()
    fails += not check("available() is False", cold.available(), False)
    fails += not check("generate() is None", cold.generate("hi", as_json=True), None)
    fails += not check("make_llm() -> Ollama", type(make_llm()).__name__, "LLM")
    os.environ["ORACLE_LLM_BACKEND"] = "cloud"
    fails += not check("BACKEND=cloud forces cloud", type(make_llm()).__name__, "CloudLLM")
    del os.environ["ORACLE_LLM_BACKEND"]
    os.environ["ORACLE_CLOUD_KEY"] = "test-key"
    fails += not check("key present -> auto picks cloud", type(make_llm()).__name__, "CloudLLM")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    os.environ["ORACLE_CLOUD_BASE"] = base
    os.environ["ORACLE_CLOUD_MODEL"] = "fake-model"

    print("\nagainst a fake OpenAI-compatible endpoint:")
    llm = make_llm()
    fails += not check("available() probes /models", llm.available(), True)

    REPLY = '{"reading": "You said yes all year.", "adventure": "Walk out past the Man."}'
    got = llm.generate("Return JSON only", system="be the turtle", as_json=True)
    fails += not check("clean JSON round-trips", json.loads(got)["reading"], "You said yes all year.")
    fails += not check("json_object mode requested",
                       SEEN[-1].get("response_format"), {"type": "json_object"})
    fails += not check("system message sent", SEEN[-1]["messages"][0]["role"], "system")

    REPLY = '<think>hmm, dust</think>\n```json\n{"roots": "a", "trunk": "b", "branches": "c"}\n```'
    got = llm.generate("Return JSON only", as_json=True)
    fails += not check("think-block + fence stripped", json.loads(got)["trunk"], "b")

    REPLY = '{"ok": true}'
    STATUS[:] = [429]
    fails += not check("retries once past a 429", json.loads(llm.generate("x", as_json=True))["ok"], True)

    STATUS[:] = [500, 500]
    fails += not check("gives up after the retry -> None", llm.generate("x", as_json=True), None)

    STATUS[:] = [401]
    fails += not check("401 is not retried -> None", llm.generate("x", as_json=True), None)

    print("\nreasoning knobs (wrong guess must not cost the reading):")
    oss = CloudLLM(model="openai/gpt-oss-20b", base=base, key="test-key")
    STATUS[:] = []
    oss.generate("x", as_json=True)
    fails += not check("gpt-oss asks for low effort", SEEN[-1].get("reasoning_effort"), "low")
    qwen = CloudLLM(model="qwen/qwen3.6-27b", base=base, key="test-key")
    qwen.generate("x", as_json=True)
    fails += not check("qwen3 asks for none", SEEN[-1].get("reasoning_effort"), "none")
    plain = CloudLLM(model="gpt-4.1-nano", base=base, key="test-key")
    plain.generate("x", as_json=True)
    fails += not check("non-reasoning model sends no knob",
                       "reasoning_effort" in SEEN[-1], False)

    STATUS[:] = [400]        # provider rejects the knob -> drop it and ask again plain
    before = len(SEEN)
    got = oss.generate("x", as_json=True)
    fails += not check("400 on an unknown knob retries bare", json.loads(got)["ok"], True)
    fails += not check("...and the retry dropped it", "reasoning_effort" in SEEN[-1], False)
    fails += not check("...in exactly two requests", len(SEEN) - before, 2)

    print("\nbad key -> unavailable, so the séance runs on templates:")
    fails += not check("wrong key fails the probe",
                       CloudLLM(base=base, key="nope").available(), False)

    print("\nresponse cleaner:")
    fails += not check("plain text untouched", _clean_json_ish('{"a":1}'), '{"a":1}')
    fails += not check("None tolerated", _clean_json_ish(None), "")

    print("\nOllama backend still constructs:")
    fails += not check("LLM() defaults", LLM(host="http://127.0.0.1:1").available(), False)

    srv.shutdown()
    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
