"""MediaAnalyzer protocol + shared result shape (Phase 5).

Provider-neutral contract per Planning.md: loom.py and voice_fallback.py both
produce the same normalized shape so metric computation is single-sourced and a
future provider (Deepgram/AssemblyAI/Uhm - see Further Considerations #15) is a
one-module swap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class AnalysisResult:
    """The normalized shape every media analyzer returns to the engine."""

    transcript_text: str
    metrics: dict[str, float]
    duration_seconds: float | None
    pauses_ok: bool
    notes: list[str] = field(default_factory=list)
    word_timestamps: list[tuple[float, str]] = field(default_factory=list)


class MediaAnalyzer(Protocol):
    """Implementations: analysis/loom.py (primary), analysis/voice_fallback.py
    (rare fallback). Future: a UhmAnalyzer lands here unchanged."""

    async def analyze(
        self, payload: Any, *, mime_type: str | None = None
    ) -> AnalysisResult: ...
