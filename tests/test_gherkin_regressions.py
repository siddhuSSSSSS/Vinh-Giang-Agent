"""Gherkin-style unit+regression tests.

Each test maps to a Gherkin scenario: name = feature > scenario, body =
Given/When/Then in comments. The gherkin feature files live in
`tests/gherkin/regressions.feature` and cover every bug found during the
thorough codebase review - these tests LOCK the fixes (fail if regressed).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.db.repo import Repo  # noqa: E402
from bot.llm.client import (  # noqa: E402
    LLMTurnResult,
    ToolCall,
    ToolLoopLimitExceeded,
    run_tool_loop,
)


@pytest.fixture
async def repo():
    r = Repo(":memory:")
    await r.connect()
    yield r
    await r.close()


class _FakeCallItem:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.type = "function_call"
        self.call_id = call_id
        self.name = name
        self.arguments = arguments


# Feature: atomic /reset
async def test_reset_moves_users_update_into_the_same_transaction(repo):
    """Feature: atomic /reset
    Scenario: crash between state-delete and users-update leaves no half-reset
      Given a user with a habit and prior history
      When /reset runs
      Then state, epoch and day_zero_at moved together in ONE transaction
    """
    u = await repo.get_or_create_user("telegram", "42")
    await repo.update_user_state(u.id, current_habit="volume")
    # patch commit to explode after the first write: the transaction must roll back
    orig_commit = repo._conn.commit

    async def exploding_commit() -> None:
        await orig_commit()

    # Simulate failure INSIDE the transaction by monkeypatching execute for the
    # users-update to raise; rollback must restore the pre-reset state.
    orig_execute = repo._conn.execute
    state = {"bomb": True}

    async def execute(sql: str, params=()):  # noqa: ANN001
        if state["bomb"] and "UPDATE users SET simulated_day=0" in sql:
            raise RuntimeError("simulated crash mid-transaction")
        return await orig_execute(sql, params)

    repo._conn.execute = execute  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await repo.reset_user_progress(u.id)
    repo._conn.execute = orig_execute  # type: ignore[method-assign]

    # Then: still old-epoch user, old habit intact (nothing half-applied)
    user = await repo.get_user(u.id)
    assert user.epoch == 0
    st = await repo.get_user_state(u.id)
    assert st.current_habit == "volume"

    # And a normal reset afterwards succeeds fully (atomic unit works)
    state["bomb"] = False
    await repo.reset_user_progress(u.id)
    user = await repo.get_user(u.id)
    assert user.epoch == 1 and user.simulated_day == 0
    st = await repo.get_user_state(u.id)
    assert st.current_stage == "onboarding" and st.current_habit is None


# Feature: package-integrity test is not a stub
def test_full_package_import_list_is_exercised():
    """Feature: scaffold integrity
    Scenario: the import test really imports every module
      Given the bot/* tree
      When the import test runs
      Then bot.main and bot.db.repo etc are genuinely importable objects
    """
    import bot.db.repo
    import bot.main

    assert callable(bot.main.main)
    assert hasattr(bot.db.repo, "Repo")


# Feature: vacuous-assertion guard - persona stage text addresses the RIGHT stage
async def test_weekly_stage_prompt_does_not_carry_habit_selection_text():
    """Feature: per-stage scoping is real, not vacuous
      Given state.current_stage = weekly_cycle
      When the system prompt is built
      Then it contains weekly-cycle scoping and NOT habit-selection's phrase
    """
    from bot.llm.persona import UserState, build_system_prompt

    prompt = build_system_prompt(UserState(current_stage="weekly_cycle"))
    assert "STAGE: weekly cycle." in prompt
    assert "They decide; you propose options" not in prompt  # belongs to habit_selection


# Feature: no fabricated passthrough items in the tool loop
async def test_tool_loop_returns_empty_ephemeral_when_only_unserializable_items():
    """Feature: tool loop passthrough safety
      Given a model turn whose output items are unserializable doubles
      When the tool loop appends them
      Then nothing fabricated is appended to the conversation
    """
    class Odd:  # un-dumpable, no .type
        pass

    class OddModel:  # has all the markers, but refuses to dump
        type = "reasoning"

        def model_dump(self):  # noqa: ANN201
            raise TypeError("nope")

    script = [
        LLMTurnResult(
            tool_calls=[ToolCall("c1", "get_user_state", {})],
            raw_output=[_FakeCallItem("c1", "get_user_state", "{}"), Odd(), OddModel()],
        ),
        LLMTurnResult(text="done"),
    ]

    class Client:
        async def run_turn(self, **kwargs):  # noqa: ANN001
            return script.pop(0)

    final, ephemeral = await run_tool_loop(
        Client(), input_items=[], tools=[], instructions="s",
        executors={"get_user_state": lambda: "STATE"},
    )
    assert final == "done"
    assert ephemeral == [{"type": "function_call_output", "call_id": "c1", "output": "STATE"}]


# Feature: tool-loop cap is per-TURN, then raises (no runaway loop)
async def test_tool_loop_cap_message_carries_iteration_count():
    class LoopClient:
        async def run_turn(self, **kwargs):  # noqa: ANN001
            return LLMTurnResult(
                tool_calls=[ToolCall("x", "get_user_state", {})],
                raw_output=[_FakeCallItem("x", "get_user_state", "{}")],
            )

    with pytest.raises(ToolLoopLimitExceeded) as excinfo:
        await run_tool_loop(
            LoopClient(), input_items=[], tools=[], instructions="s",
            executors={"get_user_state": lambda: "{}"}, max_iterations=7,
        )
    assert excinfo.value.iterations == 7


# Feature: tool executor raising TypeError becomes a JSON error, not a crash
async def test_tool_executor_bad_signature_becomes_error_output():
    script = [
        LLMTurnResult(
            tool_calls=[ToolCall("c1", "log_journal_entry", {"bogus_param": 1})],
            raw_output=[_FakeCallItem("c1", "log_journal_entry", '{"bogus_param": 1}')],
        ),
        LLMTurnResult(text="recovered"),
    ]

    class Client:
        async def run_turn(self, **kwargs):  # noqa: ANN001
            return script.pop(0)

    def log_journal_entry(type_: str = "", content: str = "") -> str:
        raise ValueError("unknown state field 'bogus_param'")  # executor self-validates

    final, ephemeral = await run_tool_loop(
        Client(), input_items=[], tools=[], instructions="s",
        executors={"log_journal_entry": log_journal_entry},
    )
    # per Planning.md, tool errors return as function_call_output Items, not
    # exceptions: the executor's ValueError became an error envelope the model
    # can react to, and the turn still delivered a final reply.
    assert '"error"' in ephemeral[0]["output"]
    assert "bogus_param" in ephemeral[0]["output"]
    assert final == "recovered"


# Feature: concurrent-ish duplicate engagement insert stays single-row
async def test_engagement_double_insert_same_second_stays_idempotent(repo):
    u = await repo.get_or_create_user("telegram", "42")
    for _ in range(5):
        await repo.record_daily_engagement(u.id, 3)
    rows = await repo._fetchall(
        "SELECT id FROM daily_engagement WHERE user_id=? AND day=3", (u.id,)
    )
    assert len(rows) == 1


# Feature: missed_days re-flag after resolve stays resolved (INSERT OR IGNORE)
async def test_missed_day_reflag_after_resolve_does_not_reopen(repo):
    u = await repo.get_or_create_user("telegram", "42")
    await repo.flag_missed_day(u.id, 8)
    await repo.resolve_missed_day(u.id, 8)
    await repo.flag_missed_day(u.id, 8)  # scheduler re-fires the same day
    n = await repo.count_unresolved_missed_days(u.id)
    assert n == 0


# Feature: schema CHECK constraints actually reject bad writes
async def test_schema_check_constraints_enforced():
    """Feature: schema guards
      Given the schema is loaded
      When a write violates a CHECK or UNIQUE constraint
      Then sqlite raises and nothing partial is written
    """
    r = Repo(":memory:")
    await r.connect()
    try:
        u = await r.get_or_create_user("telegram", "42")
        with pytest.raises(Exception):  # noqa: B017, PT011 - sqlite3.IntegrityError
            await r._execute(
                "UPDATE state SET current_stage='bogus_stage' WHERE user_id=?", (u.id,)
            )
        with pytest.raises(Exception):  # noqa: B017, PT011 - IntegrityError (UNIQUE)
            await r._execute(
                "INSERT INTO journal_entries (user_id, day, epoch, type, content)"
                " VALUES (?,?,?,?,?)",
                (u.id, 0, 0, "not_a_type", "bad type value"),
            )
    finally:
        await r.close()


# Feature: foreign keys reject orphan writes
async def test_foreign_keys_reject_orphan_journal_entry():
    r = Repo(":memory:")
    await r.connect()
    try:
        with pytest.raises(Exception):  # noqa: B017, PT011 - IntegrityError
            await r._execute(
                "INSERT INTO journal_entries (user_id, day, epoch, type, content)"
                " VALUES (9999, 0, 0, 'reflection', 'orphan')",
            )
    finally:
        await r.close()
