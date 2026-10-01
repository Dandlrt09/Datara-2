-- 0005_archives_survive_session_delete.sql: Archives outlive their chat session
--
-- Why: 0001 created `archives.chat_session` as
--   `TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE`,
-- so deleting a chat session silently destroyed the saved analyses that were
-- meant to be reopened later. SQLite has no
-- `ALTER TABLE ... DROP CONSTRAINT`, so the FK change requires the standard
-- non-destructive table rebuild: create the new table, copy every row
-- (same ids and columns), drop the old table, rename the new one into place.
--
-- New schema:
--   * `chat_session` is nullable and `ON DELETE SET NULL`: deleting a session
--     keeps the archive, it just loses the (now dead) session reference.
--   * `user_id` stays `ON DELETE CASCADE`: deleting a user still removes all
--     of that user's analyses.
--   * `name`, `payload_json`, `created_at` are unchanged.
--   * `idx_archives_user_created` supports the list query `(user_id, created_at)`.
--
-- Foreign keys: the rebuild is FK-safe under `PRAGMA foreign_keys=ON`. No other
-- table references `archives` (no inbound FKs), and the `INSERT ... SELECT`
-- only copies rows whose `chat_session` already satisfied the old NOT NULL FK.
-- PRAGMAs are therefore NOT toggled here.
--
-- Style: guarded/idempotent in line with 0001-0004 (`IF NOT EXISTS`), and the
-- migration runner records version 5 so this only persists once.

-- 1. Create the replacement table with the corrected FK.
CREATE TABLE IF NOT EXISTS archives_new (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL,
    chat_session  TEXT    REFERENCES chat_sessions(id) ON DELETE SET NULL,
    payload_json  TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 2. Copy every existing row unchanged (ids preserved, byte-for-byte columns).
--    On a re-run this only ever sees pre-existing rows, so it stays idempotent.
INSERT INTO archives_new (id, user_id, name, chat_session, payload_json, created_at)
SELECT id, user_id, name, chat_session, payload_json, created_at FROM archives;

-- 3. Swap the tables.
DROP TABLE archives;
ALTER TABLE archives_new RENAME TO archives;

-- 4. Index the list path (user's archives ordered by creation time).
CREATE INDEX IF NOT EXISTS idx_archives_user_created
    ON archives(user_id, created_at);
