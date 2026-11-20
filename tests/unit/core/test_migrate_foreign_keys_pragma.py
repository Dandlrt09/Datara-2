"""Post-migration ``PRAGMA foreign_keys`` semantics (F1 / T3, S3).

The runner switches enforcement off for a migration whose first line carries the
``-- migrate: foreign_keys=off`` marker (0014 rebuilds ``users``, and the DROP
would otherwise cascade-delete every child row). The baseline runner never
touched the pragma, so a caller that opened the connection with enforcement
deliberately off must still see it off when the runner returns -- including when
the migration fails halfway. These probes drive the real ``server.migrate``
entry point; nothing here re-implements its logic.
"""

import sqlite3
from pathlib import Path

import pytest

import server.migrate as migrate

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
LAST_BEFORE_KIND = 13
MARKED_VERSION = 14

# A throwaway marker-bearing migration that dies after its first statement, so
# the runner has already switched enforcement off when the failure lands.
FAILING_MARKED_SQL = """\
-- migrate: foreign_keys=off
CREATE TABLE throwaway (id INTEGER PRIMARY KEY);
INSERT INTO no_such_table (id) VALUES (1);
"""

PLAIN_SQL = "CREATE TABLE plain (id INTEGER PRIMARY KEY);"

# A marker-bearing migration whose first fallible step is the runner's own
# pre-rebuild backup, which the test makes abort: enforcement must come back.
MARKED_SQL = """\
-- migrate: foreign_keys=off
CREATE TABLE throwaway (id INTEGER PRIMARY KEY);
"""

PRAGMA_VALUES = [pytest.param("OFF", 0, id="opened-off"), pytest.param("ON", 1, id="opened-on")]


def _pragma(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA foreign_keys").fetchone()[0]


def _open_at_0013(db_path: Path, foreign_keys: str) -> sqlite3.Connection:
    """A file database migrated through 0013, opened with *foreign_keys* set.

    A file (not ``:memory:``) so the runner's pre-rebuild backup has something
    to copy, exactly as a real install does.
    """
    conn = sqlite3.connect(str(db_path))
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version > LAST_BEFORE_KIND:
            continue
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO migrations (version, name) VALUES (?, ?)",
            (version, sql_file.name),
        )
    conn.commit()
    conn.execute(f"PRAGMA foreign_keys={foreign_keys}")
    assert _pragma(conn) == (1 if foreign_keys == "ON" else 0)
    return conn


def _throwaway_migrations(tmp_path: Path, monkeypatch, name: str, sql: str) -> None:
    """Point the runner at a directory holding only *name*."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / name).write_text(sql, encoding="utf-8")
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", migrations)


@pytest.mark.parametrize(("opened_with", "expected"), PRAGMA_VALUES)
def test_a_marker_migration_restores_the_callers_pragma(
    tmp_path, opened_with, expected
):
    """0014 carries the marker; the caller's value survives it."""
    conn = _open_at_0013(tmp_path / "app.db", opened_with)
    try:
        migrate.run_pending_migrations(conn)

        assert MARKED_VERSION in migrate.get_applied_versions(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        assert "kind" in columns, "the marked migration must run to the end"
        assert _pragma(conn) == expected
    finally:
        conn.close()


@pytest.mark.parametrize(("opened_with", "expected"), PRAGMA_VALUES)
def test_a_failing_marker_migration_still_restores_the_previous_value(
    tmp_path, monkeypatch, opened_with, expected
):
    """A migration that dies midway must not leave enforcement switched off."""
    _throwaway_migrations(tmp_path, monkeypatch, "0001_failing.sql", FAILING_MARKED_SQL)

    conn = sqlite3.connect(str(tmp_path / "app.db"))
    conn.execute(f"PRAGMA foreign_keys={opened_with}")
    try:
        with pytest.raises(sqlite3.Error):
            migrate.run_pending_migrations(conn)

        assert migrate.get_applied_versions(conn) == set()
        assert _pragma(conn) == expected
    finally:
        conn.close()


def test_a_failure_before_the_switch_still_restores_an_enabled_pragma(
    tmp_path, monkeypatch
):
    """R4-001: a failure before the switch-off must not turn enforcement off.

    The runner samples the caller's pragma before anything that can fail. Here
    the pre-rebuild backup -- the first fallible step on an existing install --
    aborts while enforcement was ON, so the ``finally`` must restore ON. The
    previous sampling point sat right before the switch-off, which the abort
    never reached, and the ``False`` default left enforcement OFF behind a
    caller that had it deliberately ON.
    """
    conn = _open_at_0013(tmp_path / "app.db", "ON")
    _throwaway_migrations(
        tmp_path, monkeypatch, "0014_backup_fails.sql", MARKED_SQL
    )

    def _backup_aborts(_conn, _version):
        raise sqlite3.OperationalError("backup aborted")

    monkeypatch.setattr(migrate, "_backup_before", _backup_aborts)
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrate.run_pending_migrations(conn)

        assert migrate.get_applied_versions(conn) == set(
            range(1, LAST_BEFORE_KIND + 1)
        )
        assert _pragma(conn) == 1
    finally:
        conn.close()


@pytest.mark.parametrize(("opened_with", "expected"), PRAGMA_VALUES)
def test_a_markerless_migration_leaves_the_callers_pragma_untouched(
    tmp_path, monkeypatch, opened_with, expected
):
    """Without the marker the runner never reads or writes the pragma."""
    _throwaway_migrations(tmp_path, monkeypatch, "0001_plain.sql", PLAIN_SQL)

    conn = sqlite3.connect(str(tmp_path / "app.db"))
    conn.execute(f"PRAGMA foreign_keys={opened_with}")
    try:
        migrate.run_pending_migrations(conn)

        assert migrate.get_applied_versions(conn) == {1}
        assert _pragma(conn) == expected
    finally:
        conn.close()
