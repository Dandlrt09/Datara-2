-- 0017_lock_step.sql: the persisted answer to the optional lock step (F1 / T3, D1).
--
-- The lock step is mandatory on the onboarding path but the lock itself stays
-- optional (D4): after the local profile is created and before the API-key
-- setup, the screen offers the lock and the analyst either turns it on or says
-- "not now". The answer is recorded so the step does not come back.
--
-- 0 means "not answered yet". Turning the lock on (the existing lock route)
-- and declining (the new decline route) both set it to 1. A locked profile
-- counts as answered even if a pre-migration row kept the default: the GET
-- reports the step pending only when the profile is unlocked AND unanswered.
--
-- Additive ALTER only: no table rebuild, so no `foreign_keys=off` marker.

ALTER TABLE users ADD COLUMN lock_step_answered INTEGER NOT NULL DEFAULT 0;
