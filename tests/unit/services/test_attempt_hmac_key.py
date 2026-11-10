"""Regression probes for the auth-attempt HMAC key (F9/S4, T3b).

The persisted brake hashes a limiter key with HMAC-SHA256, keyed by a subkey
derived from the store's own secret. These pin the properties that make that
safe and durable: the key survives a restart, differs from the at-rest key and
from a different secret, and is never persisted for a ``:memory:`` store.
"""

from __future__ import annotations

import asyncio

from server.services.crypto import SecretBox
from server.services.sqlite_store import SqliteStore


def test_hmac_key_is_stable_across_stores_on_the_same_db(tmp_path, monkeypatch):
    """S4: a restart must reproduce the same key, or the brake would reset."""
    monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
    db = str(tmp_path / "db.sqlite")

    first = SqliteStore(db_path=db)
    asyncio.run(first.connect())
    key_one = first.attempt_hmac_key()
    asyncio.run(first.close())

    second = SqliteStore(db_path=db)
    asyncio.run(second.connect())
    try:
        assert second.attempt_hmac_key() == key_one
    finally:
        asyncio.run(second.close())


def test_hmac_key_is_separate_from_the_fernet_key():
    """Key separation: the HMAC subkey must differ from the at-rest key."""
    box = SecretBox.from_env_secret("unit-test-secret")
    assert box.attempt_hmac_key() != box._key


def test_memory_stores_get_ephemeral_keys(monkeypatch):
    """A path-less store never writes a key anywhere: each gets its own."""
    monkeypatch.delenv("DATARA_SECRET_KEY", raising=False)
    one = SqliteStore(db_path=":memory:")
    two = SqliteStore(db_path=":memory:")
    asyncio.run(one.connect())
    asyncio.run(two.connect())
    try:
        assert one.attempt_hmac_key() != two.attempt_hmac_key()
    finally:
        asyncio.run(one.close())
        asyncio.run(two.close())


def test_digest_changes_with_the_secret():
    """A different secret must not reproduce digests from an earlier one."""
    one = SecretBox.from_env_secret("secret-one").attempt_hmac_key()
    two = SecretBox.from_env_secret("secret-two").attempt_hmac_key()
    assert one != two
