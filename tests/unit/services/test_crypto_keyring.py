"""Tests for OS-keyring-backed Fernet key resolution (F9/S11, T6).

The OS keyring is the preferred store for the at-rest Fernet key, with the
``.secret_key`` file as fallback. These tests pin the resolution order, the
adopt-from-file rule that keeps an existing ciphertext readable, and the
never-fail-to-boot behaviour when no keyring backend is usable.

Every test installs an in-memory backend; the real OS keyring is never touched
and the previous backend is restored no matter how the test exits.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from server.services.crypto import SecretBox
from tests.test_helpers import InMemoryKeyring

# The single keyring slot the resolver must own (pins the public contract).
_KEY = ("datara", "api-key-encryption")


@pytest.fixture
def fake_keyring():
    """Install an in-memory keyring and restore the real one afterwards."""
    import keyring

    original = keyring.get_keyring()
    backend = InMemoryKeyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(original)


class TestResolutionOrder:
    def test_env_secret_overrides_keyring(self, monkeypatch, tmp_path, fake_keyring):
        """DATARA_SECRET_KEY is the explicit override; the keyring is ignored."""
        stored = Fernet.generate_key().decode("ascii")
        fake_keyring.store[_KEY] = stored
        monkeypatch.setenv("DATARA_SECRET_KEY", "explicit-env-secret")

        box = SecretBox.for_store(str(tmp_path / "datara.db"))

        expected = SecretBox.from_env_secret("explicit-env-secret")
        assert box.decrypt(expected.encrypt("sk-env")) == "sk-env"
        # Neither the keyring slot nor a key file may be created.
        assert fake_keyring.store[_KEY] == stored
        assert not (tmp_path / ".secret_key").exists()

    def test_keyring_key_is_preferred_over_key_file(
        self, monkeypatch, tmp_path, fake_keyring
    ):
        """With no env var, a usable keyring key wins over the file."""
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        keyring_key = Fernet.generate_key()
        fake_keyring.store[_KEY] = keyring_key.decode("ascii")
        # A pre-existing file with a different key must not shadow the keyring.
        file_key = Fernet.generate_key()
        key_path = tmp_path / ".secret_key"
        key_path.write_bytes(file_key)

        box = SecretBox.for_store(str(tmp_path / "datara.db"))

        token = SecretBox(keyring_key).encrypt("sk-from-keyring")
        assert box.decrypt(token) == "sk-from-keyring"
        assert key_path.read_bytes() == file_key


class TestAdoptFromFile:
    def test_existing_file_key_is_adopted_into_empty_keyring(
        self, monkeypatch, tmp_path, fake_keyring
    ):
        """An existing file key must survive and be copied into the keyring."""
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        file_key = Fernet.generate_key()
        key_path = tmp_path / ".secret_key"
        key_path.write_bytes(file_key)

        box = SecretBox.for_store(str(tmp_path / "datara.db"))

        assert box.decrypt(SecretBox(file_key).encrypt("sk-file")) == "sk-file"
        # Next boot must prefer the keyring, now holding the file's key.
        assert fake_keyring.store[_KEY] == file_key.decode("ascii")
        assert key_path.read_bytes() == file_key

    def test_ciphertext_stays_readable_when_keyring_loses_the_key(
        self, monkeypatch, tmp_path, fake_keyring
    ):
        """The hard rule: an existing ciphertext must remain decryptable."""
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        db_path = str(tmp_path / "datara.db")

        before = SecretBox.for_store(db_path)
        token = before.encrypt("sk-provider")
        assert (tmp_path / ".secret_key").exists()

        # Simulate a host where the keyring entry vanished (e.g. new keyring).
        fake_keyring.store.clear()
        after = SecretBox.for_store(db_path)
        assert after.decrypt(token) == "sk-provider"


class TestUnavailableKeyring:
    def test_broken_keyring_falls_back_to_file(self, monkeypatch, tmp_path):
        """A raising keyring must never stop the store from booting."""
        import keyring

        class BrokenKeyring(InMemoryKeyring):
            def get_password(self, service: str, username: str) -> str | None:
                raise RuntimeError("no secret service")

            def set_password(self, service: str, username: str, password: str) -> None:
                raise RuntimeError("no secret service")

        original = keyring.get_keyring()
        keyring.set_keyring(BrokenKeyring())
        try:
            monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
            box = SecretBox.for_store(str(tmp_path / "datara.db"))
            token = box.encrypt("sk-file")
            assert box.decrypt(token) == "sk-file"
            assert (tmp_path / ".secret_key").exists()
            # A restart reads the same file key.
            restarted = SecretBox.for_store(str(tmp_path / "datara.db"))
            assert restarted.decrypt(token) == "sk-file"
        finally:
            keyring.set_keyring(original)

    def test_the_suite_installs_a_hermetic_keyring(self):
        """The global fixture keeps every test off the real OS keyring (S11).

        Without it, any test that builds a file-backed store would read and
        write the developer's own secret store.
        """
        import keyring

        assert isinstance(keyring.get_keyring(), InMemoryKeyring)

    def test_memory_store_does_not_touch_keyring(
        self, monkeypatch, fake_keyring
    ):
        """Path-less stores stay ephemeral and must not write to any keyring."""
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        box = SecretBox.for_store(":memory:")
        assert box.decrypt(box.encrypt("sk-mem")) == "sk-mem"
        assert fake_keyring.store == {}


class TestSlotRepair:
    """The slot can be damaged; the store must still boot (F9/S11)."""

    def test_garbage_keyring_slot_falls_back_and_repairs(
        self, monkeypatch, tmp_path, fake_keyring
    ):
        """A garbage keyring value must not wedge the store.

        The file fallback wins and the slot is repaired with the valid file
        key, so the next boot finds a usable keyring entry.
        """
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        fake_keyring.store[_KEY] = "garbage-not-a-fernet-key"
        db_path = str(tmp_path / "datara.db")

        box = SecretBox.for_store(db_path)
        token = box.encrypt("sk-repair")

        assert box.decrypt(token) == "sk-repair"
        file_key = (tmp_path / ".secret_key").read_bytes().strip()
        assert fake_keyring.store[_KEY] == file_key.decode("ascii")

    def test_divergent_keyring_key_leaves_file_ciphertext_unreadable(
        self, monkeypatch, tmp_path, fake_keyring
    ):
        """Pins the documented single-slot trade-off (follow-up (b)).

        When the keyring already holds a usable key that differs from a
        pre-existing key file, the keyring wins (S11's order) and the file's
        ciphertext becomes undecryptable. Reachable only with a second DB under
        the same OS user or a hand-replaced file -- never in a single-DB
        install. Pinned so a future per-DB-namespaced slot has to break it on
        purpose.
        """
        monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
        keyring_key = Fernet.generate_key()
        fake_keyring.store[_KEY] = keyring_key.decode("ascii")
        file_key = Fernet.generate_key()
        key_path = tmp_path / ".secret_key"
        key_path.write_bytes(file_key)

        box = SecretBox.for_store(str(tmp_path / "datara.db"))
        token = SecretBox(file_key).encrypt("sk-file-era")

        assert box.decrypt(token) is None
        assert key_path.read_bytes() == file_key
