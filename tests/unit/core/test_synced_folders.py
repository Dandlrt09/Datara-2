"""Regression tests for the synced-folder detector (F3 / S1 / S3).

S3 asks the data folder to live *"fuera de cualquier carpeta sincronizada
(OneDrive/Dropbox)"*. This detector answers that single question from local
signals only: the client environment variables, well-known path segments and
the marker files the clients leave behind. It never raises and never touches
the network. S8 (*"avisar y permitir"*) is policy and lives in the caller, so
nothing here may refuse a path.
"""

from __future__ import annotations

import pytest

from server.synced_folders import detect_synced_client, is_synced_folder


@pytest.fixture(autouse=True)
def _clear_client_env(monkeypatch):
    """Keep detection deterministic: no inherited cloud-client env vars."""
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(var, raising=False)


class TestPlainPath:
    def test_plain_temp_dir_is_not_synced(self, tmp_path):
        plain = tmp_path / "Documents" / "analysis"
        assert is_synced_folder(plain) is False
        assert detect_synced_client(plain) is None


class TestPathSegments:
    def test_onedrive_root_segment_is_synced(self, tmp_path):
        synced = tmp_path / "OneDrive" / "analysis"
        assert is_synced_folder(synced) is True
        assert detect_synced_client(synced) == "OneDrive"

    def test_google_drive_segment_is_synced(self, tmp_path):
        synced = tmp_path / "Google Drive" / "analysis"
        assert is_synced_folder(synced) is True
        assert detect_synced_client(synced) == "Google Drive"


class TestEnvironmentVariable:
    def test_env_var_detects_when_folder_name_gives_nothing_away(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path / "SyncedData"
        root.mkdir()
        monkeypatch.setenv("OneDrive", str(root))
        chosen = root / "analysis"
        assert is_synced_folder(chosen) is True
        assert detect_synced_client(chosen) == "OneDrive"


class TestMarkerFiles:
    def test_dropbox_marker_file_is_synced(self, tmp_path):
        root = tmp_path / "SyncedData"
        root.mkdir()
        (root / ".dropbox").write_text("")
        chosen = root / "analysis"
        assert is_synced_folder(chosen) is True
        assert detect_synced_client(chosen) == "Dropbox"


class TestNonExistentPath:
    def test_nonexistent_path_under_synced_root_is_synced(self, tmp_path):
        chosen = tmp_path / "OneDrive" / "brand-new"
        assert not chosen.exists()
        assert is_synced_folder(chosen) is True


class TestTraversal:
    def test_traversal_out_of_synced_root_is_not_synced(self, tmp_path):
        elsewhere = tmp_path / "OneDrive" / ".." / "elsewhere"
        assert is_synced_folder(elsewhere) is False
