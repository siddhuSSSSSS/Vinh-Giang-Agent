"""Phase 5 tests: Loom transcript parsing, the seven metrics, fail-soft paths,
Plan-B duration, voice-fallback metrics, and pipeline wiring in the engine.

The spike transcript (Transcript.txt) is committed as a regression fixture -
its numbers are the documented reference (36 fillers / 11.6% / 131 wpm / 5 reps).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.agent_core import AgentCore  # noqa: E402
from bot.analysis import loom  # noqa: E402
from bot.analysis.voice_fallback import (  # noqa: E402
    analyze_voice_transcript,
    audio_words_to_segments,
    needs_conversion,
)
from bot.db.repo import Repo  # noqa: E402

SPIKE_TRANSCRIPT = (PROJECT_ROOT / "Transcript.txt").read_text(encoding="utf-8")
SPIKE_URL = "https://www.loom.com/share/d8c2c5c296c54835822d42b731b1b61f"
SPIKE_DURATION = 141.811


@pytest.fixture
async def repo():
    r = Repo(":memory:")
    await r.connect()
    yield r
    await r.close()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def test_parse_segments_count_and_stamp_punctuation_strip():
    segs = loom.parse_transcript(SPIKE_TRANSCRIPT)
    assert len(segs) == 9
    assert segs[1].start_seconds == 32
    # "0:32 , this is..." - leading punctuation stripped after the stamp
    assert not segs[1].text.startswith(",")


def test_parse_bracket_and_hms_formats_defensively():
    t = "[0:00] one\n[1:21] two\n00:02:03 three"
    segs = loom.parse_transcript(t)
    assert [(s.start_seconds, s.text) for s in segs] == [
        (0, "one"), (81, "two"), (123, "three")
    ]


def test_parse_continuation_lines_merge():
    t = "0:00 first line\ncontinuation without stamp\n0:30 next"
    segs = loom.parse_transcript(t)
    assert len(segs) == 2
    assert "continuation" in segs[0].text


def test_has_parseable_timestamps():
    assert loom.has_parseable_timestamps(SPIKE_TRANSCRIPT)
    assert not loom.has_parseable_timestamps("just some text\nno stamps at all")


# ---------------------------------------------------------------------------
# Spike regression (live oEmbed ran during the spike; duration from its record)
# ---------------------------------------------------------------------------
async def test_spike_transcript_reproduces_reference_numbers():
    result = await loom.analyze_loom_submission(
        SPIKE_TRANSCRIPT, oembed_duration=SPIKE_DURATION
    )
    m = result.metrics
    assert m["filler_word_count"] == 36.0
    assert abs(m["filler_rate"] - 11.61) < 0.1
    assert abs(m["words_per_minute"] - 131.2) < 1.0
    assert m["repetition_count"] == 5.0
    assert abs(m["duration_seconds"] - SPIKE_DURATION) < 0.01
    assert result.pauses_ok
    assert m["longest_pause_seconds"] < 12.0  # spike: ~10s before the last paragraph
    assert m["long_pause_count"] >= 2


# ---------------------------------------------------------------------------
# Fail-soft paths
# ---------------------------------------------------------------------------
async def test_failsoft_no_timestamps_drops_pause_metrics_only():
    mangled = "\n".join(
        line.lstrip("0123456789[]:") for line in SPIKE_TRANSCRIPT.splitlines()
    )
    result = await loom.analyze_loom_submission(mangled)
    assert result.pauses_ok is False
    assert "long_pause_count" not in result.metrics
    assert "longest_pause_seconds" not in result.metrics
    # five non-timestamp metrics still compute
    assert result.metrics["filler_word_count"] > 0
    assert "repetition_count" in result.metrics
    assert any("pauses" in n for n in result.notes)


async def test_failsoft_empty_transcript_no_crash():
    result = await loom.analyze_loom_submission("")
    assert result.metrics["filler_word_count"] == 0.0
    assert result.metrics["filler_rate"] == 0.0
    assert result.pauses_ok is False


async def test_failsoft_never_writes_misleading_zero_pauses():
    result = await loom.analyze_loom_submission("no stamps here")
    assert "long_pause_count" not in result.metrics  # omitted, not 0
    assert "longest_pause_seconds" not in result.metrics


# ---------------------------------------------------------------------------
# Plan-B duration fallback (oEmbed missing)
# ---------------------------------------------------------------------------
async def test_planb_duration_estimate_from_last_timestamp():
    segments = loom.parse_transcript(SPIKE_TRANSCRIPT)
    est = loom.estimate_duration_from_segments(segments, articulation_wpm=152.0)
    assert est is not None
    assert abs(est - SPIKE_DURATION) / SPIKE_DURATION < 0.05  # within 5% per spike


async def test_planb_duration_fallback_in_pipeline_when_oembed_missing():
    result = await loom.analyze_loom_submission(SPIKE_TRANSCRIPT, oembed_duration=None)
    assert result.duration_seconds is not None
    assert any("estimated" in note for note in result.notes)
    # wpm computed with the estimated duration
    assert "words_per_minute" in result.metrics


# ---------------------------------------------------------------------------
# The corrected articulation-rate math (no cancelling residuals)
# ---------------------------------------------------------------------------
async def test_articulation_rate_no_cancellation():
    segs = loom.parse_transcript(SPIKE_TRANSCRIPT)
    rate = loom.articulation_rate_wpm(segs)
    assert 120 <= rate <= 200  # plausible speaking rate, not 0/huge
    long_count, longest = loom.estimate_pauses(segs, rate)
    assert longest > 5.0  # the real dead air before the last paragraph shows up


async def test_articulation_rate_few_segments_falls_back_to_constant():
    tiny = [loom.Segment(0, "hi"), loom.Segment(30, "there friend")]
    assert loom.articulation_rate_wpm(tiny) == 150.0


# ---------------------------------------------------------------------------
# Voice fallback (pure functions; no network)
# ---------------------------------------------------------------------------
def test_needs_conversion_ogg_vs_wav():
    assert needs_conversion(b"OggS......", "audio/ogg") is True
    assert needs_conversion(b"RIFF....", "audio/wav") is False
    assert needs_conversion(b"\xff\xfb...", "audio/mpeg") is False
    assert needs_conversion(b"\x00\x01...", None) is True  # unknown -> convert


def test_voice_metrics_exact_pause_math():
    words = [
        (0.0, "hi"), (0.4, "so"), (0.8, "um"),
        (3.0, "then"), (3.4, "there"), (5.2, "again"),
    ]
    out = analyze_voice_transcript("hi so um then there again", duration=6.0,
                                   word_timestamps=words)
    m = out.metrics
    assert m["long_pause_count"] == 2.0  # 0.8->3.0 (2.2s), 3.4->5.2 (1.8s)
    assert abs(m["longest_pause_seconds"] - 2.2) < 0.01
    assert out.pauses_ok  # real ASR - the honest in-data advantage


def test_audio_words_to_segments_groups_on_gaps():
    words = [(0.0, "a"), (0.2, "b"), (2.0, "c"), (2.2, "d")]
    segs = audio_words_to_segments(words, duration=3.0)
    assert len(segs) == 2
    assert segs[0].text == "a b"
    assert segs[1].text == "c d"


# ---------------------------------------------------------------------------
# Engine wiring: Loom link + transcript -> metrics computed + processed flag
# ---------------------------------------------------------------------------
async def test_engine_full_submission_flow_computes_metrics(repo):
    uid_holder: dict[str, int] = {}

    u = await repo.get_or_create_user("telegram", "42")
    uid_holder["id"] = u.id

    class NoLLM:
        async def run_turn(self, **kwargs: Any) -> Any:  # pragma: no cover
            raise AssertionError("metrics flow must not hit the LLM")

        async def run(self, **kwargs: Any) -> Any:  # pragma: no cover
            raise AssertionError

    agent = AgentCore(repo, NoLLM())

    # link first, then transcript: the pending merge completes the pair
    out1 = await agent.handle_incoming("telegram", "42", f"my video {SPIKE_URL}")
    assert "Link received" in out1.reply
    out2 = await agent.handle_incoming("telegram", "42", SPIKE_TRANSCRIPT)
    assert "Transcript received" in out2.reply
    assert "filler" in out2.reply.lower() or "metric" in out2.reply.lower()

    row = await repo._fetchone(
        "SELECT * FROM media_refs WHERE user_id=?", (u.id,)
    )
    assert row["processed"] == 1
    assert row["loom_url"].endswith(SPIKE_URL.split("/")[-1]) or row["loom_url"].endswith(
        SPIKE_URL.split("/")[-1]
    )
    # metrics landed in entry_metrics via the journal entry
    mrow = await repo._fetchone(
        "SELECT COUNT(*) AS n FROM entry_metrics em JOIN journal_entries je"
        " ON je.id = em.journal_entry_id WHERE je.user_id=?",
        (u.id,),
    )
    assert mrow["n"] >= 5


def test_metrics_module_never_depends_on_the_llm():
    """Deterministic-count rule (Planning.md): metrics are code, never the model."""
    from bot.analysis import loom as L

    # the module imports only stdlib/math - no LLM client anywhere
    imported = set()
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(L))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
    banned = {"openai", "anthropic", "bot.llm"}
    assert imported & banned == set(), f"metrics module imports LLM bits: {imported & banned}"


# ---------------------------------------------------------------------------
# Persist path
# ---------------------------------------------------------------------------
async def test_persist_result_metrics_writes_rows(repo):
    u = await repo.get_or_create_user("telegram", "42")
    eid = await repo.log_journal_entry(u.id, 0, "transcript", "with metrics")
    result = await loom.analyze_loom_submission(SPIKE_TRANSCRIPT, oembed_duration=SPIKE_DURATION)
    await loom.persist_result_metrics(repo, eid, result)
    trend = await repo.get_metric_trend(u.id, "filler_word_count")
    assert trend and trend[0][1] == 36.0
