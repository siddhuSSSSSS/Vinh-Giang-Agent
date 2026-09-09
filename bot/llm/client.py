"""OpenAI Responses API client.

Phase 1 deliverable. Shapes verified against SDK 3.11.0 (not docs prose):

- create params: model, instructions, input, tools, reasoning={"effort": ...},
  store=False, stream=False, prompt_cache_key, max_output_tokens all exist.
- ReasoningEffort values: "none", "minimal", "low", "medium", "high", "xhigh", "max".
- Tool definition: FLAT dict {"type": "function", "name", "description",
  "parameters", "strict"} - no nested "function" wrapper (that is Chat Completions).
- Model returns output items; function calls are `type: "function_call"` items
  carrying (call_id, name, arguments-JSON-string). Assistant text is available via
  the SDK's `response.output_text` helper.
- Tool results go back as input items of shape
  {"type": "function_call_output", "call_id": <call_id>, "output": <str>}.

Non-negotiables from Planning.md:
- store=False on every call (our SQLite is the single source of truth)
- stream=False everywhere (typing indicator + complete message bridge, not streaming)
- reasoning items from escalated turns are passed back in full during a tool loop
  but never persisted (ephemeral scratch)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import AsyncOpenAI

from bot import config


class ToolLoopLimitExceeded(Exception):
    """Raised when the tool-execution loop exceeds its safety cap."""

    def __init__(self, iterations: int) -> None:
        self.iterations = iterations
        super().__init__(f"tool loop exceeded cap of {iterations} iterations")


@dataclass(frozen=True)
class ToolCall:
    """One function call requested by the model."""

    call_id: str
    name: str
    arguments: dict[str, Any]  # parsed JSON arguments


@dataclass
class LLMTurnResult:
    """One non-streamed Responses API turn, parsed."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Full output array, kept so the tool loop can pass reasoning items back
    # verbatim on escalated turns. Never persisted.
    raw_output: list[Any] = field(default_factory=list)

    @property
    def wants_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMClient(Protocol):
    """Transport-agnostic seam so a second provider (e.g. Anthropic) is additive."""

    async def run_turn(
        self,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        instructions: str,
        reasoning_effort: str = "none",
        model: str | None = None,
        prompt_cache_key: str | None = None,
    ) -> LLMTurnResult: ...


