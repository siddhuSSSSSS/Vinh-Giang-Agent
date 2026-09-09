# Vin's Sidekick — Regression features
# These scenarios lock the bugs found during the thorough codebase review.
# Executed by tests/test_gherkin_regressions.py: one Scenario per test function.

Feature: Regression guards against fixed bugs

  Scenario: /reset is atomic
    Given a user with a habit set and prior history
    When the users-table update inside /reset fails mid-transaction
    Then the whole /reset is rolled back
    And the user keeps their old epoch, old habit, and old day_zero_at

  Scenario: scaffold integrity test is real
    Given the import test in test_scaffold.py
    When it runs against the bot/* tree
    Then every module (including bot.main and bot.db.repo) is imported and callable

  Scenario: per-stage prompt scoping is not vacuous
    Given current_stage is "weekly_cycle"
    When the system prompt is assembled
    Then it contains "STAGE: weekly cycle." scoping only
    And it does NOT leak habit_selection stage text

  Scenario: tool loop never fabricates passthrough items
    Given a model output containing items without serializable bodies
    When the tool loop processes the output array
    Then only genuine function_call_output items are appended
    And no {"type": "unknown"} junk enters the next API call

  Scenario: tool loop cap is bounded
    Given a model that always requests another tool call
    When run_tool_loop reaches its iteration cap
    Then ToolLoopLimitExceeded is raised with the exact cap count

  Scenario: tool executor argument mismatch degrades to JSON error
    Given a model tool call with arguments the executor does not accept
    When the tool loop executes it
    Then the executor is not called
    And the model receives a JSON error naming the bad parameter

  Scenario: duplicate engagement writes are idempotent
    Given five identical engagement writes for the same user-day
    When they are persisted
    Then only one daily_engagement row exists

  Scenario: re-flagging a resolved missed day stays resolved
    Given a missed day resolved earlier
    When the scheduler re-fires a flag for that same day
    Then unresolved-missed-day count stays zero

  Scenario: schema CHECK constraints enforce the stage/type enums
    Given the loaded schema
    When a write sets an invalid current_stage or journal type
    Then sqlite rejects it with an IntegrityError

  Scenario: foreign keys reject orphan writes
    Given the loaded schema with foreign_keys ON
    When a journal entry is written for a nonexistent user
    Then sqlite rejects it
