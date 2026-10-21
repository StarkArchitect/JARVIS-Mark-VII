"""Central config. Everything comes from .env so you never edit code to change models."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ---------------- identity ----------------
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Jarvis")
USER_TITLE     = os.getenv("USER_TITLE", "Sir")
WAKE_WORD      = os.getenv("WAKE_WORD", "jarvis").lower().strip()

# ---------------- voice ----------------
TTS_VOICE    = os.getenv("TTS_VOICE", "en-GB-RyanNeural")
TTS_RATE     = os.getenv("TTS_RATE", "+8%")
TTS_VOLUME   = os.getenv("TTS_VOLUME", "+0%")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "en")
STT_MODEL    = os.getenv("STT_MODEL", "whisper-large-v3-turbo")

SAMPLE_RATE   = 16000
BLOCK_SIZE    = 1024
SILENCE_RMS   = float(os.getenv("SILENCE_RMS", "0.012"))
SILENCE_HANG  = float(os.getenv("SILENCE_HANG", "1.0"))
MAX_UTTERANCE = float(os.getenv("MAX_UTTERANCE", "20"))
MIC_DEVICE    = os.getenv("MIC_DEVICE") or None

# ---------------- behaviour ----------------
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "12"))
MAX_TOOL_ROUNDS   = int(os.getenv("MAX_TOOL_ROUNDS", "6"))
TEMPERATURE       = float(os.getenv("TEMPERATURE", "0.55"))
MAX_TOKENS        = int(os.getenv("MAX_TOKENS", "650"))
HOME_CITY         = os.getenv("HOME_CITY", "")
SHELL_TIMEOUT     = int(os.getenv("SHELL_TIMEOUT", "25"))
VERBOSE           = os.getenv("VERBOSE", "false").lower() in ("1", "true", "yes")

# ---------------- keys ----------------
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "").strip()
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MISTRAL_API_KEY    = os.getenv("MISTRAL_API_KEY", "").strip()
ZAI_API_KEY        = os.getenv("ZAI_API_KEY", "").strip()
PICOVOICE_KEY      = os.getenv("PICOVOICE_ACCESS_KEY", "").strip()

# ---------------- provider registry ----------------
# All of these speak the OpenAI wire format, so one SDK covers them all.
PROVIDER_SPECS = {
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key": GROQ_API_KEY,
        "model": os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"),
        "headers": {},
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key": GEMINI_API_KEY,
        "model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "headers": {},
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "key": OPENROUTER_API_KEY,
        "model": os.getenv("OPENROUTER_MODEL",
                           os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")),
        "headers": {"HTTP-Referer": "https://localhost", "X-Title": "Jarvis"},
    },
    "mistral": {
        "label": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "key": MISTRAL_API_KEY,
        "model": os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
        "headers": {},
    },
    "zai": {
        "label": "Z.ai",
        "base_url": "https://api.z.ai/api/paas/v4",
        "key": ZAI_API_KEY,
        "model": os.getenv("ZAI_MODEL", "glm-4.7-flash"),
        "headers": {},
    },
    "ollama": {                       # local, no key needed
        "label": "Ollama (local)",
        "base_url": "http://localhost:11434/v1",
        "key": "ollama",
        "model": os.getenv("OLLAMA_MODEL", "qwen3.5:9b"),
        "headers": {},
    },
}

_order = [p.strip() for p in
          os.getenv("PROVIDER_ORDER", "groq,gemini,openrouter,mistral,zai,ollama").split(",")]

PROVIDERS = []
for _name in _order:
    _spec = PROVIDER_SPECS.get(_name)
    if not _spec:
        continue
    if _name == "ollama" or _spec["key"]:
        PROVIDERS.append(_spec)

# fallback: if PROVIDER_ORDER missed a keyed provider, still include it
for _name, _spec in PROVIDER_SPECS.items():
    if _spec["key"] and _spec not in PROVIDERS:
        PROVIDERS.append(_spec)


def voice_available() -> bool:
    try:
        import sounddevice  # noqa
        return True
    except Exception:
        return False