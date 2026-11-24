-- 0020_privacy_declared.sql: declared privacy levels (F6).
--
-- A session carries the level its files inherit; a file may override it. NULL
-- means "inherit" so every existing row keeps today's behavior (F6/S4: the
-- default is "full", byte-identical to the pre-F6 payload).
--
-- ``column_aliases_json`` is the optional per-file rename map used only when
-- building the outgoing payload; the database keeps the real column names.

ALTER TABLE chat_sessions ADD COLUMN privacy_level TEXT NOT NULL DEFAULT 'full';
ALTER TABLE files ADD COLUMN privacy_level TEXT;
ALTER TABLE files ADD COLUMN column_aliases_json TEXT;
