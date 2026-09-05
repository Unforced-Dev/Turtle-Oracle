#!/usr/bin/env python3
"""Focused offline checks for the optional Kokoro engine and /api/speak contract."""
import json
import os
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from oracle import server, voice as voicemod
from oracle.voice import KokoroVoice, VoiceUnavailable


class FakePipeline:
    def __init__(self):
        self.calls = []

    def __call__(self, text, **kwargs):
        self.calls.append((text, kwargs))
        yield (text, "phonemes", [0.1, 0.2])


def unit_checks():
    engine = KokoroVoice(backend="kokoro", voice="bm_george", speed=.86, cache_size=2)
    engine._pipeline = FakePipeline()
    engine._voice_source = "bm_george"
    engine._encode_wav = lambda chunks: b"RIFF-fake-wav-" + bytes([len(chunks[0])])
    first = engine.synthesize("  Slow   is smooth. ")
    second = engine.synthesize("Slow is smooth.")
    assert first == second
    assert len(engine._pipeline.calls) == 1, "normalized duplicate must hit the line cache"
    assert engine._pipeline.calls[0][1]["voice"] == "bm_george"
    assert engine._pipeline.calls[0][1]["speed"] == .86

    disabled = KokoroVoice(backend="browser")
    try:
        disabled.synthesize("No server voice.")
        raise AssertionError("disabled engine synthesized")
    except VoiceUnavailable:
        pass
    for bad in ("", "x" * (voicemod.MAX_SPEECH + 1)):
        try:
            engine.synthesize(bad)
            raise AssertionError("invalid speech text accepted")
        except ValueError:
            pass
    # a whole reading now goes in ONE request; the old per-sentence cap was what forced
    # eight round trips of half a megabyte each over camp wifi
    assert voicemod.MAX_SPEECH >= 1600, "a reading must fit in one call"


class FakeRun:
    """Stands in for subprocess.run so the encoder path is exercised with no ffmpeg."""

    def __init__(self, out=b"OggS-fake", code=0):
        self.out, self.code, self.calls = out, code, []

    def __call__(self, argv, input=None, capture_output=None, timeout=None):
        self.calls.append((argv, input, timeout))
        return type("P", (), {"returncode": self.code, "stdout": self.out, "stderr": b""})()


def encoder_checks():
    """Opus when the box has ffmpeg, WAV when it does not — and never an exception."""
    real_ffmpeg, real_run = voicemod.FFMPEG, voicemod.subprocess.run
    try:
        voicemod.FFMPEG = None
        assert voicemod.to_opus(b"RIFF-wav") is None, "no ffmpeg must fall back, not raise"

        voicemod.FFMPEG = "/usr/bin/ffmpeg"
        run = FakeRun()
        voicemod.subprocess.run = run
        assert voicemod.to_opus(b"RIFF-wav") == b"OggS-fake"
        argv, sent, timeout = run.calls[0]
        assert argv[0] == "/usr/bin/ffmpeg" and sent == b"RIFF-wav"
        assert "libopus" in argv and "32k" in argv and "ogg" in argv, argv
        assert timeout and timeout <= 30, "a stuck encoder must not hold a request open"

        voicemod.subprocess.run = FakeRun(out=b"", code=1)
        assert voicemod.to_opus(b"RIFF-wav") is None, "a failed encode falls back to WAV"

        def boom(*a, **k):
            raise OSError("no such binary")
        voicemod.subprocess.run = boom
        assert voicemod.to_opus(b"RIFF-wav") is None, "a broken encoder must not raise"

        # end to end through the engine: the mime follows what was actually produced
        voicemod.subprocess.run = FakeRun()
        engine = KokoroVoice(backend="kokoro", voice="bm_george", cache_size=2)
        engine._pipeline = FakePipeline()
        engine._voice_source = "bm_george"
        engine._encode_wav = lambda chunks: b"RIFF-fake"
        assert engine.render("Slow is smooth.") == (b"OggS-fake", "audio/ogg")
        assert engine.render("Slow is smooth.") == (b"OggS-fake", "audio/ogg"), "cached"
        assert len(engine._pipeline.calls) == 1, "the cache holds the ENCODED bytes"

        voicemod.FFMPEG = None
        engine2 = KokoroVoice(backend="kokoro", voice="bm_george", cache_size=2)
        engine2._pipeline = FakePipeline()
        engine2._voice_source = "bm_george"
        engine2._encode_wav = lambda chunks: b"RIFF-fake"
        assert engine2.render("Slow is smooth.") == (b"RIFF-fake", "audio/wav")
    finally:
        voicemod.FFMPEG, voicemod.subprocess.run = real_ffmpeg, real_run


class FakeVoice:
    voice = "bm_george"

    def status(self):
        return {"backend": "kokoro", "ready": True, "voice": self.voice, "device": "cpu"}

    def synthesize(self, text):
        if text == "fail":
            raise VoiceUnavailable("test outage")
        if len(text) > 600:
            raise ValueError("speech line is too long")
        return b"RIFF-test-audio"


def post(base, text):
    req = Request(base + "/api/speak", method="POST",
                  headers={"Content-Type": "application/json"},
                  data=json.dumps({"text": text}).encode())
    return urlopen(req, timeout=3)


def endpoint_checks():
    original = server.VOICE_SINGLETON
    server.VOICE_SINGLETON = FakeVoice()
    httpd = server.OracleServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    try:
        with post(base, "The Turtle speaks.") as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "audio/wav"
            assert response.headers["Cache-Control"] == "no-store"
            assert response.read() == b"RIFF-test-audio"
        for text, code in (("", 400), ("x" * 601, 400), ("fail", 503)):
            try:
                post(base, text)
                raise AssertionError(f"{text[:8]!r} should return {code}")
            except HTTPError as exc:
                assert exc.code == code
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        server.VOICE_SINGLETON = original


class OggVoice(FakeVoice):
    def render(self, text):
        return b"OggS-test-audio", "audio/ogg"


def container_checks():
    """The wire: an engine that encodes is served as Ogg."""
    original = server.VOICE_SINGLETON
    server.VOICE_SINGLETON = OggVoice()
    httpd = server.OracleServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    try:
        with post(base, "The Turtle speaks.") as response:
            assert response.headers.get_content_type() == "audio/ogg"
            assert response.headers["Cache-Control"] == "no-store", "a reading is not cached"
            assert response.read() == b"OggS-test-audio"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        server.VOICE_SINGLETON = original


def main():
    unit_checks()
    encoder_checks()
    endpoint_checks()
    container_checks()
    print("kokoro voice: cache, opus encoding, validation, audio contract "
          "and graceful failure passed")


if __name__ == "__main__":
    main()
