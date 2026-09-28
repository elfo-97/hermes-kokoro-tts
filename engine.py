"""Kokoro-82M daemon: keeps the model in RAM and serves /say, /health and /shutdown.

Needs a Python with `kokoro`, `numpy` and `soundfile` installed:

    python engine.py --serve

Env: KOKORO_PORT (51235), KOKORO_IDLE_SECONDS (300). Exits on its own after
KOKORO_IDLE_SECONDS with no requests, and never in the middle of a synthesis.
"""
import argparse
import json
import os
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 24000
PORT = int(os.environ.get("KOKORO_PORT", "51235"))
IDLE_SECONDS = float(os.environ.get("KOKORO_IDLE_SECONDS", "300"))

_PIPES: dict = {}
# One lock serializes synthesis, the pipeline is not thread safe. Per-voice locks if concurrent
# requests ever matter.
_LOCK = threading.Lock()


def synth(text: str, voice: str, speed: float = 1.0) -> np.ndarray:
    """Synthesize with the pipeline for the voice's language (first letter of the id),
    reusing an already-loaded model whenever possible."""
    from kokoro import KPipeline  # late import: the daemon binds its port before loading the model
    with _LOCK:
        pipe = _PIPES.get(voice[0])
        if pipe is None:
            pipe = _PIPES[voice[0]] = KPipeline(lang_code=voice[0])
        chunks = [audio.numpy() for _, _, audio in pipe(text, voice=voice, speed=speed)]
    return np.concatenate(chunks)


def serve() -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    state = {"last": time.monotonic(), "busy": 0}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass  # keep the child's stderr clean

        def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict):
            self._send(code, json.dumps(payload).encode(), "application/json")

        def do_GET(self):
            if self.path != "/health":
                return self._send(404, b"nope")
            self._json(200, {"ok": True})

        def do_POST(self):
            if self.path == "/shutdown":
                self._json(200, {"ok": True})
                threading.Thread(target=lambda: (time.sleep(0.2), os._exit(0)), daemon=True).start()
                return
            if self.path != "/say":
                return self._send(404, b"nope")
            state["last"] = time.monotonic()
            state["busy"] += 1
            try:
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
                audio = synth(req["text"], req.get("voice") or "af_heart", float(req.get("speed") or 1.0))
                out = Path(req["output"])
                out.parent.mkdir(parents=True, exist_ok=True)
                sf.write(out, audio, SAMPLE_RATE)
                self._json(200, {"path": str(out), "seconds": len(audio) / SAMPLE_RATE})
            except Exception as exc:
                self._send(500, str(exc).encode())
            finally:
                state["last"] = time.monotonic()  # a long synthesis is not idleness
                state["busy"] -= 1

    def watchdog() -> None:
        while True:
            time.sleep(min(30.0, IDLE_SECONDS))
            if not state["busy"] and time.monotonic() - state["last"] > IDLE_SECONDS:
                os._exit(0)

    threading.Thread(target=watchdog, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kokoro-82M daemon")
    parser.add_argument("--serve", action="store_true", help="run the daemon (only mode)")
    parser.parse_args()
    serve()
