-- 0006_profile_preferences.sql: Add the per-user display preferences.
-- NULL means "not chosen"; readers resolve it to the effective default
-- (server/services/preferences.py), so existing rows keep today's behavior.

ALTER TABLE user_settings ADD COLUMN number_format TEXT;
ALTER TABLE user_settings ADD COLUMN date_format TEXT;
ALTER TABLE user_settings ADD COLUMN currency_symbol TEXT;
ALTER TABLE user_settings ADD COLUMN open_behavior TEXT;
