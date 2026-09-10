"""Environment schema + fail-fast validation.

Phase 0 deliverable (per Planning.md). Missing required vars raise a single clear
ConfigError listing exactly what is missing - never a raw traceback.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level above this package).
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
# load_dotenv is bound here so tests can no-op it during module reloads:
# importlib.reload re-executes the module source, restoring this name to
# the real loader and re-injecting the repo's real .env values over the
# test's substituted os.environ. Kept as a module attribute for that reason.


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def _non_placeholder(name: str) -> str:
    """Read an env var, treating .env.example placeholder values as missing."""
    value = os.getenv(name, "").strip()
    if not value:
        return ""
    placeholders = ("sk-fake", "1234567890:AAAA")
    return "" if value.startswith(placeholders) else value


# --- Required (all three go through placeholder detection) ---
TELEGRAM_BOT_TOKEN: str = _non_placeholder("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY: str = _non_placeholder("OPENAI_API_KEY")
DEMO_PASSCODE: str = os.getenv("DEMO_PASSCODE", "").strip()

# --- Model routing (Phase 1 defaults; overridable) ---
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
OPENAI_MODEL_ANALYSIS: str = os.getenv("OPENAI_MODEL_ANALYSIS", "gpt-5.6-sol")
OPENAI_TRANSCRIBE_MODEL: str = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
# Escalation dial for the analysis tier (Planning.md chain: none -> low -> medium -> swap)
ANALYSIS_REASONING_EFFORT: str = os.getenv("ANALYSIS_REASONING_EFFORT", "none").lower()
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower()
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "").strip()  # optional, unused MVP

# --- Runtime ---
DATABASE_PATH: Path = Path(os.getenv("DATABASE_PATH", "data/bot.db"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
try:
    DAILY_TICK_HOUR: int = int(os.getenv("DAILY_TICK_HOUR", "9"))
except ValueError:
    DAILY_TICK_HOUR = 9
# OpenCode-compat bridge (Phase 6.b): 0 disables the bridge server; a port
# number enables it (4096 matches opencode's default provider habit).
try:
    COMPAT_SERVER_PORT: int = int(os.getenv("COMPAT_SERVER_PORT", "0"))
except ValueError:
    COMPAT_SERVER_PORT = 0

_REQUIRED = ("TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "DEMO_PASSCODE")


def validate() -> dict[str, str]:
    """Fail-fast config validation. Returns the resolved required values.

    Raises ConfigError with one message listing every problem found.
    """
    problems: list[str] = []
    resolved: dict[str, str] = {}

    for name in _REQUIRED:
        value = globals().get(name, "")
        if not isinstance(value, str) or not value:
            problems.append(f"  - {name} is missing or set to a placeholder value")
        else:
            resolved[name] = value

    if LLM_PROVIDER not in ("openai",):
        problems.append(f"  - LLM_PROVIDER={LLM_PROVIDER!r} but only 'openai' is supported in MVP")

    if LOG_LEVEL not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        problems.append(f"  - LOG_LEVEL={LOG_LEVEL!r} is not a valid level")

    if not 0 <= DAILY_TICK_HOUR <= 23:
        problems.append(f"  - DAILY_TICK_HOUR={DAILY_TICK_HOUR} is not an hour (0-23)")

    valid_efforts = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
    if ANALYSIS_REASONING_EFFORT not in valid_efforts:
        problems.append(
            f"  - ANALYSIS_REASONING_EFFORT={ANALYSIS_REASONING_EFFORT!r} is not a valid effort"
        )

    if problems:
        raise ConfigError(
            "Configuration errors:\n" + "\n".join(problems)
            + "\nFix them in .env (copy .env.example if you don't have one)."
        )
    return resolved
