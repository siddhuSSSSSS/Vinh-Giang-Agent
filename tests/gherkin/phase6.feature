# Vin's Sidekick — Phase 6 features (demo polish)
# Executed by tests/test_phase6.py

Feature: Demo polish — startup safety, runbook, log hygiene

  Scenario: a bad OpenAI key aborts before polling
    Given post_init runs with an invalid OPENAI_API_KEY
    When pre-flight 2 probes models.list
    Then the failure is caught, logged, and stop_running is called
    And one clear SystemExit names the fix - no partial bot alive

  Scenario: noisy third-party loggers are pinned to WARNING
    Given basicConfig at the configured level
    When _setup_logging runs
    Then httpx, httpcore, apscheduler and telegram loggers sit at WARNING or above

  Scenario: the README carries the Demo Day Runbook
    Given the README
    When inspected
    Then a "Demo Day Runbook" section exists with the pre-demo checklist
    And it maps demo beats to the stage graph

  Scenario: the error handler never leaks secrets into user-visible output
    Given the global on_error handler
    When its source is inspected
    Then it logs exc_info with a generic message
    And no passcode/api_key words appear
    And no reply_text embeds the error content

  Scenario: agent_core never logs user message text
    Given handle_incoming's logging surface
    When inspected
    Then exactly one logger call exists (the failure branch)
    And it logs ids, never the message content
