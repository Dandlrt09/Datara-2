-- migrate: foreign_keys=off
-- 0014_users_kind.sql: local profiles (F1 / T2a, D1).
--
-- A local profile has no email and, until the optional lock is turned on, no
-- password. SQLite cannot drop a NOT NULL, so `users` is rebuilt with the
-- documented 12-step recipe (https://sqlite.org/lang_altertable.html#otheralter).
--
-- WHY foreign_keys=off (the marker on line 1; see server/migrate.py): seven
-- child tables reference users(id) ON DELETE CASCADE. With enforcement on,
-- DROP TABLE users performs an implicit DELETE FROM users, which would cascade
-- and erase every chat, file and setting. The runner switches enforcement off
-- OUTSIDE the transaction (the pragma is a no-op inside one), takes a backup
-- first, and switches it back on afterwards.
--
-- Invariants kept by the rebuild:
--   * every row and id is copied verbatim; existing accounts become 'hosted';
--   * the AUTOINCREMENT counter is carried over, so a deleted id is never reused;
--   * email uniqueness stays case-insensitive (NULL emails never collide);
--   * a 'hosted' account still needs an email and a password (CHECK); only a
--     'local' profile may go without.
-- The guard at the end aborts (and rolls back) if the rebuild left an orphan.
BEGIN;

CREATE TABLE users_new (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    email                           TEXT,
    password_hash                   TEXT,
    created_at                      TEXT    NOT NULL DEFAULT (datetime('now')),
    pending_deletion_at             TEXT,
    sessions_notice_seen_session_id INTEGER,
    name                            TEXT,
    terms_version                   TEXT,
    terms_accepted_at               TEXT,
    email_verified_at               TEXT,
    kind                            TEXT    NOT NULL DEFAULT 'hosted'
                                    CHECK (kind IN ('local', 'hosted')),
    CHECK (kind = 'local' OR (email IS NOT NULL AND password_hash IS NOT NULL))
);

INSERT INTO users_new (
    id, email, password_hash, created_at, pending_deletion_at,
    sessions_notice_seen_session_id, name, terms_version, terms_accepted_at,
    email_verified_at, kind
)
SELECT
    id, email, password_hash, created_at, pending_deletion_at,
    sessions_notice_seen_session_id, name, terms_version, terms_accepted_at,
    email_verified_at, 'hosted'
FROM users;

-- Carry the AUTOINCREMENT high-water mark (it can exceed MAX(id) when the
-- newest account was deleted).
DELETE FROM sqlite_sequence WHERE name = 'users_new';
INSERT INTO sqlite_sequence (name, seq)
    SELECT 'users_new', seq FROM sqlite_sequence WHERE name = 'users';

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

CREATE UNIQUE INDEX idx_users_email_nocase ON users(email COLLATE NOCASE);
CREATE INDEX idx_users_pending_deletion ON users(pending_deletion_at);

-- Guard: any orphaned child row means the rebuild went wrong. The CHECK fails,
-- the runner rolls the whole transaction back and startup stops loudly.
CREATE TABLE _fk_guard (orphans INTEGER NOT NULL CHECK (orphans = 0));
INSERT INTO _fk_guard SELECT COUNT(*) FROM pragma_foreign_key_check;
DROP TABLE _fk_guard;

COMMIT;