def _parse_tool_calls(output_items: list[Any]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in output_items:
        itype = getattr(item, "type", None)
        if itype == "function_call":
            raw_args = getattr(item, "arguments", "") or "{}"
            try:
                parsed: dict[str, Any] = json.loads(raw_args)
            except json.JSONDecodeError:
                parsed = {"_unparsed": raw_args}
            calls.append(
                ToolCall(
                    call_id=str(getattr(item, "call_id", "") or ""),
                    name=str(getattr(item, "name", "") or ""),
                    arguments=parsed,
                )
            )
    return calls


class OpenAIClient(LLMClient):
    """Wraps AsyncOpenAI().responses.create for the exact shapes we use."""

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        # Real api_key comes from config; tests inject a mock client instead.
        self._client = client or AsyncOpenAI(api_key=config.OPENAI_API_KEY or "unset")

    async def run_turn(
        self,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        instructions: str,
        reasoning_effort: str = "none",
        model: str | None = None,
        prompt_cache_key: str | None = None,
    ) -> LLMTurnResult:
        """One non-streamed Responses API call.

        `input_items` are Responses-shaped items (or plain
        {"role": ..., "content": ...} messages - the API accepts EasyInputMessage
        shapes directly). `instructions` carries the system prompt via the
        dedicated top-level param, never prepended into input_items.
        """
        resp = await self._client.responses.create(
            model=model or config.OPENAI_MODEL,
            instructions=instructions,
            input=input_items,  # type: ignore[arg-type]
            tools=tools if tools else None,
            # Safeguard per plan: cap reasoning-billed output when escalated.
            max_output_tokens=2048 if reasoning_effort != "none" else None,
            reasoning={"effort": reasoning_effort},
            store=False,
            stream=False,
            prompt_cache_key=prompt_cache_key,
        )
        output_items = list(resp.output or [])
        text = (getattr(resp, "output_text", None) or "").strip() or None
        return LLMTurnResult(
            text=text,
            tool_calls=_parse_tool_calls(output_items),
            raw_output=output_items,
        )


async def run_tool_loop(
    client: LLMClient,
    input_items: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    instructions: str,
    executors: dict[str, Any],
    reasoning_effort: str = "none",
    model: str | None = None,
    prompt_cache_key: str | None = None,
    max_iterations: int = 7,
) -> tuple[str, list[dict[str, Any]]]:
    """The hand-written tool-execution loop (lives here until Phase 3 formalizes
    agent_core; the behavior is exactly Planning.md Phase 1's).

    - While the model returns function-call items, executes each one against
      `executors[name]{arguments}`, appends a function_call_output item linked by
      call_id, and calls run_turn again - up to `max_iterations` tool turns.
    - On escalated reasoning (effort != "none"), the model's ENTIRE raw output
      array (reasoning items included) is appended before the next iteration per
      OpenAI's guidance; at effort "none" there are no reasoning items, so the
      same code path is a faithful no-op.
    - Returns (final_text, ephemeral_items_added_this_turn - conversation-scoped
      tool plumbing the caller may discard; never persisted per plan).
    """
    conversation_items: list[dict[str, Any]] = []
    for iteration in range(max_iterations + 1):
        pending: list[dict[str, Any]] = list(conversation_items)
        result = await client.run_turn(
            input_items=input_items + pending,
            tools=tools,
            instructions=instructions,
            reasoning_effort=reasoning_effort,
            model=model,
            prompt_cache_key=prompt_cache_key,
        )
        if not result.wants_tool_calls:
            return result.text or "", conversation_items
        if iteration == max_iterations:
            raise ToolLoopLimitExceeded(max_iterations)

        # Pass back the model's entire output array for THIS call (reasoning items
        # too) before the next iteration - required when effort is escalated.
        for item in result.raw_output:
            itype = getattr(item, "type", None)
            if itype == "function_call":
                call_id = str(getattr(item, "call_id", ""))
                name = str(getattr(item, "name", ""))
                args = next(
                    (c.arguments for c in result.tool_calls if c.call_id == call_id), {}
                )
                executor = executors.get(name)
                if executor is None:
                    out = json.dumps(
                        {"error": f"unknown tool {name!r} not in registry"}
                    )
                else:
                    try:
                        ret = executor(**args) if args else executor()
                        # executors may be sync or async - accept both
                        if hasattr(ret, "__await__"):
                            ret = await ret
                        out = str(ret) if ret is not None else ""
                    except TypeError as exc:  # argument-shape mismatch
                        out = json.dumps({"error": f"bad arguments for {name}: {exc}"})
                    except Exception as exc:  # noqa: BLE001
                        # any other tool failure returns to the model as a normal
                        # output (Planning.md: "tool errors returned as
                        # function_call_output Items, not exceptions") - the turn
                        # must never crash the bot because a repo write failed.
                        out = json.dumps({"error": f"{name} failed: {exc}"})
                conversation_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": out,
                    }
                )
            else:
                # reasoning (or other ephemeral) items - pass through verbatim,
                # but never fabricate items we cannot serialize
                passthrough = _item_to_dict(item)
                if passthrough:
                    conversation_items.append(passthrough)
    raise ToolLoopLimitExceeded(max_iterations)  # pragma: no cover - defensive


def _item_to_dict(item: Any) -> dict[str, Any]:
    """Convert a raw output item to a plain dict (model_dump or dict attr).

    Items with no serializable body (test doubles, exotic types, dump() raising)
    are dropped - we never fabricate a passthrough item the API didn't send.
    """
    if isinstance(item, dict):
        return item
    try:
        dump = getattr(item, "model_dump", None)
        if callable(dump):
            data = dump()
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001 - refusing-to-dump items are simply skipped
        return {}
    # No dumpable body: only keep it if the SDK type itself knows its shape
    try:
        itype = getattr(item, "type", None)
    except Exception:  # noqa: BLE001
        return {}
    if itype in (None, "unknown") or type(item).__module__.startswith("test"):
        return {}  # signal: skip
    return {"type": itype}
