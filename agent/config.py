"""Run configuration from the environment (and an optional .env file)."""
import os
from datetime import date
from pathlib import Path

from paylane.data import TODAY

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_dotenv()

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4.1"}


def _default_provider() -> str:
    """Use OpenAI when only an OpenAI key is configured; otherwise Anthropic."""
    if os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        return "openai"
    return "anthropic"


PROVIDER = (os.getenv("PROVIDER") or _default_provider()).lower()
if PROVIDER not in DEFAULT_MODELS:
    raise SystemExit(f"PROVIDER must be one of {sorted(DEFAULT_MODELS)}, got {PROVIDER!r}")
MODEL = os.getenv("MODEL") or DEFAULT_MODELS[PROVIDER]
EFFORT = os.getenv("EFFORT", "medium")              # Anthropic effort: low | medium | high
JUDGE_MODEL = os.getenv("JUDGE_MODEL") or MODEL
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v1")
# Server-side refusal fallback (Claude API only). Set to 0 to disable.
FALLBACKS = os.getenv("ANTHROPIC_FALLBACKS", "1") != "0"
TODAY_DATE = date.fromisoformat(os.getenv("TODAY", TODAY.isoformat()))


def snapshot() -> dict:
    snap = {"provider": PROVIDER, "model": MODEL, "prompt_version": PROMPT_VERSION,
            "today": TODAY_DATE.isoformat()}
    if PROVIDER == "anthropic":
        snap.update(effort=EFFORT, refusal_fallbacks=FALLBACKS)
    else:
        snap.update(effort=os.getenv("OPENAI_REASONING_EFFORT") or "default",
                    temperature=os.getenv("OPENAI_TEMPERATURE") or "default")
    return snap
