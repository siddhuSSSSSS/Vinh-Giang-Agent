"""Executable Gherkin scenarios (tests/gherkin/scenarios.feature).

One test function per Scenario; Given/When/Then live in the .feature file and
in test comments/codematch here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.db.repo import Repo, day_from_day_zero, local_midnight_iso  # noqa: E402


@pytest.fixture
async def repo():
    r = Repo(":memory:")
    await r.connect()
    yield r
    await r.close()


# Scenario: timezone first-set signal fires exactly once
async def test_timezone_first_set_signal_exactly_once(repo):
    u = await repo.get_or_create_user("telegram", "42")
    first = await repo.set_timezone(u.id, "Asia/Kolkata")
    second = await repo.set_timezone(u.id, "Europe/Berlin")
    assert first is True and second is False
    user = await repo.get_user(u.id)
    assert user.timezone == "Europe/Berlin"  # later sets overwrite, don't stack


# Scenario: /advance bumps offset without touching engagement
async def test_advance_bumps_offset_only(repo):
    u = await repo.get_or_create_user("telegram", "42")
    await repo.update_passcode_state(u.id, verified_delta=1)
    before_msg = (await repo.get_user(u.id)).last_message_at
    await repo.record_daily_engagement(u.id, 1)
    n_before = (
        await repo._fetchone("SELECT COUNT(*) AS n FROM daily_engagement WHERE user_id=?", (u.id,))
    )["n"]

    await repo.bump_simulated_day(u.id, 5)

    user = await repo.get_user(u.id)
    assert user.simulated_day == 5
    eff = day_from_day_zero(user.day_zero_at, user.simulated_day)
    eff_before = day_from_day_zero(
        user.day_zero_at, 0
    )  # offset 0 contrast would be per-day; formula sanity:
    assert eff >= eff_before
    n_after = (
        await repo._fetchone("SELECT COUNT(*) AS n FROM daily_engagement WHERE user_id=?", (u.id,))
    )["n"]
    assert n_before == n_after == 1
    assert user.last_message_at == before_msg


# Scenario: Week-start transition-day guard (Phase 4's check lives on data here)
async def test_weekly_transition_day_not_flagged_by_condition(repo):
    """Phase 4's guard: day-1 > weekly_cycle_started_effective_day must hold BEFORE
    flagging. The data contract: weekly_cycle_started_effective_day is stored on
    state and set at the same moment as the stage advance."""
    u = await repo.get_or_create_user("telegram", "42")
    await repo.update_user_state(
        u.id, current_stage="weekly_cycle", weekly_cycle_started_effective_day=10
    )
    st = await repo.get_user_state(u.id)
    transition_day = 10
    # guard expression exactly as Phase 4's rule will evaluate it:
    would_flag = transition_day - 1 > st.weekly_cycle_started_effective_day
    assert would_flag is False  # transition day itself is never flagged

    a_later_day = 12
    assert (a_later_day - 1) > st.weekly_cycle_started_effective_day  # normal flag days clear


# Scenario: metric trend respects the limit parameter
async def test_metric_trend_default_limit_8(repo):
    u = await repo.get_or_create_user("telegram", "42")
    for d in range(12):
        eid = await repo.log_journal_entry(u.id, d, "transcript", f"day {d}")
        await repo.record_entry_metrics(eid, {"filler_word_count": float(d)})
    trend = await repo.get_metric_trend(u.id, "filler_word_count")
    assert trend == [(d, float(d)) for d in range(4, 12)]  # last 8, oldest->newest


# Scenario: journal bool tri-state
async def test_journal_bool_tri_state(repo):
    u = await repo.get_or_create_user("telegram", "42")
    for completed, expected in [(True, 1), (False, 0), (None, None)]:
        eid = await repo.log_journal_entry(
            u.id, 0, "exercise", "wallpaper", completed=completed, reason=None
        )
        row = await repo._fetchone(
            "SELECT completed FROM journal_entries WHERE id=?", (eid,)
        )
        assert row["completed"] == expected


# Scenario: summary chunk marking is idempotent
async def test_summary_fold_idempotent(repo):
    u = await repo.get_or_create_user("telegram", "42")
    ids = [
        await repo.append_conversation_message(u.id, "user", f"m{i}") for i in range(4)
    ]
    await repo.append_summary_chunk(u.id, "chunk1", ids[0], ids[1])
    await repo.mark_messages_folded(ids[:2])
    await repo.mark_messages_folded(ids[:2])  # double-run must be harmless
    msgs = await repo.get_recent_messages(u.id, limit=10)
    assert [m["content"] for m in msgs] == ["m2", "m3"]
    assert await repo.get_summary_chunks(u.id) == ["chunk1"]


# Scenario: composite user identity
async def test_composite_platform_identity(repo):
    a = await repo.get_or_create_user("telegram", "42")
    b = await repo.get_or_create_user("hilos", "42")
    assert a.id != b.id
    await repo.update_user_state(a.id, current_habit="volume")
    st_b = await repo.get_user_state(b.id)
    assert st_b.current_habit is None  # state didn't cross identity boundary


# extra: local_midnight_iso rejects naive timestamps gone-wrong (fresh eyes check)
def test_local_midnight_iso_utc_passthrough_without_tz():
    from datetime import UTC, datetime

    now = datetime(2026, 9, 9, 23, 59, tzinfo=UTC)
    assert local_midnight_iso(None, now=now).startswith("2026-09-09T23:59:00+00:00")
