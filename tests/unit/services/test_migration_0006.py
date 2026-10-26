"""Regression tests for migration 0006_profile_preferences (T7a / D4).

The *production* migration runner (``server.migrate.apply_migrations``) must
apply 0006, stay idempotent when run again, and add the four display-preference
columns to ``user_settings`` as NULL-able TEXT with no default: NULL means
"not chosen", and readers resolve it to the effective default.
"""

import sqlite3

from server.migrate import apply_migrations

PREFERENCE_COLUMNS = (
    "number_format",
    "date_format",
    "currency_symbol",
    "open_behavior",
)


def _table_info(db_path: str) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[1]: {"type": row[2].upper(), "notnull": row[3], "default": row[4]}
            for row in conn.execute("PRAGMA table_info(user_settings)").fetchall()
        }
    finally:
        conn.close()


def _applied_versions(db_path: str) -> list[tuple[int, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT version, name FROM migrations ORDER BY version"
        ).fetchall()
    finally:
        conn.close()


def test_0006_is_applied_by_the_production_runner(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)

    versions = _applied_versions(db_path)
    assert [version for version, _ in versions] == [1, 2, 3, 4, 5, 6]
    assert versions[-1][1] == "0006_profile_preferences.sql"


def test_0006_columns_are_nullable_text_without_default(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)

    info = _table_info(db_path)
    for column in PREFERENCE_COLUMNS:
        assert column in info, column
        assert info[column]["type"] == "TEXT", (column, info[column])
        assert info[column]["notnull"] == 0, (column, info[column])
        assert info[column]["default"] is None, (column, info[column])


def test_0006_is_idempotent(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)
    first = _applied_versions(db_path)

    # A second run must be a no-op: no error, no re-application, no new rows.
    apply_migrations(db_path)

    assert _applied_versions(db_path) == first
    assert len(first) == 6
