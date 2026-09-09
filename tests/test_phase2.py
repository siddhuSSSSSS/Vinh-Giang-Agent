"""Phase 2 tests: schema, repo functions, epoch semantics, admin operations.

Per Planning.md: :memory: SQLite fixtures; scripted conversational scenarios
mock the LLM and assert on tool invocations + DB state (not model prose).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.db.repo import Repo, day_from_day_zero  # noqa: E402


@pytest.fixture
async def repo():
    r = Repo(":memory:")
    await r.connect()
    yield r
    await r.close()


# ---------------------------------------------------------------------------
# PRAGMAs + schema
# ---------------------------------------------------------------------------
@pytest.fixture
def real_db_path(tmp_path):
    """File-backed DB for WAL assertions (WAL is a no-op on :memory:)."""
    return str(tmp_path / "wal_test.db")


async def test_pragmas_memory_ok_but_wal_needs_file(repo, real_db_path):
    # :memory: is fine for everything except WAL persistence
    row = await repo._fetchone("PRAGMA foreign_keys")
    assert row[0] == 1
    row = await repo._fetchone("PRAGMA busy_timeout")
    assert row[0] == 5000
    file_repo = Repo(real_db_path)
    await file_repo.connect()
    try:
        row = await file_repo._fetchone("PRAGMA journal_mode")
        assert row[0].lower() == "wal"
    finally:
        await file_repo.close()


async def test_schema_created_all_tables(repo):
    rows = await repo._fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {r["name"] for r in rows}
    assert {
        "users", "state", "journal_entries", "entry_metrics", "media_refs",
        "missed_days", "daily_engagement", "conversation_messages", "summary_chunks",
    } <= names


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
async def test_get_or_create_user_is_idempotent(repo):
    u1 = await repo.get_or_create_user("telegram", "42")
    u2 = await repo.get_or_create_user("telegram", "42")
    assert u1.id == u2.id
    assert u1.day_zero_at is not None and u1.epoch == 0 and u1.simulated_day == 0
    assert u1.passcode_verified is False


async def test_get_verified_users_filters(repo):
    u = await repo.get_or_create_user("telegram", "42")
    empty = await repo.get_verified_users()
    assert empty == []
    await repo.update_passcode_state(u.id, verified_delta=1)
    assert len(await repo.get_verified_users()) == 1


# ---------------------------------------------------------------------------
# State routing (update_user_state's timezone -> users)
# ---------------------------------------------------------------------------
async def test_update_user_state_routes_timezone_to_users(repo):
    u = await repo.get_or_create_user("telegram", "42")
    await repo.update_user_state(u.id, timezone="Asia/Kolkata", current_habit="volume")
    user = await repo.get_user(u.id)
    assert user.timezone == "Asia/Kolkata"
    st = await repo.get_user_state(u.id)
    assert st.current_habit == "volume"


async def test_update_user_state_skips_none_values(repo):
    u = await repo.get_or_create_user("telegram", "42")
    await repo.update_user_state(u.id, current_habit="volume")
    # a null current_habit call must NOT wipe the previous value
    await repo.update_user_state(u.id, current_habit=None)
    st = await repo.get_user_state(u.id)
    assert st.current_habit == "volume"


async def test_update_user_state_rejects_unknown_field(repo):
    u = await repo.get_or_create_user("telegram", "42")
    with pytest.raises(ValueError):
        await repo.update_user_state(u.id, not_a_field=1)


# ---------------------------------------------------------------------------
# Journal + metrics + epoch filtering
# ---------------------------------------------------------------------------
async def test_journal_and_metric_trend_current_epoch_only(repo):
    u = await repo.get_or_create_user("telegram", "42")
    e1 = await repo.log_journal_entry(u.id, 0, "reflection", "baseline")
    await repo.record_entry_metrics(e1, {"filler_word_count": 36})
    # simulate later days
    for d, v in [(7, 28.0), (14, 22.0)]:
        eid = await repo.log_journal_entry(u.id, d, "transcript", f"week {d}")
        await repo.record_entry_metrics(eid, {"filler_word_count": v})

    trend = await repo.get_metric_trend(u.id, "filler_word_count")
    assert trend == [(0, 36.0), (7, 28.0), (14, 22.0)]

    # /reset increments epoch: old rows must vanish from trend queries
    await repo.reset_user_progress(u.id)
    assert await repo.get_metric_trend(u.id, "filler_word_count") == []
    # new-epoch writes land with the new epoch and don't interleave
    eid = await repo.log_journal_entry(u.id, 0, "transcript", "fresh run")
    await repo.record_entry_metrics(eid, {"filler_word_count": 5.0})
    assert await repo.get_metric_trend(u.id, "filler_word_count") == [(0, 5.0)]


async def test_baseline_and_latest_metrics(repo):
    u = await repo.get_or_create_user("telegram", "42")
    e1 = await repo.log_journal_entry(u.id, 0, "transcript", "b")
    await repo.record_entry_metrics(e1, {"filler_word_count": 36, "words_per_minute": 131})
    eid = await repo.log_journal_entry(u.id, 21, "transcript", "l")
    await repo.record_entry_metrics(eid, {"filler_word_count": 22})

    out = await repo.get_baseline_and_latest_metrics(
        u.id, ["filler_word_count", "words_per_minute", "nonexistent_metric"]
    )
    assert out["filler_word_count"] == {
        "baseline_day": 0, "baseline_value": 36.0, "latest_day": 21, "latest_value": 22.0,
    }
    # metric present only at baseline: baseline==latest, that's honest
    assert out["words_per_minute"]["baseline_value"] == 131.0
    assert "nonexistent_metric" not in out  # never fabricated

    # bool coercion survived the round trip
    e3 = await repo.log_journal_entry(u.id, 1, "exercise", "wallpaper", completed=True, reason=None)
    row = await repo._fetchone("SELECT completed FROM journal_entries WHERE id=?", (e3,))
    assert row["completed"] == 1


# ---------------------------------------------------------------------------
# Media refs
# ---------------------------------------------------------------------------
async def test_media_ref_pending_row_merges_pieces_in_any_order(repo):
    u = await repo.get_or_create_user("telegram", "42")
    # transcript lands first (no link yet)
    mid = await repo.record_media_ref(
        u.id, "loom", "initial_recording", transcript_text="0:00 hello uhm"
    )
    # then the link + duration
    mid2 = await repo.record_media_ref(
        u.id, "loom", "initial_recording",
        loom_url="https://www.loom.com/share/x", loom_duration_seconds=141.8,
    )
    assert mid2 == mid  # merged into the same pending row
    row = await repo._fetchone("SELECT * FROM media_refs WHERE id=?", (mid,))
    assert row["loom_url"].endswith("/x") and row["transcript_text"].startswith("0:00")
    assert row["loom_duration_seconds"] == 141.8 and row["processed"] == 0
    await repo.mark_media_processed(mid)
    row = await repo._fetchone("SELECT processed FROM media_refs WHERE id=?", (mid,))
    assert row["processed"] == 1


async def test_voice_fallback_media_ref(repo):
    u = await repo.get_or_create_user("telegram", "42")
    await repo.record_media_ref(
        u.id, "voice_fallback", "audit_day3",
        telegram_file_id="FILEID1", telegram_message_id=7, fallback_mode="full_metrics",
    )
    row = await repo._fetchone("SELECT * FROM media_refs")
    assert row["kind"] == "voice_fallback" and row["fallback_mode"] == "full_metrics"


# ---------------------------------------------------------------------------
# Engagement / missed days / counters
# ---------------------------------------------------------------------------
async def test_engagement_and_nudge_counter_reset_together(repo):
    u = await repo.get_or_create_user("telegram", "42")
    await repo.update_user_state(u.id, reengagement_nudge_count=2)
    await repo.record_daily_engagement(u.id, 5)
    assert await repo.has_engagement_on_day(u.id, 5) is True
    st = await repo.get_user_state(u.id)
    assert st.reengagement_nudge_count == 0
    # idempotent on re-delivery
    await repo.record_daily_engagement(u.id, 5)  # no duplicate, no error


async def test_missed_day_flag_resolve_and_unresolved_count(repo):
    u = await repo.get_or_create_user("telegram", "42")
    await repo.update_user_state(u.id, adaptive_nudge_sent=1)
    await repo.flag_missed_day(u.id, 3)
    await repo.flag_missed_day(u.id, 4)
    assert await repo.count_unresolved_missed_days(u.id) == 2
    await repo.resolve_missed_day(u.id, 3)
    # resolve resets adaptive_nudge_sent in the same commit
    st = await repo.get_user_state(u.id)
    assert st.adaptive_nudge_sent == 0
    assert await repo.count_unresolved_missed_days(u.id) == 1


# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------
async def test_conversation_roundtrip_and_folding(repo):
    u = await repo.get_or_create_user("telegram", "42")
    ids = []
    for i, (role, content) in enumerate([
        ("user", "hello"), ("assistant", "hi there"), ("user", "long old message"),
        ("assistant", "old reply"), ("user", "fresh"),
    ]):
        ids.append(await repo.append_conversation_message(u.id, role, content))
    recent = await repo.get_recent_messages(u.id, limit=5)
    assert [m["content"] for m in recent] == [
        "hello", "hi there", "long old message", "old reply", "fresh",
    ]
    # fold the first three into summary; recent must then exclude them
    await repo.append_summary_chunk(u.id, "user said hello; agent greeted", ids[0], ids[2])
    await repo.mark_messages_folded(ids[:3])
    msgs = await repo.get_recent_messages(u.id, limit=10)
    assert [m["content"] for m in msgs] == ["old reply", "fresh"]
    assert await repo.get_summary_chunks(u.id) == ["user said hello; agent greeted"]


async def test_conversation_rejects_tool_role(repo):
    u = await repo.get_or_create_user("telegram", "42")
    with pytest.raises(AssertionError):
        await repo.append_conversation_message(u.id, "tool", "x")


# ---------------------------------------------------------------------------
# Admin: /reset keeps history with new epoch; /wipe deletes all
# ---------------------------------------------------------------------------
async def test_reset_keeps_history_bumps_epoch_and_restamps(repo):
    u = await repo.get_or_create_user("telegram", "42")
    old_day_zero = (await repo.get_user(u.id)).day_zero_at
    await repo.log_journal_entry(u.id, 3, "reflection", "keep me")
    await repo.append_conversation_message(u.id, "user", "also keep")
    await repo.update_user_state(u.id, current_habit="volume")

    import asyncio

    await asyncio.sleep(1.1)  # day_zero re-stamp has 1s resolution; ensure a new second
    await repo.reset_user_progress(u.id)

    user = await repo.get_user(u.id)
    assert user.epoch == 1 and user.simulated_day == 0
    assert user.day_zero_at != old_day_zero  # re-stamped
    st = await repo.get_user_state(u.id)
    assert st.current_stage == "onboarding" and st.current_habit is None
    # history intact, epoch-stamped, invisible to current-epoch queries
    row = await repo._fetchone(
        "SELECT COUNT(*) AS n FROM journal_entries WHERE user_id=?", (u.id,)
    )
    assert row["n"] == 1
    row = await repo._fetchone(
        "SELECT COUNT(*) AS n FROM conversation_messages WHERE user_id=?", (u.id,)
    )
    assert row["n"] == 1


async def test_wipe_deletes_everything(repo):
    u = await repo.get_or_create_user("telegram", "42")
    e = await repo.log_journal_entry(u.id, 1, "reflection", "x")
    await repo.record_entry_metrics(e, {"filler_word_count": 3})
    await repo.record_daily_engagement(u.id, 1)
    await repo.append_conversation_message(u.id, "user", "y")

    await repo.wipe_user(u.id)
    for sql in (
        "SELECT COUNT(*) AS n FROM users", "SELECT COUNT(*) AS n FROM state",
        "SELECT COUNT(*) AS n FROM journal_entries",
        "SELECT COUNT(*) AS n FROM entry_metrics",
        "SELECT COUNT(*) AS n FROM daily_engagement",
        "SELECT COUNT(*) AS n FROM conversation_messages",
    ):
        row = await repo._fetchone(sql)
        assert row["n"] == 0, sql


# ---------------------------------------------------------------------------
# Canonical-day helpers
# ---------------------------------------------------------------------------
def test_day_from_day_zero_formula():
    from datetime import UTC, datetime

    base = datetime(2026, 9, 9, 12, 0, tzinfo=UTC).isoformat()
    now = datetime(2026, 9, 10, 13, 30, tzinfo=UTC)
    assert day_from_day_zero(base, 0, now=now) == 1      # 25.5h elapsed -> day 1
    assert day_from_day_zero(base, 5, now=now) == 6      # /advance 5 added


def test_local_midnight_iso():
    from bot.db.repo import local_midnight_iso

    iso = local_midnight_iso("Asia/Kolkata")
    assert iso.endswith("+00:00")
    from datetime import datetime

    dt = datetime.fromisoformat(iso)
    assert dt.hour == 18 or dt.hour == 19  # IST midnight = 18:30 UTC (hab half-year)
    assert dt.minute in (0, 30)
