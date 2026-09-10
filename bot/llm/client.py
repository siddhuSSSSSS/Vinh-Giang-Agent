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

logger = __import__("logging").getLogger(__name__)


def _opencode_session_default() -> str:
    """Stable fallback x-opencode-session ID for OpenCode Go.

    Go requires the header since 2026-09-05. Per-request calls override it
    with the caller's prompt_cache_key (user key) when present.
    """
    import uuid

    return "vins-sidekick-" + uuid.UUID(int=0).hex[:12]


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
    """Wraps AsyncOpenAI().responses.create for the exact shapes we use.

    Phase 6.c provider seam: with LLM_BASE_URL set (e.g. OpenCode Go at
    https://opencode.ai/zen/go/v1), the same client object targets that
    backend. Proxy backends reject `store`/`prompt_cache_key`, so those are
    stripped (no-ops for us regardless: our SQLite is the single source of
    truth). There is no `effort:"none"` semantics on Zen/Go - the param is
    simply omitted at effort "none".

    OpenCode Go contract (since 2026-09-05): EVERY request must carry an
    `x-opencode-session` header - one stable ID per conversation, used for
    routing and prompt caching. We map it to the caller's prompt_cache_key
    (= user/thread key) so caching lands where it belongs; absent that, a
    stable per-process fallback keeps the bot routable.
    """

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        # Real api_key comes from config; tests inject a mock client instead.
        if client is not None:
            self._client = client
            self._custom_base = bool(config.LLM_BASE_URL)
        else:
            kwargs: dict[str, Any] = {"api_key": config.LLM_API_KEY or "unset"}
            if config.LLM_BASE_URL:
                kwargs["base_url"] = config.LLM_BASE_URL
                session_id = _opencode_session_default()
                kwargs["default_headers"] = {"x-opencode-session": session_id}
                logger.info(
                    "LLM backend: %s (opencode-session=%s...)",
                    config.LLM_BASE_URL,
                    session_id[:12],
                )
            self._client = AsyncOpenAI(**kwargs)
            self._custom_base = bool(config.LLM_BASE_URL)

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
        # Build the request body explicitly (Phase 6.c):
        # - At effort "none", OMIT reasoning entirely: OpenAI treats it the
        #   same as {"effort":"none"}, and Zen rejects reasoning: null.
        # - store=False is OpenAI-opt-out-of-server-storage; Zen rejects it.
        # - prompt_cache_key: cache hint; Zen rejects it. Only sent to OpenAI.
        create_kwargs: dict[str, Any] = {
            "model": model or config.OPENAI_MODEL,
            "instructions": instructions,
            "input": input_items,  # type: ignore[arg-type]
            "stream": False,
        }
        if reasoning_effort != "none":
            create_kwargs["reasoning"] = {"effort": reasoning_effort}
            # Safeguard per plan: cap reasoning-billed output when escalated.
            create_kwargs["max_output_tokens"] = 2048
        if tools:
            create_kwargs["tools"] = tools
        if not self._custom_base:  # OpenAI-direct extras (no-ops elsewhere)
            create_kwargs["store"] = False
            create_kwargs["prompt_cache_key"] = prompt_cache_key

        # OpenCode Go: every request needs x-opencode-session (since
        # 2026-09-05). Per-CONVERSATION identity: prompt_cache_key carries the
        # user's cache key from agent_core, so it is exactly the stable ID Go
        # wants for routing + prompt caching.
        if self._custom_base and prompt_cache_key:
            create_kwargs["extra_headers"] = {
                "x-opencode-session": f"vins-{prompt_cache_key}"
            }

        resp = await self._client.responses.create(**create_kwargs)
        output_items = list(resp.output or [])
        text = (getattr(resp, "output_text", None) or "").strip() or None
        return LLMTurnResult(
            text=text,
            tool_calls=_parse_tool_calls(output_items),
            raw_output=output_items,
        )


_ZEN_BILLING_URL = "https://opencode.ai/workspace/wrk_01KF8AGRK3640Z2PPK9JA82RDW/billing"


def _credit_hint(exc: BaseException) -> str | None:
    """Zen's CreditsError surfaces as a 401 with its own JSON error body.

    The SDK raises a generic AuthenticationError for it - we map the known
    case to an actionable hint, everything else stays untouched.
    """
    if "CreditsError" in str(exc) or "Insufficient balance" in str(exc):
        return f"LLM backend has no credits - top up at {_ZEN_BILLING_URL}"
    return None


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
    strip_status: bool = False,
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
                if strip_status:
                    # OpenAI-direct: the API pairs function_call_output with the
                    # call it just returned automatically. Go's upstream does
                    # NOT - it errors "No tool call found for function call
                    # output" unless the matching function_call item is present
                    # in the same request. So echo the call item (minus its own
                    # `status`, per the strip_status contract above) ahead of
                    # the output item.
                    call_item = _item_to_dict(item, strip_status=True)
                    if call_item:
                        conversation_items.append(call_item)
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
                passthrough = _item_to_dict(item, strip_status=strip_status)
                if passthrough:
                    conversation_items.append(passthrough)
    raise ToolLoopLimitExceeded(max_iterations)  # pragma: no cover - defensive


def _item_to_dict(item: Any, *, strip_status: bool = False) -> dict[str, Any]:
    """Convert a raw output item to a plain dict (model_dump or dict attr).

    Items with no serializable body (test doubles, exotic types, dump() raising)
    are dropped - we never fabricate a passthrough item the API didn't send.

    strip_status: OpenCode Go's upstream rejects `status` on pass-backed items
    ("Unknown parameter: input[N].status") even though Go itself returns that
    field - we round-trip everything Go sends and its own validator calls
    foul on its own fields. Dropping `status` on custom backends is honest
    (we don't rely on it) and required for the tool loop to work there.
    """
    if isinstance(item, dict):
        data = item
    else:
        try:
            dump = getattr(item, "model_dump", None)
            if callable(dump):
                data = dump()
                if not isinstance(data, dict):
                    return {}
            else:
                return {}
        except Exception:  # noqa: BLE001 - refusing-to-dump items are simply skipped
            return {}
    if strip_status:
        data.pop("status", None)
        # SDK quirk: pydantic renames the `async` field to `async_` (python
        # keyword); Go's upstream expects the wire name. Un-rename it.
        if "async_" in data:
            data["async"] = data.pop("async_")
    return data
