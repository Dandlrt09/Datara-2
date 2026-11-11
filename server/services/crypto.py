"""Symmetric encryption for user-supplied API keys at rest.

Wraps ``cryptography.fernet.Fernet`` (AES-128-CBC + HMAC-SHA256) behind a
small ``SecretBox`` abstraction. The Fernet key is resolved once per store,
in this order:

1. ``DATARA_SECRET_KEY`` env var, when set and non-empty, is stretched with
   HKDF-SHA256. IMPORTANT: HKDF is used WITHOUT a salt, so it adds no
   entropy — the secret must already be high-entropy (e.g.
   ``openssl rand -base64 32``). A weak passphrase is brute-forceable
   directly from the ciphertext.
2. Otherwise the OS keyring is asked for the key (F9/S11).
3. Otherwise a random key file ``<db_dir>/.secret_key`` is created next to
   the database (mode 0600) and reused across boots.
4. When the store has no real on-disk path (e.g. ``:memory:`` in tests), an
   ephemeral per-instance key is generated and NEVER written anywhere. A
   file-backed store, by contrast, always writes the key file beside its DB —
   including tests that build one from a ``tempfile.mkstemp`` path, which
   therefore leave a real ``.secret_key`` (mode 0600) next to that temp DB.

Hard rule (S11): an existing ``.secret_key`` is never orphaned. If the
keyring holds no usable key but the file does, the file's key is adopted and
copied into the keyring, so the ciphertext already stored stays readable and
the next boot prefers the keyring. The file is never deleted or overwritten.
When the keyring is missing or raises (WSL, headless Linux), resolution falls
back to the file and the app still boots.
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

try:  # keyring is a declared dependency; guard import so a broken install
    # degrades to the key-file path instead of failing to boot.
    import keyring
except Exception:  # pragma: no cover - defensive only
    keyring = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Keyring slot owned by the at-rest Fernet key (service, username).
_KEYRING_SERVICE = "datara"
_KEYRING_USERNAME = "api-key-encryption"

# HKDF context string, versioned so a future scheme can derive a different key.
_HKDF_INFO = b"datara/user-settings-api-key/v1"

# Separate HKDF context for the auth-attempt HMAC key (F9/S4). Deriving it from
# the same secret material with a different info keeps key separation: the
# limiter digest never shares a key with the at-rest encryption.
_ATTEMPT_HMAC_INFO = b"datara/auth-attempt-hmac/v1"

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


def _keyring_load_key() -> bytes | None:
    """Return the Fernet key stored in the OS keyring, or ``None``.

    Every keyring failure (no backend, locked collection, missing D-Bus) is
    swallowed and logged: at-rest encryption must keep booting on hosts where
    the keyring is unusable, falling back to the key file.
    """
    if keyring is None:
        return None
    try:
        stored = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
        if not stored:
            return None
        return stored.encode("ascii")
    except Exception as exc:  # noqa: BLE001 - any backend failure is a fallback
        logger.warning(
            "OS keyring unavailable; falling back to the key file: %s", exc
        )
        return None


def _keyring_store_key(key: bytes) -> bool:
    """Persist *key* in the OS keyring; return whether it was stored."""
    if keyring is None:
        return False
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, key.decode("ascii"))
    except Exception as exc:  # noqa: BLE001 - best effort, file stays authoritative
        logger.warning("Could not persist secret key to OS keyring: %s", exc)
        return False
    return True


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
        self._key = key
        self._fernet = Fernet(key)

    def attempt_hmac_key(self) -> bytes:
        """A distinct subkey for the auth-attempt HMAC (F9/S4).

        Derived from the same secret material as the at-rest encryption key,
        with a different HKDF info so the two uses never share a key. The
        result is deterministic for a given secret (env var or key file), which
        is what lets the persisted brake survive a restart.
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=_ATTEMPT_HMAC_INFO,
        )
        return hkdf.derive(self._key)

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

        Resolution order (S11): ``DATARA_SECRET_KEY`` (explicit override) →
        OS keyring → on-disk key file → ephemeral in-memory key for
        ``:memory:`` / path-less stores.
        """
        secret = os.environ.get("DATARA_SECRET_KEY")
        if secret:
            return cls.from_env_secret(secret)
        if db_path and db_path != ":memory:":
            # ``db_path`` has already been resolved by every consumer through
            # ``server.db_path.resolve_db_path``; expanding here too is a safe
            # no-op that keeps direct callers consistent with them.
            key_path = Path(db_path).expanduser().parent / _SECRET_FILE_NAME
            return cls._from_keyring_or_file(key_path)
        return cls.ephemeral()

    @classmethod
    def _from_keyring_or_file(cls, key_path: Path) -> SecretBox:
        """Resolve from the keyring, adopting the key file when needed.

        A usable keyring key wins. Otherwise the file key is used and copied
        into the keyring so a later boot prefers it; the file is never deleted
        or overwritten, which is what keeps an existing ciphertext readable.
        """
        keyring_key = _keyring_load_key()
        if keyring_key is not None:
            try:
                box = cls(keyring_key)
            except ValueError:
                logger.warning(
                    "Ignoring unusable key in the OS keyring; "
                    "falling back to key file %s",
                    key_path,
                )
            else:
                # Keep the file fallback in step with the keyring without ever
                # touching a file that already exists.
                cls._write_new_key_file(key_path, keyring_key)
                return box
        box = cls.from_key_file(key_path)
        _keyring_store_key(box._key)
        return box

    @staticmethod
    def _write_new_key_file(key_path: Path, key: bytes) -> None:
        """Create *key_path* with *key* only when it does not exist yet."""
        try:
            fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return
        try:
            os.write(fd, key)
        finally:
            os.close(fd)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            logger.warning("Could not chmod secret key file %s", key_path)

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