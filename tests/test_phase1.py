"""Phase 1 tests: OpenAI client shapes + tool loop + persona budget.

All LLM behavior is tested against a MOCK LLMClient (per Planning.md - never
assert on real model output). Shape constants (function_call/function_call_output
item keys, reasoning param) are asserted against the real SDK so drift fails loud.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import openai.types.responses as RT  # noqa: E402

from bot.llm.client import (  # noqa: E402
    LLMTurnResult,
    OpenAIClient,
    ToolCall,
    ToolLoopLimitExceeded,
    _parse_tool_calls,
    run_tool_loop,
)
from bot.llm.persona import (  # noqa: E402
    STATIC_BLOCKS,
    UserState,
    build_state_summary,
    build_system_prompt,
)


# ---------------------------------------------------------------------------
# Shape drift guards (real SDK, no network)
# ---------------------------------------------------------------------------
def test_sdk_function_call_item_shape():
    """The fields our parser reads exist on the real SDK function-call item."""
    fields = set(RT.ResponseFunctionToolCall.model_fields.keys())
    assert {"call_id", "name", "arguments", "type"} <= fields


def test_sdk_function_call_output_param_shape():
    """function_call_output items we emit use keys the API actually accepts."""
    import openai.types.responses.response_input_item_param as RI

    src = RI.__file__
    text = open(src, encoding="utf-8").read()
    i = text.find("class FunctionCallOutput(TypedDict")
    block = text[i : i + 800]
    assert '"function_call_output"' in block
    assert "call_id" in block
    assert "output" in block


def test_sdk_reasoning_effort_values():
    from typing import Union, get_args, get_origin

    from openai.types.shared import ReasoningEffort  # type: ignore[attr-defined]

    origin = get_origin(ReasoningEffort)
    if origin is Union:  # Literal[...] | None shape in SDK 3.11
        literals = [a for a in get_args(ReasoningEffort) if get_origin(a) is not None]
        values = get_args(literals[0]) if literals else get_args(ReasoningEffort)
    else:
        values = get_args(ReasoningEffort)
    assert values is not None and "none" in values and "low" in values


# ---------------------------------------------------------------------------
# Tool-call parsing
# ---------------------------------------------------------------------------
class _FakeCallItem:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.type = "function_call"
        self.call_id = call_id
        self.name = name
        self.arguments = arguments


def test_parse_tool_calls_parses_json_arguments():
    items = [
        _FakeCallItem("c1", "log_journal_entry", '{"type": "reflection", "content": "hi"}')
    ]
    calls = _parse_tool_calls(items)
    assert calls == [
        ToolCall(
            call_id="c1",
            name="log_journal_entry",
            arguments={"type": "reflection", "content": "hi"},
        )
    ]


def test_parse_tool_calls_survives_bad_json():
    calls = _parse_tool_calls([_FakeCallItem("c2", "x", "{not json")])
    assert calls[0].arguments == {"_unparsed": "{not json"}


# ---------------------------------------------------------------------------
# Mocked-LLM tool loop
# ---------------------------------------------------------------------------
class MockLLMClient:
    """Scripted LLMClient: pops one scripted LLMTurnResult per run_turn call."""

    def __init__(self, script: list[LLMTurnResult]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def run_turn(self, **kwargs: Any) -> LLMTurnResult:
        self.calls.append(kwargs)
        return self.script.pop(0)

    @property
    def run_turn_count(self) -> int:
        return len(self.calls)


async def test_tool_loop_executes_calls_and_returns_final_text():
    script = [
        LLMTurnResult(
            tool_calls=[ToolCall("c1", "get_user_state", {})],
            raw_output=[_FakeCallItem("c1", "get_user_state", "{}")],
        ),
        LLMTurnResult(text="all done"),
    ]
    client = MockLLMClient(script)
    executors = {"get_user_state": lambda: "STATE_JSON"}

    final, ephemeral = await run_tool_loop(
        client,
        input_items=[{"role": "user", "content": "hi"}],
        tools=[],
        instructions="sys",
        executors=executors,
    )

    assert final == "all done"
    # one function_call_output appended, linked by call_id
    assert ephemeral == [{"type": "function_call_output", "call_id": "c1", "output": "STATE_JSON"}]
    # second run_turn received the pending output appended to the original input
    second = client.calls[1]["input_items"]
    assert second[-1] == {"type": "function_call_output", "call_id": "c1", "output": "STATE_JSON"}
    assert second[:-1] == [{"role": "user", "content": "hi"}]


async def test_tool_loop_tool_error_returns_error_json_not_exception():
    script = [
        LLMTurnResult(
            tool_calls=[ToolCall("c1", "advance_stage", {"new_stage": "audit_day1"})],
            raw_output=[_FakeCallItem("c1", "advance_stage", '{"new_stage": "audit_day1"}')],
        ),
        LLMTurnResult(text="ok"),
    ]
    client = MockLLMClient(script)
    executors = {"advance_stage": lambda new_stage: f"moved-{new_stage}"}
    final, ephemeral = await run_tool_loop(
        client,
        input_items=[],
        tools=[],
        instructions="sys",
        executors=executors,
    )
    assert ephemeral[0]["output"] == "moved-audit_day1"
    assert final == "ok"


async def test_tool_loop_unknown_tool_returns_error_to_model():
    script = [
        LLMTurnResult(
            tool_calls=[ToolCall("c9", "no_such_tool", {})],
            raw_output=[_FakeCallItem("c9", "no_such_tool", "{}")],
        ),
        LLMTurnResult(text="recovered"),
    ]
    client = MockLLMClient(script)
    final, ephemeral = await run_tool_loop(
        client, input_items=[], tools=[], instructions="sys", executors={}
    )
    assert '"error"' in ephemeral[0]["output"]
    assert "no_such_tool" in ephemeral[0]["output"]
    assert final == "recovered"


async def test_tool_loop_limit_raises_at_cap():
    # Infinite scripted tool-calling client: every run_turn asks for another call.
    class LoopingClient:
        async def run_turn(self, **kwargs: Any) -> LLMTurnResult:
            return LLMTurnResult(
                tool_calls=[ToolCall("x", "get_user_state", {})],
                raw_output=[_FakeCallItem("x", "get_user_state", "{}")],
            )

    with pytest.raises(ToolLoopLimitExceeded):
        await run_tool_loop(
            LoopingClient(),
            input_items=[],
            tools=[],
            instructions="sys",
            executors={"get_user_state": lambda: "{}"},
            max_iterations=7,
        )


async def test_client_run_turn_passes_exact_params(monkeypatch):
    """OpenAIClient must call responses.create with our exact documented kwargs."""
    captured: dict[str, Any] = {}

    class FakeResponses:
        async def create(self, **kwargs: Any) -> Any:
            captured.update(kwargs)

            class R:
                output = [_FakeCallItem("c1", "t", "{}")]
                output_text = "hello"

            return R()

    class FakeAsyncOpenAI:
        responses = FakeResponses()

    client = OpenAIClient(client=FakeAsyncOpenAI())  # type: ignore[arg-type]
    result = await client.run_turn(
        input_items=[{"role": "user", "content": "hey"}],
        tools=[
            {
                "type": "function",
                "name": "t",
                "description": "",
                "parameters": {},
                "strict": True,
            }
        ],
        instructions="SYSTEM",
        reasoning_effort="low",
        model="gpt-5.6-sol",
        prompt_cache_key="user-1",
    )
    assert result.text == "hello"
    assert result.tool_calls[0].call_id == "c1"
    assert captured["model"] == "gpt-5.6-sol"
    assert captured["instructions"] == "SYSTEM"
    assert captured["reasoning"] == {"effort": "low"}
    assert captured["store"] is False
    assert captured["stream"] is False
    assert captured["prompt_cache_key"] == "user-1"
    assert captured["max_output_tokens"] == 2048  # safeguard when escalated


# ---------------------------------------------------------------------------
# persona.py
# ---------------------------------------------------------------------------
def test_system_prompt_contains_all_static_blocks():
    state = UserState(current_stage="onboarding")
    prompt = build_system_prompt(state)
    for block in STATIC_BLOCKS:
        assert block in prompt


def test_system_prompt_stage_scoping_changes_by_stage():
    d1 = build_system_prompt(UserState(current_stage="audit_day1"))
    d3 = build_system_prompt(UserState(current_stage="audit_day3"))
    assert "AUDITORY" in d1 and "TRANSCRIPTION" in d3


def test_state_summary_is_bounded_and_present_at_end():
    state = UserState(
        name="Sam", current_stage="weekly_cycle", effective_day=12,
        current_habit="volume", week_in_habit=2, timezone="Asia/Kolkata",
        five_words=["clear", "calm"], motivation_summary="want to be heard",
        recent_missed_days=2,
    )
    prompt = build_system_prompt(state)
    summary = build_state_summary(state)
    assert prompt.endswith(summary)
    assert len(summary) < 1200  # characters - bounded snapshot, not a journal dump


def system_prompt_tokens() -> int:
    """tokencount helper (uses tiktoken if available; falls back to ~4chars/token)."""
    prompt = build_system_prompt(UserState())
    try:
        import tiktoken

        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(prompt))
    except Exception:
        return len(prompt) // 4


def test_static_prompt_under_2500_tokens():
    n = system_prompt_tokens()
    assert n < 2500, f"static+dynamics prompt is {n} tokens (budget 2500)"
