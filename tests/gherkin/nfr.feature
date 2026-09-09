# Vin's Sidekick — Non-functional requirements
# Executed by tests/test_nfr.py

Feature: Non-functional requirements

  Scenario: read-path latency at POC scale
    Given a user with 60 conversation messages, metrics, a summary chunk and 20 missed days
    When the per-turn read path runs (state + recent + summary + missing + trend)
    Then it completes within 50 ms

  Scenario: static prompt token budget
    Given the static system-prompt blocks
    When tokenized with the production tokenizer
    Then they cost fewer than 2500 tokens

  Scenario: context-bloat guardrail
    Given adversarially long user-supplied strings (10k-50k chars)
    When the bounded state summary is built
    Then the summary remains bounded
    And unbounded growth is impossible without an explicit truncation contract

  Scenario: concurrent task safety on one connection
    Given four interleaved async tasks writing messages, engagement and journal data
    When the writes complete
    Then every write landed exactly once
    And SQLITE_BUSY never surfaced

  Scenario: multi-user data isolation
    Given three users each holding exactly one private message
    When each user reads their own history
    Then no message crosses user boundaries

  Scenario: configuration errors never leak secret values
    Given a configuration error is raised
    When the message is inspected
    Then it names only variable names, never their values

  Scenario: production DB directory bootstrap
    Given a DATABASE_PATH whose parent directories do not exist
    When open_repo runs
    Then the directory tree is created
    And the same DB reopens with persisted data intact

  Scenario: log-noise discipline
    Given INFO-level logging with quiet third-party loggers
    When probes are emitted at INFO and DEBUG
    Then only INFO+ records are captured

  Scenario: repeated /reset epochs never lose data
    Given three journey runs each with journal metrics
    When /reset runs after each
    Then the epoch count is exactly three
    And each run's rows survive under their own epoch
    And current-epoch metric reads see an empty fresh journey

  Scenario: /wipe then re-registration starts clean
    Given a user wiped with /wipe
    When the same platform identity re-registers
    Then their new account has epoch 0, day 0 and onboarding state
