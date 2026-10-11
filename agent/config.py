"""Run configuration from the environment (and an optional .env file)."""
import os
from datetime import date
from pathlib import Path

from paylane.data import TODAY

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = ROOT / ".env"):
    """The project's .env wins over variables already set in the shell, so a stale
    system-wide key can't silently replace the one configured for this project.
    Empty values in .env are skipped rather than blanking a shell variable."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v:
                os.environ[k.strip()] = v


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
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v3")   # final prompt; v1 and v2 kept for comparison
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
