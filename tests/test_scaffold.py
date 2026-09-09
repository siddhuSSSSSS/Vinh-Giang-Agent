"""Package-integrity smoke test (Phase 0).

Proves the whole tree imports cleanly and the Python-telegram-bot + openai
runtime deps are actually installed and importable (stubs must not drift).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_bot_package_imports():
    """The whole bot/* tree (incl. every stub) must import cleanly."""
    import bot
    import bot.adapters
    import bot.agent_core
    import bot.analysis
    import bot.analysis.base
    import bot.analysis.loom
    import bot.analysis.voice_fallback
    import bot.config
    import bot.db
    import bot.db.repo
    import bot.gates
    import bot.handlers
    import bot.llm
    import bot.llm.client
    import bot.llm.persona
    import bot.main
    import bot.scheduler

    assert bot is not None and bot.main is not None


def test_third_party_deps_importable():
    import aiosqlite  # noqa: F401
    import apscheduler  # noqa: F401  (bundled by the [job-queue] extra)
    import dotenv  # noqa: F401
    import openai  # noqa: F401
    import telegram  # noqa: F401  (python-telegram-bot)


def test_schema_sql_present():
    sql = PROJECT_ROOT / "bot" / "db" / "schema.sql"
    assert sql.exists(), "schema.sql must exist (even as a Phase 0 stub)"
    assert isinstance(sql.read_text(encoding="utf-8"), str)


def test_config_module_has_expected_surface():
    import bot.config as cfg

    assert hasattr(cfg, "ConfigError")
    assert hasattr(cfg, "validate")
    for name in (
        "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "DEMO_PASSCODE",
        "OPENAI_MODEL", "OPENAI_MODEL_ANALYSIS", "OPENAI_TRANSCRIBE_MODEL",
        "LLM_PROVIDER", "ANTHROPIC_API_KEY", "DATABASE_PATH", "LOG_LEVEL",
        "DAILY_TICK_HOUR",
    ):
        assert hasattr(cfg, name), f"bot.config missing documented var {name}"
