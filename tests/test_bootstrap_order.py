"""Regression: the real run_polling bootstrap order.

The first true `python -m bot.main` smoke test (Windows dev box + Ubuntu VPS,
PTB 22.8) crashed with KeyError: 'repo' because run() wired handlers before
post_init seeded bot_data["repo"]. These tests pin the contract so the
bootstrap can't silently regress.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

import bot.handlers as handlers


def test_run_registers_wiring_in_post_init_not_run() -> None:
    """run() must NOT call build_agent/register_handlers before post_init.

    build_agent reads bot_data["repo"], which only exists after post_init
    opens the repo - pre-post_init wiring is the exact KeyError traceback.
    """
    # run() is a plain sync function; strip comments, then assert the wiring
    # calls never appear in live code (only in the explaining comment).
    run_src = inspect.getsource(handlers.run)
    code_only = "\n".join(
        ln.split("#")[0].rstrip() for ln in run_src.splitlines()
    )
    assert "build_agent" not in code_only and "register_handlers" not in code_only, (
        "run() wires handlers before post_init - bot_data['repo'] is not "
        "seeded yet and the bot crashes at startup (KeyError: 'repo')"
    )


def test_post_init_wires_handlers_after_seeding_repo() -> None:
    """post_init must seed repo BEFORE calling build_agent (source order)."""
    post_src = inspect.getsource(handlers.post_init)
    seed_idx = post_src.index('app.bot_data["repo"]')
    wire_idx = post_src.index("build_agent")
    assert seed_idx < wire_idx, (
        "post_init must seed bot_data['repo'] BEFORE build_agent reads it"
    )


@pytest.mark.asyncio
async def test_post_init_seeds_repo_then_agent(monkeypatch: Any) -> None:
    """Behavioral check with stubs: post_init leaves bot_data fully populated."""
    seeded: dict[str, Any] = {}
    wired: list[str] = []

    class FakeRepo:
        async def close(self) -> None:
            pass

        async def get_users_in_stage(self, _stage: str) -> list[Any]:
            return []  # no waiting_24h users in the stub post_init

    class FakeMe:
        username = "vins_sidekick_test"

    class FakeBot:
        async def get_me(self) -> FakeMe:
            return FakeMe()

    class FakeApp:
        bot = FakeBot()
        bot_data = seeded
        stop_running_calls = 0

        async def stop_running(self) -> None:
            self.stop_running_calls += 1

        class _FakeJobQueue:  # scheduler.schedule_hourly_sweep touches this
            def run_repeating(self, *_a: Any, **_k: Any) -> None:
                pass

            def run_once(self, *_a: Any, **_k: Any) -> None:
                pass

        job_queue = _FakeJobQueue()

    class FakeProbeModels:
        async def list(self) -> list[int]:
            return []

    class FakeProbe:
        models = FakeProbeModels()

    fake_app = FakeApp()

    # stub external effects: repo open, telegram get_me, openai models probe
    async def fake_open_repo(_path: str) -> FakeRepo:
        return FakeRepo()

    monkeypatch.setattr(handlers, "open_repo", fake_open_repo, raising=False)
    # open_repo is imported inside post_init from bot.db.repo; patch source
    import bot.db.repo as repo_mod

    monkeypatch.setattr(repo_mod, "open_repo", fake_open_repo)

    import openai as openai_mod

    monkeypatch.setattr(
        openai_mod, "AsyncOpenAI", lambda **_kw: FakeProbe(), raising=False
    )
    monkeypatch.setattr(handlers, "AsyncOpenAI", FakeProbe, raising=False)

    # stub LLM probe + wiring so only ordering is exercised
    orig_build = handlers.build_agent
    orig_register = handlers.register_handlers

    def fake_build(_app: Any) -> str:
        assert seeded.get("repo") is not None, (
            "build_agent called before bot_data['repo'] was seeded"
        )
        return "agent-sentinel"

    def fake_register(app: Any, agent: str) -> None:
        wired.append(agent)
        app.bot_data["agent"] = agent

    monkeypatch.setattr(handlers, "build_agent", fake_build)
    monkeypatch.setattr(handlers, "register_handlers", fake_register)

    try:
        await handlers.post_init(fake_app)
    finally:
        monkeypatch.setattr(handlers, "build_agent", orig_build, raising=False)
        monkeypatch.setattr(handlers, "register_handlers", orig_register, raising=False)

    assert seeded.get("repo") is not None
    assert wired == ["agent-sentinel"]
    assert seeded.get("agent") == "agent-sentinel"
    assert fake_app.stop_running_calls == 0, "pre-flight 2 must not abort on stub"


def test_build_agent_raises_when_repo_missing() -> None:
    """build_agent without a seeded repo must raise KeyError (contract keep)."""

    class EmptyApp:
        bot_data: dict[str, Any] = {}

    with pytest.raises(KeyError):
        handlers.build_agent(EmptyApp())
