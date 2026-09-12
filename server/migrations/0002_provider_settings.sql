-- 0002_provider_settings.sql: Add provider_type and base_url columns to user_settings
-- Migration preserves all existing rows and keys (NULL values = today's behavior)

ALTER TABLE user_settings ADD COLUMN provider_type TEXT;
ALTER TABLE user_settings ADD COLUMN base_url TEXT;