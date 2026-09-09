-- Vin's Sidekick schema (Phase 2 deliverable)
-- Idempotent, no migration framework (POC scope). Tables from Planning.md verbatim
-- with the review-hardening fixes: epoch columns, NOT NULL day_zero_at at SQL level,
-- daily_engagement table, nullable media path columns, narrowed conversation roles.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL DEFAULT 'telegram',
  platform_user_id TEXT NOT NULL,
  name TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  day_zero_at TEXT NOT NULL DEFAULT (datetime('now')),  -- stamped at row creation, never NULL
  simulated_day INTEGER NOT NULL DEFAULT 0,   -- offset added by /advance, not the absolute day
  epoch INTEGER NOT NULL DEFAULT 0,           -- incremented by /reset; disambiguates day-numbered history
  timezone TEXT,                              -- IANA tz name, captured at onboarding
  last_sweep_day INTEGER,                     -- backs the hourly sweep's dedup
  passcode_verified INTEGER NOT NULL DEFAULT 0,
  failed_attempts INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT,
  last_message_at TEXT,
  UNIQUE(platform, platform_user_id)
);

CREATE TABLE IF NOT EXISTS state (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  current_stage TEXT NOT NULL DEFAULT 'onboarding' CHECK (current_stage IN (
    'onboarding','initial_recording','waiting_24h','audit_day1','audit_day2','audit_day3',
    'habit_selection','weekly_cycle')),
  current_habit TEXT,
  week_in_habit INTEGER NOT NULL DEFAULT 0,
  last_checkin_at TEXT,
  motivation_summary TEXT,
  recording_submitted_at TEXT,
  recording_submitted_effective_day INTEGER,
  kaizen_reveal_shown INTEGER NOT NULL DEFAULT 0,
  recording_ready_nudge_sent INTEGER NOT NULL DEFAULT 0,
  last_daily_checkin_sent_day INTEGER,
  adaptive_nudge_sent INTEGER NOT NULL DEFAULT 0,
  weekly_cycle_started_effective_day INTEGER,
  reengagement_nudge_count INTEGER NOT NULL DEFAULT 0,  -- caps early-stage re-engagement nudges
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS journal_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day INTEGER NOT NULL,
  epoch INTEGER NOT NULL DEFAULT 0,           -- disambiguates day numbers across /reset runs
  type TEXT NOT NULL CHECK (type IN ('exercise','audit_note','reflection','transcript')),
  content TEXT NOT NULL,
  completed INTEGER,                          -- 0/1/NULL; explicit bool coercion in repo
  reason TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_journal_user_day ON journal_entries(user_id, epoch, day);

CREATE TABLE IF NOT EXISTS entry_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
  metric_name TEXT NOT NULL,
  metric_value REAL NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(journal_entry_id, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_entry_metrics_entry ON entry_metrics(journal_entry_id);
CREATE INDEX IF NOT EXISTS idx_entry_metrics_name ON entry_metrics(metric_name);

CREATE TABLE IF NOT EXISTS media_refs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('loom','voice_fallback')),
  loom_url TEXT,                              -- the Loom share URL (primary path)
  loom_duration_seconds REAL,                 -- from oEmbed; NULL if it didn't return one
  transcript_text TEXT,                       -- raw pasted/uploaded transcript, held while pending
  summary_text TEXT,                          -- optional Loom AI summary, supplementary only
  telegram_file_id TEXT,                      -- only populated for the voice_fallback path
  telegram_message_id INTEGER,                -- only populated for the voice_fallback path
  fallback_mode TEXT CHECK (fallback_mode IN ('self_report','full_metrics')),
  stage_context TEXT,
  processed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, loom_url),
  UNIQUE(user_id, telegram_file_id)
);
CREATE INDEX IF NOT EXISTS idx_media_user ON media_refs(user_id);

CREATE TABLE IF NOT EXISTS missed_days (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day INTEGER NOT NULL,
  epoch INTEGER NOT NULL DEFAULT 0,
  resolved INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, epoch, day)
);
CREATE INDEX IF NOT EXISTS idx_missed_user_day ON missed_days(user_id, epoch, day);

CREATE TABLE IF NOT EXISTS daily_engagement (      -- backs the redefined missed-day logic
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day INTEGER NOT NULL,
  epoch INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, epoch, day)
);
CREATE INDEX IF NOT EXISTS idx_engagement_user_day ON daily_engagement(user_id, epoch, day);

CREATE TABLE IF NOT EXISTS conversation_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user','assistant')),  -- tool plumbing is ephemeral, never persisted
  content TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  folded_into_summary INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_conv_user_created ON conversation_messages(user_id, created_at);

CREATE TABLE IF NOT EXISTS summary_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  chunk_text TEXT NOT NULL,
  covers_from_message_id INTEGER NOT NULL,
  covers_to_message_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
