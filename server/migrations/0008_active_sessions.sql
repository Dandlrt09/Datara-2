-- 0008_active_sessions.sql: active sessions list and new-session notice (T2).
--
-- ``auth_sessions.user_agent`` is the (truncated) browser string captured when
-- the session was opened -- the only way to tell "Chrome en Windows" from
-- "Safari en iPhone" in the sessions list. No IP address is stored (D2): the
-- list does not need it and it is personal data with no retention story.
--
-- ``users.sessions_notice_seen_session_id`` is the newest *other* session id the
-- user acknowledged (D9). It lives per user, not per browser, so a login from the
-- phone warns once and does not warn again on every other device. The mark is an
-- id (monotonic, AUTOINCREMENT) rather than a timestamp on purpose: timestamps
-- here have second granularity, so two logins inside the same second would be
-- indistinguishable and the notice would go missing. NULL means "never
-- acknowledged" -- any other live session then triggers the notice once.
--
-- ALTER TABLE ADD COLUMN is a metadata-only change in SQLite (no table rewrite),
-- and both columns are NULL-able with no default: NULL means "unknown browser"
-- and "never acknowledged" respectively.
ALTER TABLE auth_sessions ADD COLUMN user_agent TEXT;

ALTER TABLE users ADD COLUMN sessions_notice_seen_session_id INTEGER;
