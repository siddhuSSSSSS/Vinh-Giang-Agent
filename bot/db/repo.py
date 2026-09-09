"""Async repository over the Vin's Sidekick SQLite schema.

Phase 2 deliverable. Thin wrappers around aiosqlite - no ORM. Design rules from
Planning.md:
- single shared connection for the process lifetime (aiosqlite serializes all
  calls onto one internal thread; no extra locking needed)
- WAL + foreign_keys + busy_timeout set on every open (incl. :memory: fixtures)
- booleans are INTEGER (0/1/NULL) in SQLite - explicit coercion on read/write
- epoch-stamped day-scoped writes and reads (current-user-epoch filter)
- INSERT OR IGNORE idempotency guards wherever Telegram/scheduler could re-deliver
- multi-table operations (wipe/reset) wrapped in explicit transactions
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite

from bot import config


class Database:
    """Owns the single shared aiosqlite connection for the process."""

    def __init__(self, path: str | sqlite3.Connection = ":memory:") -> None:
        # For tests ":memory:" (str) is allowed; production passes config.DATABASE_PATH.
        self._path = path if isinstance(path, str) else str(path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        db = await aiosqlite.connect(self._path)
        db.row_factory = aiosqlite.Row
        # PRAGMAs must be set through executescript-style single statements
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("PRAGMA busy_timeout=5000")
        import pathlib

        schema_path = pathlib.Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            await db.executescript(schema_path.read_text(encoding="utf-8"))
        await db.commit()
        self._conn = db

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not opened - call await db.connect() first")
        return self._conn

    async def _fetchone(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        cur = await self._conn.execute(sql, tuple(params))
        return await cur.fetchone()

    async def _fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        cur = await self._conn.execute(sql, tuple(params))
        return list(await cur.fetchall())

    async def _execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        cur = await self._conn.execute(sql, tuple(params))
        await self._conn.commit()
        return cur.rowcount  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Dataclasses (thin, the rest of the app speaks in these)
# ---------------------------------------------------------------------------
@dataclass
class User:
    id: int
    platform: str
    platform_user_id: str
    name: str | None
    day_zero_at: str
    simulated_day: int
    epoch: int
    timezone: str | None
    last_sweep_day: int | None
    passcode_verified: bool
    failed_attempts: int
    locked_until: str | None
    last_message_at: str | None


@dataclass
class State:
    user_id: int
    current_stage: str
    current_habit: str | None
    week_in_habit: int
    last_checkin_at: str | None
    motivation_summary: str | None
    recording_submitted_at: str | None
    recording_submitted_effective_day: int | None
    kaizen_reveal_shown: bool
    recording_ready_nudge_sent: bool
    last_daily_checkin_sent_day: int | None
    adaptive_nudge_sent: bool
    weekly_cycle_started_effective_day: int | None
    reengagement_nudge_count: int


def _user_from_row(row: aiosqlite.Row) -> User:
    return User(
        id=row["id"],
        platform=row["platform"],
        platform_user_id=row["platform_user_id"],
        name=row["name"],
        day_zero_at=row["day_zero_at"],
        simulated_day=row["simulated_day"],
        epoch=row["epoch"],
        timezone=row["timezone"],
        last_sweep_day=row["last_sweep_day"],
        passcode_verified=bool(row["passcode_verified"]),
        failed_attempts=row["failed_attempts"],
        locked_until=row["locked_until"],
        last_message_at=row["last_message_at"],
    )


def _state_from_row(row: aiosqlite.Row) -> State:
    return State(
        user_id=row["user_id"],
        current_stage=row["current_stage"],
        current_habit=row["current_habit"],
        week_in_habit=row["week_in_habit"],
        last_checkin_at=row["last_checkin_at"],
        motivation_summary=row["motivation_summary"],
        recording_submitted_at=row["recording_submitted_at"],
        recording_submitted_effective_day=row["recording_submitted_effective_day"],
        kaizen_reveal_shown=bool(row["kaizen_reveal_shown"]),
        recording_ready_nudge_sent=bool(row["recording_ready_nudge_sent"]),
        last_daily_checkin_sent_day=row["last_daily_checkin_sent_day"],
        adaptive_nudge_sent=bool(row["adaptive_nudge_sent"]),
        weekly_cycle_started_effective_day=row["weekly_cycle_started_effective_day"],
        reengagement_nudge_count=row["reengagement_nudge_count"],
    )


def _coerce_bool(value: bool | None) -> int | None:
    return None if value is None else int(bool(value))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class UsersMixin:
    async def get_or_create_user(self, platform: str, platform_user_id: str) -> User:
        """Fetch-or-create by (platform, platform_user_id); day_zero_at SQL-defaults."""
        row = await self._fetchone(
            "SELECT * FROM users WHERE platform=? AND platform_user_id=?",
            (platform, platform_user_id),
        )
        if row is not None:
            return _user_from_row(row)
        await self._execute(
            "INSERT OR IGNORE INTO users (platform, platform_user_id) VALUES (?, ?)",
            (platform, platform_user_id),
        )
        row = await self._fetchone(
            "SELECT * FROM users WHERE platform=? AND platform_user_id=?",
            (platform, platform_user_id),
        )
        assert row is not None
        user = _user_from_row(row)
        # every user ALWAYS has a state row - create it with the user, not lazily
        await self._execute(
            "INSERT OR IGNORE INTO state (user_id, current_stage) VALUES (?, 'onboarding')",
            (user.id,),
        )
        return user

    async def get_user(self, user_id: int) -> User | None:
        row = await self._fetchone("SELECT * FROM users WHERE id=?", (user_id,))
        return _user_from_row(row) if row is not None else None

    async def get_verified_users(self) -> list[User]:
        rows = await self._fetchall("SELECT * FROM users WHERE passcode_verified=1")
        return [_user_from_row(r) for r in rows]

    async def get_users_in_stage(self, stage: str) -> list[tuple[User, Any]]:
        """Users currently in the given stage, joined with their state."""
        rows = await self._fetchall(
            "SELECT u.*, s.current_stage AS _stage FROM users u"
            " JOIN state s ON s.user_id = u.id WHERE s.current_stage=?",
            (stage,),
        )
        out: list[tuple[User, Any]] = []
        for row in rows:
            user = _user_from_row(row)
            state = await self.get_user_state(user.id)
            out.append((user, state))
        return out

    async def update_passcode_state(
        self,
        user_id: int,
        *,
        verified_delta: int = 0,
        failed_attempts: int | None = None,
        locked_until: str | None = None,
    ) -> None:
        """Maintain the passcode/lockout columns mechanically (handlers' job)."""
        if failed_attempts is not None:
            await self._execute(
                "UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?",
                (failed_attempts, locked_until, user_id),
            )
        if verified_delta:
            await self._execute(
                "UPDATE users SET passcode_verified=? WHERE id=?",
                (verified_delta, user_id),
            )

    async def mark_message_seen(self, user_id: int, iso_now: str) -> None:
        await self._execute(
            "UPDATE users SET last_message_at=? WHERE id=?", (iso_now, user_id)
        )

    async def set_timezone(self, user_id: int, iana: str) -> bool:
        """Route timezone to the users table. Returns True if this was the FIRST set.

        Phase 3 uses the first-set signal to realign day_zero_at to local midnight.
        """
        row = await self._fetchone("SELECT timezone FROM users WHERE id=?", (user_id,))
        first = row is None or row["timezone"] is None
        await self._execute("UPDATE users SET timezone=? WHERE id=?", (iana, user_id))
        return first

    # --- canonical clock (get_effective_day / /advance land in gates/Phase 4) ---
    async def bump_simulated_day(self, user_id: int, days: int) -> None:
        """/advance N: bump the offset half of the formula. Never decremented except
        through validation upstream; never touched by /wipe (deletes the row)."""
        await self._execute(
            "UPDATE users SET simulated_day = simulated_day + ? WHERE id=?",
            (days, user_id),
        )

    async def record_sweep_run(self, user_id: int, day: int) -> None:
        """Unconditional last_sweep_day write backing the hourly sweep dedup."""
        await self._execute(
            "UPDATE users SET last_sweep_day=? WHERE id=?", (day, user_id)
        )


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class StateMixin:
    _STATE_FIELDS = {
        "current_stage", "current_habit", "week_in_habit", "last_checkin_at",
        "motivation_summary", "recording_submitted_at",
        "recording_submitted_effective_day", "kaizen_reveal_shown",
        "recording_ready_nudge_sent", "last_daily_checkin_sent_day",
        "adaptive_nudge_sent", "weekly_cycle_started_effective_day",
        "reengagement_nudge_count",
    }

    async def get_user_state(self, user_id: int) -> State:
        row = await self._fetchone("SELECT * FROM state WHERE user_id=?", (user_id,))
        assert row is not None, f"state row missing for user {user_id}"
        return _state_from_row(row)

    async def update_user_state(self, user_id: int, **fields: Any) -> None:
        """Route: timezone -> users table; everything else -> state.

        None values are skipped (null means 'not provided this call'), matching
        the tool schema's nullable-but-required design. Boolean fields coerce.
        """
        tz = fields.pop("timezone", None)
        if isinstance(tz, str) and tz:
            await self.set_timezone(user_id, tz)

        cols: list[str] = []
        vals: list[Any] = []
        for key, value in fields.items():
            if key not in self._STATE_FIELDS:
                raise ValueError(f"unknown state field {key!r}")
            if value is None:
                continue
            if key in {"kaizen_reveal_shown", "recording_ready_nudge_sent",
                       "adaptive_nudge_sent"}:
                value = _coerce_bool(bool(value))
            cols.append(f"{key}=?")
            vals.append(value)
        if cols:
            cols.append("updated_at=datetime('now')")
            await self._execute(
                f"UPDATE state SET {', '.join(cols)} WHERE user_id=?",
                (*vals, user_id),
            )


# ---------------------------------------------------------------------------
# Journal + metrics
# ---------------------------------------------------------------------------
class JournalMixin:
    async def log_journal_entry(
        self,
        user_id: int,
        day: int,
        type_: str,
        content: str,
        completed: bool | None = None,
        reason: str | None = None,
    ) -> int:
        """Insert one journal row stamped with the user's CURRENT epoch."""
        user = await self.get_user(user_id)
        assert user is not None
        cur = await self._conn.execute(
            "INSERT INTO journal_entries (user_id, day, epoch, type, content, completed, reason)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                user_id,
                day,
                user.epoch,
                type_,
                content,
                _coerce_bool(completed),
                reason,
            ),
        )
        await self._conn.commit()
        return int(cur.lastrowid or 0)

    async def record_entry_metrics(
        self, journal_entry_id: int, metrics: dict[str, float]
    ) -> None:
        if not metrics:
            return
        await self._conn.executemany(
            "INSERT OR IGNORE INTO entry_metrics (journal_entry_id, metric_name, metric_value)"
            " VALUES (?,?,?)",
            [(journal_entry_id, k, float(v)) for k, v in metrics.items()],
        )
        await self._conn.commit()

    async def get_metric_trend(
        self, user_id: int, metric_name: str, limit: int = 8
    ) -> list[tuple[int, float]]:
        """(day, value) pairs, oldest -> newest, current-epoch only."""
        user = await self.get_user(user_id)
        assert user is not None
        rows = await self._fetchall(
            """
            SELECT je.day AS day, em.metric_value AS value
            FROM entry_metrics em
            JOIN journal_entries je ON je.id = em.journal_entry_id
            WHERE je.user_id=? AND je.epoch=? AND em.metric_name=?
            ORDER BY je.day ASC, em.id ASC
            """,
            (user_id, user.epoch, metric_name),
        )
        return [(int(r["day"]), float(r["value"])) for r in rows][-limit:]

    async def get_baseline_and_latest_metrics(
        self, user_id: int, metric_names: list[str]
    ) -> dict[str, dict[str, float | int] | None]:
        """Powers the habit-transition comparison artifact.

        For each requested metric: first-ever and most-recent value (current epoch).
        Shape: {metric: {"baseline_day": int, "baseline_value": float,
                          "latest_day": int, "latest_value": float}}
        Missing metrics are omitted rather than fabricated.
        """
        user = await self.get_user(user_id)
        assert user is not None
        out: dict[str, dict[str, Any]] = {}
        for name in metric_names:
            rows = await self._fetchall(
                """
                SELECT je.day AS day, em.metric_value AS value
                FROM entry_metrics em
                JOIN journal_entries je ON je.id = em.journal_entry_id
                WHERE je.user_id=? AND je.epoch=? AND em.metric_name=?
                ORDER BY je.day ASC, em.id ASC
                """,
                (user_id, user.epoch, name),
            )
            if not rows:
                continue
            out[name] = {
                "baseline_day": int(rows[0]["day"]),
                "baseline_value": float(rows[0]["value"]),
                "latest_day": int(rows[-1]["day"]),
                "latest_value": float(rows[-1]["value"]),
            }
        return out


