"""Every number and setting lives here. Override any of them in .env."""
import logging
import os
import re
from pathlib import Path  # noqa: F401  (also used as config.Path)
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("friday.config")


def _bool(name, default):
    return os.getenv(name, str(default)).lower() == "true"


def pick_model(value, default):
    """Gemini 3+ only. A 1.x/2.x name from the environment is ignored, never used."""
    m = re.match(r"gemini-(\d+)", value or "")
    if m and int(m.group(1)) < 3:
        log.warning("Ignoring %s: Gemini 2.x and older no longer work. Using %s.", value, default)
        return default
    return value or default


# --- model ---
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
DEFAULT_MODEL = pick_model(os.getenv("DEFAULT_MODEL"), "gemini-3.8-flash")
# The live API often answers 503 "high demand" on one model while another is fine, so keep a wide chain.
FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.6-flash",
                   "gemini-flash-latest", "gemini-3.8-flash"]
THINKING_LEVEL = os.getenv("THINKING_LEVEL", "MINIMAL")  # voice assistant: speed over depth
STICKY_MODEL_S = 5 * 60   # after a fallback answers, try it first for this long
# Local models through Ollama. Pick one in the UI; ids look like "ollama/qwen2.5-coder:3b".
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
LOCAL_CALL_TIMEOUT_S = 60     # local models think slower than the cloud; no hedging while they do
LOCAL_TURN_BUDGET_S = 150


def is_local(model):
    return (model or "").startswith("ollama/")


ULTRON_ASIDE_RATE = float(os.getenv("ULTRON_ASIDE_RATE", "0.5"))   # share of replies where Ultron cuts in

# --- voices: Kokoro (local, free) first, then Gemini TTS, then the browser voice ---
KOKORO_MODEL = ROOT / "data" / "voices" / "kokoro-v1.0.int8.onnx"
KOKORO_VOICES = ROOT / "data" / "voices" / "voices-v1.0.bin"
TTS_MODELS = ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"]
TTS_MAX_CHARS = 600
STT_MODELS = ["gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.7-flash"]   # cloud fallback for speech-to-text
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")   # local speech-to-text, ~0.3 s per sentence
WHISPER_DIR = ROOT / "data" / "models"
STT_MAX_BYTES = 2_000_000   # ~60 s of 16 kHz mono WAV
# Written -> spoken. The owner's name is pronounced "Shresht Pandey".
PRONOUNCE = {"Shrestha": "Shresht"}

# --- server ---
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "3000"))
ENABLE_HTTPS = _bool("ENABLE_HTTPS", True)
SSL_CERTFILE = os.getenv("SSL_CERTFILE", "")
SSL_KEYFILE = os.getenv("SSL_KEYFILE", "")
DEBUG = _bool("DEBUG", False)

# --- agent budgets (seconds unless noted) ---
MAX_STEPS = 8
TURN_BUDGET_S = 60
MODEL_CALL_TIMEOUT_S = 20
TOOL_TIMEOUT_S = 15
HEDGE_AFTER_S = 3        # leader model silent this long -> race the next model against it
LOOP_GUARD = 3            # same tool + same args this many times -> stop
CONFIRM_TTL_S = 60
MAX_TOOL_RESULT_CHARS = 8000

# --- sessions ---
MAX_HISTORY_TURNS = 20
SESSION_IDLE_S = 30 * 60

# --- time & proactive ---
TZ = ZoneInfo(os.getenv("FRIDAY_TZ", "Asia/Calcutta"))
BRIEFING_TIME = os.getenv("BRIEFING_TIME", "08:00")
QUIET_HOURS = os.getenv("QUIET_HOURS", "23:00-07:00")
ALERT_COOLDOWN_S = 30 * 60
BATTERY_LOW_PCT = 20
BATTERY_CRITICAL_PCT = 10
DISK_HIGH_PCT = 90
RAM_HIGH_PCT = 90
RAM_HIGH_FOR_S = 120
TICK_S = 5
WATCH_EVERY_S = 60

CLAUDE_TIMEOUT_S = 30 * 60   # a Claude Code job may run this long in the background

# --- storage ---
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "friday.db"
BACKUP_DIR = DATA_DIR / "backups"
BACKUPS_KEPT = 7
TOKEN_PATH = DATA_DIR / "session_token"

# --- file policy (ask the owner to widen this) ---
ALLOWED_ROOTS = [
    Path(p).expanduser().resolve()
    for p in os.getenv("FRIDAY_ALLOWED_ROOTS", str(ROOT.parent)).split(":")
    if p
]
