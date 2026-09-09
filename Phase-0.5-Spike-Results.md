# Phase 0.5 — Loom Transcript-Parsing Spike: Results

Executed: Sept 9, 2026. Real recording, real copy-pasted transcript, live oEmbed call.
Test video: https://www.loom.com/share/d8c2c5c296c54835822d42b731b1b61f ("Building a Browser Agent Test Loop", 141.8s)
Transcript source: Loom transcript panel copy-paste, desktop, saved as `Transcript.txt` in this workspace.

## Decision gate verdict: PASS — proceed with the fail-soft pause-estimation design as planned.

## 1. oEmbed at DEFAULT privacy — WORKS
- `GET https://www.loom.com/v1/oembed?url=<share_url>` returned **200 OK** with the video
  left at whatever visibility Loom assigns by default (user confirms default is
  "anyone with the link" on their account).
- Payload confirms: `duration: 141.811` (seconds, float), `title`, `description`,
  `thumbnail_url`, iframe `html`, 1920x1440 dimensions.
- Consequence: the realistic first-run condition (user submits link without touching
  visibility settings) resolves `duration` with no extra step. The "set to anyone with
  the link" onboarding instruction stays as defensive copy, not a hard requirement,
  and the Plan-B duration fallback remains as belt-and-braces.

## 2. Transcript format (desktop copy-paste) — CONFIRMED PARSEABLE
- Format: `M:SS ` at line start, one paragraph per timestamp line. E.g. `0:00 Yeah, hello, ...`
- Timestamps **survive the copy** — 9/9 paragraphs carried timestamps.
- Quirk found: a timestamp can be followed directly by punctuation+space
  (`0:32 , this is, ...`) — parser must strip leading punctuation after the timestamp.
- Continuation lines without timestamps did not occur, but the parser handles them
  (append to previous paragraph).
- Not yet verified: mobile app copy format (optional spike step 2). Parser regex
  should defensively accept `H:MM:SS`, `HH:MM:SS`, and `[M:SS]` variants.

## 3. The five non-timestamp metrics — SENSIBLE VALUES
| Metric | Value | Note |
|---|---|---|
| words | 310 | from 9 paragraphs |
| filler_word_count | 36 | list: uhm, uh, um, you know, like, i mean |
| filler_rate | 11.6% | high — deliberate, as intended by the test |
| words_per_minute | 131 | 310 words / 141.8s — plausible conversational pace |
| repetition_count | 5 | adjacent same-word repeats |

Known limitation observed: Loom transcripts are ASR-generated, so homophone errors
appear in the raw text ("deliberate filters" for "fillers", "cap die at" for "cap at").
Filler sounds (uhm/uh) themselves transcribe reliably; this does not affect the metrics.

## 4. Corrected articulation-rate pause estimation — NO CANCELLING RESIDUALS
- Per-paragraph rates: 122–169 wpm; 85th-percentile baseline = **163 wpm**.
- Estimated silences per paragraph: only **2 of 8 negative** residuals — the old
  (overall-WPM) formula would have produced ~4/4 by mathematical construction.
- `long_pause_count` (≥1.5s) = 4; `longest_pause_seconds` = 10.2 (real gap before
  the 2:12 paragraph — visible dead air in the recording).
- Caveat: the final paragraph's trailing gap (to video end) is excluded (no next
  timestamp) — trailing silence is not counted as a "pause"; acceptable.

## 5. oEmbed-duration Plan B (last-timestamp fallback) — VALIDATED
- Estimate: last timestamp 132s + est. final speech 7.7s = **140s** vs real 142s
  (98.6% accurate). Good enough for WPM if oEmbed ever fails.

## 6. Fail-soft behavior — CONFIRMED
- Input with timestamps stripped: no crash, 9 segments parsed, timestamps flagged
  absent → the two pause metrics are omitted, the five core metrics still compute.

## Open leftovers (all minor, none blocking)
1. Mobile copy-paste format unverified (optional step) — parser already fail-soft.
2. Parser regex hardening for other formats (defensive, cheap).
3. Leading-punctuation strip after timestamps (noted in #2 above).

## Consequence for the build
Phase 5 (`bot/analysis/loom.py`) is now unblocked and can be built exactly as
specified: oEmbed fetch for duration + regex paragraph parse + five deterministic
metrics + articulation-rate pause estimation, fail-soft on unparseable input.
No design changes required — the spike confirmed every assumption.
