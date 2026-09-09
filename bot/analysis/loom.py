"""Loom-link + transcript metrics (Phase 5 PRIMARY path).

Every assumption here was validated by the executed Phase 0.5 spike (see
Phase-0.5-Spike-Results.md):
- oEmbed resolves `duration` (seconds, float) at default sharing visibility
- desktop copy-paste preserves `M:SS` per-paragraph timestamps; one line may
  start with punctuation right after the stamp ("0:32 , this is...")
- the corrected articulation-rate pause estimate (85th-percentile per-paragraph
  rate, NOT overall WPM) produced no cancelling residuals on a real recording
- fail-soft: unparseable input drops ONLY the two pause metrics, never crashes,
  and tells the user transparently

Output shape (shared with voice_fallback.py - Provider-neutral, Planning.md):
AnalysisResult(transcript_text, segments, duration_seconds, metrics, pauses_ok)
where metrics always carries the five text-derived fields; pause fields appear
only when timestamps parsed.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

PriceTag = dict[str, float]  # metric_name -> value

# Filler list: keep close to the spike's counts. Order matters only for phrase spans.
FILLER_WORDS = ("uhm", "uh", "um", "erm", "hmm", "like")
FILLER_PHRASES = ("you know", "i mean", "sort of", "kind of")

_TS_LINE = re.compile(
    r"^\s*(?:\[(\d{1,2}):(\d{2})\]|(\d{1,2}):(\d{2}):(\d{2})|(\d{1,2}):(\d{2}))\s?"
)
LONG_PAUSE_THRESHOLD_S = 1.5
ARTICULATION_FALLBACK_WPM = 150.0
MIN_SEGMENTS_FOR_PERCENTILE = 5


@dataclass
class Segment:
    start_seconds: int
    text: str

    @property
    def word_count(self) -> int:
        return len(_words(self.text))


@dataclass
class AnalysisResult:
    transcript_text: str
    segments: list[Segment]
    duration_seconds: float | None
    metrics: dict[str, float]
    pauses_ok: bool
    notes: list[str] = field(default_factory=list)

    def as_json(self) -> str:
        return json.dumps(
            {
                "metrics": self.metrics,
                "duration_seconds": self.duration_seconds,
                "pauses_ok": self.pauses_ok,
                "notes": self.notes,
            }
        )


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


# ---------------------------------------------------------------------------
# Parser (M:SS lines; bracket/H:MM:SS accepted defensively per plan)
# ---------------------------------------------------------------------------
def parse_transcript(raw: str) -> list[Segment]:
    segments: list[Segment] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _TS_LINE.match(line)
        if m:
            if m.group(1) is not None:          # [M:SS]
                seconds = int(m.group(1)) * 60 + int(m.group(2))
                text = line[m.end():].strip()
            elif m.group(3) is not None:        # H:MM:SS
                seconds = int(m.group(3)) * 3600 + int(m.group(4)) * 60 + int(m.group(5))
                text = line[m.end():].strip()
            else:                               # M:SS
                seconds = int(m.group(6)) * 60 + int(m.group(7))
                text = line[m.end():].strip()
            # spike quirk: strip leading punctuation after the stamp
            text = text.lstrip(" ,.-")
            segments.append(Segment(start_seconds=seconds, text=text))
        elif segments:
            # continuation of the previous paragraph
            segments[-1].text = (segments[-1].text + " " + line).strip()
        else:
            segments.append(Segment(start_seconds=0, text=line))
    return segments


def has_parseable_timestamps(raw: str) -> bool:
    return any(_TS_LINE.match(line.strip()) for line in raw.splitlines())


# ---------------------------------------------------------------------------
# oEmbed duration fetch (Plan B: last-timestamp estimate if it fails)
# ---------------------------------------------------------------------------
async def fetch_oembed_duration(loom_url: str, timeout: float = 20.0) -> float | None:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://www.loom.com/v1/oembed?url=" + quote(loom_url, safe="")
            )
        if resp.status_code == 200:
            data = resp.json()
            duration = data.get("duration")
            if duration:
                return float(duration)
    except Exception:  # noqa: BLE001 - oEmbed failure is None (Plan B kicks in)
        return None
    return None


def estimate_duration_from_segments(
    segments: list[Segment], articulation_wpm: float
) -> float | None:
    """Plan B: last timestamp + est. speech time of the final paragraph."""
    if not segments:
        return None
    last = segments[-1]
    if last.word_count <= 0:
        return float(last.start_seconds)
    final_speech = last.word_count / articulation_wpm * 60.0
    return float(last.start_seconds) + final_speech


# ---------------------------------------------------------------------------
# The five text-derived metrics + pause estimation (spike-validated math)
# ---------------------------------------------------------------------------
def compute_fillers(text: str) -> tuple[int, int, float]:
    """(filler_word_count, total_words, filler_rate_pct) over raw text."""
    words = _words(text)
    total = len(words)
    count = 0
    lowered = text.lower()
    for phrase in FILLER_PHRASES:
        count += len(re.findall(r"\b" + re.escape(phrase) + r"\b", lowered))
    count += sum(1 for w in words if w in FILLER_WORDS)
    rate = (count / total * 100.0) if total else 0.0
    return count, total, rate


def compute_repetitions(text: str) -> int:
    """Adjacent same-word repeats (spike method)."""
    words = _words(text)
    return sum(1 for a, b in zip(words, words[1:]) if a == b)


def compute_wpm(total_words: int, duration_seconds: float | None) -> float | None:
    if not duration_seconds or duration_seconds <= 0:
        return None
    return total_words / duration_seconds * 60.0


def articulation_rate_wpm(segments: list[Segment]) -> float:
    """85th-percentile per-paragraph rate; falls back to ~150 wpm with <5 paragraphs.
    This is the corrected math - the old overall-WPM version cancelled to zero."""
    rates: list[float] = []
    for i in range(len(segments) - 1):
        gap = segments[i + 1].start_seconds - segments[i].start_seconds
        if gap > 0 and segments[i].word_count > 0:
            rates.append(segments[i].word_count / gap * 60.0)
    if len(rates) < MIN_SEGMENTS_FOR_PERCENTILE:
        return ARTICULATION_FALLBACK_WPM
    return float(statistics.quantiles(rates, n=20, method="inclusive")[16])


def estimate_pauses(
    segments: list[Segment], articulation_wpm: float
) -> tuple[int, float]:
    """(long_pause_count, longest_pause_seconds) - residual per paragraph."""
    residuals: list[float] = []
    for i in range(len(segments) - 1):
        gap = segments[i + 1].start_seconds - segments[i].start_seconds
        spoken = segments[i].word_count / articulation_wpm * 60.0
        residuals.append(gap - spoken)
    long_count = sum(1 for r in residuals if r >= LONG_PAUSE_THRESHOLD_S)
    longest = max((r for r in residuals), default=0.0)
    return long_count, max(longest, 0.0)


# ---------------------------------------------------------------------------
# Full pipeline entrypoint
# ---------------------------------------------------------------------------
async def analyze_loom_submission(
    transcript_text: str,
    loom_url: str | None = None,
    oembed_duration: float | None = None,
) -> AnalysisResult:
    """Compute all seven metrics from a pasted transcript (+ optional oEmbed duration).

    Never raises on bad input: with unparseable timestamps, pause metrics are
    omitted and pauses_ok=False (the agent tells the user transparently).
    """
    notes: list[str] = []
    ts_ok = has_parseable_timestamps(transcript_text)
    segments = parse_transcript(transcript_text) if ts_ok else []

    filler_count, total_words, filler_rate = compute_fillers(transcript_text)
    metrics: dict[str, float] = {
        "filler_word_count": float(filler_count),
        "filler_rate": round(filler_rate, 2),
    }

    duration = oembed_duration
    duration_source = "oembed" if duration else None

    articulation = articulation_rate_wpm(segments) if ts_ok else ARTICULATION_FALLBACK_WPM

    if duration is None and ts_ok and segments:
        duration = estimate_duration_from_segments(segments, articulation)
        if duration is not None:
            duration_source = "estimated (Plan B)"

    wpm = compute_wpm(total_words, duration)
    if wpm is not None:
        metrics["words_per_minute"] = round(wpm, 1)
    metrics["repetition_count"] = float(compute_repetitions(transcript_text))
    if duration is not None:
        metrics["duration_seconds"] = round(float(duration), 2)

    pauses_ok = False
    if ts_ok and len(segments) >= 2:
        long_count, longest = estimate_pauses(segments, articulation)
        metrics["long_pause_count"] = float(long_count)
        metrics["longest_pause_seconds"] = round(longest, 2)
        pauses_ok = True
    else:
        notes.append(
            "couldn't estimate pauses from what you pasted - everything else came "
            "through fine"
        )

    if duration_source == "estimated (Plan B)":
        notes.append("duration was estimated from the transcript (Loom metadata unavailable)")

    return AnalysisResult(
        transcript_text=transcript_text,
        segments=segments,
        duration_seconds=duration,
        metrics=metrics,
        pauses_ok=pauses_ok,
        notes=notes,
    )


async def persist_result_metrics(
    repo: Any, journal_entry_id: int, result: AnalysisResult
) -> None:
    """Write metrics into entry_metrics via the repo (deterministic code, never LLM)."""
    await repo.record_entry_metrics(journal_entry_id, result.metrics)
