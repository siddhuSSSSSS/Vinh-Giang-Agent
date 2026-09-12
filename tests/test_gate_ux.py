"""Gate UX regression: bare /start greets warmly and counts NO failed attempt.

Matches sessions/gherkin style: the real _check_passcode against a real
in-memory Repo, with minimal Telegram-shaped fakes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot import config, handlers  # noqa: E402
from bot.db.repo import Repo  # noqa: E402


class FakeMsg:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, t: str) -> None:
        self.replies.append(t)


class FakeUser:
    id = 7
    username = "cool_kid"


class FakeUpdate:
    def __init__(self, text: str) -> None:
        self.effective_message = FakeMsg(text)
        self.effective_user = FakeUser()


class FakeApp:
    bot_data: dict[str, Any] = {}


class FakeCtx:
    application = FakeApp()
    user_data: dict[str, Any] = {}


@pytest.fixture
async def gate_repo():
    r = Repo(":memory:")
    await r.connect()
    yield r
    await r.close()


async def test_bare_start_greets_without_counting_attempt(gate_repo: Any):
    """/start with no code: warm hello that asks for the code, 0 attempts."""
    repo = gate_repo
    await repo.get_or_create_user("telegram", "7")
    ctx = FakeCtx()
    ctx.application.bot_data["repo"] = repo

    u = FakeUpdate("/start")
    ok = await handlers._check_passcode(u, ctx, repo)
    row = await repo._fetchone(
        "SELECT * FROM users WHERE platform='telegram' AND platform_user_id='7'"
    )
    assert ok is False
    assert row["failed_attempts"] == 0
    assert "access code" in u.effective_message.replies[0]


async def test_wrong_code_still_counts_attempt(gate_repo: Any):
    """A real wrong guess still costs one failed attempt (brute-force guard)."""
    repo = gate_repo
    await repo.get_or_create_user("telegram", "7")
    ctx = FakeCtx()
    ctx.application.bot_data["repo"] = repo
    config.DEMO_PASSCODE = "karwaan"

    u = FakeUpdate("definitely-not-it")
    ok = await handlers._check_passcode(u, ctx, repo)
    row = await repo._fetchone(
        "SELECT * FROM users WHERE platform='telegram' AND platform_user_id='7'"
    )
    assert ok is False
    assert row["failed_attempts"] == 1


async def test_correct_code_via_start_inline_verifies(gate_repo: Any):
    """/start <code> verifies, resets the counter, greets."""
    repo = gate_repo
    await repo.get_or_create_user("telegram", "7")
    ctx = FakeCtx()
    ctx.application.bot_data["repo"] = repo
    config.DEMO_PASSCODE = "karwaan"

    u = FakeUpdate("/start karwaan")
    ok = await handlers._check_passcode(u, ctx, repo)
    row = await repo._fetchone(
        "SELECT * FROM users WHERE platform='telegram' AND platform_user_id='7'"
    )
    assert ok is True
    assert row["passcode_verified"] == 1
    assert row["failed_attempts"] == 0
    assert "You're in" in u.effective_message.replies[0]
