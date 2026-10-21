"""Configuration loading for JARVIS.

Reads safe defaults, merges optional config.yaml overrides, and loads
API keys from the existing .env file for all free providers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    model: str = "gemini-3.8-flash"
    temperature: float = 0.4
    max_tokens: int = 650
    history_turns: int = 12
    wake_word: str = "jarvis"
    tts_voice: str = "en-GB-RyanNeural"
    stt_model: str = "whisper-large-v3-turbo"
    confirm_shell: bool = True
    allow_paths: list[str] = field(default_factory=lambda: ["~", "."])
    max_tool_iters: int = 6
    log_level: str = "INFO"
    assistant_name: str = "Jarvis"
    user_title: str = "Sir"


def load_config(path: Path | None = None) -> Config:
    """Return a Config, with any values in *path* overriding safe defaults."""
    cfg = Config()
    
    # Also load identity from .env if present
    load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)
    cfg.assistant_name = os.getenv("ASSISTANT_NAME", "Jarvis")
    cfg.user_title = os.getenv("USER_TITLE", "Sir")

    yaml_path = Path(path) if path else _PROJECT_ROOT / "config.yaml"
    if not yaml_path.is_file():
        return cfg

    raw: dict[str, Any] = {}
    try:
        import yaml
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        # Fallback simple key-value parser if PyYAML has issues
        try:
            for line in yaml_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                k, v = line.split(":", 1)
                raw[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass

    for key, value in raw.items():
        if not hasattr(cfg, key):
            continue
        current = getattr(cfg, key)
        if isinstance(current, bool):
            setattr(cfg, key, str(value).lower() in ("true", "1", "yes"))
        elif isinstance(current, float):
            try:
                setattr(cfg, key, float(value))
            except ValueError:
                pass
        elif isinstance(current, int) and not isinstance(current, bool):
            try:
                setattr(cfg, key, int(value))
            except ValueError:
                pass
        elif isinstance(current, list):
            setattr(cfg, key, [str(v) for v in value] if isinstance(value, list) else [str(value)])
        else:
            setattr(cfg, key, str(value))
    return cfg


def load_api_keys() -> dict[str, str]:
    """Load all API keys from the project's .env without modifying it."""
    dotenv_path = _PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path=str(dotenv_path), override=False)
    return {
        "groq": os.getenv("GROQ_API_KEY", "").strip(),
        "gemini": os.getenv("GEMINI_API_KEY", "").strip(),
        "openrouter": os.getenv("OPENROUTER_API_KEY", "").strip(),
        "mistral": os.getenv("MISTRAL_API_KEY", "").strip(),
        "zai": os.getenv("ZAI_API_KEY", "").strip(),
        "picovoice": os.getenv("PICOVOICE_ACCESS_KEY", "").strip(),
    }


def load_api_key() -> str:
    """Backward compatibility helper: returns the first active LLM API key."""
    keys = load_api_keys()
    for name in ("gemini", "groq", "openrouter", "mistral", "zai"):
        if keys.get(name):
            return keys[name]
    return ""


def get_providers(cfg: Config) -> list[dict[str, Any]]:
    """Return ordered list of available free providers with working API keys."""
    keys = load_api_keys()

    specs = {
        "gemini": {
            "label": "Google Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "key": keys["gemini"],
            "model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            "headers": {},
        },
        "groq": {
            "label": "Groq",
            "base_url": "https://api.groq.com/openai/v1",
            "key": keys["groq"],
            "model": os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"),
            "headers": {},
        },
        "openrouter": {
            "label": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "key": keys["openrouter"],
            "model": os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
            "headers": {"HTTP-Referer": "https://localhost", "X-Title": "JARVIS"},
        },
        "mistral": {
            "label": "Mistral",
            "base_url": "https://api.mistral.ai/v1",
            "key": keys["mistral"],
            "model": os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
            "headers": {},
        },
        "zai": {
            "label": "Z.ai",
            "base_url": "https://api.z.ai/api/paas/v4",
            "key": keys["zai"],
            "model": os.getenv("ZAI_MODEL", "glm-5.3-flash"),
            "headers": {},
        },
        "ollama": {
            "label": "Ollama (local)",
            "base_url": "http://localhost:11434/v1",
            "key": "ollama",
            "model": os.getenv("OLLAMA_MODEL", "llama3.2:latest"),
            "headers": {},
        },
    }

    order_str = os.getenv("PROVIDER_ORDER", "gemini,groq,openrouter,mistral,zai,ollama")
    preferred_order = [p.strip().lower() for p in order_str.split(",") if p.strip()]

    providers = []
    for name in preferred_order:
        spec = specs.get(name)
        if spec and (spec["key"] or name == "ollama"):
            providers.append(spec)

    # Fallback to any keyed provider not yet in list
    for name, spec in specs.items():
        if spec["key"] and spec not in providers:
            providers.append(spec)

    return providers
