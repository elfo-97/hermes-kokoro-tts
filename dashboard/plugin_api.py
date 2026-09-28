"""Kokoro TTS plugin backend, mounted at /api/plugins/kokoro/.

The desktop panel is the only consumer: it reads the voice catalog and writes the language/voice
choice through the same writer the Plugins settings form and `ctx.set_config` use
(`plugins.entries.kokoro.settings.*`), so every surface agrees on where a setting lives.

The catalog is read from the registered TTS provider, so the 54 voices live in exactly one place.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from hermes_cli.plugins_settings import plugin_settings_fields, save_plugin_settings

router = APIRouter()

PLUGIN_ID = "kokoro"
PLUGIN_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LANGUAGE = "en-us"
DEFAULT_IDLE_SECONDS = 300


def _catalog() -> Dict[str, List[str]]:
    """Voices per language, straight from the provider this plugin registers."""
    try:
        from agent.tts_registry import get_provider
        from hermes_cli.plugins import _ensure_plugins_discovered
        _ensure_plugins_discovered()
        provider = get_provider(PLUGIN_ID)
    except Exception:
        return {}
    return dict(provider.voices_by_language()) if provider is not None else {}


def _current() -> Dict[str, Any]:
    """The plugin's declared settings keys with their live values."""
    return {field["key"]: field.get("value") for field in plugin_settings_fields(PLUGIN_ID, PLUGIN_DIR)}


class Settings(BaseModel):
    language: Optional[str] = None
    voice: Optional[str] = None
    python: Optional[str] = None
    port: Optional[int] = None
    idle_seconds: Optional[int] = None


@router.get("/state")
def state() -> Dict[str, Any]:
    catalog = _catalog()
    current = _current()
    language = str(current.get("language") or DEFAULT_LANGUAGE).lower()
    return {
        "languages": sorted(catalog),
        "voices": catalog,
        "language": language if language in catalog else DEFAULT_LANGUAGE,
        "voice": str(current.get("voice") or ""),
        "python": str(current.get("python") or ""),
        "idle_seconds": int(current.get("idle_seconds") or DEFAULT_IDLE_SECONDS),
    }


@router.post("/settings")
def save_settings(body: Settings) -> Dict[str, Any]:
    """Write the changed keys through the shared plugin-settings writer.

    An empty string means "use the default" for the free-text keys, but an enum (the voice) has no
    empty choice, so it is dropped instead of being rejected.
    """
    fields = {field["key"]: field for field in plugin_settings_fields(PLUGIN_ID, PLUGIN_DIR)}
    payload = {key: value for key, value in body.model_dump().items() if value is not None}
    payload = {key: value for key, value in payload.items()
               if not (value == "" and fields.get(key, {}).get("type") == "enum")}
    if payload:
        save_plugin_settings(PLUGIN_ID, PLUGIN_DIR, payload)
    return state()
