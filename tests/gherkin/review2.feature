# Vin's Sidekick — Second review round (Phase 4 code audit)
# Executed by tests/test_review2.py

Feature: Review-2 regression guards and behavioral contracts

  Scenario: passcode lockout columns round-trip exactly
    Given a user with five failed attempts and a lockout timestamp
    When the row is re-read
    Then failed_attempts is 5 and locked_until matches
    And passcode_verified is still false

  Scenario: an expired lockout clears for retry
    Given a lockout set in the past
    When the gate evaluates it
    Then the comparison sees expired
    And clearing writes failed_attempts=0, locked_until=None

  Scenario: rate-limit gap comparison is honest over last_message_at
    Given a message stamped 3 s ago and a 2 s limit
    When the gap is compared
    Then the message is admitted

  Scenario: /advance only ever moves the day forward
    Given a user at day 3
    When /advance bumps once
    Then effective day reads 4 or later
    And nothing in the repo path can move the offset backwards

  Scenario: the hourly sweep builds a sender PER USER
    Given a verified user matching DAILY_TICK_HOUR locally
    When the sweep composes a nudge
    Then the send function was constructed for that user's chat
    And last_sweep_day is stamped unconditionally afterwards

  Scenario: one consolidated proactive message for many reasons
    Given reasons [daily_checkin, weekly_reeval_prompt, daily_checkin]
    When initiate_conversation composes
    Then exactly ONE send happens
    And empty reason lists send nothing and call no LLM

  Scenario: the 24h-gate job is a no-op after stage progress
    Given a user whose current_stage is no longer waiting_24h
    When check_24h_gate fires
    Then no LLM composition and no send occur

  Scenario: the sweep's timezone filter admits only matching local hours
    Given one user in UTC and another in UTC+14
    When the hourly sweep runs at the UTC hour
    Then only the UTC user is processed and stamped
    And the UTC+14 user is untouched

  Scenario: classification holds at the window edge
    Given a ~4000-char single-line message with no timestamps
    When classify_text runs
    Then it is "chat" (inside the window)
    Given the same text plus two timestamped lines
    When classify_text runs again
    Then it is "transcript"

  Scenario: bracket-timestamp transcripts are recognized
    Given "[0:00] ..." style lines
    When classify_text runs
    Then it is "transcript"

  Scenario: the Loom regex matches share and embed links only
    Given a loom.com/share/ or loom.com/embed/ URL (trailing slash ok)
    When LOOM_RE searches
    Then it matches
    Given a non-Loom link
    Then it does not match

  Scenario: proactive composition contexts never mention credential words
    Given the static REASON_PROMPTS
    When each prompt is inspected
    Then no api_key/token/passcode/secret words appear
