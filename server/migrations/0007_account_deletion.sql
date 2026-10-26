-- 0007_account_deletion.sql: deferred account deletion (T3).
-- ``users.pending_deletion_at`` holds the PURGE DEADLINE, not the request time
-- (decision D1): when it is non-NULL and has already passed, the hourly sweep
-- purges the account. NULL means no deletion is scheduled. Storing the deadline
-- makes the sweep a single ``<= datetime('now')`` comparison and lets the UI show
-- the exact date the account disappears.
-- ALTER TABLE ADD COLUMN is a metadata-only change in SQLite (no table rewrite).
ALTER TABLE users ADD COLUMN pending_deletion_at TEXT;

-- The hourly sweep filters on a deadline that is set for a small subset of
-- users; the index keeps it from scanning every row.
CREATE INDEX IF NOT EXISTS idx_users_pending_deletion
    ON users(pending_deletion_at);
