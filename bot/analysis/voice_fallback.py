"""Voice-note fallback ASR (Phase 5 RARE branch - full-metrics mode only).

Fires ONLY when (a) the Loom flow failed, AND (b) the user picked "full metrics"
at that moment (self_report needs none of this). Flow per Planning.md:
1. Telegram voice note arrives as OGG/Opus (typically 1-4 MB for up to 20 min,
   comfortably under the cloud Bot API's 20 MB limit - no local server needed)
2. OpenAI's transcription input formats are mp3/mp4/mpeg/mpga/m4a/wav/webm - NOT
   ogg - so a lightweight ffmpeg conversion may be needed (single call, deprecated
   full pipeline explicitly avoided)
3. whisper-1 (verbose_json + word timestamps) yields EXACT word-level pause data,
   better than the Loom estimate path - an acknowledged bonus of this branch
4. Output is the same provider-neutral shape as loom.py's, so the metric
   computation stays single-sourced (switching to Deepgram = one module)

whisper-1 is deprecated (Aug 26 2026, shutdown Feb 2027): acceptable precisely
because this branch is rare, and the interface is provider-agnostic by design.
"""

from __future__ import annotations

import logging
import os
import subprocess  # noqa: S404 - ffmpeg invocation is deliberate, local CLI
from dataclasses import dataclass
from typing import Any

from bot import config
from bot.analysis.loom import Segment, compute_fillers, compute_repetitions, compute_wpm

logger = logging.getLogger(__name__)

SUPPORTED_INPUT_FORMATS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"}


@dataclass
class VoiceAnalysisResult:
    transcript_text: str
    duration_seconds: float | None
    metrics: dict[str, float]
    word_timestamps: list[tuple[float, str]]  # exact per this branch
    pauses_ok: bool  # always True here (real ASR timestamps), modulo ASR failure


# ---------------------------------------------------------------------------
# Container handling (OGG/Opus -> a transcribable format)
# ---------------------------------------------------------------------------
def needs_conversion(content: bytes, mime_type: str | None = None) -> bool:
    if mime_type and mime_type.lower() in {"audio/mpeg", "audio/mp4", "audio/x-m4a"}:
        return False
    if mime_type and mime_type.lower() in {"audio/ogg", "application/ogg"}:
        return True
    # unknown container: assume telegram's default OGG/Opus
    known = (b"RIFF", b"ID3", b"\xff\xfb", b"fLaC", b"OggS")
    return not any(content.startswith(m) for m in known)


