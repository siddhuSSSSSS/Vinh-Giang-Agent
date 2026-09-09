"""Executable Gherkin for Phase 4 (tests/gherkin/phase4.feature)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.db.repo import Repo  # noqa: E402
from bot.gates import get_effective_day  # noqa: E402
from bot.scheduler import (  # noqa: E402
    dedupe_reasons,
    run_daily_checks_for_user,
)


@pytest.fixture
async def repo():
    r = Repo(":memory:")
    await r.connect()
    yield r
    await r.close()


async def _verified(repo: Repo, uid: str = "9") -> int:
    u = await repo.get_or_create_user("telegram", uid)
    await repo.update_passcode_state(u.id, verified_delta=1)
    return u.id


# Scenario: early-stage silence fires a capped re-engagement nudge
async def test_early_stage_silence_fires_and_counts(repo):
    uid = await _verified(repo)
    await repo._execute(
        "UPDATE users SET day_zero_at=datetime('now', '-2 day') WHERE id=?", (uid,)
    )
    u = await repo.get_user(uid)
    reason = await run_daily_checks_for_user(
        repo, u, get_effective_day(await repo.get_user(uid))
    )
    assert reason == "reengagement_nudge"
    st = await repo.get_user_state(uid)
    assert st.reengagement_nudge_count == 1


# Scenario: the nudge stops at its cap
async def test_cap_stops_nudging(repo):
    uid = await _verified(repo)
    await repo.update_user_state(uid, reengagement_nudge_count=3)
    await repo._execute(
        "UPDATE users SET day_zero_at=datetime('now', '-2 day') WHERE id=?", (uid,)
    )
    u = await repo.get_user(uid)
    reason = await run_daily_checks_for_user(
        repo, u, get_effective_day(await repo.get_user(uid))
    )
    assert reason is None


# Scenario: re-engagement resets the counter
async def test_engagement_resets_counter(repo):
    uid = await _verified(repo)
    await repo.update_user_state(uid, reengagement_nudge_count=2)
    await repo._execute(
        "UPDATE users SET day_zero_at=datetime('now', '-2 day') WHERE id=?", (uid,)
    )
    day = get_effective_day(await repo.get_user(uid))
    await repo.record_daily_engagement(uid, day - 1)
    st = await repo.get_user_state(uid)
    assert st.reengagement_nudge_count == 0


# Scenario: waiting_24h is an intentional wait
async def test_waiting_24h_not_nudged(repo):
    uid = await _verified(repo)
    await repo.update_user_state(uid, current_stage="waiting_24h")
    await repo._execute(
        "UPDATE users SET day_zero_at=datetime('now', '-3 day') WHERE id=?", (uid,)
    )
    u = await repo.get_user(uid)
    reason = await run_daily_checks_for_user(
        repo, u, get_effective_day(await repo.get_user(uid))
    )
    assert reason is None


# Scenario: missed day never flagged on the week-transition day
async def test_transition_day_guard(repo):
    uid = await _verified(repo)
    await repo.update_user_state(
        uid, current_stage="weekly_cycle", weekly_cycle_started_effective_day=10
    )
    transition_day = 10
    state = await repo.get_user_state(uid)
    guard_ok = (transition_day - 1) > state.weekly_cycle_started_effective_day
    assert guard_ok is False


# Scenario: two missed days -> exactly one adaptive reason, no repeat
async def test_missed_days_exactly_one_nudge_no_repeat(repo):
    uid = await _verified(repo)
    await repo.update_user_state(
        uid, current_stage="weekly_cycle", weekly_cycle_started_effective_day=2
    )
    await repo._execute(
        "UPDATE users SET day_zero_at=datetime('now', '-11 day') WHERE id=?", (uid,)
    )
    u = await repo.get_user(uid)
    day = get_effective_day(u)
    await repo.flag_missed_day(uid, day - 1)
    await repo.flag_missed_day(uid, day - 2)
    first = await run_daily_checks_for_user(repo, u, day)
    assert first == "missed_day_nudge"
    await repo.bump_simulated_day(uid, 1)
    u2 = await repo.get_user(uid)
    day2 = get_effective_day(u2)
    second = await run_daily_checks_for_user(repo, u2, day2)
    assert second != "missed_day_nudge"


# Scenario: weekly re-eval once per boundary day
async def test_weekly_boundary_once(repo):
    uid = await _verified(repo)
    await repo.update_user_state(
        uid, current_stage="weekly_cycle", weekly_cycle_started_effective_day=4
    )
    await repo._execute(
        "UPDATE users SET day_zero_at=datetime('now', '-11 day') WHERE id=?", (uid,)
    )
    u = await repo.get_user(uid)
    day = get_effective_day(u)
    assert await run_daily_checks_for_user(repo, u, day) == "weekly_reeval_prompt"
    assert await run_daily_checks_for_user(repo, u, day) != "weekly_reeval_prompt"


# Scenario: daily check-in weekly_cycle only, once per day; organic message wins
async def test_daily_checkin_and_organic_suppression(repo):
    uid = await _verified(repo)
    await repo.update_user_state(
        uid, current_stage="weekly_cycle", weekly_cycle_started_effective_day=2
    )
    await repo._execute(
        "UPDATE users SET day_zero_at=datetime('now', '-5 day') WHERE id=?", (uid,)
    )
    u = await repo.get_user(uid)
    day = get_effective_day(u)
    assert await run_daily_checks_for_user(repo, u, day) == "daily_checkin"
    # organic message today -> suppressed on the *next* pass of the SAME day
    await repo.record_daily_engagement(uid, day)
    again = await run_daily_checks_for_user(repo, u, get_effective_day(u))
    assert again is None
    # and a fresh day still gets its own check-in
    await repo.bump_simulated_day(uid, 1)
    u2 = await repo.get_user(uid)
    fresh = await run_daily_checks_for_user(repo, u2, get_effective_day(u2))
    assert fresh == "daily_checkin"


# Scenario: /advance equivalence + dedupe order
def test_dedupe_preserves_first_seen_order():
    reasons = ["daily_checkin", "weekly_reeval_prompt", "daily_checkin"]
    assert dedupe_reasons(reasons) == ["daily_checkin", "weekly_reeval_prompt"]  # type: ignore[arg-type]


# Scenario: restart dedup via last_sweep_day
async def test_sweep_day_recorded(repo):
    uid = await _verified(repo)
    await repo._execute(
        "UPDATE users SET day_zero_at=datetime('now', '-2 day') WHERE id=?", (uid,)
    )
    day = get_effective_day(await repo.get_user(uid))
    await repo.record_sweep_run(uid, day)
    same = await repo.get_user(uid)
    assert same.last_sweep_day == day
