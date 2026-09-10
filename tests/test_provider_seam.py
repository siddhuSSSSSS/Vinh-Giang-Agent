"""Phase 6.c tests - the provider seam (OpenCode Zen / custom base URLs)."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot import config  # noqa: E402
from bot.analysis.voice_fallback import transcript_client  # noqa: E402
from bot.llm.client import OpenAIClient  # noqa: E402


class _FakeResp:
    def __init__(self) -> None:
        self.output: list[Any] = []
        self.output_text = "ok"


class _FakeResponses:
    def __init__(self) -> None:
        self.captured: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> _FakeResp:
        self.captured = kwargs
        return _FakeResp()


class _FakeAsyncOpenAI:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


# ---------------------------------------------------------------------------
# run_turn param assembly: what is sent to which backend
# ---------------------------------------------------------------------------
async def test_openai_direct_keeps_store_and_cache_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_BASE_URL", "")
    c = OpenAIClient(client=_FakeAsyncOpenAI())  # type: ignore[arg-type]
    await c.run_turn([{"role": "user", "content": "x"}], [], "sys", "none", None, "u1")
    captured = c._client.responses.captured
    assert captured["store"] is False
    assert captured["prompt_cache_key"] == "u1"
    assert "reasoning" not in captured  # effort none -> omitted, not {effort:none}


async def test_custom_base_strips_store_and_cache_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://opencode.ai/zen/v1")
    c = OpenAIClient(client=_FakeAsyncOpenAI())  # type: ignore[arg-type]
    await c.run_turn([{"role": "user", "content": "x"}], [], "sys", "none", None, "u1")
    captured = c._client.responses.captured
    assert "store" not in captured  # Zen rejects it
    assert "prompt_cache_key" not in captured  # Zen rejects it
    assert "reasoning" not in captured  # effort none -> omitted (Zen: no null)
    assert captured["stream"] is False


async def test_escalated_effort_still_sends_reasoning_and_cap(monkeypatch):
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://opencode.ai/zen/v1")
    c = OpenAIClient(client=_FakeAsyncOpenAI())  # type: ignore[arg-type]
    await c.run_turn([], [], "sys", "low", None, None)
    captured = c._client.responses.captured
    assert captured["reasoning"] == {"effort": "low"}
    assert captured["max_output_tokens"] == 2048


async def test_tools_always_sent_when_present(monkeypatch):
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://opencode.ai/zen/v1")
    c = OpenAIClient(client=_FakeAsyncOpenAI())  # type: ignore[arg-type]
    tool = {"type": "function", "name": "n", "description": "d",
            "parameters": {"type": "object"}, "strict": False}
    await c.run_turn([], [tool], "sys", "none")
    assert c._client.responses.captured["tools"] == [tool]


# ---------------------------------------------------------------------------
# transcript_client: whisper-1 stays OpenAI-direct or degrades
# ---------------------------------------------------------------------------
def test_transcript_client_none_when_only_custom_backend(monkeypatch):
    monkeypatch.setattr(config, "TRANSCRIBE_API_KEY", "")
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://opencode.ai/zen/v1")
    monkeypatch.setattr(config, "LLM_API_KEY", "sk-custom")
    assert transcript_client() is None  # honest: no STT path


def test_transcript_client_uses_explicit_override(monkeypatch):
    monkeypatch.setattr(config, "TRANSCRIBE_API_KEY", "sk-stt")
    monkeypatch.setattr(config, "TRANSCRIBE_BASE_URL", "https://api.openai.com/v1")
    client = transcript_client()
    assert client is not None
    assert str(client.base_url).rstrip("/") == "https://api.openai.com/v1"


def test_transcript_client_falls_back_to_llm_key_when_openai_direct(monkeypatch):
    monkeypatch.setattr(config, "TRANSCRIBE_API_KEY", "")
    monkeypatch.setattr(config, "TRANSCRIBE_BASE_URL", "")
    monkeypatch.setattr(config, "LLM_BASE_URL", "")  # OpenAI direct
    monkeypatch.setattr(config, "LLM_API_KEY", "sk-llm")
    client = transcript_client()
    assert client is not None


# ---------------------------------------------------------------------------
# pre-flight 2 honors the seam (source-level, mirrors phase-6 test style)
# ---------------------------------------------------------------------------
def test_preflight_source_names_zen_seam():
    from bot import handlers

    src = inspect.getsource(handlers.post_init)
    assert "LLM_BASE_URL" in src and "LLM_API_KEY" in src


def test_client_uses_zen_model_defaults():
    # models come from config in every run_turn; nothing hardcodes openai.com
    src = inspect.getsource(OpenAIClient)
    assert "api.openai.com" not in src  # default comes from the SDK when unset
