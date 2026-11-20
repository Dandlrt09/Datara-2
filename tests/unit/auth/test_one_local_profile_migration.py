"""Schema invariant for migration 0015 (F1 / T2b, S1, D1).

A partial unique index makes "at most one local profile" a property of the
database, not of a check-then-insert in the route. The route's 409 is the
friendly face of this: two simultaneous first-boot requests can both pass its
``get_mode()``/lookup gate, so the database is what truly refuses the second
row. Hosted accounts stay unconstrained -- a multi-user deployment has as many
as it wants.
"""

import sqlite3

import pytest

from server.migrate import apply_migrations


def _index_names(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA index_list(users)")}
    finally:
        conn.close()


def test_the_partial_index_exists_after_the_upgrade(tmp_path):
    db_path = str(tmp_path / "datara.db")

    apply_migrations(db_path)

    assert "idx_users_one_local" in _index_names(db_path)


def test_a_second_local_profile_is_refused_by_the_database(tmp_path):
    """S1 as an invariant: the row that makes the route's 409 possible."""
    db_path = str(tmp_path / "datara.db")
    apply_migrations(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO users (kind, name) VALUES ('local', 'Ana')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (kind, name) VALUES ('local', 'otro')"
            )
    finally:
        conn.close()


def test_hosted_accounts_stay_unconstrained(tmp_path):
    """The index is partial: a hosted deployment keeps many email accounts."""
    db_path = str(tmp_path / "datara.db")
    apply_migrations(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (kind, email, password_hash) "
            "VALUES ('hosted', 'a@x.com', 'h')"
        )
        conn.execute(
            "INSERT INTO users (kind, email, password_hash) "
            "VALUES ('hosted', 'b@x.com', 'h')"
        )
    finally:
        conn.close()
