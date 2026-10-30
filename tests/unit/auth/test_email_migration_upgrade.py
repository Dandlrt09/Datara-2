"""Schema-upgrade probes for migration 0010 (S4).

Reconstructs a pre-0010 install: migrations 1-9 applied and recorded plus real
user rows. Then it runs the startup migration runner and checks every existing
mixed-case email is lowercased, and that a collision aborts the migration
loudly instead of merging or losing an account.
"""

import sqlite3
from pathlib import Path

import pytest

from server.migrate import apply_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"


def _legacy_db(tmp_path: Path, emails: list[str]) -> str:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version > 9:
            continue
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO migrations (version, name) VALUES (?, ?)",
            (version, sql_file.name),
        )
    for index, email in enumerate(emails):
        conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, f"h{index}"),
        )
    conn.commit()
    conn.close()
    return str(db_path)


def test_0010_upgrade_lowercases_existing_emails(tmp_path):
    db_path = _legacy_db(tmp_path, ["Alice@Example.COM", "bob@example.com"])

    apply_migrations(db_path)

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT email FROM users ORDER BY id").fetchall()
    recorded = conn.execute("SELECT version FROM migrations ORDER BY version").fetchall()
    conn.close()

    assert [row[0] for row in rows] == ["alice@example.com", "bob@example.com"]
    assert (10,) in recorded


def test_0010_upgrade_aborts_on_collision_and_touches_nothing(tmp_path):
    db_path = _legacy_db(tmp_path, ["Dup@example.com", "dup@example.com"])

    with pytest.raises(sqlite3.Error):
        apply_migrations(db_path)

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT email FROM users ORDER BY id").fetchall()
    recorded = conn.execute("SELECT version FROM migrations ORDER BY version").fetchall()
    conn.close()

    # Both accounts survive, exactly as they were, and 0010 is not recorded.
    assert [row[0] for row in rows] == ["Dup@example.com", "dup@example.com"]
    assert (10,) not in recorded
