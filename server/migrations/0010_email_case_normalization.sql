-- 0010_email_case_normalization.sql: the email becomes a case-insensitive
-- identity (S4/S5).
--
-- Until now ``users.email`` was stored and matched exactly as typed, so
-- ``Alice@Example.COM`` and ``alice@example.com`` were two different accounts
-- and a capitalization typo locked a person out of their own login. The write
-- path now normalizes (``normalize_email`` in ``server/services/auth_service.py``)
-- and this migration brings the rows written before that rule into the same
-- shape: every existing email is lowercased and trimmed.
--
-- The NOCASE unique index is the database-level backstop: even if a future
-- writer forgets to normalize, two accounts cannot share a case-insensitive
-- email.
--
-- Collisions are possible in theory (two rows differing only by case already
-- exist in a case-sensitive UNIQUE column). We prefer a loud failure over
-- silently merging or losing an account: the UPDATE trips the existing UNIQUE
-- constraint, the transaction rolls back, the migration is not recorded, and
-- startup stops with the error. An operator resolves the duplicate by hand.
BEGIN;
UPDATE users SET email = lower(trim(email));
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_nocase
    ON users(email COLLATE NOCASE);
COMMIT;
