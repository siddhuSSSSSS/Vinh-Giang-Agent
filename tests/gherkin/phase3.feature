# Vin's Sidekick — Phase 3 features (conversation engine)
# Executed by tests/test_gherkin_phase3.py

Feature: Phase 3 — conversation engine, stage machine, handlers

  Background:
    Given a fresh in-memory database with the real AgentCore wired to a mock LLM

  Scenario: onboarding captures are structured, not lost in scrollback
    Given a new user chatting with the sidekick
    When onboarding turns happen (name via journal, motivation + timezone via state)
    Then user.timezone is set from the message
    And state.motivation_summary matches what the model persisted
    And day_zero_at is realigned to local midnight exactly once (first timezone set)

  Scenario: the full stage graph advances only through legal moves
    Given a user that genuinely completes each stage with its gates satisfied
    When advance_stage is called for every next stage in sequence
    Then every move lands (no tool errors)
    And entering weekly_cycle stamps weekly_cycle_started_effective_day

  Scenario: turn failure keeps user data durable and replies gracefully
    Given an LLM outage mid-turn
    When handle_incoming runs
    Then the user's message still landed in the conversation window
    And the user got the graceful fallback line
    And no assistant echo was fabricated

  Scenario: summary submissions file without an LLM turn
    Given a long text that reads as a summary
    When handle_incoming classifies it
    Then no LLM call is made
    And the text files into media_refs.summary_text
