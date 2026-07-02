"""The Tale-Book: the shell's persistent memory of seekers, sealed quests, and told tales.

One JSONL file, append-only, survives reboots. Records:
  {"type":"quest", "ts", "name", "title", "shares":[...], "cards":[ids], "quest":{...}}
  {"type":"tale",  "ts", "name", "tale", "quest_title"}
"""
import json
import os
import re
import time

from .deck import REPO

LOG = os.path.join(REPO, "app", "state", "talebook.jsonl")


def _norm(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def append(rec):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    rec = dict(rec, ts=time.time(), when=time.strftime("%a %b %d %H:%M"))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load():
    if not os.path.exists(LOG):
        return []
    out = []
    with open(LOG, encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def find(name):
    """All records for a seeker, oldest first."""
    n = _norm(name)
    return [r for r in load() if n and _norm(r.get("name")) == n] if n else []


def last_quest(name):
    qs = [r for r in find(name) if r.get("type") == "quest"]
    return qs[-1] if qs else None


def last_tale(name):
    ts = [r for r in find(name) if r.get("type") == "tale"]
    return ts[-1] if ts else None


def counts():
    recs = load()
    quests = [r for r in recs if r.get("type") == "quest"]
    tales = [r for r in recs if r.get("type") == "tale"]
    return {
        "sealed": len(quests),
        "tales": len(tales),
        "recent_titles": [q.get("title", "") for q in quests[-5:]][::-1],
    }
