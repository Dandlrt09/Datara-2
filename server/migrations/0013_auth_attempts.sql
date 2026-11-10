-- 0013_auth_attempts.sql: persist the auth attempt brake (S4).
--
-- The in-memory limiter (server/api/rate_limit.py) kept the app's promise of
-- never writing an IP or email, but a restart cleared every counter, so a
-- brute-force brake could be reset by bouncing the process. Persisting the
-- counters closes that gap (F9, item 3) while keeping the privacy promise.
--
-- Only a SHA-256 HASH of the limiter key is ever stored: ``key_hash``. The raw
-- key is built as "<scope>:ip:<addr>" or "<scope>:email:<normalized>", so a
-- plaintext column would write the caller's IP and the account's email to disk.
-- Hashing at the boundary (rate_limit.hash_attempt_key) makes a leaked database
-- yield no contacts and no addresses, exactly like ``auth_sessions.token_hash``
-- and ``auth_tokens.token_hash``. The trade-off: a hash cannot be reversed to
-- tell whose counter it is, which is the point.
--
-- ``attempted_at`` is wall-clock epoch seconds (REAL), NOT time.monotonic: a
-- monotonic clock resets with the process, and the whole purpose here is to
-- survive a restart. The window math compares against wall-clock "now".
BEGIN;
CREATE TABLE IF NOT EXISTS auth_attempts (
    key_hash     TEXT NOT NULL,
    attempted_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_key_time
    ON auth_attempts(key_hash, attempted_at);
COMMIT;
