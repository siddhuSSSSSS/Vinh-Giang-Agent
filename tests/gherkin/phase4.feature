# Vin's Sidekick — Phase 4 features (proactive scheduling)
# Executed by tests/test_gherkin_phase4.py

Feature: Proactive scheduling — the ordered rule set

  Background:
    Given a fresh in-memory database with the shared rule engine

  Scenario: early-stage silence fires a capped re-engagement nudge
    Given a verified user still in onboarding, silent for one day
    When the daily checks run
    Then "reengagement_nudge" returns
    And the counter increments toward its cap of 3

  Scenario: the nudge stops at its cap and never becomes nagging
    Given a user whose reengagement_nudge_count is already 3
    When the daily checks run
    Then no reason returns and the counter stays put

  Scenario: re-engagement resets the counter in the same commit
    Given a user at count 2 who messages again
    When record_daily_engagement lands
    Then the counter is back to 0 without a separate write

  Scenario: waiting_24h is an intentional wait, never nudged
    Given a user in waiting_24h, silent for days
    When the daily checks run
    Then no re-engagement nudge fires

  Scenario: missed days keyed on engagement, never on the transition day
    Given a weekly-cycle user whose week started on day N
    When the daily checks run for day N
    Then no missed day is flagged for day N

  Scenario: two misses trigger exactly one adaptive-replanning reason
    Given unresolved missed days on day N-1 and N-2
    When the daily checks run
    Then "missed_day_nudge" returns and the flag is set
    When the daily checks run again the next day (still unresolved)
    Then the reason does not repeat until a day is resolved

  Scenario: weekly re-evaluation fires at the 7-day boundary, once
    Given a weekly-cycle user whose week started 7 days ago
    When the daily checks run
    Then "weekly_reeval_prompt" returns
    When they run again that same day
    Then the boundary is not re-fires

  Scenario: plain daily check-in only in weekly_cycle, once per day
    Given a weekly-cycle user with no organic message today
    When the daily checks run
    Then "daily_checkin" returns
    Given the same user already messaged today
    When the daily checks run
    Then no check-in reason returns

  Scenario: /advance collects reasons day-by-day and batches one message
    Given a verified user and /advance 12
    When the loop runs each day's checks in order
    Then the reasons collected equal N separate runs of the same helper
    And dedupe_reasons preserves first-seen order for the consolidated message

  Scenario: restart within the same local hour does not double-nudge
    Given users.last_sweep_day already recorded for today
    When the hourly sweep passes again
    Then the user is skipped (record_sweep_run wrote unconditionally)
