"""Integration tests for the optional local lock and its rescue key (F1 / T4, S1, D4).

The local profile is created WITHOUT a password (L10), exactly as before, and
the optional lock is turned on later from the Profile screen. Turning it on
(``POST /api/auth/local-profile/lock``) stores a password hash plus the hash of
a one-time rescue key, and answers with the RAW rescue key exactly once -- it
never appears in the database nor in any later read. Opening a locked profile
(``POST /api/auth/local-profile/open``) verifies the password and mints a
session; rescuing it (``POST /api/auth/local-profile/rescue``) verifies the
rescue key, sets a new password and ROTATES the key. The get-or-create route
must never open a locked profile, and every route is refused outside local mode.
"""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.auth import router as auth_router
from server.services.auth_service import (
    generate_raw_token,
    hash_password,
    hash_token,
)
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations

PASSWORD = "correct horse battery"
MODE_DETAIL = "Local profile is only available in local mode"
SHORT_DETAIL = "Password must be at least 8 characters"


@pytest.fixture
def store():
    """A fresh in-memory store injected into ``server.api.store._store``."""
    from server.api import store as api_store  # noqa: PLC0415

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        await apply_all_migrations(s)

    asyncio.run(_setup())
    api_store._store = s

    yield s

    asyncio.run(s.close())
    api_store._store = None


@pytest.fixture
def app(store):
    """Create a minimal FastAPI app with the auth router wired up."""
    application = FastAPI()
    application.include_router(auth_router)
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


def _local_row(store: SqliteStore) -> dict | None:
    """Read the local profile's lock columns straight from the database.

    This is the one place a test looks under the public interface, and only to
    prove what the API must never reveal: that the rescue key is stored hashed.
    """

    async def _fetch():
        rows = await store.conn.execute_fetchall(
            "SELECT id, password_hash, local_rescue_hash FROM users "
            "WHERE kind = 'local'"
        )
        return dict(rows[0]) if rows else None

    return asyncio.run(_fetch())


def _session_count(store: SqliteStore) -> int:
    """Count rows in ``auth_sessions`` -- only to prove a refusal wrote none."""

    async def _count() -> int:
        rows = await store.conn.execute_fetchall("SELECT COUNT(*) FROM auth_sessions")
        return rows[0][0]

    return asyncio.run(_count())


def _lock(client, password: str = PASSWORD):
    """Turn the lock on with the client's current session cookie."""
    return client.post("/api/auth/local-profile/lock", json={"password": password})


def _create_local(client, monkeypatch, name: str = "Ana") -> None:
    """Create the profile in local mode, leaving the client's session cookie set."""
    monkeypatch.setenv("DATARA_MODE", "local")
    created = client.post("/api/auth/local-profile", json={"name": name})
    assert created.status_code == 201


def _seed_hosted_session(store: SqliteStore) -> str:
    """Create a hosted account and one session; return its raw cookie token.

    The lock route must refuse a session whose user is not the local profile,
    and the only way to hold such a session through the public API is the
    email login -- which needs a verified address. Seeding the row directly is
    the shortest honest way to reach that state.
    """

    async def _seed() -> str:
        user = await store.create_user(
            "ana@example.com", hash_password(PASSWORD), name="Ana"
        )
        raw = generate_raw_token()
        await store.create_auth_session(user["id"], hash_token(raw))
        return raw

    return asyncio.run(_seed())


