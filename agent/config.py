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

PROVIDER = os.getenv("PROVIDER", "anthropic")
MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
EFFORT = os.getenv("EFFORT", "medium")              # low | medium | high
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-sonnet-5-5")
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v1")
# Server-side refusal fallback (Claude API only). Set to 0 to disable.
FALLBACKS = os.getenv("ANTHROPIC_FALLBACKS", "1") != "0"
TODAY_DATE = date.fromisoformat(os.getenv("TODAY", TODAY.isoformat()))


def snapshot() -> dict:
    return {"provider": PROVIDER, "model": MODEL, "effort": EFFORT, "prompt_version": PROMPT_VERSION,
            "today": TODAY_DATE.isoformat(), "refusal_fallbacks": FALLBACKS}
