-- 0001_init.sql: Initial schema for Datara
-- All user-scoped tables have NOT NULL user_id per cross-cutting requirement.

CREATE TABLE IF NOT EXISTS migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    applied_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Auth sessions: id is a SURROGATE INTEGER AUTOINCREMENT row id only.
-- It is internal bookkeeping and is NEVER sent to the client.
-- The cookie carries a raw random token (secrets.token_urlsafe(32));
-- the DB stores ONLY token_hash = SHA-256(token), unique indexed.
-- Session lookup is by token_hash only.
CREATE TABLE IF NOT EXISTS auth_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash    TEXT    NOT NULL UNIQUE,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at    TEXT    NOT NULL,
    last_seen_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user    ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id            TEXT    PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT    NOT NULL DEFAULT 'New chat',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id);

CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_session  TEXT    NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    filename      TEXT    NOT NULL,
    storage_path  TEXT    NOT NULL,
    size_bytes    INTEGER NOT NULL,
    format        TEXT    NOT NULL,
    encoding      TEXT,
    sheet_name    TEXT,
    row_count     INTEGER,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_files_user_session ON files(user_id, chat_session);

CREATE TABLE IF NOT EXISTS profiles (
    file_id       INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    schema_json   TEXT    NOT NULL,
    stats_json    TEXT    NOT NULL,
    sample_json   TEXT    NOT NULL,
    generated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_session  TEXT    NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role          TEXT    NOT NULL,
    content_text  TEXT    NOT NULL,
    code          TEXT,
    artifacts_json TEXT,
    model         TEXT,
    provider      TEXT,
    tokens_in     INTEGER,
    tokens_out    INTEGER,
    cost_usd      REAL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session_time ON messages(user_id, chat_session, created_at);

CREATE TABLE IF NOT EXISTS archives (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL,
    chat_session  TEXT    NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    payload_json  TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    api_key_enc   TEXT,
    default_model TEXT,
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);