# ---------------------------------------------------------------------------
# Media refs
# ---------------------------------------------------------------------------
class MediaMixin:
    async def record_media_ref(
        self,
        user_id: int,
        kind: str,
        stage_context: str,
        *,
        loom_url: str | None = None,
        loom_duration_seconds: float | None = None,
        transcript_text: str | None = None,
        summary_text: str | None = None,
        telegram_file_id: str | None = None,
        telegram_message_id: int | None = None,
        fallback_mode: str | None = None,
    ) -> int:
        """Create pending media row on whichever piece lands FIRST.

        If an unprocessed Loom row already exists for this user, subsequent
        pieces (transcript/summary/link) UPDATE that same pending row instead of
        inserting a second one. Returns the media_ref id.
        """
        # find an existing pending loom row to merge into (Loom path only)
        if kind == "loom":
            pending = await self._fetchone(
                "SELECT id FROM media_refs WHERE user_id=? AND kind='loom' AND processed=0"
                " ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
            sets = ["loom_url=COALESCE(?, loom_url)"] if loom_url else []
            params: list[Any] = []
            if loom_url:
                params.append(loom_url)
            if loom_duration_seconds is not None:
                sets.append("loom_duration_seconds=COALESCE(?, loom_duration_seconds)")
                params.append(loom_duration_seconds)
            if transcript_text:
                sets.append("transcript_text=?")
                params.append(transcript_text)
            if summary_text:
                sets.append("summary_text=?")
                params.append(summary_text)
            if pending is not None and sets:
                await self._execute(
                    f"UPDATE media_refs SET {', '.join(sets)} WHERE id=?",
                    (*params, pending["id"]),
                )
                return int(pending["id"])

        cur = await self._conn.execute(
            """
            INSERT INTO media_refs
              (user_id, kind, loom_url, loom_duration_seconds, transcript_text,
               summary_text, telegram_file_id, telegram_message_id, fallback_mode,
               stage_context)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id, kind, loom_url, loom_duration_seconds, transcript_text,
                summary_text, telegram_file_id, telegram_message_id, fallback_mode,
                stage_context,
            ),
        )
        await self._conn.commit()
        return int(cur.lastrowid or 0)

    async def mark_media_processed(self, media_ref_id: int) -> None:
        await self._execute(
            "UPDATE media_refs SET processed=1 WHERE id=?", (media_ref_id,)
        )


# ---------------------------------------------------------------------------
# Missed days + daily engagement
# ---------------------------------------------------------------------------
class EngagementMixin:
    async def record_daily_engagement(self, user_id: int, day: int) -> None:
        """INSERT OR IGNORE on (user, epoch, day) - and reset the reengagement
        counter in the SAME commit (the user re-engaged)."""
        user = await self.get_user(user_id)
        assert user is not None
        await self._conn.execute(
            "INSERT OR IGNORE INTO daily_engagement (user_id, day, epoch) VALUES (?,?,?)",
            (user_id, day, user.epoch),
        )
        await self._conn.execute(
            "UPDATE state SET reengagement_nudge_count=0"
            " WHERE user_id=? AND reengagement_nudge_count != 0",
            (user_id,),
        )
        await self._conn.commit()

    async def has_engagement_on_day(self, user_id: int, day: int) -> bool:
        user = await self.get_user(user_id)
        assert user is not None
        row = await self._fetchone(
            "SELECT 1 FROM daily_engagement WHERE user_id=? AND epoch=? AND day=? LIMIT 1",
            (user_id, user.epoch, day),
        )
        return row is not None

    async def flag_missed_day(self, user_id: int, day: int) -> None:
        user = await self.get_user(user_id)
        assert user is not None
        await self._execute(
            "INSERT OR IGNORE INTO missed_days (user_id, day, epoch) VALUES (?,?,?)",
            (user_id, day, user.epoch),
        )

    async def resolve_missed_day(self, user_id: int, day: int) -> None:
        """Mark resolved AND reset adaptive_nudge_sent in the same transaction."""
        user = await self.get_user(user_id)
        assert user is not None
        await self._conn.execute(
            "UPDATE missed_days SET resolved=1 WHERE user_id=? AND epoch=? AND day=?",
            (user_id, user.epoch, day),
        )
        await self._conn.execute(
            "UPDATE state SET adaptive_nudge_sent=0 WHERE user_id=? AND adaptive_nudge_sent != 0",
            (user_id,),
        )
        await self._conn.commit()

    async def count_unresolved_missed_days(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        assert user is not None
        row = await self._fetchone(
            "SELECT COUNT(*) AS n FROM missed_days WHERE user_id=? AND epoch=? AND resolved=0",
            (user_id, user.epoch),
        )
        return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# Conversation memory + rolling summary
# ---------------------------------------------------------------------------
class ConversationMixin:
    async def append_conversation_message(
        self, user_id: int, role: str, content: str
    ) -> int:
        assert role in ("user", "assistant")
        cur = await self._conn.execute(
            "INSERT INTO conversation_messages (user_id, role, content) VALUES (?,?,?)",
            (user_id, role, content),
        )
        await self._conn.commit()
        return int(cur.lastrowid or 0)

    async def get_recent_messages(self, user_id: int, limit: int = 40) -> list[dict[str, str]]:
        rows = await self._fetchall(
            "SELECT role, content FROM conversation_messages"
            " WHERE user_id=? AND folded_into_summary=0 ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def append_summary_chunk(
        self, user_id: int, chunk_text: str, from_id: int, to_id: int
    ) -> None:
        await self._execute(
            "INSERT INTO summary_chunks (user_id, chunk_text, covers_from_message_id,"
            " covers_to_message_id) VALUES (?,?,?,?)",
            (user_id, chunk_text, from_id, to_id),
        )

    async def get_summary_chunks(self, user_id: int) -> list[str]:
        rows = await self._fetchall(
            "SELECT chunk_text FROM summary_chunks WHERE user_id=? ORDER BY id ASC",
            (user_id,),
        )
        return [r["chunk_text"] for r in rows]

    async def mark_messages_folded(self, message_ids: list[int]) -> None:
        if not message_ids:
            return
        marks = ",".join("?" * len(message_ids))
        await self._execute(
            f"UPDATE conversation_messages SET folded_into_summary=1 WHERE id IN ({marks})",
            message_ids,
        )


# ---------------------------------------------------------------------------
# Admin: /reset (keeps history, new epoch) and /wipe (deletes everything)
# ---------------------------------------------------------------------------
class AdminMixin:
    async def reset_user_progress(self, user_id: int) -> None:
        """Atomic multi-table /reset: state to defaults, offset to 0, day_zero
        re-stamped, epoch incremented; journal/media/conversation history KEPT.

        Everything in ONE transaction - the earlier commit-then-write sequencing
        would have left a half-reset user (state gone, epoch stale) on a crash.
        """
        conn = self._conn
        await conn.execute("BEGIN")
        try:
            await conn.execute("DELETE FROM state WHERE user_id=?", (user_id,))
            await conn.execute(
                "INSERT INTO state (user_id, current_stage) VALUES (?, 'onboarding')",
                (user_id,),
            )
            await conn.execute(
                "UPDATE users SET simulated_day=0, day_zero_at=datetime('now'),"
                " epoch=epoch+1 WHERE id=?",
                (user_id,),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    async def wipe_user(self, user_id: int) -> None:
        """Atomic full deletion (CASCADE handles most; sweep/lockout columns live on users)."""
        conn = self._conn
        await conn.execute("BEGIN")
        try:
            # children first for explicitness; CASCADE would also cover them
            await conn.execute(
                "DELETE FROM entry_metrics WHERE journal_entry_id IN"
                " (SELECT id FROM journal_entries WHERE user_id=?)",
                (user_id,),
            )
            for table in (
                "journal_entries", "media_refs", "missed_days", "daily_engagement",
                "conversation_messages", "summary_chunks", "state",
            ):
                await conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
            await conn.execute("DELETE FROM users WHERE id=?", (user_id,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


class Repo(
    UsersMixin, StateMixin, JournalMixin, MediaMixin, EngagementMixin,
    ConversationMixin, AdminMixin, Database,
):
    """Full repository: one shared connection, all mixins composed."""


# Convenience factory used by handlers/scheduler in later phases.
async def open_repo(path: str | None = None) -> Repo:
    target = path or str(config.DATABASE_PATH)
    # create parent dirs for prod paths - a fresh checkout must not crash on
    # first boot because data/ doesn't exist yet
    import pathlib

    parent = pathlib.Path(target).parent
    if isinstance(target, str) and target != ":memory:" and (
        str(parent) not in ("", ".")
    ):
        parent.mkdir(parents=True, exist_ok=True)
    repo = Repo(target)
    await repo.connect()
    return repo


def local_midnight_iso(tz_name: str | None, now: datetime | None = None) -> str:
    """Most recent local midnight in UTC ISO8601 - used by Phase 3's day-boundary
    realignment the first time a timezone is set."""
    now = now or datetime.now(UTC)
    if not tz_name:
        return now.isoformat()
    from zoneinfo import ZoneInfo

    local = now.astimezone(ZoneInfo(tz_name))
    local_midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(UTC).isoformat()


def day_from_day_zero(day_zero_at: str, simulated_day: int = 0, now: datetime | None = None) -> int:
    """The canonical formula (shared by gates Phase 4): floor((now - day_zero)/1d) + offset."""
    now = now or datetime.now(UTC)
    base = datetime.fromisoformat(day_zero_at)
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    return int((now - base).total_seconds() // 86400) + int(simulated_day)


__all__ = (
    "Repo", "open_repo", "User", "State", "local_midnight_iso", "day_from_day_zero",
    "timedelta", "sqlite3",
)
