-- 0018_tutorial_seen.sql: the persisted answer to the guided first-boot tour
-- (F4 / T1, S3, D9).
--
-- The guided tour teaches the parts of the app by pointing at the real UI on the
-- first entry to /app, and it is for a NEW account (S1). The flag that says it
-- was already seen lives in the server, per profile, so it survives shutting the
-- app down, locking and unlocking, and a later boot does not bring the tour back
-- (S3). It belongs to every profile -- the local one and a hosted account alike
-- because a freshly created hosted account is a new account too.
--
-- 0 means "not seen yet", which is what a profile created AFTER this migration
-- starts at, by the column default. The backfill marks every profile that
-- already existed as already seen (D9): an install with history must not be
-- shown the tour for the first time right after upgrading, because that profile
-- is not a new account.
--
-- Additive ALTER only: no table rebuild, so no `foreign_keys=off` marker.

ALTER TABLE users ADD COLUMN tutorial_seen INTEGER NOT NULL DEFAULT 0;

UPDATE users SET tutorial_seen = 1;
