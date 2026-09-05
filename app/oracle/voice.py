"""Optional local Kokoro voice for the Turtle.

The core oracle stays dependency-free.  Kokoro and its audio stack are imported only when
ORACLE_TTS_BACKEND=kokoro, and every failure is surfaced as VoiceUnavailable so the kiosk can
fall back to the tablet's browser voice.
"""
from collections import OrderedDict
from io import BytesIO
import os
import re
import shutil
import subprocess
import threading
import time


SAMPLE_RATE = 24_000

# WHAT THE WIRE COSTS. Kokoro's PCM is 48 KB per spoken second: a forty-word line measured
# 602 KB on the Spark, and the kiosk asked for one of those PER SENTENCE. Over camp 2.4 GHz
# with half a second of round trip that is where the pauses came from, and every timeout
# dropped through to the tablet's own browser voice — which is the voice the camp lead
# heard and did not like. Opus at 32 kbit/s is 4 KB per second, forty times smaller, and
# Android Chrome plays Ogg/Opus natively.
#
# ffmpeg is on the Spark and is NOT a dependency of this repo: when it is absent (the
# laptop, CI) the WAV path is unchanged and everything still works, only fatter.
FFMPEG = shutil.which("ffmpeg")
OPUS_ARGS = ["-loglevel", "error", "-f", "wav", "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "32k", "-application", "voip", "-f", "ogg", "pipe:1"]
ENCODE_TIMEOUT = 10

# A whole reading in ONE request. The old 600 was a per-sentence cap and it is what forced
# eight round trips per reading; kokoro is asked sentence by sentence internally now and the
# pieces are concatenated before a single encode.
MAX_SPEECH = int(os.environ.get("ORACLE_TTS_MAX_CHARS", "1600"))
# Kokoro synthesizes each sentence cold, so butting them together sounds like a splice.
GAP_SECONDS = 0.18

# THE TURTLE'S INTERJECTIONS ARE FOR THE EYE, NOT THE EAR. "Mm." and "Hm." are how the
# Turtle's written lines breathe, and they are all over the copy — but a TTS engine reads a
# lone "Mm." as a flat two-letter syllable with no context around it, and the kiosk speaks
# one sentence per request, so it lands as a bare grunt with a pause on either side. Strip
# them from what goes to the voice; the screen text is never touched.
INTERJECTION = re.compile(r"^[\s\"'“”(\[]*(?:mm+|hm+|ah+|mhm+|hmm+|uh+)[\s.,!?…\-—]*[\s\"'“”)\]]*$", re.I)


def is_interjection(text):
    """True when a line is nothing but a spoken breath — never send it to the voice."""
    return bool(INTERJECTION.match(text or ""))


def strip_interjections(text):
    """Drop standalone interjection sentences from a line bound for the voice."""
    parts = [p for p in re.split(r"(?<=[.!?…])\s+", (text or "").strip()) if p.strip()]
    kept = [p for p in parts if not is_interjection(p)]
    return " ".join(kept).strip()


class VoiceUnavailable(RuntimeError):
    pass


def to_opus(wav):
    """WAV bytes -> Ogg/Opus bytes, or None when this box has no ffmpeg (or it failed).

    Never raises: a missing or broken encoder must degrade to the fat-but-correct WAV, not
    take the Turtle's voice away entirely.
    """
    if not FFMPEG or not wav:
        return None
    try:
        done = subprocess.run([FFMPEG] + OPUS_ARGS, input=wav, capture_output=True,
                              timeout=ENCODE_TIMEOUT)
    except Exception:
        return None
    if done.returncode != 0 or not done.stdout:
        return None
    return done.stdout


class KokoroVoice:
    def __init__(self, backend=None, voice=None, speed=None, device=None, cache_size=None):
        self.backend = (backend or os.environ.get("ORACLE_TTS_BACKEND", "browser")).lower()
        self.voice = voice or os.environ.get("ORACLE_TTS_VOICE", "bm_george")
        self.lang = self.voice[0] if self.voice and self.voice[0] in "ab" else "b"
        try:
            self.speed = float(speed if speed is not None else
                               os.environ.get("ORACLE_TTS_SPEED", "0.86"))
        except (TypeError, ValueError):
            self.speed = 0.86
        self.device = device if device is not None else os.environ.get("ORACLE_TTS_DEVICE", "cpu")
        self.model_dir = os.environ.get("ORACLE_TTS_MODEL_DIR", "").strip()
        try:
            self.cache_size = max(0, int(cache_size if cache_size is not None else
                                         os.environ.get("ORACLE_TTS_CACHE_LINES", "192")))
        except (TypeError, ValueError):
            self.cache_size = 192
        self._pipeline = None
        self._voice_source = self.voice
        self._cache = OrderedDict()
        self._lock = threading.RLock()
        self._retry_at = 0.0
        self.last_error = None

    @property
    def enabled(self):
        return self.backend == "kokoro"

    def status(self):
        return {
            "backend": "kokoro" if self.enabled else "browser",
            "ready": bool(self._pipeline) if self.enabled else False,
            "voice": self.voice if self.enabled else None,
            "device": self.device if self.enabled else None,
            "local_model": bool(self.model_dir) if self.enabled else False,
        }

    def _load(self):
        if not self.enabled:
            raise VoiceUnavailable("server voice is disabled")
        if self._pipeline is not None:
            return self._pipeline
        if time.monotonic() < self._retry_at:
            raise VoiceUnavailable("server voice is cooling down after a load failure")
        try:
            from kokoro import KModel, KPipeline
            kwargs = {"lang_code": self.lang, "repo_id": "hexgrad/Kokoro-82M"}
            if self.model_dir:
                config = os.path.join(self.model_dir, "config.json")
                weights = os.path.join(self.model_dir, "kokoro-v1_0.pth")
                self._voice_source = os.path.join(self.model_dir, "voices", self.voice + ".pt")
                for path in (config, weights, self._voice_source):
                    if not os.path.isfile(path):
                        raise FileNotFoundError(path)
                model = KModel(config=config, model=weights)
                if self.device:
                    model = model.to(self.device)
                kwargs["model"] = model.eval()
            elif self.device:
                kwargs["device"] = self.device
            self._pipeline = KPipeline(**kwargs)
            self.last_error = None
            return self._pipeline
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self._retry_at = time.monotonic() + 30
            raise VoiceUnavailable("Kokoro could not load") from exc

    @staticmethod
    def _clean(text):
        return " ".join((text or "").split())

    @staticmethod
    def _encode_wav(chunks):
        import numpy as np
        import soundfile as sf

        if len(chunks) > 1:
            gap = np.zeros(int(GAP_SECONDS * SAMPLE_RATE), dtype=np.asarray(chunks[0]).dtype)
            joined = []
            for i, c in enumerate(chunks):
                if i:
                    joined.append(gap)
                joined.append(np.asarray(c))
            audio = np.concatenate(joined)
        else:
            audio = chunks[0]
        out = BytesIO()
        sf.write(out, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return out.getvalue()

    def render(self, text):
        """(bytes, mime) for one whole utterance. Ogg/Opus where ffmpeg exists, WAV where
        it does not. The cache holds the ENCODED bytes, so a repeated line costs nothing."""
        text = self._clean(text)
        if not text:
            raise ValueError("no text")
        if len(text) > MAX_SPEECH:
            raise ValueError("speech line is too long")
        key = (self.voice, round(self.speed, 3), text)
        with self._lock:
            cached = self._cache.pop(key, None)
            if cached is not None:
                self._cache[key] = cached
                return cached
            pipeline = self._load()
            try:
                chunks = []
                # sentence by sentence, because a paragraph handed to kokoro whole runs past
                # its token window and comes back quietly truncated; the pieces are joined as
                # PCM here and encoded once
                for result in pipeline(text, voice=self._voice_source, speed=self.speed,
                                       split_pattern=r"(?<=[.!?\u2026])\s+"):
                    audio = result.audio if hasattr(result, "audio") else result[2]
                    if audio is not None and len(audio):
                        chunks.append(audio)
                if not chunks:
                    raise RuntimeError("Kokoro returned no audio")
                wav = self._encode_wav(chunks)
            except VoiceUnavailable:
                raise
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                raise VoiceUnavailable("Kokoro could not synthesize this line") from exc
            opus = to_opus(wav)
            out = (opus, "audio/ogg") if opus else (wav, "audio/wav")
            if self.cache_size:
                self._cache[key] = out
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
            return out

    def synthesize(self, text):
        """The encoded bytes alone — kept for callers that do not care about the container."""
        return self.render(text)[0]

    def warm(self):
        if self.enabled:
            self.render("The Turtle wakes.")
