#!/usr/bin/env python3
"""A/B whisper.cpp: small.en vs medium.en on real speech.

    python3 tools/bench_whisper.py \
      --cli whisper-cli \
      --small /path/ggml-small.en.bin \
      --medium /path/ggml-medium.en.bin \
      --wav samples/jfk.wav --expect "And so my fellow Americans..." \
      --wav samples/seeker.wav --expect "first burn, came with my camp..."

Times wall-clock of whisper-cli (decode only; model load is in the same
process so first call of each model includes load — we run each wav
twice and report the second as warm). Prints WER-lite vs --expect.

Does not change production. Spark path:
  WHISPER_MODEL=.../ggml-small.en.bin  (current)
  whisper-cli is the CPU build until a CUDA rebuild.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time


def words(s):
    return re.findall(r"[a-z0-9']+", (s or "").lower())


def wer(ref, hyp):
    """Classic word error rate. 0 = perfect."""
    r, h = words(ref), words(hyp)
    if not r:
        return 0.0 if not h else 1.0
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + (0 if r[i - 1] == h[j - 1] else 1),
            )
    return dp[-1][-1] / len(r)


def run_once(cli, model, wav, timeout=90):
    t0 = time.monotonic()
    try:
        out = subprocess.run(
            [cli, "-m", model, "-f", wav, "-nt", "-np"],
            capture_output=True, text=True, timeout=timeout, check=True,
        )
    except subprocess.CalledProcessError as e:
        return {"error": (e.stderr or e.stdout or str(e))[:300],
                "wall": time.monotonic() - t0, "text": ""}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}",
                "wall": time.monotonic() - t0, "text": ""}
    text = " ".join(out.stdout.split()).strip()
    return {"error": None, "wall": time.monotonic() - t0, "text": text}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cli", default=shutil.which("whisper-cli") or "whisper-cli")
    ap.add_argument("--small", required=True)
    ap.add_argument("--medium", required=True)
    ap.add_argument("--wav", action="append", default=[],
                    help="wav path (repeatable). Pair with --expect in the same order.")
    ap.add_argument("--expect", action="append", default=[],
                    help="reference transcript for the corresponding --wav")
    ap.add_argument("--timeout", type=float, default=90)
    args = ap.parse_args()
    if not args.wav:
        sys.exit("pass at least one --wav")
    if args.expect and len(args.expect) != len(args.wav):
        sys.exit("--expect count must match --wav count")
    for p in (args.cli, args.small, args.medium, *args.wav):
        if not os.path.exists(p):
            sys.exit(f"missing: {p}")

    print(f"cli={args.cli}")
    print(f"small={args.small}  {os.path.getsize(args.small)/1e6:.0f} MB")
    print(f"medium={args.medium}  {os.path.getsize(args.medium)/1e6:.0f} MB")
    hdr = f"{'model':<10} {'wav':<16} {'pass':<6} {'wall':>7} {'WER':>6} text"
    print(hdr)
    print("-" * 90)

    rows = []
    for label, model in (("small.en", args.small), ("medium.en", args.medium)):
        for i, wav in enumerate(args.wav):
            name = os.path.basename(wav)
            cold = run_once(args.cli, model, wav, args.timeout)
            warm = run_once(args.cli, model, wav, args.timeout)
            ref = args.expect[i] if args.expect else ""
            w = wer(ref, warm["text"]) if ref else None
            print(f"{label:<10} {name:<16} {'cold':<6} {cold['wall']:7.2f} "
                  f"{'  n/a' if w is None else f'{w:6.2f}'} "
                  f"{(cold['error'] or cold['text'])[:80]}")
            print(f"{label:<10} {name:<16} {'warm':<6} {warm['wall']:7.2f} "
                  f"{'  n/a' if w is None else f'{w:6.2f}'} "
                  f"{(warm['error'] or warm['text'])[:80]}")
            rows.append({"model": label, "wav": name, "cold": cold["wall"],
                         "warm": warm["wall"], "wer": w,
                         "text": warm["text"], "error": warm["error"]})

    print("\nRhythm: a seeker speaks ~8–12s; transcribe should stay well under "
          "the kiosk's next beat (a couple of seconds of '…' is fine; 8s+ feels broken).")
    print(json_summary(rows))
    return 0 if all(not r["error"] for r in rows) else 1


def json_summary(rows):
    import json
    return json.dumps(rows, indent=2)


if __name__ == "__main__":
    sys.exit(main())
