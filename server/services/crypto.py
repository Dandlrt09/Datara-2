"""Symmetric encryption for user-supplied API keys at rest.

Wraps ``cryptography.fernet.Fernet`` (AES-128-CBC + HMAC-SHA256) behind a
small ``SecretBox`` abstraction. The Fernet key is resolved once per store,
in this order:

1. ``DATARA_SECRET_KEY`` env var, when set and non-empty, is stretched with
   HKDF-SHA256. IMPORTANT: HKDF is used WITHOUT a salt, so it adds no
   entropy — the secret must already be high-entropy (e.g.
   ``openssl rand -base64 32``). A weak passphrase is brute-forceable
   directly from the ciphertext.
2. Otherwise a random key file ``<db_dir>/.secret_key`` is created next to
   the database (mode 0600) and reused across boots.
3. When the store has no real on-disk path (e.g. ``:memory:`` in tests), an
   ephemeral per-instance key is generated and NEVER written anywhere. A
   file-backed store, by contrast, always writes the key file beside its DB —
   including tests that build one from a ``tempfile.mkstemp`` path, which
   therefore leave a real ``.secret_key`` (mode 0600) next to that temp DB.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

# HKDF context string, versioned so a future scheme can derive a different key.
_HKDF_INFO = b"datara/user-settings-api-key/v1"

# Fernet tokens carry a stable version+timestamp prefix; legacy plaintext API
# keys never start with it, which is what makes the heuristic safe.
_FERNET_PREFIX = "gAAAAA"

_SECRET_FILE_NAME = ".secret_key"

# A process that loses the key-file creation race can observe a zero-byte file
# for a few milliseconds. Retry briefly before declaring the file unusable.
_EMPTY_KEY_READ_ATTEMPTS = 10
_EMPTY_KEY_READ_DELAY_SECONDS = 0.05


class SecretKeyFileError(RuntimeError):
    """The on-disk Fernet key file is empty or not a valid key.

    Raised instead of a bare ``ValueError`` so callers and tests can handle
    an unusable key file explicitly. The file's contents are never included.
    """


def _derive_key(secret: str) -> bytes:
    """Derive a Fernet key from ``DATARA_SECRET_KEY`` deterministically."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    )
    return base64.urlsafe_b64encode(hkdf.derive(secret.encode("utf-8")))


def _key_file_error(key_path: Path) -> SecretKeyFileError:
    """Build the operator-facing error for an unusable key file."""
    return SecretKeyFileError(
        f"Secret key file {key_path} is empty or not a valid Fernet key. "
        "Delete the file to regenerate a fresh key, or provide the "
        "DATARA_SECRET_KEY env var to use a stable secret."
    )


class SecretBox:
    """Thin Fernet wrapper with legacy-plaintext passthrough."""

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_env_secret(cls, secret: str) -> SecretBox:
        """Build a box from a raw ``DATARA_SECRET_KEY`` value."""
        return cls(_derive_key(secret))

    @classmethod
    def from_key_file(cls, key_path: Path) -> SecretBox:
        """Read (or atomically create) a Fernet key file at *key_path*.

        An existing file that stays empty after a short retry window (a lost
        creation race) or that is not a valid Fernet key raises
        ``SecretKeyFileError`` naming the path. File contents are never logged.
        """
        try:
            fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # Another process may have won the creation race but not finished
            # writing yet — read with a bounded retry instead of failing on the
            # transient zero-byte window.
            key = cls._read_existing_key(key_path)
        else:
            try:
                key = Fernet.generate_key()
                os.write(fd, key)
            finally:
                os.close(fd)
            # Some filesystems ignore the mode passed to os.open. Re-assert it.
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                logger.warning("Could not chmod secret key file %s", key_path)
        try:
            return cls(key)
        except ValueError as exc:
            raise _key_file_error(key_path) from exc

    @staticmethod
    def _read_existing_key(key_path: Path) -> bytes:
        """Read an existing key file, retrying while it is transiently empty."""
        for attempt in range(_EMPTY_KEY_READ_ATTEMPTS):
            key = key_path.read_bytes().strip()
            if key:
                return key
            if attempt < _EMPTY_KEY_READ_ATTEMPTS - 1:
                time.sleep(_EMPTY_KEY_READ_DELAY_SECONDS)
        raise _key_file_error(key_path)

    @classmethod
    def ephemeral(cls) -> SecretBox:
        """Build a throwaway box; its key is never persisted."""
        return cls(Fernet.generate_key())

    @classmethod
    def for_store(cls, db_path: str | None) -> SecretBox:
        """Resolve a box for a store backed by *db_path*.

        Env var wins; then an on-disk key file next to the DB; then an
        ephemeral in-memory key for ``:memory:`` / path-less stores.
        """
        secret = os.environ.get("DATARA_SECRET_KEY")
        if secret:
            return cls.from_env_secret(secret)
        if db_path and db_path != ":memory:":
            # ``db_path`` has already been resolved by every consumer through
            # ``server.db_path.resolve_db_path``; expanding here too is a safe
            # no-op that keeps direct callers consistent with them.
            key_path = Path(db_path).expanduser().parent / _SECRET_FILE_NAME
            return cls.from_key_file(key_path)
        return cls.ephemeral()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt *plaintext* into a Fernet token string."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str | None) -> str | None:
        """Decrypt a stored value, tolerating legacy plaintext.

        ``None``/empty → ``None``. Values that do not look like a Fernet
        token are returned unchanged (rows written before encryption).
        Values that look token-like but fail to decrypt → ``None`` (logged):
        returning the ciphertext would silently hand the caller a bogus API
        key.
        """
        if not value:
            return None
        if not self.is_encrypted(value):
            return value
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            logger.error(
                "Cannot decrypt api_key_enc: it was encrypted with a different "
                "DATARA_SECRET_KEY (or key file). Treating it as absent; "
                "re-save the API key in Settings."
            )
            return None

    @staticmethod
    def is_encrypted(value: str | None) -> bool:
        """True when *value* looks like a Fernet token."""
        return bool(value) and value.startswith(_FERNET_PREFIX)