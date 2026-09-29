-- 0004_files_unique_name_nocase.sql: Make idx_files_unique_name case-insensitive
--
-- Why: 0003 created idx_files_unique_name over the default BINARY collation,
-- so `CASE.csv` and `case.csv` could coexist in the same (user_id, chat_session)
-- while the application pre-check claimed the name was unique. That let a
-- single capital letter dodge the duplicate rule on BOTH upload and rename
-- (both go through SqliteStore.get_file_by_name). Recreating the index with
-- COLLATE NOCASE closes the race at the DB layer; the application layer folds
-- with str.casefold() (Unicode-correct) and stays a superset of this index.
--
-- Guard policy: unlike 0003, the pre-existing case-variant rows are RENAMED,
-- never deleted. 0003's DELETE policy was acceptable for exact-name duplicates
-- (the bytes were identical-looking re-uploads), but a case-variant sibling is
-- a real, distinct file the user uploaded — deleting it would destroy data.
-- Keeping the lowest id is stable and idempotent; the suffix embeds the id so
-- the new name cannot collide with another row in the same group.
--
-- ASCII boundary: SQLite's lower() / NOCASE fold ASCII only (no ICU), so
-- `AÑO.csv` and `año.csv` are NOT equal to this index. That is intentional:
-- the index is the race backstop for the ASCII subset the DB can enforce, while
-- str.casefold() in the app covers the full Unicode range. The app never ALLOWS
-- a name the index would reject, because its casefold check is strictly broader.
-- Idempotent in style with 0001-0003 (guarded ALTERs, IF EXISTS/IF NOT EXISTS).

-- 1. Non-destructive dedupe: rename every row that is not the lowest id of its
--    (user_id, chat_session, lower(filename)) group. No-op on a clean DB.
UPDATE files
SET filename = filename || ' (dup-' || id || ')'
WHERE id NOT IN (
    SELECT MIN(id) FROM files GROUP BY user_id, chat_session, lower(filename)
);

-- 2. Drop the BINARY index before recreating it with NOCASE.
DROP INDEX IF EXISTS idx_files_unique_name;

-- 3. Enforce case-insensitive uniqueness for every future insert/update.
CREATE UNIQUE INDEX IF NOT EXISTS idx_files_unique_name
    ON files(user_id, chat_session, filename COLLATE NOCASE);
