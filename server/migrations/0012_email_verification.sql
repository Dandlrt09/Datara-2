-- 0012_email_verification.sql: prove the address, recover the password.
--
-- Two things arrive together because they share one mechanism (D1): a one-time
-- token mailed to an address.
--
-- ``users.email_verified_at`` records WHEN the address was proven, not merely
-- that it was. A timestamp can never be confused with "verified by default":
-- every account that already exists keeps NULL, which is exactly its history
-- (it was created when Datara had no way to prove anything). Requiring the
-- address at login is what makes that NULL meaningful.
--
-- ``auth_tokens`` is the single token table for both flows. ``purpose`` keeps
-- them apart ('verify_email' vs 'reset_password') while the mechanics --
-- generation, hashing, expiry, one-shot redemption -- stay in one place. Only
-- the HASH is stored (never the raw token), exactly as with ``auth_sessions``:
-- a leaked database yields no usable links. ``used_at`` is what makes a link
-- single-use; ``email`` is the address the link was mailed to, so a future
-- email-change flow can tell that the proof belongs to the old address.
--
-- ALTER TABLE ADD COLUMN is metadata-only in SQLite (no rewrite), and the new
-- column is NULL-able with no default, so existing rows read as unverified.
BEGIN;
ALTER TABLE users ADD COLUMN email_verified_at TEXT;

CREATE TABLE IF NOT EXISTS auth_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL UNIQUE,
    purpose    TEXT    NOT NULL CHECK (purpose IN ('verify_email', 'reset_password')),
    email      TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT    NOT NULL,
    used_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_purpose ON auth_tokens(user_id, purpose);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_expires      ON auth_tokens(expires_at);
COMMIT;
