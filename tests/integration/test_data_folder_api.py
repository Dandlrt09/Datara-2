"""Integration tests for the data-folder endpoints (F3b / T1, S2-S4).

Contract under test: where the analyst's data lives is an *at-boot* decision
(``server.db_path``), so the screen that makes it runs **before** any account
exists -- both routes are unauthenticated on purpose. ``GET`` tells the screen
whether the decision is still open; ``PUT`` accepts it only on a first run,
validates that the folder is absolute and writable, records it in the pointer
file and reports the cloud sync client so the UI can warn in a single call
(S6: warn and allow, never refuse).

Every test moves ``HOME``/``XDG_DATA_HOME`` into ``tmp_path``: the real pointer
of the machine running the suite is never read and never written.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import db_path
from server.api.routers.data_folder import router as data_folder_router

POINTER_NAME = "data-location.txt"

# A permission test is meaningless as root: it can write anywhere.
_IS_ROOT = os.name != "nt" and os.geteuid() == 0


@pytest.fixture(autouse=True)
def isolated_os_dir(tmp_path, monkeypatch) -> Path:
    """Point the OS default data dir (and therefore the pointer) at tmp."""
    home = tmp_path / "home"
    home.mkdir()
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    monkeypatch.delenv("DATARA_DB_PATH", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    return xdg / "Datara"


@pytest.fixture
def client():
    application = FastAPI()
    application.include_router(data_folder_router)
    return TestClient(application)


class TestGetDataFolder:
    def test_fresh_machine_is_undecided_and_names_the_os_default(
        self, client, isolated_os_dir
    ):
        """No credentials on purpose: this screen runs before the login."""
        response = client.get("/api/data-folder")

        assert response.status_code == 200
        data = response.json()
        assert set(data) == {"decided", "path", "default_path"}
        assert data["decided"] is False
        assert data["default_path"] == str(isolated_os_dir)
        assert data["path"] == str(isolated_os_dir)

    def test_a_written_pointer_makes_it_decided(self, client, isolated_os_dir, tmp_path):
        chosen = tmp_path / "chosen"
        db_path.write_data_location(chosen)

        data = client.get("/api/data-folder").json()

        assert data["decided"] is True
        assert data["path"] == str(chosen)
        assert data["default_path"] == str(isolated_os_dir)

    def test_a_legacy_install_is_already_decided(self, client, tmp_path):
        """S3: a live pre-F3 install is not a first run — it is out of scope."""
        legacy = tmp_path / "home" / ".datara"
        legacy.mkdir(parents=True)
        (legacy / "datara.db").write_bytes(b"legacy")

        data = client.get("/api/data-folder").json()

        assert data["decided"] is True
        assert data["path"] == str(legacy)


class TestPutDataFolder:
    def test_put_records_the_folder_and_reports_the_sync_client(
        self, client, isolated_os_dir, tmp_path
    ):
        chosen = tmp_path / "chosen" / "datara-data"
        assert not chosen.exists()

        response = client.put("/api/data-folder", json={"path": str(chosen)})

        assert response.status_code == 200
        data = response.json()
        assert data["decided"] is True
        assert data["path"] == str(chosen)
        assert data["default_path"] == str(isolated_os_dir)
        assert data["synced_client"] is None
        # The folder exists, the pointer holds exactly the chosen path...
        assert chosen.is_dir()
        pointer = isolated_os_dir / POINTER_NAME
        assert pointer.read_text(encoding="utf-8").strip() == str(chosen)
        # ...and resolution now boots from there.
        assert db_path.resolve_db_path() == str(chosen / "datara.db")
        assert client.get("/api/data-folder").json()["path"] == str(chosen)

    def test_put_is_refused_once_a_location_is_decided(self, client, tmp_path):
        first = tmp_path / "first"
        client.put("/api/data-folder", json={"path": str(first)})
        second = tmp_path / "second"

        response = client.put("/api/data-folder", json={"path": str(second)})

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "already_decided"
        # Nothing was created and the stored decision is untouched.
        assert not second.exists()
        assert db_path.read_data_location() == first

    def test_put_expands_a_tilde_path(self, client, tmp_path):
        response = client.put("/api/data-folder", json={"path": "~/datara-data"})

        assert response.status_code == 200
        assert response.json()["path"] == str(tmp_path / "home" / "datara-data")

    def test_put_rejects_a_relative_path(self, client, isolated_os_dir):
        response = client.put("/api/data-folder", json={"path": "datos/datara"})

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_path"
        assert "absoluta" in detail["message"]
        # Nothing stored, nothing created.
        assert db_path.read_data_location() is None
        assert not (isolated_os_dir / POINTER_NAME).exists()

    def test_put_rejects_an_empty_path(self, client, isolated_os_dir):
        response = client.put("/api/data-folder", json={"path": "   "})

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_path"
        assert db_path.read_data_location() is None
        assert not (isolated_os_dir / POINTER_NAME).exists()

    def test_put_rejects_a_folder_that_cannot_be_created(self, client, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")

        response = client.put(
            "/api/data-folder", json={"path": str(blocker / "datara-data")}
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "path_not_writable"
        assert str(blocker) in detail["message"]
        assert db_path.read_data_location() is None

    def test_put_rejects_a_path_that_is_not_a_folder(self, client, tmp_path):
        plain_file = tmp_path / "plain.txt"
        plain_file.write_text("not a directory", encoding="utf-8")

        response = client.put("/api/data-folder", json={"path": str(plain_file)})

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "path_not_writable"
        assert db_path.read_data_location() is None

    @pytest.mark.skipif(_IS_ROOT, reason="root ignores directory permissions")
    def test_put_rejects_a_folder_that_cannot_be_written(self, client, tmp_path):
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        readonly.chmod(0o500)
        try:
            response = client.put("/api/data-folder", json={"path": str(readonly)})
        finally:
            readonly.chmod(0o700)

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "path_not_writable"
        assert db_path.read_data_location() is None

    def test_put_reports_a_synced_folder_and_still_accepts_it(self, client, tmp_path):
        """S6: name the risk once, then allow it — never refuse the folder."""
        chosen = tmp_path / "Dropbox" / "datara-data"

        response = client.put("/api/data-folder", json={"path": str(chosen)})

        assert response.status_code == 200
        data = response.json()
        assert data["synced_client"] == "Dropbox"
        assert data["path"] == str(chosen)
        assert chosen.is_dir()
        assert db_path.read_data_location() == chosen