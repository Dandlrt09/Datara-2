"""Hardening probes for the editable display name (T1).

These pin the edges the spec fixes in letters and that the first pass of
``test_auth_api.py::TestEditableName`` did not cover: the 80-character limit is
measured AFTER normalization (D4), a malformed body is a malformed request
rather than a second spelling of "clear" (D2/D3), ``register`` and ``login``
carry the same ``name`` key as ``/me`` (S2/D2), and no field in the body can
steer which user is written (D5).
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.services.auth_service import MAX_DISPLAY_NAME_LENGTH
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def client():
    application = FastAPI()
    application.include_router(auth_router)
    store = SqliteStore(db_path=":memory:")
    asyncio.run(store.connect())
    asyncio.run(apply_all_migrations(store))
    api_store._store = store
    yield TestClient(application)
    asyncio.run(store.close())
    api_store._store = None


def _register(client, email: str) -> str:
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


class TestNameHardening:
    def test_register_and_login_payloads_carry_name(self, client):
        """S2/D2: all three routes share one UserResponse shape, name null."""
        register = client.post(
            "/api/auth/register",
            json={"email": "shape@example.com", "password": "password123"},
        )
        assert set(register.json()) == {
            "id",
            "email",
            "name",
            "pending_deletion_at",
        }
        assert register.json()["name"] is None

        login = client.post(
            "/api/auth/login",
            json={"email": "shape@example.com", "password": "password123"},
        )
        assert set(login.json()) == {
            "id",
            "email",
            "name",
            "pending_deletion_at",
        }
        assert login.json()["name"] is None

    def test_limit_is_measured_after_normalization(self, client):
        """D4: raw input over the limit that normalizes inside it is accepted;
        over the limit after normalizing is 422 and leaves the stored name.

        Written against ``MAX_DISPLAY_NAME_LENGTH`` on purpose: the number moved
        from 80 to 50 on 29/10 (D4 rewritten) and this probe must keep checking
        the rule, not the figure."""
        limit = MAX_DISPLAY_NAME_LENGTH
        cookie = _register(client, "normalized@example.com")
        # Three spaces collapse to one, so the raw input is two characters over
        # the limit while the normalized name sits exactly on it.
        raw_over_limit_normalizing_inside = "a" * (limit - 2) + "   " + "a"
        assert len(raw_over_limit_normalizing_inside) == limit + 2

        accepted = client.patch(
            "/api/auth/me",
            json={"name": raw_over_limit_normalizing_inside},
            headers={"Cookie": cookie},
        )
        assert accepted.status_code == 200
        assert len(accepted.json()["name"]) == limit

        assert (
            client.patch(
                "/api/auth/me",
                json={"name": "b" * limit},
                headers={"Cookie": cookie},
            ).status_code
            == 200
        )
        rejected = client.patch(
            "/api/auth/me",
            json={"name": "c" * (limit + 1)},
            headers={"Cookie": cookie},
        )
        assert rejected.status_code == 422
        assert rejected.json()["detail"] == (
            f"Name must be at most {limit} characters"
        )

        me = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me.json()["name"] == "b" * limit

    def test_the_limit_is_the_decided_fifty(self, client):
        """D4: the figure itself is part of the spec, so it is pinned with
        literals -- 50 is a valid name and 51 is not.

        The other limit probes are written against ``MAX_DISPLAY_NAME_LENGTH``
        (they check the rule, which survives a figure change); this one is what
        notices if the number moves without a decision (it was 80 before
        29/10).
        """
        cookie = _register(client, "figure@example.com")

        at_limit = client.patch(
            "/api/auth/me", json={"name": "F" * 50}, headers={"Cookie": cookie}
        )
        over_limit = client.patch(
            "/api/auth/me", json={"name": "F" * 51}, headers={"Cookie": cookie}
        )

        assert at_limit.status_code == 200
        assert over_limit.status_code == 422
        assert over_limit.json()["detail"] == "Name must be at most 50 characters"

    def test_blank_names_are_rejected_not_cleared(self, client):
        """D3 (rewritten): blank input is invalid, so the stored name survives."""
        cookie = _register(client, "blank@example.com")
        client.patch(
            "/api/auth/me", json={"name": "Ana"}, headers={"Cookie": cookie}
        )

        for blank in ("", "   ", "\n\t "):
            resp = client.patch(
                "/api/auth/me", json={"name": blank}, headers={"Cookie": cookie}
            )
            assert resp.status_code == 422
            assert resp.json()["detail"] == "Name cannot be empty"

        me = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me.json()["name"] == "Ana"

    def test_malformed_bodies_are_rejected(self, client):
        """D2: a missing or non-string name is malformed, not a clear."""
        cookie = _register(client, "malformed@example.com")

        no_body = client.patch("/api/auth/me", headers={"Cookie": cookie})
        numeric = client.patch(
            "/api/auth/me", json={"name": 123}, headers={"Cookie": cookie}
        )

        assert no_body.status_code == 422
        assert numeric.status_code == 422
        me = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me.json()["name"] is None

    def test_forged_identity_fields_in_the_body_are_ignored(self, client):
        """D5: id/user_id/email in the body never steer the session's user."""
        cookie_a = _register(client, "forged-a@example.com")
        cookie_b = _register(client, "forged-b@example.com")
        user_b = client.get("/api/auth/me", headers={"Cookie": cookie_b}).json()

        forged = client.patch(
            "/api/auth/me",
            json={
                "name": "Hacked",
                "id": user_b["id"],
                "user_id": user_b["id"],
                "email": "evil@example.com",
            },
            headers={"Cookie": cookie_a},
        )

        assert forged.status_code == 200
        assert forged.json()["id"] != user_b["id"]
        assert forged.json()["email"] == "forged-a@example.com"
        assert forged.json()["name"] == "Hacked"

        other = client.get("/api/auth/me", headers={"Cookie": cookie_b})
        assert other.json()["name"] is None
        assert other.json()["email"] == "forged-b@example.com"

    def test_login_carries_the_chosen_name(self, client):
        """S2: the chosen name survives a fresh login, not just /me."""
        cookie = _register(client, "rename@example.com")
        client.patch(
            "/api/auth/me", json={"name": "Ana Lopez"}, headers={"Cookie": cookie}
        )

        login = client.post(
            "/api/auth/login",
            json={"email": "rename@example.com", "password": "password123"},
        )

        assert login.json()["name"] == "Ana Lopez"
