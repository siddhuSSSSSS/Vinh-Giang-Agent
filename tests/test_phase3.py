"""Phase 3 tests: conversation engine, stage machine, handlers' logic surface.

All conversations run against a MOCK LLMClient + the REAL repo and REAL
agent_core (Planning.md: assert on tool invocations and DB state, not prose).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.agent_core import (  # noqa: E402
    STAGE_TRANSITIONS,
    STAGES,
    AgentCore,
    TurnOutcome,
    build_tool_schemas,
    classify_text,
    get_active_synthesis_trigger,
)
from bot.db.repo import Repo  # noqa: E402
from bot.gates import (  # noqa: E402
    get_effective_day,
)
from bot.llm.client import LLMTurnResult, ToolCall  # noqa: E402


class MockLLMClient:
    """Scripted engine: can also emit dynamic turns via a factory."""

    def __init__(self, script: list[LLMTurnResult] | None = None, factory: Any = None) -> None:
        self.script = list(script or [])
        self.factory = factory
        self.calls: list[dict[str, Any]] = []
        self.tool_outputs_seen: list[dict[str, str]] = []

    async def run_turn(self, **kwargs: Any) -> LLMTurnResult:
        self.calls.append(kwargs)
        # inspect function_call_output items surfaced back to the model
        for item in kwargs.get("input_items", []):
            if item.get("type") == "function_call_output":
                self.tool_outputs_seen.append(item)
        if self.factory:
            return self.factory(self.tool_outputs_seen)
        return self.script.pop(0)


@pytest.fixture
async def repo():
    r = Repo(":memory:")
    await r.connect()
    yield r
    await r.close()


def _scripted(state_chain: list[tuple[list[ToolCall], str]], final: str = "ok"):
    """Build a MockLLMClient that calls tools then finishes."""
    scripted = [
        LLMTurnResult(tool_calls=calls, raw_output=[]) for calls, _ in state_chain
    ] + [LLMTurnResult(text=final)]
    return scripted


# ---------------------------------------------------------------------------
# classify_text
# ---------------------------------------------------------------------------
def test_classify_text_short_chat():
    assert classify_text("hey! how's it going?") == "chat"


def test_classify_text_timestamped_paste_is_transcript_even_short():
    t = "0:00 heyo so uhm\n0:32 , this is more words here"
    assert classify_text(t) == "transcript"


def test_classify_text_long_multi_paragraph_without_ts_is_transcript():
    t = "\n".join(
        (f"paragraph {i}: a fairly long paste line with many words in it" * 3)
        + " plus enough trailing words to clear the four thousand char "
          "message limit comfortably on any platform " * 3
        for i in range(10)
    )
    assert len(t) > 4000  # genuinely over the chat ceiling
    assert classify_text(t) == "transcript"


def test_classify_text_summary_marker():
    t = "In this video the speaker explains things. " + "filler " * 200
    assert classify_text(t) == "summary"


# ---------------------------------------------------------------------------
# Stage machine (server-side enforcement)
# ---------------------------------------------------------------------------
def test_stage_graph_shape():
    assert set(STAGE_TRANSITIONS) == set(STAGES)
    assert STAGE_TRANSITIONS["onboarding"] == ("initial_recording",)
    assert STAGE_TRANSITIONS["weekly_cycle"] == ("weekly_cycle",)


async def test_advance_stage_enforced_server_side(repo):
    """Feature: graph cannot be skipped
      Given a user in onboarding
      When the model asks to jump to weekly_cycle
      Then advance_stage returns a tool-error naming the allowed move
      And the stage is unchanged in the DB
    """
    u = await repo.get_or_create_user("telegram", "42")
    agent = AgentCore(repo, MockLLMClient())
    ex = agent._build_executors(u, 0)
    out = await ex["advance_stage"](new_stage="weekly_cycle")
    payload = json.loads(out)
    assert "error" in payload
    assert "initial_recording" in payload["error"]
    st = await repo.get_user_state(u.id)
    assert st.current_stage == "onboarding"


async def test_advance_stage_legal_move_advances(repo):
    u = await repo.get_or_create_user("telegram", "42")
    agent = AgentCore(repo, MockLLMClient())
    ex = agent._build_executors(u, 0)
    out = await ex["advance_stage"](new_stage="initial_recording")
    assert out == "stage is now initial_recording"
    assert (await repo.get_user_state(u.id)).current_stage == "initial_recording"


async def test_24h_gate_blocks_stage_jump(repo):
    """Feature: 24h gate not model-bypassable
      Given a user in waiting_24h whose recording was submitted 3 hours ago
      When the model calls advance_stage(audit_day1)
      Then a tool-error explains the hold - stage unchanged
    """
    u = await repo.get_or_create_user("telegram", "42")
    await repo.update_user_state(
        u.id, current_stage="waiting_24h",
        recording_submitted_at=_iso_hours_ago(3),
        recording_submitted_effective_day=5,
    )
    # force current effective day = 5 (submitted day)

    await repo._execute(
        "UPDATE users SET day_zero_at=? WHERE id=?",
        (_iso_date_days_ago(5), u.id),
    )
    u = await repo.get_user(u.id)
    agent = AgentCore(repo, MockLLMClient())
    ex = agent._build_executors(u, 5)  # eff_day 5
    out = await ex["advance_stage"](new_stage="audit_day1")
    payload = json.loads(out)
    assert "error" in payload and "24-hour" in payload["error"]
    assert (await repo.get_user_state(u.id)).current_stage == "waiting_24h"


async def test_24h_gate_opens_next_day(repo):
    u = await repo.get_or_create_user("telegram", "42")
    await repo.update_user_state(
        u.id, current_stage="waiting_24h",
        recording_submitted_at=_iso_hours_ago(26),
        recording_submitted_effective_day=5,
    )
    await repo._execute(
        "UPDATE users SET day_zero_at=? WHERE id=?", (_iso_date_days_ago(6), u.id)
    )
    u = await repo.get_user(u.id)
    assert get_effective_day(u) == 6
    agent = AgentCore(repo, MockLLMClient())
    ex = agent._build_executors(u, 6)
    out = await ex["advance_stage"](new_stage="audit_day1")
    assert out == "stage is now audit_day1"  # day arithmetic term cleared it


# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------
def test_synthesis_trigger_day3_and_habit_selection():

    assert (
        get_active_synthesis_trigger("audit_day3", 0, 12, None, None, 0)
        == "habit_decision_synthesis"
    )
    assert (
        get_active_synthesis_trigger("habit_selection", 0, 12, None, None, 0)
        == "habit_decision_synthesis"
    )
    assert get_active_synthesis_trigger("audit_day1", 0, 12, None, None, 0) is None


def test_synthesis_trigger_adaptive_replanning():
    assert get_active_synthesis_trigger("weekly_cycle", 1, 30, 20, None, 2) == "adaptive_replanning"


def test_synthesis_trigger_weekly_reeval_boundary_and_once_only():
    # day 27, started day 20 -> boundary
    assert get_active_synthesis_trigger(
        "weekly_cycle", 1, 27, 20, None, 0
    ) == "weekly_reeval"
    # already handled today: not again
    assert get_active_synthesis_trigger(
        "weekly_cycle", 1, 27, 20, _iso_hours_ago(1), 0
    ) is None


# ---------------------------------------------------------------------------
# Engine turn-level tests (mocked LLM)
# ---------------------------------------------------------------------------
async def test_engine_plain_chat_roundtrip_persists_both_messages(repo):
    u = await repo.get_or_create_user("telegram", "42")
    client = MockLLMClient(script=[LLMTurnResult(text="hello! what should I call you?")])
    agent = AgentCore(repo, client)
    outcome = await agent.handle_incoming("telegram", "42", "hi there")

    assert isinstance(outcome, TurnOutcome) and not outcome.error_reply
    assert outcome.model_used  # routed
    msgs = await repo.get_recent_messages(u.id, limit=10)
    assert [m["content"] for m in msgs][-2:] == ["hi there", "hello! what should I call you?"]
    assert await repo.has_engagement_on_day(u.id, get_effective_day(await repo.get_user(u.id)))


async def test_engine_tool_call_flows_through_executors(repo):
    """Feature: tool loop end-to-end through the real registry
      Given a mock LLM that calls get_user_state then update_user_state then answers
      When handle_incoming runs
      Then each tool hit the real executors and the DB reflects every write
    """
    u = await repo.get_or_create_user("telegram", "42")

    # raw_output items drive function_call handling in the loop
    def mk(cid: str, tname: str, args: str) -> Any:
        class It:
            pass

        it = It()
        it.type = "function_call"
        it.call_id = cid
        it.name = tname
        it.arguments = args
        return it

    chain = [
        LLMTurnResult(
            text=None,
            tool_calls=[
                ToolCall("c1", "get_user_state", {}),
                ToolCall("c2", "update_user_state", {
                    "current_habit": "filler words", "week_in_habit": 0,
                    "motivation_summary": None, "kaizen_reveal_shown": None,
                    "timezone": "Asia/Kolkata",
                }),
            ],
            raw_output=[mk("c1", "get_user_state", "{}"),
                        mk("c2", "update_user_state", json.dumps({
                            "current_habit": "filler words", "week_in_habit": 0,
                            "motivation_summary": None, "kaizen_reveal_shown": None,
                            "timezone": "Asia/Kolkata",
                        }))],
        ),
        LLMTurnResult(text="Locked in - we'll work on your filler words."),
    ]
    client = MockLLMClient(script=chain)
    agent = AgentCore(repo, client)
    await agent.handle_incoming("telegram", "42", "can we start on filler words?")

    # DB effects from within the closure executors:
    st = await repo.get_user_state(u.id)
    assert st.current_habit == "filler words"
    u = await repo.get_user(u.id)
    assert u.timezone == "Asia/Kolkata"
    # outputs surfaced to the model included the fidelity of the state read
    assert any('"stage"' in t["output"] for t in client.tool_outputs_seen)
    # final reply persisted
    msgs = await repo.get_recent_messages(u.id, limit=10)
    assert msgs[-1]["content"] == "Locked in - we'll work on your filler words."


async def test_engine_transcript_never_enters_window_and_files_media(repo):
    u = await repo.get_or_create_user("telegram", "42")
    transcript = "0:00 random paragraph about uhm one\n0:31 second paragraph with more\n"
    transcript += "extra narrative line\n" * 3
    client = MockLLMClient(script=[])  # must never be called for transcripts
    agent = AgentCore(repo, client)
    outcome = await agent.handle_incoming("telegram", "42", transcript)

    assert "Transcript received" in outcome.reply
    assert not client.calls  # no LLM turn for transcript flow
    row = await repo._fetchone(
        "SELECT transcript_text FROM media_refs WHERE user_id=?", (u.id,)
    )
    assert row["transcript_text"].startswith("0:00")
    # NOT in the conversation window
    msgs = await repo.get_recent_messages(u.id, limit=50)
    assert all("0:00" not in m["content"] for m in msgs)


async def test_engine_loop_cap_returns_graceful_reply(repo):
    class LoopClient:
        async def run_turn(self, **kwargs: Any) -> LLMTurnResult:
            def mk() -> Any:
                class It:
                    type = "function_call"
                    call_id = "x"
                    name = "get_user_state"
                    arguments = "{}"

                return It()

            return LLMTurnResult(
                tool_calls=[ToolCall("x", "get_user_state", {})],
                raw_output=[mk()],
            )

    u = await repo.get_or_create_user("telegram", "42")
    agent = AgentCore(repo, LoopClient())
    outcome = await agent.handle_incoming("telegram", "42", "hello")
    assert outcome.error_reply
    assert outcome.reply == "Hit a snag there - let's try that again."
    # user message did persist (context integrity)
    msgs = await repo.get_recent_messages(u.id, limit=5)
    assert msgs[-1]["role"] == "user"


# ---------------------------------------------------------------------------
# Tool schemas sanity
# ---------------------------------------------------------------------------
def test_tool_schemas_flat_responses_shape():
    tools = build_tool_schemas()
    assert len(tools) == 4
    names = {t["name"] for t in tools}
    assert names == {"get_user_state", "update_user_state", "log_journal_entry", "advance_stage"}
    for t in tools:
        assert t["type"] == "function" and "function" not in t  # flat, no wrapper
        if t["name"] != "get_user_state":
            assert set(t["parameters"]["required"]), f"{t['name']} missing required"


# helpers
def _iso_hours_ago(h: int) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(hours=h)).isoformat()


def _iso_date_days_ago(d: int) -> str:
    """day_zero_at floored so get_effective_day(now)==d."""
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(days=d)).isoformat()
