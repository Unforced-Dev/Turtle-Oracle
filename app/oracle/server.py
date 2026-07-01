"""Zero-dependency local server for the oracle kiosk.

Run:  PYTHONPATH=app python3 -m oracle.server   (then open http://localhost:8777)

Stdlib only, so it runs on playa with no pip installs. Uses a local Ollama model if one is
running; otherwise the offline template weave. Single-threaded on purpose: one seeker at a time.
"""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .deck import load_deck, SLOT_LABEL, REPO
from .select import select_cards
from .weave import weave
from .llm import LLM
from .geo import locate, locate_spread, directions_lines, COMPASS_ROSE
from . import printer

WEB = os.path.join(REPO, "app", "web")
ART = os.path.join(REPO, "cards", "art")
PORT = int(os.environ.get("ORACLE_PORT", "8777"))
LLM_SINGLETON = LLM()
ART_RE = re.compile(r"^(shell|roots|trunk|branches)-\d{2}\.png$")
WEBIMG_RE = re.compile(r"^((shell|roots|trunk|branches)-\d{2}|back)\.jpg$")
LAST = {}  # last built reading (kiosk = one seeker at a time), for /api/print


def card_payload(c, loc=None):
    loc = loc or {}
    return {
        "id": c["id"], "name": c["name"], "realm": c["realm"],
        "slot": SLOT_LABEL.get(c["realm"], ""),
        "reading": c["reading"], "shadow": c.get("shadow", ""),
        "turtle_dare": c["turtle_dare"],
        "real_2026": c["real_2026"]["name"],
        "location": {"directions": loc.get("directions", ""), "status": loc.get("status", ""),
                     "clock": loc.get("clock")},
        "image": (f"/med/{c['id']}.jpg" if os.path.exists(os.path.join(REPO, "cards/web/med", f"{c['id']}.jpg"))
                  else (f"/art/{c['id']}.png" if os.path.exists(os.path.join(ART, f"{c['id']}.png")) else None)),
        "thumb": (f"/thumb/{c['id']}.jpg" if os.path.exists(os.path.join(REPO, "cards/web/thumb", f"{c['id']}.jpg"))
                  else (f"/med/{c['id']}.jpg" if os.path.exists(os.path.join(REPO, "cards/web/med", f"{c['id']}.jpg")) else None)),
    }


def build_reading(question):
    _, _, by_realm = load_deck()
    picks, sel_mode = select_cards(question, by_realm, LLM_SINGLETON)
    located = locate_spread(picks)
    reading, weave_mode = weave(question, picks, LLM_SINGLETON, located)
    payload = {
        "question": question,
        "cards": {r: card_payload(picks[r], located[r]) for r in ("roots", "trunk", "branches")},
        "reading": reading["reading"],
        "adventure": reading["adventure"],
        "map": COMPASS_ROSE,
        "directions": directions_lines(picks, located),
        "modes": {"select": sel_mode, "weave": weave_mode},
    }
    LAST.clear()
    LAST.update({"payload": payload, "picks": picks, "located": located})
    return payload


REALM_ORDER = {"shell": 0, "roots": 1, "trunk": 2, "branches": 3}


def all_cards_payload():
    _, cards, _ = load_deck()
    ordered = sorted(cards, key=lambda c: (REALM_ORDER[c["realm"]], c["number"]))
    return [card_payload(c, locate(c)) for c in ordered]


DOWNLOADS = {
    "booklet.pdf": ("print/booklet.pdf", "application/pdf"),
    "proof.pdf": ("print/proof.pdf", "application/pdf"),
    "contact-sheet.png": ("cards/contact-sheet.png", "image/png"),
}


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 (connection closes per request) + threading = robust; no keep-alive edge cases.
    timeout = 20  # cap a slow client's request read so a thread can't hang forever

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            # never cache HTML/API (so fixes land on refresh); images/pdf may cache
            if ctype.startswith("text/html") or ctype == "application/json":
                self.send_header("Cache-Control", "no-store")
            else:
                self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_file(self, relpath, ctype):
        try:
            with open(os.path.join(REPO, relpath), "rb") as f:
                return self._send(200, f.read(), ctype)
        except FileNotFoundError:
            return self._send(404, {"error": f"{relpath} missing"})

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/site.html"):
            return self._serve_file("app/web/site.html", "text/html; charset=utf-8")
        if path in ("/oracle", "/oracle.html", "/app"):
            return self._serve_file("app/web/index.html", "text/html; charset=utf-8")
        if path == "/api/deck":
            data, cards, _ = load_deck()
            return self._send(200, {"title": data["deck"]["title"],
                                    "subtitle": data["deck"]["subtitle"],
                                    "count": len(cards),
                                    "llm": LLM_SINGLETON.available()})
        if path == "/api/cards":
            return self._send(200, all_cards_payload())
        if path.startswith("/thumb/") or path.startswith("/med/"):
            sub = "thumb" if path.startswith("/thumb/") else "med"
            name = os.path.basename(path)
            if WEBIMG_RE.match(name):
                return self._serve_file(f"cards/web/{sub}/{name}", "image/jpeg")
            return self._send(404, {"error": "no such image"})
        if path == "/art/back.png":
            return self._serve_file("cards/back.png", "image/png")
        if path.startswith("/art/"):
            name = os.path.basename(path)
            if ART_RE.match(name):
                fp = os.path.join(ART, name)
                if os.path.exists(fp):
                    with open(fp, "rb") as f:
                        return self._send(200, f.read(), "image/png")
            return self._send(404, {"error": "no such card art"})
        if path.startswith("/download/"):
            name = os.path.basename(path)
            if name in DOWNLOADS:
                rel, ctype = DOWNLOADS[name]
                return self._serve_file(rel, ctype)
            return self._send(404, {"error": "no such download"})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        if path == "/api/reading":
            try:
                q = (json.loads(raw or b"{}").get("question") or "").strip()
            except Exception:
                q = ""
            if not q:
                return self._send(400, {"error": "no question"})
            try:
                return self._send(200, build_reading(q))
            except Exception as e:
                return self._send(500, {"error": str(e)})
        if path == "/api/print":
            if not LAST:
                return self._send(400, {"error": "no reading to print yet"})
            text = printer.format_receipt(LAST["payload"], LAST["picks"], LAST["located"])
            result = printer.print_or_preview(text)
            result["receipt"] = text
            return self._send(200, result)
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass  # quiet


class OracleServer(ThreadingHTTPServer):
    request_queue_size = 128   # larger listen backlog so bursts of parallel connections aren't dropped
    daemon_threads = True
    allow_reuse_address = True


def main():
    print(f"🐢  Terrible Turtle Oracle at http://localhost:{PORT}")
    print(f"    LLM (Ollama {LLM_SINGLETON.model}): {'available' if LLM_SINGLETON.available() else 'OFF — using offline weave'}")
    OracleServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
