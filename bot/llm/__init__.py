"""LLM layer: Responses API client + persona builder.

Phase 0 scaffold stub.
- client.py (Phase 1): LLMClient protocol, OpenAIClient wrapping
  AsyncOpenAI().responses.create(..., store=False, stream=False),
  reasoning_effort routing, ToolLoopLimitExceeded.
- persona.py (Phase 1): build_system_prompt() - condensed Video.md knowledge base,
  9 behavioral principles (terse imperative form), per-stage scoping, static
  portion under ~2500 tokens (verified via tiktoken in a unit test).
"""
