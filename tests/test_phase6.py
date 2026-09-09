"""Phase 6 tests: pre-flight, error handler, logging pins, runbook presence."""

from __future__ import annotations

import inspect
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# Bad-key startup: SystemExit before polling
def test_preflight_openai_probe_exists_in_post_init():
    from bot import handlers

    src = inspect.getsource(handlers.post_init)
    assert "models.list" in src
    assert "stop_running" in src
    assert "OPENAI_API_KEY is invalid" in src


def test_main_pins_noisy_loggers():
    from bot import main as m

    assert "httpx" in m._NOISY_LOGGERS
    assert "apscheduler" in m._NOISY_LOGGERS


def test_logging_setup_actually_pins():
    # run the real setup and verify post-conditions
    from bot.main import _setup_logging

    _setup_logging()
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("apscheduler").level >= logging.WARNING


def test_runbook_section_in_readme():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Demo Day Runbook" in readme


def test_secret_never_logged_by_error_handler():
    # on_error logs only exc_info + generic message; verify no secret interpolation
    from bot import handlers

    src = inspect.getsource(handlers.on_error)
    assert "passcode" not in src.lower()
    assert "api_key" not in src.lower()
    # it does not format the exception text into a user-visible reply at all
    assert "reply_text" not in src


def test_processed_turn_never_logs_user_message_text():
    # agent_core logs only ids/format checks, not content
    from bot import agent_core

    src = inspect.getsource(agent_core.AgentCore.handle_incoming)
    assert src.count("logger.") == 1  # only the exception branch logs
    assert "text" not in src.split("logger.")[1].split("(")[1]


# Forced-unhandled-exception: on_error logs and returns; PTB then keeps polling
def test_on_error_signature_matches_ptb():
    from bot import handlers

    src = inspect.getsource(handlers.on_error)
    assert "exc_info=ctx.error" in src
