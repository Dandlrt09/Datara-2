-- 0011_terms_acceptance.sql: the terms of use acceptance (terms-of-use S1/S6).
--
-- Until now an account existed with no record of the terms it was created
-- under, so the acceptance checkbox would have been decoration. Two columns are
-- added instead of one boolean: the version says WHICH text was accepted and
-- the date says when, which is what makes the acceptance provable.
--
-- Both columns are NULL for every row written before this migration -- that is
-- history (the account was created when there were no terms), not an error, and
-- the old write path keeps working unchanged.
BEGIN;
ALTER TABLE users ADD COLUMN terms_version TEXT;
ALTER TABLE users ADD COLUMN terms_accepted_at TEXT;
COMMIT;
