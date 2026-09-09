# Vin's Sidekick — Happy-path & behavioral features (coverage expansion)
# Executed by tests/test_gherkin_scenarios.py

Feature: Extended Gherkin coverage for data + persona contracts

  Background:
    Given a fresh in-memory database

  Scenario: timezone first-set signal fires exactly once
    Given a brand-new user
    When the timezone is set for the first time
    Then set_timezone reports it was the first set
    When the timezone is set a second time
    Then set_timezone reports it was NOT the first set

  Scenario: /advance bumps the offset without touching engagement history
    Given a verified user mid-journey
    When /advance 5 bumps simulated_day
    Then effective day math reads day+5
    And daily_engagement rows and last_message_at are untouched

  Scenario: Week-start boundary guard on weekly_cycle
    Given a user who just entered weekly_cycle on day N
    When missed-day detection runs for day N (transition day)
    Then no missed day is flagged for the transition day itself

  Scenario: metric trend respects the limit parameter
    Given 12 recorded metric points across days
    When get_metric_trend is called with default limit
    Then only the most recent 8 points are returned, oldest-to-newest

  Scenario: journal entry bool tri-state round trip
    Given journal entries with completed=True, False and None
    When all three are written and read back
    Then they persist as 1, 0 and NULL respectively

  Scenario: summary chunk marking is idempotent
    Given a set of messages folded into a summary chunk
    When mark_messages_folded runs twice on the same ids
    Then the recent-window query result is unchanged
    And no summary chunk duplication occurs

  Scenario: user identity is composite on (platform, platform_user_id)
    Given two users on different platforms with the same numeric id string
    When both register
    Then they are distinct rows with isolated state
