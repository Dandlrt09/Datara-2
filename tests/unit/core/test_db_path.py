"""Regression tests for the single-source DB path resolver.

Bug history: an unexpanded ``~`` in ``DATARA_DB_PATH`` made the database land
in a literal ``./~/.datara/datara.db`` while the encryption key file landed in
the expanded home directory — two different places. ``resolve_db_path`` is now
the one resolver every consumer uses, so the DB and its key file can never
drift apart.
"""

from __future__ import annotations

from pathlib import Path

from server.db_path import resolve_db_path
from server.services.sqlite_store import SqliteStore


class TestResolveDbPath:
    def test_explicit_argument_wins_and_expands(self, monkeypatch, tmp_path):
        fresh_home = tmp_path / "home"
        fresh_home.mkdir()
        monkeypatch.setenv("HOME", str(fresh_home))
        monkeypatch.setenv("DATARA_DB_PATH", "/should/be/ignored.db")
        assert resolve_db_path("~/other.db") == str(fresh_home / "other.db")

    def test_env_var_used_when_no_explicit(self, monkeypatch, tmp_path):
        fresh_home = tmp_path / "home"
        fresh_home.mkdir()
        monkeypatch.setenv("HOME", str(fresh_home))
        monkeypatch.setenv("DATARA_DB_PATH", "~/.datara/datara.db")
        assert resolve_db_path() == str(fresh_home / ".datara" / "datara.db")

    def test_empty_explicit_falls_back_to_env(self, monkeypatch, tmp_path):
        fresh_home = tmp_path / "home"
        fresh_home.mkdir()
        monkeypatch.setenv("HOME", str(fresh_home))
        monkeypatch.setenv("DATARA_DB_PATH", "~/from-env.db")
        assert resolve_db_path("") == str(fresh_home / "from-env.db")

    def test_unset_env_resolves_to_expanded_default(self, monkeypatch, tmp_path):
        fresh_home = tmp_path / "home"
        fresh_home.mkdir()
        monkeypatch.setenv("HOME", str(fresh_home))
        monkeypatch.delenv("DATARA_DB_PATH", raising=False)
        assert resolve_db_path() == str(fresh_home / ".datara" / "datara.db")


class TestStoreKeepsDbAndKeyTogether:
    async def test_unexpanded_tilde_env_does_not_split_db_from_key(
        self, monkeypatch, tmp_path
    ):
        fresh_home = tmp_path / "home"
        fresh_home.mkdir()
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.setenv("HOME", str(fresh_home))
        monkeypatch.setenv("DATARA_DB_PATH", "~/.datara/datara.db")
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        monkeypatch.chdir(cwd)

        # Mirrors server/api/main.py lifespan Step 1 exactly.
        db_path = resolve_db_path()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # The unexpanded env value must not survive resolution.
        assert "~" not in db_path
        assert Path(db_path).parent == fresh_home / ".datara"

        # Building the store must not crash and writes the key beside the DB.
        store = SqliteStore(db_path=db_path)
        await store.connect()
        await store.close()

        key_path = fresh_home / ".datara" / ".secret_key"
        assert key_path.exists()
        assert Path(db_path).exists()
        assert key_path.parent == Path(db_path).parent
        # No literal "~" directory may be created under the CWD.
        assert not (cwd / "~").exists()

    async def test_raw_unexpanded_path_passed_directly_still_expands(
        self, monkeypatch, tmp_path
    ):
        """A caller handing the store a raw ``~`` path must not split DB from key."""
        fresh_home = tmp_path / "home"
        fresh_home.mkdir()
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.setenv("HOME", str(fresh_home))
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        monkeypatch.chdir(cwd)

        expanded_parent = fresh_home / ".datara"
        expanded_parent.mkdir(parents=True, exist_ok=True)

        # Deliberately unexpanded, bypassing main.py's own resolution.
        store = SqliteStore(db_path="~/.datara/datara.db")
        await store.connect()
        await store.close()

        assert (expanded_parent / "datara.db").exists()
        assert (expanded_parent / ".secret_key").exists()
        assert not (cwd / "~").exists()