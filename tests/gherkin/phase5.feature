# Vin's Sidekick — Phase 5 features (Loom parsing + metrics + voice fallback)
# Executed by tests/test_gherkin_phase5.py

Feature: Media metrics — the communication mirror's numbers

  Background:
    Given the real Phase 0.5 spike transcript committed as a regression fixture

  Scenario: the spike transcript reproduces the reference numbers
    Given the spike transcript with its real runtime duration
    When analyze_loom_submission computes the metrics
    Then filler_word_count is 36
    And filler_rate is about 11.6
    And words_per_minute is about 131
    And repetition_count is 5
    And pauses_ok is true

  Scenario: unparseable input is fail-soft
    Given a transcript whose timestamps were mangled or absent
    When analyze_loom_submission runs
    Then nothing crashes
    And the two pause metrics are OMITTED, never written as zero
    And the five text-derived metrics still compute
    And the result flags pauses_ok false with a transparent note

  Scenario: duration Plan B when oEmbed is unavailable
    Given no oEmbed duration
    When analyze_loom_submission runs
    Then duration is estimated from the last paragraph timestamp
    And the result notes say the duration was estimated
    And words_per_minute still computes

  Scenario: bracket and H:MM:SS timestamp formats parse
    Given "[0:00] ..." and "00:02:03 ..." style lines
    When parse_transcript runs
    Then segments start at the correct seconds
    And continuation lines merge into the prior paragraph

  Scenario: voice-fallback metrics compute from exact word timestamps
    Given a word-level timestamp list with two >1.5s gaps
    When analyze_voice_transcript runs
    Then long_pause_count is 2 and longest_pause_seconds matches the largest gap
    And pauses_ok is true (real ASR, better than the Loom estimate)

  Scenario: OGG voice notes are detected for conversion, WAV passes through
    Given content with OGG or unknown magic bytes
    When needs_conversion runs
    Then it is true
    Given RIFF/ID3/mpeg content
    Then it is false

  Scenario: the engine computes metrics on a complete Loom submission
    Given a Loom link already recorded and a transcript now submitted
    When handle_incoming processes the transcript
    Then the reply includes the computed numbers
    And the media_refs row is marked processed
    And entry_metrics holds at least five metrics
    And no LLM call was needed for any of it

  Scenario: metrics are code-computed, never the model's job
    Given the analysis modules
    When their imports are inspected
    Then no LLM client appears anywhere in them
