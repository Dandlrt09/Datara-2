"""Database migration runner for Datara.

Applies pending .sql migration files in sorted order, recording each
application in the `migrations` table. Called on server startup.
"""

import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of migration version numbers already applied."""
    try:
        rows = conn.execute("SELECT version FROM migrations ORDER BY version").fetchall()
        return {row[0] for row in rows}
    except sqlite3.OperationalError:
        # migrations table doesn't exist yet — no migrations applied
        return set()


def run_pending_migrations(conn: sqlite3.Connection) -> None:
    """Discover and apply pending .sql migration files."""
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return

    applied = get_applied_versions(conn)

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
        try:
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


def apply_migrations(db_path: str) -> None:
    """Open a SQLite database at *db_path* and apply all pending migrations.

    Creates the database file and parent directories if they don't exist.
    """
    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path_obj))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        run_pending_migrations(conn)
    finally:
        conn.close()