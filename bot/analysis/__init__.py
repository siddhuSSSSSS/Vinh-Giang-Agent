"""Media analysis layer.

Phase 0 scaffold stub.
- base.py (Phase 5): MediaAnalyzer protocol -> AnalysisResult; shared normalized
  (transcript_text, segment_or_word_timestamps, duration_seconds) output shape for
  every provider so metric computation stays single-sourced.
- loom.py (Phase 5, PRIMARY): oEmbed duration fetch + M:SS paragraph-timestamp
  parser + 5 deterministic metrics + articulation-rate pause estimation, fail-soft.
  Phase 0.5 spike PASSED: default-privacy oEmbed resolves; desktop copy-paste keeps
  `M:SS` timestamps (strip leading punctuation after the timestamp); 85th-percentile
  per-paragraph articulation rate produced no cancelling residuals on a real recording
  (see Phase-0.5-Spike-Results.md).
- voice_fallback.py (Phase 5, RARE fallback only): OGG/Opus voice note -> optional
  lightweight ffmpeg conversion (OpenAI accepts mp3/mp4/mpeg/mpga/m4a/wav/webm, not ogg)
  -> whisper-1 ASR. Same normalized output shape as loom.py.
"""