class TestLock:
    def test_lock_returns_a_raw_key_and_stores_only_hashes(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)

        resp = _lock(client)

        assert resp.status_code == 200
        rescue_key = resp.json()["rescue_key"]
        assert rescue_key

        row = _local_row(store)
        assert row is not None
        # The password is hashed (bcrypt), never the plaintext.
        assert row["password_hash"] != PASSWORD
        assert row["password_hash"].startswith("$2")
        # The rescue key exists only as its SHA-256 hash; the raw value never
        # touches storage.
        assert row["local_rescue_hash"] == hash_token(rescue_key)
        assert row["local_rescue_hash"] != rescue_key
        assert rescue_key not in json.dumps(row)

    def test_a_second_lock_is_refused(self, client, store, monkeypatch):
        _create_local(client, monkeypatch)
        first = _lock(client)
        assert first.status_code == 200
        stored = _local_row(store)

        resp = _lock(client, "another password")

        assert resp.status_code == 409
        assert resp.json()["detail"] == "This profile is already locked"
        # The refusal changed nothing: same hashes, no new rescue key issued.
        assert _local_row(store) == stored

    def test_a_short_password_is_refused_and_leaves_no_lock(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)

        resp = _lock(client, "short")

        assert resp.status_code == 422
        assert resp.json()["detail"] == SHORT_DETAIL
        row = _local_row(store)
        assert row is not None
        assert row["password_hash"] is None
        assert row["local_rescue_hash"] is None

    def test_lock_outside_local_mode_is_forbidden(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)

        monkeypatch.setenv("DATARA_MODE", "hosted")
        resp = _lock(client)

        assert resp.status_code == 403
        assert resp.json()["detail"] == MODE_DETAIL
        assert _local_row(store)["password_hash"] is None

    def test_lock_for_a_hosted_session_is_not_found(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)
        client.cookies.clear()
        token = _seed_hosted_session(store)

        resp = client.post(
            "/api/auth/local-profile/lock",
            json={"password": PASSWORD},
            headers={"Cookie": f"session_id={token}"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Local profile not found"
        assert _local_row(store)["password_hash"] is None


class TestStatus:
    def test_get_reports_locked_true_after_locking(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)

        before = client.get("/api/auth/local-profile")
        assert before.status_code == 200
        assert before.json() == {
            "exists": True,
            "hosted_accounts": False,
            "locked": False,
        }
        assert "rescue_key" not in before.json()

        assert _lock(client).status_code == 200

        after = client.get("/api/auth/local-profile")
        assert after.status_code == 200
        assert after.json() == {
            "exists": True,
            "hosted_accounts": False,
            "locked": True,
        }
        assert "rescue_key" not in after.json()

    def test_the_rescue_key_never_appears_in_a_later_read(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)
        rescue_key = _lock(client).json()["rescue_key"]

        status = client.get("/api/auth/local-profile")
        assert rescue_key not in status.text

        opened = client.post(
            "/api/auth/local-profile/open", json={"password": PASSWORD}
        )
        assert opened.status_code == 200
        assert rescue_key not in opened.text

        me_resp = client.get("/api/auth/me")
        assert me_resp.status_code == 200
        assert rescue_key not in me_resp.text
        assert set(me_resp.json()) == {
            "id",
            "email",
            "name",
            "pending_deletion_at",
        }


class TestOpen:
    def test_get_or_create_does_not_open_a_locked_profile(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)
        assert _lock(client).status_code == 200
        client.cookies.clear()
        sessions_before = _session_count(store)

        resp = client.post("/api/auth/local-profile", json={})

        assert resp.status_code == 401
        assert resp.json()["detail"] == "This profile is locked"
        assert resp.headers.get("set-cookie") is None
        assert _session_count(store) == sessions_before

    def test_open_with_the_right_password_starts_a_session(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)
        assert _lock(client).status_code == 200
        client.cookies.clear()

        resp = client.post(
            "/api/auth/local-profile/open", json={"password": PASSWORD}
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] is None
        set_cookie = resp.headers.get("set-cookie")
        assert set_cookie is not None

        me_resp = client.get("/api/auth/me", headers={"Cookie": set_cookie})
        assert me_resp.status_code == 200
        assert me_resp.json()["id"] == data["id"]

    def test_open_with_a_wrong_password_is_refused(
        self, client, store, monkeypatch
    ):
        _create_local(client, monkeypatch)
        assert _lock(client).status_code == 200
        client.cookies.clear()
        sessions_before = _session_count(store)

        resp = client.post(
            "/api/auth/local-profile/open", json={"password": "not the password"}
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid password"
        assert resp.headers.get("set-cookie") is None
        assert _session_count(store) == sessions_before

    def test_open_without_a_lock_is_refused(
        self, client, store, monkeypatch
    ):
        """A profile with no lock has nothing to open with a password."""
        _create_local(client, monkeypatch)
        client.cookies.clear()
        sessions_before = _session_count(store)

        resp = client.post(
            "/api/auth/local-profile/open", json={"password": PASSWORD}
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid password"
        assert resp.headers.get("set-cookie") is None
        assert _session_count(store) == sessions_before

    def test_open_without_a_profile_is_not_found(self, client, store, monkeypatch):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post(
            "/api/auth/local-profile/open", json={"password": PASSWORD}
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Local profile not found"

    def test_open_outside_local_mode_is_forbidden(self, client, monkeypatch):
        monkeypatch.setenv("DATARA_MODE", "hosted")

        resp = client.post(
            "/api/auth/local-profile/open", json={"password": PASSWORD}
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == MODE_DETAIL


class TestRescue:
    def _locked(self, client, monkeypatch) -> str:
        _create_local(client, monkeypatch)
        resp = _lock(client)
        assert resp.status_code == 200
        client.cookies.clear()
        return resp.json()["rescue_key"]

    def test_a_wrong_key_is_refused(
        self, client, store, monkeypatch
    ):
        self._locked(client, monkeypatch)
        sessions_before = _session_count(store)

        resp = client.post(
            "/api/auth/local-profile/rescue",
            json={"rescue_key": "not the key", "new_password": "new password 123"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid rescue key"
        assert resp.headers.get("set-cookie") is None
        assert _session_count(store) == sessions_before

    def test_a_short_new_password_is_refused_and_keeps_the_key(
        self, client, store, monkeypatch
    ):
        rescue_key = self._locked(client, monkeypatch)
        before = _local_row(store)

        resp = client.post(
            "/api/auth/local-profile/rescue",
            json={"rescue_key": rescue_key, "new_password": "short"},
        )

        assert resp.status_code == 422
        assert resp.json()["detail"] == SHORT_DETAIL
        assert resp.headers.get("set-cookie") is None
        # The key was not rotated and the password was not touched.
        assert _local_row(store) == before

    def test_rescue_rotates_the_key_and_opens_with_the_new_password(
        self, client, store, monkeypatch
    ):
        old_key = self._locked(client, monkeypatch)

        resp = client.post(
            "/api/auth/local-profile/rescue",
            json={"rescue_key": old_key, "new_password": "a brand new password"},
        )

        assert resp.status_code == 200
        new_key = resp.json()["rescue_key"]
        assert new_key and new_key != old_key
        assert resp.headers.get("set-cookie") is not None
        row = _local_row(store)
        assert row["local_rescue_hash"] == hash_token(new_key)

        # The used key must stop working: the rotation is deliberate.
        client.cookies.clear()
        reused = client.post(
            "/api/auth/local-profile/rescue",
            json={"rescue_key": old_key, "new_password": "yet another password"},
        )
        assert reused.status_code == 401
        assert reused.json()["detail"] == "Invalid rescue key"

        # The rotated key works, and the new password opens the profile.
        rotated = client.post(
            "/api/auth/local-profile/rescue",
            json={"rescue_key": new_key, "new_password": "another new password"},
        )
        assert rotated.status_code == 200

        client.cookies.clear()
        opened = client.post(
            "/api/auth/local-profile/open",
            json={"password": "another new password"},
        )
        assert opened.status_code == 200

    def test_rescue_without_a_profile_is_not_found(self, client, store, monkeypatch):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post(
            "/api/auth/local-profile/rescue",
            json={"rescue_key": "anything", "new_password": "new password 123"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Local profile not found"

    def test_rescue_without_a_rescue_key_is_invalid(
        self, client, store, monkeypatch
    ):
        """An unlocked profile has no stored rescue hash to match."""
        _create_local(client, monkeypatch)
        client.cookies.clear()

        resp = client.post(
            "/api/auth/local-profile/rescue",
            json={"rescue_key": "anything", "new_password": "new password 123"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid rescue key"

    def test_rescue_outside_local_mode_is_forbidden(self, client, monkeypatch):
        monkeypatch.setenv("DATARA_MODE", "hosted")

        resp = client.post(
            "/api/auth/local-profile/rescue",
            json={"rescue_key": "anything", "new_password": "new password 123"},
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == MODE_DETAIL