def convert_ogg_to_wav(content: bytes) -> bytes | None:
    """One lightweight ffmpeg call: OGG/Opus -> 16k mono WAV in memory."""
    import shutil
    import tempfile

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        logger.error("ffmpeg not on PATH - required for voice-fallback conversion")
        return None
    with tempfile.TemporaryDirectory() as td:
        inbox = os.path.join(td, "in.ogg")
        outbox = os.path.join(td, "out.wav")
        with open(inbox, "wb") as f:
            f.write(content)
        proc = subprocess.run(  # noqa: S603
            [ffmpeg, "-y", "-i", inbox, "-ar", "16000", "-ac", "1", outbox],
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0 or not os.path.exists(outbox):
            logger.error("ffmpeg failed rc=%s", proc.returncode)
            return None
        with open(outbox, "rb") as f:
            return f.read()


def wav_bytes_to_file_tuple(content: bytes) -> tuple[str, bytes, str]:
    """OpenAI SDK shape for raw file upload: (filename, bytes, content_type)."""
    return ("audio.wav", content, "audio/wav")


# ---------------------------------------------------------------------------
# ASR call (verbose_json + word timestamps)
# ---------------------------------------------------------------------------
async def transcribe_voice_note(
    openai_client: Any, content: bytes, *, mime_type: str | None = None
) -> tuple[str, float, list[tuple[float, str]], dict[str, Any]]:
    """(transcript, duration_s, [(start, word)...], raw_response_meta)."""
    payload = content
    if needs_conversion(content, mime_type):
        converted = convert_ogg_to_wav(content)
        if converted is None:
            raise RuntimeError(
                "voice note needs ffmpeg conversion but ffmpeg is unavailable - "
                "ask the user to resend or switch to self-report"
            )
        payload = converted
    file_tuple = wav_bytes_to_file_tuple(payload)
    resp = await openai_client.audio.transcriptions.create(
        model=config.OPENAI_TRANSCRIBE_MODEL,
        file=file_tuple,
        response_format="verbose_json",
        timestamp_granularities=["word"],
    )
    transcript = (getattr(resp, "text", "") or "").strip()
    duration = float(getattr(resp, "duration", 0.0) or 0.0)
    words: list[tuple[float, str]] = []
    raw_words = getattr(resp, "words", None) or []
    for w in raw_words:
        start = getattr(w, "start", None)
        word = getattr(w, "word", None)
        if start is not None and word:
            words.append((float(start), str(word)))
    return transcript, duration, words, {"model": config.OPENAI_TRANSCRIBE_MODEL}


# ---------------------------------------------------------------------------
# Metric computation in the shared shape
# ---------------------------------------------------------------------------
def audio_words_to_segments(word_timestamps: list[tuple[float, str]],
                            duration: float) -> list[Segment]:
    """Group word timestamps into pseudo-paragraph segments at >1.5s gaps so the
    SAME pause math as the Loom path applies (provider-neutral contract)."""
    if not word_timestamps:
        return []
    segments: list[Segment] = []
    cur_start = 0.0
    cur_words: list[str] = []
    last_end: float | None = None
    for start, word in word_timestamps:
        if last_end is not None and (start - last_end) > 1.5:
            seg = Segment(start_seconds=int(cur_start), text=" ".join(cur_words))
            segments.append(seg)
            cur_start = start
            cur_words = []
        if not cur_words:
            cur_start = start
        cur_words.append(word)
        last_end = start
    if cur_words:
        segments.append(
            Segment(start_seconds=int(cur_start), text=" ".join(cur_words))
        )
    return segments


def analyze_voice_transcript(
    transcript_text: str, duration: float, word_timestamps: list[tuple[float, str]]
) -> VoiceAnalysisResult:
    filler_count, total_words, filler_rate = compute_fillers(transcript_text)
    metrics: dict[str, float] = {
        "filler_word_count": float(filler_count),
        "filler_rate": round(filler_rate, 2),
        "repetition_count": float(compute_repetitions(transcript_text)),
    }
    wpm = compute_wpm(total_words, duration)
    if wpm is not None:
        metrics["words_per_minute"] = round(wpm, 1)
    metrics["duration_seconds"] = round(duration, 2)

    pauses_ok = False
    if word_timestamps:
        # EXACT word-level pauses from real ASR: iterate consecutive word gaps
        gaps = [
            (b[0] - a[0])
            for a, b in zip(word_timestamps, word_timestamps[1:])
        ]
        longs = sum(1 for g in gaps if g >= 1.5)
        longest = max((g for g in gaps), default=0.0)
        metrics["long_pause_count"] = float(longs)
        metrics["longest_pause_seconds"] = round(longest, 2)
        pauses_ok = True
    return VoiceAnalysisResult(
        transcript_text=transcript_text,
        duration_seconds=duration,
        metrics=metrics,
        word_timestamps=word_timestamps,
        pauses_ok=pauses_ok,
    )


async def full_metrics_pipeline(
    openai_client: Any, voice_bytes: bytes, *, mime_type: str | None = None
) -> VoiceAnalysisResult:
    transcript, duration, words = await transcribe_voice_note(
        openai_client, voice_bytes, mime_type=mime_type
    )
    return analyze_voice_transcript(transcript, duration, words)


__all__ = (
    "VoiceAnalysisResult",
    "full_metrics_pipeline",
    "transcribe_voice_note",
    "analyze_voice_transcript",
    "audio_words_to_segments",
    "needs_conversion",
    "convert_ogg_to_wav",
)
