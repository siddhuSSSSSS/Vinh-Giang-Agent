"""Config smoke test (Planning.md Phase 0 verification).

Covers:
- all-required-vars-present -> validate() passes and echoes them back
- missing var -> failure lists EVERY missing var (not just the first)
- placeholder env values -> treated as missing (copies .env.example verbatim = broken)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _restore_clean_config():
    """Each test in this file reloads bot.config; the LAST reload would otherwise
    pollute the import cache (e.g. DAILY_TICK_HOUR=99 leaking into later tests).
    Always end by reloading under the good baseline."""
    yield
    clean = {k: v for k, v in os.environ.items() if k not in {
        "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "DEMO_PASSCODE", "LLM_PROVIDER",
        "OPENAI_MODEL", "OPENAI_MODEL_ANALYSIS", "OPENAI_TRANSCRIBE_MODEL",
        "ANTHROPIC_API_KEY", "DATABASE_PATH", "LOG_LEVEL", "DAILY_TICK_HOUR",
    }}
    good = {
        "TELEGRAM_BOT_TOKEN": "1234567890:AA-real-looking-token-for-tests",
        "OPENAI_API_KEY": "sk-real-looking-key-for-tests",
        "DEMO_PASSCODE": "test-passcode",
    }
    os.environ.clear()
    os.environ.update({**clean, **good})
    import bot.config as cfg
    importlib.reload(cfg)


def _reload_config(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]):
    """Reload bot.config under a controlled environment."""
    clean = {k: v for k, v in os.environ.items() if k not in {
        "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "DEMO_PASSCODE", "LLM_PROVIDER",
        "OPENAI_MODEL", "OPENAI_MODEL_ANALYSIS", "OPENAI_TRANSCRIBE_MODEL",
        "ANTHROPIC_API_KEY", "DATABASE_PATH", "LOG_LEVEL", "DAILY_TICK_HOUR",
    }}
    monkeypatch.setattr(os, "environ", {**clean, **env})
    import bot.config as cfg
    importlib.reload(cfg)
    return cfg


GOOD_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:AA-real-looking-token-for-tests",
    "OPENAI_API_KEY": "sk-real-looking-key-for-tests",
    "DEMO_PASSCODE": "test-passcode",
}


def test_config_validates_when_complete(monkeypatch):
    cfg = _reload_config(monkeypatch, GOOD_ENV)
    resolved = cfg.validate()
    assert resolved["TELEGRAM_BOT_TOKEN"] == GOOD_ENV["TELEGRAM_BOT_TOKEN"]
    assert resolved["OPENAI_API_KEY"] == GOOD_ENV["OPENAI_API_KEY"]
    assert resolved["DEMO_PASSCODE"] == GOOD_ENV["DEMO_PASSCODE"]
    assert cfg.OPENAI_MODEL == "gpt-5.6-luna"
    assert cfg.OPENAI_MODEL_ANALYSIS == "gpt-5.6-sol"
    assert cfg.OPENAI_TRANSCRIBE_MODEL == "whisper-1"
    assert cfg.LLM_PROVIDER == "openai"
    assert cfg.LOG_LEVEL == "INFO"
    assert cfg.DAILY_TICK_HOUR == 9
    assert str(cfg.DATABASE_PATH) == str(Path("data/bot.db"))


def test_config_lists_all_missing_vars(monkeypatch):
    cfg = _reload_config(monkeypatch, {"DEMO_PASSCODE": "test-passcode"})
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.validate()
    msg = str(excinfo.value)
    assert "TELEGRAM_BOT_TOKEN" in msg
    assert "OPENAI_API_KEY" in msg
    assert "DEMO_PASSCODE" not in msg  # the one var that IS present must not be flagged
    assert ".env" in msg  # tells the user where to fix it


def test_config_rejects_placeholder_env_example_values(monkeypatch):
    env = {
        "TELEGRAM_BOT_TOKEN": "1234567890:AAAA-fake-placeholder-token",
        "OPENAI_API_KEY": "sk-fake-placeholder-key",
        "DEMO_PASSCODE": "change-me",
    }
    cfg = _reload_config(monkeypatch, env)
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.validate()
    msg = str(excinfo.value)
    assert "TELEGRAM_BOT_TOKEN" in msg
    assert "OPENAI_API_KEY" in msg


def test_config_rejects_bad_values(monkeypatch):
    env = {
        **GOOD_ENV,
        "LLM_PROVIDER": "cohere",
        "LOG_LEVEL": "VERBOSE",
        "DAILY_TICK_HOUR": "99",
    }
    cfg = _reload_config(monkeypatch, env)
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.validate()
    msg = str(excinfo.value)
    assert "LLM_PROVIDER" in msg
    assert "LOG_LEVEL" in msg
    assert "DAILY_TICK_HOUR" in msg
