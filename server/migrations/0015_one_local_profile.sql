-- 0015_one_local_profile.sql: at most one local profile (F1 / T2b, S1, D1).
--
-- A partial unique index, not a table rebuild: the route's check-then-insert is
-- not atomic, so two simultaneous first-boot requests could both pass its gate
-- and create two profiles. This index makes the database the authority that
-- refuses the second row -- the route's 409 is only the friendly face of it.
--
-- It is partial on purpose: only 'local' rows are constrained, so a hosted
-- deployment keeps as many email accounts as it wants. Hosted rows are not
-- touched by this migration at all.
--
-- No `foreign_keys=off` marker: an index needs no table rebuild.

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_one_local
    ON users(kind)
    WHERE kind = 'local';
