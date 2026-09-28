"""Kokoro-82M as a Hermes TTS provider: CPU-only, offline, warm daemon, language picker.

Settings live in the plugin's own settings block, declared by `config_schema` in plugin.yaml and
stored under `plugins.entries.kokoro.settings` in config.yaml:

    language: en-us        # en-us | en-gb | es | fr | hi | it | ja | pt-br | zh
    voice: ""              # an explicit id (e.g. pm_alex) overrides `language`
    python: ""             # interpreter with kokoro installed (empty = the Hermes one)
    port: 51235
    idle_seconds: 300      # the daemon exits on its own after this much idle time

The desktop panel (`dashboard/plugin_api.py`) and the Plugins settings form both write there, and
`hermes tools` lists the 54 voices with the language of each one.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.tts_provider import TTSProvider

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "engine.py"

# Kokoro v1.0 voices, grouped by language: the first letter of an id is the language
# and the second one the gender (f/m).
VOICES: Dict[str, List[str]] = {
    "en-us": ["af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore", "af_nicole",
              "af_nova", "af_river", "af_sarah", "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir",
              "am_liam", "am_michael", "am_onyx", "am_puck", "am_santa"],
    "en-gb": ["bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis"],
    "es": ["ef_dora", "em_alex", "em_santa"],
    "fr": ["ff_siwis"],
    "hi": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
    "it": ["if_sara", "im_nicola"],
    "ja": ["jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo"],
    "pt-br": ["pf_dora", "pm_alex", "pm_santa"],
    "zh": ["zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi", "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"],
}
DEFAULT_LANGUAGE = "en-us"
DEFAULT_PORT = 51235
DEFAULT_IDLE_SECONDS = 300
# Everything the daemon needs to find its interpreter, the Hugging Face cache and tmp.
_KEEP_ENV = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "HOME")

# ctx.get_config() reads this manifest's config_schema keys, at plugins.entries.<id>.settings.*.
_CTX: Any = None
_SETTING_KEYS = ("language", "voice", "python", "port", "idle_seconds")


def _section() -> Dict[str, Any]:
    """Provider settings for the profile in use. A broken config never breaks synthesis."""
    section: Dict[str, Any] = {}
    if _CTX is not None:
        for key in _SETTING_KEYS:
            try:
                value = _CTX.get_config(key)
            except Exception as exc:
                logger.debug("plugin setting %s unreadable: %s", key, exc)
                continue
            if value not in (None, ""):
                section[key] = value
    return section


def _json_request(port: int, path: str, payload: Optional[dict] = None, timeout: float = 600.0) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


class KokoroProvider(TTSProvider):
    """Writes WAV through a local daemon, starting one when it is not running."""

    @property
    def name(self) -> str:
        return "kokoro"

    @property
    def display_name(self) -> str:
        return "Kokoro-82M (local, CPU)"

    def get_setup_schema(self) -> Dict[str, Any]:
        return {"name": self.display_name, "badge": "local", "env_vars": [],
                "tag": "82M params · offline · CPU"}

    def is_available(self) -> bool:
        # Importing kokoro here would pull torch on every picker repaint, so only the file is checked.
        return self._python(_section()).exists()

    def list_voices(self) -> List[Dict[str, Any]]:
        return [{"id": voice, "display": f"{voice} ({language})", "language": language,
                 "gender": "female" if voice[1] == "f" else "male"}
                for language, voices in VOICES.items() for voice in voices]

    def voices_by_language(self) -> Dict[str, List[str]]:
        """Voice ids per language, for surfaces that offer a language picker."""
        return {language: list(voices) for language, voices in VOICES.items()}

    def default_voice(self) -> Optional[str]:
        """First voice of the configured language, falling back to en-us."""
        section = _section()
        language = str(section.get("language") or DEFAULT_LANGUAGE).lower()
        return VOICES.get(language, VOICES[DEFAULT_LANGUAGE])[0]

    def synthesize(self, text: str, output_path: str, *, voice: Optional[str] = None,
                   model: Optional[str] = None, speed: Optional[float] = None,
                   format: str = "mp3", **extra: Any) -> str:
        section = _section()
        chosen = self._resolve_voice(voice, section)
        speed = float(speed if speed is not None else 1.0)
        # The engine writes WAV, so the path has to carry the matching extension.
        out = Path(output_path)
        if out.suffix.lower() != ".wav":
            out = out.with_suffix(".wav")
        self._request("/say", {"text": text, "voice": chosen, "speed": speed, "output": str(out)}, section)
        return str(out)

    def warm(self) -> None:
        """Speech output was enabled: have the daemon ready for the first reply."""
        section = _section()
        try:
            self._health(self._port(section))
        except Exception:
            try:
                self._ensure_daemon(section)
            except Exception as exc:
                logger.debug("kokoro warm failed: %s", exc)

    def release(self) -> None:
        """Last speech lease released: drop the daemon instead of waiting for the idle timeout."""
        try:
            _json_request(self._port(_section()), "/shutdown", {}, timeout=5)
        except Exception as exc:
            logger.debug("kokoro release failed: %s", exc)

    def _resolve_voice(self, voice: Optional[str], section: Dict[str, Any]) -> str:
        """The caller's voice, else the Voice setting, else the first voice of the Language setting."""
        for candidate in (voice, section.get("voice")):
            if isinstance(candidate, str) and candidate.strip():
                key = candidate.strip()
                if key in {v for voices in VOICES.values() for v in voices}:
                    return key
                logger.warning("kokoro: unknown voice %r, using the configured language", key)
                break
        return self.default_voice() or VOICES[DEFAULT_LANGUAGE][0]

    def _port(self, section: Dict[str, Any]) -> int:
        try:
            return int(section.get("port") or DEFAULT_PORT)
        except (TypeError, ValueError):
            return DEFAULT_PORT

    def _python(self, section: Dict[str, Any]) -> Path:
        configured = str(section.get("python") or "").strip()
        return Path(configured) if configured else Path(sys.executable)

    def _request(self, path: str, payload: dict, section: Dict[str, Any]) -> dict:
        port = self._port(section)
        try:
            return _json_request(port, path, payload)
        except Exception:
            pass
        self._ensure_daemon(section)
        return _json_request(port, path, payload)

    def _health(self, port: int) -> dict:
        return _json_request(port, "/health", timeout=2)

    def _ensure_daemon(self, section: Dict[str, Any]) -> None:
        """Spawn the detached daemon and wait up to 60s for it to answer."""
        python = self._python(section)
        if not python.exists():
            raise RuntimeError(f"Kokoro: interpreter not found at {python} (set the plugin's "
                               "Interpreter setting to a Python that has `kokoro` and `soundfile`)")
        exe = python
        if os.name == "nt" and (python.parent / "pythonw.exe").exists():
            exe = python.parent / "pythonw.exe"
        env = {key: value for key, value in os.environ.items() if key in _KEEP_ENV}
        env["KOKORO_PORT"] = str(self._port(section))
        env["KOKORO_IDLE_SECONDS"] = str(section.get("idle_seconds") or DEFAULT_IDLE_SECONDS)
        subprocess.Popen([str(exe), str(ENGINE), "--serve"], cwd=str(HERE), env=env, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                         | getattr(subprocess, "CREATE_NO_WINDOW", 0))
        port = self._port(section)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            time.sleep(0.5)
            try:
                self._health(port)
                return
            except Exception:
                continue
        raise RuntimeError(f"Kokoro: daemon did not answer on 127.0.0.1:{port} (run "
                           f"`{python} {ENGINE} --serve` by hand to see the error)")


def register(ctx) -> None:
    global _CTX
    _CTX = ctx
    ctx.register_tts_provider(KokoroProvider())
