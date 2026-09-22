"""Tests for the SecretBox API-key encryption helper.

Covers env-var key derivation, round-trips, legacy plaintext passthrough,
unreadable tokens, and the hermetic in-memory path.
"""

from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet

from server.services.crypto import SecretBox, SecretKeyFileError, _derive_key


class TestKeyResolution:
    def test_env_secret_derivation_is_deterministic(self, monkeypatch):
        """The same DATARA_SECRET_KEY must yield a key that can decrypt itself."""
        monkeypatch.setenv("DATARA_SECRET_KEY", "high-entropy-secret-0123456789")
        box_a = SecretBox.for_store(None)
        token = box_a.encrypt("sk-round-trip")
        box_b = SecretBox.for_store(None)
        assert box_b.decrypt(token) == "sk-round-trip"

    def test_different_env_secrets_do_not_interoperate(self, monkeypatch):
        monkeypatch.setenv("DATARA_SECRET_KEY", "secret-one")
        token = SecretBox.for_store(None).encrypt("sk-round-trip")
        monkeypatch.setenv("DATARA_SECRET_KEY", "secret-two")
        assert SecretBox.for_store(None).decrypt(token) is None

    def test_derive_key_changes_with_secret(self):
        assert _derive_key("a") != _derive_key("b")
        assert _derive_key("a") == _derive_key("a")

    def test_env_secret_takes_precedence_over_key_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATARA_SECRET_KEY", "env-secret")
        box = SecretBox.for_store(str(tmp_path / "datara.db"))
        assert not (tmp_path / ".secret_key").exists()
        assert box.decrypt(box.encrypt("sk-x")) == "sk-x"

    def test_in_memory_store_writes_no_key_file(self, monkeypatch, tmp_path):
        """Tests must stay hermetic: :memory: never touches the filesystem."""
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        box = SecretBox.for_store(":memory:")
        assert box.decrypt(box.encrypt("sk-x")) == "sk-x"
        assert list(tmp_path.iterdir()) == []

    def test_on_disk_store_creates_and_reuses_key_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        db_path = tmp_path / "datara.db"
        box_a = SecretBox.for_store(str(db_path))
        key_path = tmp_path / ".secret_key"
        assert key_path.exists()
        assert (key_path.stat().st_mode & 0o777) == 0o600
        token = box_a.encrypt("sk-file-key")
        # A fresh store pointed at the same DB reads the same key.
        box_b = SecretBox.for_store(str(db_path))
        assert box_b.decrypt(token) == "sk-file-key"


class TestEncryptDecrypt:
    def test_round_trip(self):
        box = SecretBox.ephemeral()
        token = box.encrypt("sk-super-secret-123")
        assert token != "sk-super-secret-123"
        assert token.startswith("gAAAAA")
        assert box.decrypt(token) == "sk-super-secret-123"

    def test_encrypt_is_non_deterministic(self):
        box = SecretBox.ephemeral()
        assert box.encrypt("sk-x") != box.encrypt("sk-x")

    @pytest.mark.parametrize("value", [None, ""])
    def test_decrypt_none_or_empty_returns_none(self, value):
        assert SecretBox.ephemeral().decrypt(value) is None

    def test_legacy_plaintext_passthrough(self):
        box = SecretBox.ephemeral()
        assert box.decrypt("sk-legacy-plaintext") == "sk-legacy-plaintext"

    def test_is_encrypted_detects_fresh_token(self):
        box = SecretBox.ephemeral()
        assert box.is_encrypted(box.encrypt("sk-x")) is True
        assert box.is_encrypted("sk-legacy") is False
        assert box.is_encrypted(None) is False
        assert box.is_encrypted("") is False

    def test_unreadable_token_returns_none_and_logs(self, caplog):
        """A token from another key must not be returned as if it were a key."""
        box = SecretBox.ephemeral()
        foreign_token = SecretBox.ephemeral().encrypt("sk-other-key")
        with caplog.at_level(logging.ERROR):
            assert box.decrypt(foreign_token) is None
        assert "Cannot decrypt api_key_enc" in caplog.text


class TestKeyFileRecovery:
    """An unusable key file must fail clearly instead of crashing at boot."""

    def test_empty_key_file_raises_clear_error_naming_path(self, tmp_path):
        key_path = tmp_path / ".secret_key"
        key_path.write_bytes(b"")

        with pytest.raises(SecretKeyFileError) as excinfo:
            SecretBox.from_key_file(key_path)

        message = str(excinfo.value)
        assert str(key_path) in message
        assert "DATARA_SECRET_KEY" in message

    def test_corrupt_key_file_raises_clear_error_naming_path(self, tmp_path):
        key_path = tmp_path / ".secret_key"
        key_path.write_bytes(b"this-is-not-a-fernet-key")

        with pytest.raises(SecretKeyFileError) as excinfo:
            SecretBox.from_key_file(key_path)

        message = str(excinfo.value)
        assert str(key_path) in message
        # Never leak file contents into the error message.
        assert "this-is-not-a-fernet-key" not in message

    def test_valid_existing_key_file_is_reused(self, tmp_path):
        key_path = tmp_path / ".secret_key"
        key_path.write_bytes(Fernet.generate_key())

        box = SecretBox.from_key_file(key_path)
        assert box.decrypt(box.encrypt("sk-reused")) == "sk-reused"