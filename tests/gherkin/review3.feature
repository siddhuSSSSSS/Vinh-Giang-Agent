# Vin's Sidekick — Third review round (robustness audit)
# Executed by tests/test_review3.py

Feature: Robustness — parser pauses, gates, and huge inputs

  Scenario: impossible M:SS stamps are dropped, never believed
    Given a paste containing a '59:59' stamp
    When parse_transcript runs
    Then the corrupt line is dropped entirely
    And the honest timestamp lines survive with correct seconds
    And no nonsense multi-hour pause value can be reported

  Scenario: the longest reported pause stays within a sane ceiling
    Given fabricate segments 40 minutes apart with tiny word counts
    When estimate_pauses runs
    Then longest_pause_seconds is capped at 600s
    So a corrupt-paste outlier can never masquerade as a real pause

  Scenario: same-second stamps don't crash and fall back honestly
    Given two paragraphs stamped identically
    When parse_transcript + articulation_rate_wpm run
    Then both survive and the rate falls back to the 150 wpm constant

  Scenario: descending stamps (negative gaps) don't crash
    Given a paste where 11:59 precedes 00:00
    When estimate_pauses runs
    Then long_count and longest_pause_seconds are non-negative

  Scenario: a future submission timestamp never clears the 24h gate
    Given a submission timestamp one hour in the future (clock skew)
    When is_24h_gate_cleared is checked at day 0
    Then it returns false
    And with no recorded submitted_effective_day, it also returns false (wall-clock alone)
    And a submission 10 minutes ago with submitted_effective_day=0 clears on day 1 (day short-circuits first)

  Scenario: weekly re-eval rejects bad states
    Given weekly_cycle with start day 12 and current day 10 (nonsense)
    When is_weekly_reeval_due runs
    Then it returns false
    Given weekly_cycle with no start day or wrong stage
    Then it also returns false

  Scenario: a 100k-char single word files as transcript
    Given one unbroken 100k-char string
    When classify_text runs
    Then it is "transcript" (never sent to the LLM)

  Scenario: transcript docs mixed with stamps and huge lines file cleanly
    Given a doc with a real timestamped paragraph plus a 30k-word line
    When classify_text runs
    Then it is "transcript"
