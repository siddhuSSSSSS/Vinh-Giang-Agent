# Vin's Sidekick - Phase 6.b: OpenAI-compatible bridge for OpenCode
# Executed by tests/test_compat_server.py

Feature: OpenCode compatibility via an OpenAI-shaped bridge (Option B)

  Background:
    Given the bot process runs with COMPAT_SERVER_PORT enabled
    And the bridge binds only after both pre-flights pass

  Scenario: OpenCode lists available models
    Given a client sends GET /v1/models with Bearer demo passcode
    Then the reply is 200 with object "list"
    And both OPENAI_MODEL and OPENAI_MODEL_ANALYSIS appear as model ids

  Scenario: Wrong or missing bearer token is rejected
    Given a client sends GET /v1/models without a Bearer token
    Then the reply is 401 shaped like an OpenAI error

  Scenario: A chat completion becomes an agent turn
    Given a client posts an OpenAI-chat payload to /v1/chat/completions
      | role      | content          |
      | system    | sys              |
      | user      | I mumbled today  |
    When the bridge dispatches the last user message to agent_core
    Then the reply is 200 with an OpenAI chat.completion body
    And the message content equals the agent's reply
    And agent_core was called with platform "opencode" and the user text

  Scenario: Agent snag surfaces as 502 with the graceful line intact
    Given an agent whose turn returns error_reply
    When a client posts a valid chat completion payload
    Then the reply is 502 with type "agent_unavailable"
    And the error body carries the agent's graceful reply verbatim

  Scenario: Malformed and unsupported requests fail loudly but safely
    When a client posts malformed JSON to /v1/chat/completions
    Then the reply is 400
    When a client posts to /v1/embeddings
    Then the reply is 404
    When a chat payload carries no user-role message
    Then the reply is 400
