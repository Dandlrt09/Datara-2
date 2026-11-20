-- 0016_local_lock.sql: the hashed rescue key of the optional local lock (F1 / T4, D4).
--
-- The local profile starts unlocked (L10) and the optional lock is turned on
-- later from the Profile screen, so this column is added to the existing
-- `users` table. `password_hash`, already there since 0001, carries the lock's
-- password; `local_rescue_hash` carries the SHA-256 hash of the one-time rescue
-- key handed to the person when they lock the profile. The raw key is shown
-- once and never stored.
--
-- NULL means the lock was never turned on -- or a rescue key is not outstanding.
-- A rotate overwrites it, so exactly one key is ever valid.
--
-- Additive ALTER only: no table rebuild, so no `foreign_keys=off` marker.

ALTER TABLE users ADD COLUMN local_rescue_hash TEXT;
