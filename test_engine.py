"""Smoke test for engine.py: start the daemon, synthesize twice, watch it exit when idle.

    python test_engine.py

Needs `kokoro`, `numpy` and `soundfile` importable by this interpreter.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PORT = "51236"
IDLE_SECONDS = "8"
HERE = Path(__file__).resolve().parent
OUT = HERE / "test_out.wav"


def request(path, payload=None, timeout=300):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read() or b"{}")


def say(text):
    started = time.monotonic()
    request("/say", {"text": text, "voice": "af_heart", "output": str(OUT)})
    return time.monotonic() - started


env = {**os.environ, "KOKORO_PORT": PORT, "KOKORO_IDLE_SECONDS": IDLE_SECONDS}
daemon = subprocess.Popen([sys.executable, str(HERE / "engine.py"), "--serve"], env=env)
try:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        time.sleep(0.5)
        try:
            request("/health", timeout=2)
            break
        except Exception:
            continue
    else:
        raise SystemExit("daemon did not answer /health within 60s")

    cold = say("First call, the model still has to load.")
    assert OUT.exists() and OUT.stat().st_size > 1000, "no audio was written"
    warm = say("Second call, the model is already in memory.")
    print(f"cold {cold:.1f}s -> warm {warm:.1f}s")
    assert warm < cold, "the warm call should be faster than the cold one"

    time.sleep(float(IDLE_SECONDS) + 12)
    try:
        request("/health", timeout=2)
    except Exception:
        print("daemon exited on its own after the idle timeout")
    else:
        raise SystemExit("daemon stayed up past the idle timeout")
finally:
    daemon.terminate()

print("OK")
