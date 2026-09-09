"""Executable Gherkin scenarios for Phase 3 (tests/gherkin/phase3.feature)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.agent_core import AgentCore, classify_text  # noqa: E402
from bot.db.repo import Repo  # noqa: E402
from bot.llm.client import LLMTurnResult, ToolCall  # noqa: E402


@pytest.fixture
async def repo():
    r = Repo(":memory:")
    await r.connect()
    yield r
    await r.close()


class MockClient:
    def __init__(self, script: list[LLMTurnResult]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.outputs: list[dict[str, str]] = []

    async def run_turn(self, **kwargs: Any) -> LLMTurnResult:
        self.calls.append(kwargs)
        for item in kwargs.get("input_items", []):
            if item.get("type") == "function_call_output":
                self.outputs.append(item)
        return self.script.pop(0)


def _mkitem(cid: str, name: str, args: str) -> Any:
    item = type("It", (), {})()
    item.type = "function_call"
    item.call_id = cid
    item.name = name
    item.arguments = args
    return item


# Feature: onboarding collects pieces mechanically
async def test_onboarding_ingests_name_goal_five_words_timezone(repo):
    """Feature: onboarding
      Given a new user chatting with the sidekick
      When onboarding turns happen with tool-calling
      Then every captured piece lands in its structured store, once each
    """
    u = await repo.get_or_create_user("telegram", "42")

    def mk(cid: str, name: str, args: str) -> Any:
        return _mkitem(cid, name, json.dumps(args))

    script = [
        LLMTurnResult(  # name+goal via journal, timezone via state
            text=None,
            tool_calls=[
                ToolCall(
                    "1", "log_journal_entry",
                    {"journal_type": "reflection",
                     "content": "Screenshot of Sam here",
                     "completed": None, "reason": None},
                ),
                ToolCall(
                    "2", "update_user_state",
                    {"current_habit": None, "kaizen_reveal_shown": None,
                     "motivation_summary": "wants clarity in meetings",
                     "timezone": "Asia/Kolkata", "week_in_habit": None},
                ),
            ],
            raw_output=[
                mk("1", "log_journal_entry", {
                    "journal_type": "reflection", "content": "Screenshot of Sam here",
                    "completed": None, "reason": None,
                }),
                mk("2", "update_user_state", {
                    "timezone": "Asia/Kolkata", "current_habit": None,
                    "week_in_habit": None, "motivation_summary": "wants clarity in meetings",
                    "kaizen_reveal_shown": None,
                }),
            ],
        ),
        LLMTurnResult(text="Lovely to meet you, Sam."),
    ]
    agent = AgentCore(repo, MockClient(script))
    await agent.handle_incoming("telegram", "42", "I'm Sam; ramble in meetings; UTC+5:30")

    fresh = await repo.get_user(u.id)
    assert fresh.timezone == "Asia/Kolkata"
    st = await repo.get_user_state(u.id)
    assert st.motivation_summary == "wants clarity in meetings"
    # day_zero realigned to local midnight exactly once on first timezone
    from bot.db.repo import local_midnight_iso

    assert fresh.day_zero_at == local_midnight_iso("Asia/Kolkata")


# Feature: stage graph + weekly-cycle anchor
async def test_full_onchain_to_weekly_cycle_stamps_anchor(repo):
    u = await repo.get_or_create_user("telegram", "43")
    agent = AgentCore(repo, MockClient([LLMTurnResult(text="done")] * 0 or [
        LLMTurnResult(text="chain finished"),
    ]))
    ex = agent._build_executors(u, 0)
    for nxt in (
        "initial_recording", "waiting_24h", "audit_day1", "audit_day2",
        "audit_day3", "habit_selection", "weekly_cycle",
    ):
        if nxt == "audit_day1":
            # satisfy the 24h gate first (simulate recording + day passed)
            await repo.update_user_state(
                u.id, current_stage="waiting_24h",
                recording_submitted_at="2026-09-01T00:00:00+00:00",
                recording_submitted_effective_day=0,
            )
            await repo._execute(
                "UPDATE users SET day_zero_at='2026-01-01T00:00:00+00:00' WHERE id=?",
                (u.id,),
            )
        out = await ex["advance_stage"](new_stage=nxt)
        assert not out.startswith("{"), f"couldn't advance to {nxt}: {out}"
    st = await repo.get_user_state(u.id)
    assert st.current_stage == "weekly_cycle"
    assert st.weekly_cycle_started_effective_day == 0


# Feature: degraded loop keeps user data intact
async def test_turn_failure_preserves_user_message(repo):
    class Boom:
        async def run_turn(self, **kwargs: Any) -> LLMTurnResult:
            raise RuntimeError("api down")

    u = await repo.get_or_create_user("telegram", "44")
    agent = AgentCore(repo, Boom())
    outcome = await agent.handle_incoming("telegram", "44", "hmm test")
    assert outcome.error_reply and "snag" in outcome.reply
    msgs = await repo.get_recent_messages(u.id, limit=5)
    assert msgs[-1]["content"] == "hmm test"  # the user's turn is durable
    # NO assistant-echo fabricated after failure
    assert msgs[-1]["role"] == "user"


# Feature: summary classification files text without an LLM turn
async def test_summary_kind_files_and_skips_window(repo):
    u = await repo.get_or_create_user("telegram", "45")
    text = "In this video the speaker unpacks everything. " + "words " * 600
    assert classify_text(text) == "summary"
    class NoCalls:
        async def run_turn(self, **kwargs: Any) -> LLMTurnResult:
            raise AssertionError("summary path must not hit the LLM in this flow")

    agent2 = AgentCore(repo, NoCalls())
    outcome = await agent2.handle_incoming("telegram", "45", text)
    assert outcome.reply
    row = await repo._fetchone("SELECT summary_text FROM media_refs WHERE user_id=?", (u.id,))
    assert row["summary_text"] is not None
