-- 0019_dataset_crossings.sql: the persisted recipe of a dataset crossing (F5/T1, S4).
--
-- F5 crosses two files of one session (S5) and what the analyst confirms is a
-- RECIPE, not data (S4): which two files, which key on each side, and how they
-- are joined. The crossing is re-materialized inside the sandbox on every turn,
-- so no derived file is written and no dataset is duplicated.
--
-- "One crossing stays active per session" (S5) is enforced by the BASE and not
-- by the handler: the UNIQUE index on chat_session makes confirming a second
-- crossing an in-place UPDATE of the same row, so two recipes can never be
-- active at once, not even if two requests race.
--
-- Ties follow the other session-scoped tables: the row dies with its session and
-- with either file (ON DELETE CASCADE, same as ``files``), and ``user_id`` keeps
-- ownership checkable without joining ``files`` (the spirit of Decision #14:
-- never trust an id on its own).
BEGIN;
CREATE TABLE IF NOT EXISTS dataset_crossings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_session  TEXT    NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    left_file_id  INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    right_file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    left_key      TEXT    NOT NULL,
    right_key     TEXT    NOT NULL,
    how           TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dataset_crossings_session
    ON dataset_crossings(chat_session);
COMMIT;
