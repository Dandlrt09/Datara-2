"""Resource resolution: source tree vs frozen bundle.

Two worlds have to agree here. Running from the repository, the app's read-only
files (the built frontend, the .sql migrations, the sandbox runner) live in the
repo and uploads land in ``<repo>/uploads``. Running from a frozen binary, the
read-only files live wherever PyInstaller unpacked the bundle
(``sys._MEIPASS``) and nothing may be written next to the executable — so
uploads move to the per-user data directory, next to the database.

These tests pin both worlds, and pin the four consumers that used to compute
their own ``Path(__file__)``, so relocating them cannot silently change where
the app reads from.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

from server import resources
from server.api.routers import files as files_router
from server.api import main as api_main
from server import migrate
from server.services import sandbox_local

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def frozen(monkeypatch, tmp_path):
    """Pretend the interpreter is a PyInstaller bundle unpacked in tmp_path."""

    def _make(bundle: Path | None = None) -> Path:
        root = bundle or (tmp_path / "_MEI123456")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        if root is None:
            monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        else:
            monkeypatch.setattr(sys, "_MEIPASS", str(root), raising=False)
        return root

    return _make


class TestFrozenDetection:
    def test_source_run_is_not_frozen(self):
        assert resources.is_frozen() is False

    def test_frozen_run_is_detected(self, frozen):
        frozen()
        assert resources.is_frozen() is True


class TestBundleRoot:
    def test_source_root_is_the_repository(self):
        assert resources.bundle_root() == REPO_ROOT

    def test_source_frontend_resource_is_found(self):
        # The mapping has to point at a directory that really exists, or the
        # SPA is silently not mounted.
        assert resources.resource_path("web", "dist").is_dir()

    def test_frozen_root_is_the_unpacked_bundle(self, frozen):
        root = frozen()
        assert resources.bundle_root() == root

    def test_frozen_resource_lands_under_the_bundle(self, frozen):
        root = frozen()
        assert resources.resource_path("web", "dist") == root / "web" / "dist"

    def test_frozen_without_meipass_falls_back_to_the_executable_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        assert resources.bundle_root() == Path(sys.executable).resolve().parent


class TestDataDir:
    def test_data_dir_is_the_database_directory(self, monkeypatch, tmp_path):
        db = tmp_path / "nested" / "datara.db"
        monkeypatch.setenv("DATARA_DB_PATH", str(db))
        assert resources.data_dir() == tmp_path / "nested"

    def test_data_dir_expands_the_home_shorthand(self, monkeypatch):
        monkeypatch.setenv("DATARA_DB_PATH", "~/datara-test-dir/datara.db")
        assert "~" not in str(resources.data_dir())
        assert resources.data_dir() == Path.home() / "datara-test-dir"


class TestUploadsDefault:
    def test_source_uploads_stay_in_the_repository(self, monkeypatch):
        # Historical location: moving it from source would orphan the files of
        # every existing development install.
        monkeypatch.delenv("DATARA_UPLOADS_DIR", raising=False)
        assert resources.default_uploads_dir() == REPO_ROOT / "uploads"

    def test_frozen_uploads_move_to_the_data_dir(self, frozen, monkeypatch, tmp_path):
        frozen()
        monkeypatch.setenv("DATARA_DB_PATH", str(tmp_path / "datadir" / "datara.db"))
        assert resources.default_uploads_dir() == tmp_path / "datadir" / "uploads"

    def test_frozen_uploads_never_land_next_to_the_bundle(self, frozen, monkeypatch, tmp_path):
        # A frozen app can be installed under Program Files: writing there
        # either fails or lands in a virtualised, invisible location.
        root = frozen()
        monkeypatch.setenv("DATARA_DB_PATH", str(tmp_path / "datadir" / "datara.db"))
        assert root not in resources.default_uploads_dir().parents


class TestConsumersKeepReadingFromTheSamePlaces:
    """The four sites that used to roll their own ``Path(__file__)``."""

    def test_frontend_static_dir_is_the_repo_build(self):
        assert api_main.static_dir == REPO_ROOT / "web" / "dist"

    def test_migrations_dir_is_the_server_migrations(self):
        assert migrate.MIGRATIONS_DIR == REPO_ROOT / "server" / "migrations"

    def test_migrations_are_still_discovered(self):
        # The runner globs this directory; an empty glob would boot a schema-less
        # database and look like a fresh install.
        assert sorted(migrate.MIGRATIONS_DIR.glob("*.sql"))

    def test_sandbox_runner_path_is_the_server_script(self):
        assert sandbox_local.SANDBOX_RUNNER_PATH == str(
            REPO_ROOT / "server" / "sandbox_runner.py"
        )
        assert os.path.exists(sandbox_local.SANDBOX_RUNNER_PATH)

    def test_uploads_dir_defaults_to_the_repo_uploads(self, monkeypatch):
        monkeypatch.delenv("DATARA_UPLOADS_DIR", raising=False)
        module = importlib.reload(files_router)
        assert module.UPLOADS_DIR == REPO_ROOT / "uploads"

    def test_uploads_dir_is_still_overridable_by_env(self, monkeypatch, tmp_path):
        override = tmp_path / "elsewhere"
        monkeypatch.setenv("DATARA_UPLOADS_DIR", str(override))
        module = importlib.reload(files_router)
        assert module.UPLOADS_DIR == override
