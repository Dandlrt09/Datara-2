"""Database migration runner for Datara.

Applies pending .sql migration files in sorted order, recording each
application in the `migrations` table. Called on server startup.
"""

import logging
import sqlite3
from pathlib import Path

from server.db_path import resolve_db_path
from server.resources import resource_path

logger = logging.getLogger(__name__)

# A migration whose FIRST line is this marker rebuilds a table that other tables
# reference with ON DELETE CASCADE. SQLite needs foreign_keys=OFF for that (the
# DROP TABLE would otherwise cascade-delete the children), and the pragma is a
# no-op inside a transaction, so the runner owns it. Opt-in: every older
# migration keeps running with enforcement on.
FOREIGN_KEYS_OFF_MARKER = "-- migrate: foreign_keys=off"

# Resolved through server.resources: a frozen build ships the .sql files inside
# the bundle, and an empty directory here boots a schema-less database that
# looks like a fresh install rather than a packaging error.
MIGRATIONS_DIR = resource_path("server", "migrations")


def get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of migration version numbers already applied."""
    try:
        rows = conn.execute("SELECT version FROM migrations ORDER BY version").fetchall()
        return {row[0] for row in rows}
    except sqlite3.OperationalError:
        # migrations table doesn't exist yet — no migrations applied
        return set()


def _needs_foreign_keys_off(sql: str) -> bool:
    return sql.lstrip().startswith(FOREIGN_KEYS_OFF_MARKER)


def _foreign_keys_enabled(conn: sqlite3.Connection) -> bool:
    """Return whether *conn* currently enforces foreign keys."""
    return bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])


def _backup_before(conn: sqlite3.Connection, version: int) -> None:
    """Copy the database file to ``<db>.pre-<version>.bak`` before a rebuild.

    Only called for an install that already had migrations applied when the
    runner started; an in-memory database has no file to copy.
    """
    main = next((row for row in conn.execute("PRAGMA database_list") if row[1] == "main"), None)
    db_file = main[2] if main else ""
    if not db_file:
        return
    conn.commit()
    backup_path = f"{db_file}.pre-{version:04d}.bak"
    target = sqlite3.connect(backup_path)
    try:
        conn.backup(target)
    finally:
        target.close()
    logger.info("Backed up the database to %s before migration %04d", backup_path, version)


def run_pending_migrations(conn: sqlite3.Connection) -> None:
    """Discover and apply pending .sql migration files."""
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return

    applied = get_applied_versions(conn)
    existing_install = bool(applied)

    for sql_path in sql_files:
        try:
            version = int(sql_path.stem.split("_")[0])
        except (ValueError, IndexError):
            logger.warning("Skipping migration with unparseable version: %s", sql_path.name)
            continue

        if version in applied:
            logger.debug("Migration %s already applied, skipping", sql_path.name)
            continue

        sql = sql_path.read_text(encoding="utf-8")
        fk_off = _needs_foreign_keys_off(sql)
        # Restoration target for the pragma. Restoring the caller's own value
        # matters: the baseline runner never read or wrote this pragma, so a
        # caller that opened the connection with enforcement deliberately off
        # must not get it switched on behind its back just because a migration
        # needed the rebuild.
        fk_was_enabled = False
        try:
            if fk_off:
                if existing_install:  # a brand-new database has nothing to protect
                    _backup_before(conn, version)
                conn.commit()
                # Read right before switching off: the pragma is a no-op inside a
                # transaction, so after the commit this is the value the caller
                # actually had.
                fk_was_enabled = _foreign_keys_enabled(conn)
                conn.execute("PRAGMA foreign_keys=OFF")
            conn.executescript(sql)
            # Ensure migrations table exists before recording (first migration
            # typically creates it, but standalone .sql files may not).
            conn.execute(
                "CREATE TABLE IF NOT EXISTS migrations ("
                "  version INTEGER PRIMARY KEY,"
                "  name TEXT NOT NULL,"
                "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
                ")"
            )
            conn.execute(
                "INSERT INTO migrations (version, name) VALUES (?, ?)",
                (version, sql_path.name),
            )
            conn.commit()
            logger.info("Applied migration %s", sql_path.name)
        except sqlite3.Error as exc:
            conn.rollback()
            logger.error("Failed to apply migration %s: %s", sql_path.name, exc)
            raise
        finally:
            if fk_off:
                # A pragma cannot be parameterised, so the literal is built from
                # the captured value. This runs on the failure path too: an
                # aborted migration must not leave enforcement switched off.
                restore = "ON" if fk_was_enabled else "OFF"
                conn.execute(f"PRAGMA foreign_keys={restore}")


def apply_migrations(db_path: str) -> None:
    """Open a SQLite database at *db_path* and apply all pending migrations.

    Creates the database file and parent directories if they don't exist.
    The path is resolved through ``resolve_db_path`` so the migration runner
    and the encryption key file agree on the database directory.
    """
    db_path_obj = Path(resolve_db_path(db_path))
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path_obj))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        run_pending_migrations(conn)
    finally:
        conn.close()