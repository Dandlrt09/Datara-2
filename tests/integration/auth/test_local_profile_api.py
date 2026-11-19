"""Integration tests for ``/api/auth/local-profile`` (F1 / T2b, S1, D2, D5, L10).

In local mode the first boot creates the profile on this machine: no email, a
required display name, and -- unlike register -- it immediately starts the
session, because there is no address to prove and a profile nobody could enter
would be a dead end. Under L10 the lock is optional, so a later boot OPENS the
existing profile instead of being refused (200 rather than the old 409), and
``GET /api/auth/local-profile`` reports ``{exists, hosted_accounts}`` before any
session so the frontend can pick the first-boot screen, open silently, or keep
an existing install's email login (D3). In hosted mode both routes are a
backstop that refuses with 403.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.errors import DuplicateError
from server.api.routers.auth import router as auth_router
from server.services.auth_service import MAX_DISPLAY_NAME_LENGTH
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
from tests.test_helpers import apply_all_migrations


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


def _user_count(store: SqliteStore) -> int:
    """Count rows in ``users``; there is no public surface that exposes it."""

    async def _count() -> int:
        rows = await store.conn.execute_fetchall("SELECT COUNT(*) FROM users")
        return rows[0][0]

    return asyncio.run(_count())


def _session_count(store: SqliteStore) -> int:
    """Count rows in ``auth_sessions`` -- only to prove a refusal wrote none."""

    async def _count() -> int:
        rows = await store.conn.execute_fetchall("SELECT COUNT(*) FROM auth_sessions")
        return rows[0][0]

    return asyncio.run(_count())


def _register_hosted(client, email: str = "ana@example.com") -> None:
    """Register one email account through the real route (D3 signal)."""
    resp = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "password123",
            "terms_version": TERMS_VERSION,
        },
    )
    assert resp.status_code == 200


class TestLocalProfile:
    def test_local_mode_creates_the_profile_and_starts_a_session(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post("/api/auth/local-profile", json={"name": "Ana"})

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Ana"
        assert data["email"] is None
        assert data["pending_deletion_at"] is None
        set_cookie = resp.headers.get("set-cookie")
        assert set_cookie is not None

        me_resp = client.get("/api/auth/me", headers={"Cookie": set_cookie})
        assert me_resp.status_code == 200
        assert me_resp.json()["id"] == data["id"]
        assert me_resp.json()["name"] == "Ana"
        assert me_resp.json()["email"] is None

    def test_hosted_mode_refuses_and_creates_no_row(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "hosted")

        resp = client.post("/api/auth/local-profile", json={"name": "Ana"})

        assert resp.status_code == 403
        assert resp.json()["detail"] == (
            "Local profile is only available in local mode"
        )
        assert _user_count(store) == 0

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
    def test_blank_name_is_rejected_and_creates_no_row(
        self, client, store, monkeypatch, blank
    ):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post("/api/auth/local-profile", json={"name": blank})

        assert resp.status_code == 422
        assert resp.json()["detail"] == "Name is required"
        assert _user_count(store) == 0

    def test_name_over_the_limit_is_rejected_and_creates_no_row(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post(
            "/api/auth/local-profile",
            json={"name": "x" * (MAX_DISPLAY_NAME_LENGTH + 1)},
        )

        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            f"Name must be at most {MAX_DISPLAY_NAME_LENGTH} characters"
        )
        assert _user_count(store) == 0

    def test_the_name_is_normalized_before_it_is_stored(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post("/api/auth/local-profile", json={"name": "  Ana   María  "})

        assert resp.status_code == 201
        assert resp.json()["name"] == "Ana María"

    def test_a_second_local_profile_is_opened_not_refused(
        self, client, store, monkeypatch
    ):
        """L10 replaced the old 409: without a lock, a later boot opens the app.

        The maintainer's decision (``odd/tasks/local-identity.md``, L10): the
        local lock is optional, so when it is OFF the app must just open. This
        test used to expect a 409 ``"A local profile already exists"``; do NOT
        restore that refusal -- a second boot has to reach the same profile.
        """
        monkeypatch.setenv("DATARA_MODE", "local")
        first = client.post("/api/auth/local-profile", json={"name": "Ana"})
        assert first.status_code == 201
        first_data = first.json()

        resp = client.post("/api/auth/local-profile", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == first_data["id"]
        assert data["name"] == "Ana"
        set_cookie = resp.headers.get("set-cookie")
        assert set_cookie is not None

        me_resp = client.get("/api/auth/me", headers={"Cookie": set_cookie})
        assert me_resp.status_code == 200
        assert me_resp.json()["id"] == first_data["id"]
        assert me_resp.json()["name"] == "Ana"
        assert _user_count(store) == 1

    def test_opening_does_not_rename_the_profile(
        self, client, store, monkeypatch
    ):
        """A boot opens the profile; it does not rename it (L10)."""
        monkeypatch.setenv("DATARA_MODE", "local")
        first = client.post("/api/auth/local-profile", json={"name": "Ana"})
        assert first.status_code == 201

        resp = client.post("/api/auth/local-profile", json={"name": "Otra"})

        assert resp.status_code == 200
        assert resp.json()["name"] == "Ana"

        async def _stored_name() -> str | None:
            rows = await store.conn.execute_fetchall(
                "SELECT name FROM users WHERE kind = 'local'"
            )
            return rows[0][0]

        assert asyncio.run(_stored_name()) == "Ana"

    def test_opening_without_a_name_creates_no_row(
        self, client, store, monkeypatch
    ):
        monkeypatch.setenv("DATARA_MODE", "local")

        resp = client.post("/api/auth/local-profile", json={})

        assert resp.status_code == 422
        assert resp.json()["detail"] == "Name is required"
        assert _user_count(store) == 0

    def test_a_bogus_mode_fails_closed_and_creates_no_row(
        self, client, store, monkeypatch
    ):
        """A typo in DATARA_MODE must never hand out a local profile.

        T1 makes an unknown value raise instead of guessing a mode, which is
        why ``GET /api/app-config`` fails the same way, so the error itself is
        the intended answer and is pinned here as such. What matters for this
        route is the other half of failing closed: no identity, no session,
        nothing written.
        """
        monkeypatch.setenv("DATARA_MODE", "locla")

        with pytest.raises(ValueError, match="DATARA_MODE"):
            client.post("/api/auth/local-profile", json={"name": "Ana"})

        assert _user_count(store) == 0

    def test_a_lost_creation_race_opens_the_winner(
        self, client, store, monkeypatch
    ):
        """Two first boots at once: the loser opens the winner's session (L10).

        The route reads "no profile" before it inserts, so the pre-check is not
        atomic and the partial unique index (0015) is what actually decides the
        race: the loser's INSERT is refused and the route re-reads and opens the
        row that won. Without this test, a regression back to a 409 refusal
        would still pass the rest of the suite (L8/verifier finding), so the
        store is driven into exactly the losing state instead.
        """
        monkeypatch.setenv("DATARA_MODE", "local")
        created = client.post("/api/auth/local-profile", json={"name": "Ana"})
        assert created.status_code == 201
        winner_id = created.json()["id"]

        real_get = store.get_local_user
        seen = {"calls": 0}

        async def _lose_the_race():
            # The winner's row is already there, but this caller looked first.
            seen["calls"] += 1
            return None if seen["calls"] == 1 else await real_get()

        async def _duplicate(_name):
            raise DuplicateError("a local profile already exists")

        monkeypatch.setattr(store, "get_local_user", _lose_the_race)
        monkeypatch.setattr(store, "create_local_user", _duplicate)

        resp = client.post("/api/auth/local-profile", json={"name": "Otra"})

        assert resp.status_code == 200
        assert resp.json()["id"] == winner_id
        assert resp.json()["name"] == "Ana"
        assert resp.headers.get("set-cookie") is not None
        assert _user_count(store) == 1

    def test_a_lost_race_with_no_winner_fails_closed(
        self, client, store, monkeypatch
    ):
        """The impossible case invents nothing: no identity, no session (L10).

        If the INSERT is refused and the profile still cannot be read, the only
        safe answer is an explicit 500. A route that "helpfully" created a
        second profile here would break S1 silently.
        """
        monkeypatch.setenv("DATARA_MODE", "local")

        async def _no_profile():
            return None

        async def _duplicate(_name):
            raise DuplicateError("a local profile already exists")

        monkeypatch.setattr(store, "get_local_user", _no_profile)
        monkeypatch.setattr(store, "create_local_user", _duplicate)

        resp = client.post("/api/auth/local-profile", json={"name": "Ana"})

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Local profile could not be created"
        assert resp.headers.get("set-cookie") is None
        assert _user_count(store) == 0
        assert _session_count(store) == 0

    def test_opening_ignores_an_invalid_name(
        self, client, store, monkeypatch
    ):
        """The name rule guards creation, not a boot (L10).

        An open call has nothing to name, so a blank or over-long name in the
        body must not turn a boot into a 422 and lock the analyst out of the
        profile that already exists.
        """
        monkeypatch.setenv("DATARA_MODE", "local")
        created = client.post("/api/auth/local-profile", json={"name": "Ana"})
        assert created.status_code == 201

        for body in (
            {"name": "   "},
            {"name": "x" * (MAX_DISPLAY_NAME_LENGTH + 1)},
        ):
            resp = client.post("/api/auth/local-profile", json=body)
            assert resp.status_code == 200
            assert resp.json()["name"] == "Ana"

        assert _user_count(store) == 1


class TestLocalProfileStatus:
    def test_exists_is_false_before_and_true_after_creation(
        self, client, store, monkeypatch
    ):
        """The frontend asks this BEFORE it holds a session (L10)."""
        monkeypatch.setenv("DATARA_MODE", "local")

        before = client.get("/api/auth/local-profile")
        assert before.status_code == 200
        assert before.json() == {"exists": False, "hosted_accounts": False}

        created = client.post("/api/auth/local-profile", json={"name": "Ana"})
        assert created.status_code == 201

        after = client.get("/api/auth/local-profile")
        assert after.status_code == 200
        assert after.json() == {"exists": True, "hosted_accounts": False}

    def test_hosted_accounts_is_true_after_a_hosted_account_is_registered(
        self, client, monkeypatch
    ):
        """D3: an install that already has email accounts keeps its login."""
        monkeypatch.setenv("DATARA_MODE", "local")

        _register_hosted(client)

        resp = client.get("/api/auth/local-profile")

        assert resp.status_code == 200
        assert resp.json() == {"exists": False, "hosted_accounts": True}

    def test_hosted_accounts_counts_a_row_scheduled_for_deletion(
        self, client, store, monkeypatch
    ):
        """D3: a pending purge still owns data and can still sign in."""
        monkeypatch.setenv("DATARA_MODE", "local")
        _register_hosted(client)

        async def _schedule() -> None:
            await store.conn.execute(
                "UPDATE users SET pending_deletion_at = datetime('now') "
                "WHERE kind = 'hosted'"
            )
            await store.conn.commit()

        asyncio.run(_schedule())

        resp = client.get("/api/auth/local-profile")

        assert resp.json() == {"exists": False, "hosted_accounts": True}

    def test_a_local_profile_and_hosted_accounts_are_reported_together(
        self, client, monkeypatch
    ):
        """D3: the two facts are independent; the profile still wins the offer."""
        monkeypatch.setenv("DATARA_MODE", "local")
        _register_hosted(client)

        created = client.post("/api/auth/local-profile", json={"name": "Ana"})
        assert created.status_code == 201

        resp = client.get("/api/auth/local-profile")

        assert resp.json() == {"exists": True, "hosted_accounts": True}

    def test_hosted_mode_refuses_the_status(self, client, store, monkeypatch):
        monkeypatch.setenv("DATARA_MODE", "hosted")

        resp = client.get("/api/auth/local-profile")

        assert resp.status_code == 403
        assert resp.json()["detail"] == (
            "Local profile is only available in local mode"
        )
