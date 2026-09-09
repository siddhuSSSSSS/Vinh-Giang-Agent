"""Canonical day resolver + the two time gates.

Phase 3/4 deliverable per Planning.md:
- get_effective_day(): the ONE definition of "what day is it for this user" —
  floor((now - day_zero_at)/1d) + simulated_day offset. Real wall-clock time
  advances the day automatically; /advance bumps the offset half of the formula.
  There is no second definition of "day" anywhere.
- is_24h_gate_cleared(): waiting_24h -> audit_day1 gate, OR of real-hours and
  effective-day terms (the second term makes the gate fire under /advance).
- is_weekly_reeval_due(): derived, not a stored stage — day multiple of 7 since
  weekly_cycle started, gated by last_checkin_at so it fires once per boundary day
  (the Chat.md over-firing fix).
"""

from __future__ import annotations

from datetime import UTC, datetime

from bot.db.repo import User, day_from_day_zero


def get_effective_day(user: User, now: datetime | None = None) -> int:
    """The canonical clock. `user.day_zero_at` + `user.simulated_day` is the only
    source of truth; callers pass the user ROW they already hold."""
    return day_from_day_zero(user.day_zero_at, user.simulated_day, now=now)


def is_24h_gate_cleared(
    submitted_at: str | None,
    submitted_effective_day: int | None,
    current_effective_day: int,
    now: datetime | None = None,
) -> bool:
    """24-hour rule on waiting_24h -> audit_day1.

    Cleared iff (now - recording_submitted_at) >= 24h OR
    (current_effective_day - recording_submitted_effective_day) >= 1.
    The second term means /advance past the boundary clears the gate even for a
    submission minutes old - and a NULL submitted_at never blocks on the first
    term (fails safe to the day-arithmetic term only).
    """
    if submitted_effective_day is not None:
        if current_effective_day - int(submitted_effective_day) >= 1:
            return True
    if submitted_at:
        base = _parse_iso(submitted_at)
        ref = now or datetime.now(UTC)
        return (ref - base).total_seconds() >= 86400
    return False  # nothing recorded: gate stays closed


def is_weekly_reeval_due(
    current_stage: str,
    weekly_cycle_started_effective_day: int | None,
    current_effective_day: int,
    last_checkin_at: str | None,
    last_checkin_effective_day: int | None = None,
) -> bool:
    """Weekly re-evaluation trigger (derived state, never a stage of its own).

    Due iff: in weekly_cycle AND (day - start) >= 7 AND the boundary day hasn't
    already had its re-eval conversation (last_checkin gate prevents the
    same-day over-firing Chat.md identified).
    """
    if current_stage != "weekly_cycle" or weekly_cycle_started_effective_day is None:
        return False
    if current_effective_day - weekly_cycle_started_effective_day < 7:
        return False
    # same-day gate: if the last checkin happened on the CURRENT effective day,
    # it has already been handled this boundary
    if last_checkin_effective_day is not None:
        return current_effective_day != int(last_checkin_effective_day)
    if last_checkin_at:
        base = _parse_iso(last_checkin_at)
        ref = datetime.now(UTC)
        return base.date() != ref.date()
    return True


def _parse_iso(value: str) -> datetime:
    base = datetime.fromisoformat(value)
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    return base


__all__ = ("get_effective_day", "is_24h_gate_cleared", "is_weekly_reeval_due")
