"""Review-3 tests: robustness edge cases in the parser/pause math and the
time gates, punishing them with adversarial inputs. Companion to
tests/gherkin/review3.feature.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.agent_core import classify_text  # noqa: E402
from bot.analysis.loom import (  # noqa: E402
    articulation_rate_wpm,
    estimate_pauses,
    parse_transcript,
)
from bot.gates import is_24h_gate_cleared, is_weekly_reeval_due  # noqa: E402


# Feature: corrupt timestamp stamps are dropped, not believed
def test_corrupt_hour_stamp_line_dropped(fuzz = ""):
    """GIVEN a paste containing impossible stamps like '59:59'
    WHEN parse_transcript runs
    THEN the corrupt line is dropped entirely
    AND no nonsense 3597-second pause can ever appear later
    """
    fuzz = "59:59 words from a corrupt paste\n11:59 one line of words here"
    segs = parse_transcript(fuzz)
    starts = [s.start_seconds for s in segs]
    assert 3599 not in starts, "corrupt 59:59 stamp must be dropped"
    # the honest second line survived
    assert 719 in starts


def test_pause_metric_clamped_to_sane_ceiling():
    """GIVEN residuals that would exceed sane speech-span assumptions
    (corrupt data slipping through), the reported longest pause is capped.
    """
    # fabricate segments 40 minutes apart with tiny word counts
    segs = parse_transcript("00:00 alpha\n59:00 beta")
    long_count, longest = estimate_pauses(segs, articulation_rate_wpm(segs))
    assert longest <= 600.0, f"a clamp to a sane ceiling failed: {longest}"


# Feature: same-second and descending stamps don't crash
def test_same_second_stamps_ok():
    segs = parse_transcript("00:30 alpha words\n00:30 beta words")
    assert len(segs) == 2
    # rate calc guards gap>0: falls back to constant
    assert articulation_rate_wpm(segs) == 150.0


def test_descending_stamps_negative_gap_no_crash():
    segs = parse_transcript("11:59 one line of words here\n00:00 shouldn't count earlier")
    # residual for a *negative or zero* gap must not crash, and the honest
    # guard keeps long_count small
    long_count, longest = estimate_pauses(segs, articulation_rate_wpm(segs))
    assert long_count >= 0 and longest >= 0


# Feature: gates hold up on adversarial input
def test_24h_gate_future_submission_is_not_cleared():
    """A future submission timestamp (clock skew) must NOT clear the gate.
    Contract: with a real submitted_effective_day, day arithmetic (current -
    submitted >= 1) short-circuits to True BEFORE the wall-clock term; with
    submitted_effective_day=None the wall-clock term alone governs and a
    future stamp correctly fails it."""
    from datetime import UTC, datetime, timedelta

    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert is_24h_gate_cleared(future, 0, 0) is False
    # a corrupt record (None effective day) falls to wall-clock alone: future fails
    assert is_24h_gate_cleared(future, None, 1) is False
    # the day-arithmetic term short-circuits BEFORE wall-clock: day wins
    assert is_24h_gate_cleared(
        (datetime.now(UTC) - timedelta(minutes=10)).isoformat(), 0, 1
    ) is True


def test_weekly_reeval_rejects_bad_states():
    # start date in the "future" relative to now -> start > now is nonsense
    assert is_weekly_reeval_due("weekly_cycle", 12, 10, None) is False
    # None start -> right False
    assert is_weekly_reeval_due("weekly_cycle", None, 10, None) is False
    # not in weekly cycle -> right False
    assert is_weekly_reeval_due("audit_day1", 5, 10, None) is False


# Feature: hyperscale input is handled without hanging
def test_classify_huge_single_word():
    assert classify_text("x" * 100_000) == "transcript"


def test_classify_mixed_ts_and_long_line():
    """A doc containing both stamps and one huge line files as transcript,
    NOT as an LLM turn."""
    big = "0:00 real para\n" + ("words " * 30_000)
    assert classify_text(big) == "transcript"


def test_parse_transcript_strips_timestamp_prefix_zero():
    # continuation lines append to the previous SEGMENT's text, never their own
    t = "0:00 alpha words\nand a continuation\n0:05 next one"
    segs = parse_transcript(t)
    assert len(segs) == 2
    assert "continuation" in segs[0].text
    assert segs[0].start_seconds == 0
