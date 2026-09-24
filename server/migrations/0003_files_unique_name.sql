-- 0003_files_unique_name.sql: Enforce UNIQUE(user_id, chat_session, filename) on files
-- Idempotent and safe to run on a database that may already contain duplicate
-- rows: dedupe first (keep the lowest id per key), then create the unique
-- index. Relies on no transaction semantics of the runner.

-- 1. Keep the lowest id per (user_id, chat_session, filename) and delete the rest.
DELETE FROM files
WHERE EXISTS (
    SELECT 1
    FROM files f2
    WHERE f2.user_id = files.user_id
      AND f2.chat_session = files.chat_session
      AND f2.filename = files.filename
      AND f2.id < files.id
);

-- 2. Defensively purge profiles whose file row is gone, in case FK cascade
--    was not active on the connection that ran the delete above.
DELETE FROM profiles
WHERE file_id NOT IN (SELECT id FROM files);

-- 3. Enforce the constraint for every future insert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_files_unique_name
    ON files(user_id, chat_session, filename);
