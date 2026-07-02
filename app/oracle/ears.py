"""Local ears: transcribe the seeker's voice with whisper.cpp — fully offline.

Needs `brew install whisper-cpp ffmpeg` and a ggml model at app/models/ggml-base.en.bin
(or WHISPER_MODEL env). If anything is missing, transcribe() returns None and the kiosk
falls back to typed input.
"""
import os
import shutil
import subprocess
import tempfile

from .deck import REPO

MODEL = os.environ.get("WHISPER_MODEL",
                       os.path.join(REPO, "app", "models", "ggml-base.en.bin"))


def _bin(name):
    """Find a binary even under a LaunchAgent's bare PATH."""
    found = shutil.which(name)
    if found:
        return found
    for p in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if os.path.exists(p):
            return p
    return None


def available():
    return bool(_bin("whisper-cli")) and bool(_bin("ffmpeg")) and os.path.exists(MODEL)


def transcribe(audio_bytes, suffix=".webm"):
    """Audio bytes (any container ffmpeg knows) -> text, or None."""
    if not audio_bytes or not available():
        return None
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in" + suffix)
        wav = os.path.join(td, "in.wav")
        with open(src, "wb") as f:
            f.write(audio_bytes)
        try:
            subprocess.run([_bin("ffmpeg"), "-y", "-loglevel", "error",
                            "-i", src, "-ar", "16000", "-ac", "1", wav],
                           check=True, timeout=30)
            out = subprocess.run([_bin("whisper-cli"), "-m", MODEL, "-f", wav, "-nt", "-np"],
                                 capture_output=True, text=True, timeout=90, check=True)
        except Exception:
            return None
        text = " ".join(out.stdout.split()).strip()
        return text or None
