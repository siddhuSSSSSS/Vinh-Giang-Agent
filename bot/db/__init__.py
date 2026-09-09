"""Persistence layer: aiosqlite schema + repository.

Phase 0 scaffold stub.
- schema.sql (Phase 2): users / state / journal_entries / entry_metrics /
  media_refs / missed_days / daily_engagement / conversation_messages / summary_chunks,
  PRAGMAs journal_mode=WAL + foreign_keys=ON + busy_timeout=5000,
  epoch-stamped day-scoped tables.
- repo.py (Phase 2): thin async wrappers; single shared connection stored on
  application.bot_data["db"], opened in post_init, closed in post_shutdown.
"""
