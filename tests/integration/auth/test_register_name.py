"""The optional display name accepted at registration (register-experience S2).

The signup form asks for a name but lets it empty: an empty name is not an
error, it is the documented fallback to the email-derived name. These probes pin
that contract on the server, which is the only place it can be enforced.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.services.auth_service import MAX_DISPLAY_NAME_LENGTH
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
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


def _register(client, email: str, name=None):
    body = {
        "email": email,
        "password": "password123",
        "terms_version": TERMS_VERSION,
    }
    if name is not None:
        body["name"] = name
    return client.post("/api/auth/register", json=body)


class TestRegisterName:
    def test_chosen_name_is_stored_and_returned(self, client):
        """S2: a typed name survives registration and reads back on /me."""
        resp = _register(client, "chosen@example.com", "  Daniel  ")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Daniel"

        cookie = resp.headers["set-cookie"]
        me = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert me.json()["name"] == "Daniel"

    def test_inner_whitespace_is_collapsed(self, client):
        """S2/D4: the same normalization the profile edit route applies."""
        resp = _register(client, "collapsed@example.com", "Daniel\n\n  de los Ríos")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Daniel de los Ríos"

    def test_blank_name_falls_back_to_null(self, client):
        """S2: leaving the field empty is the documented fallback, not a 422."""
        for index, blank in enumerate(["", "   ", "\n\t "]):
            resp = _register(client, f"blank{index}@example.com", blank)
            assert resp.status_code == 200
            assert resp.json()["name"] is None

    def test_missing_name_is_the_same_as_blank(self, client):
        """S2: an older client that never sends the key keeps working."""
        resp = _register(client, "omitted@example.com")
        assert resp.status_code == 200
        assert resp.json()["name"] is None

    def test_name_at_the_limit_is_accepted(self, client):
        """D4: the ceiling is measured after normalization, same as /me."""
        limit = "a" * MAX_DISPLAY_NAME_LENGTH
        resp = _register(client, "atlimit@example.com", limit)
        assert resp.status_code == 200
        assert resp.json()["name"] == limit

    def test_name_over_the_limit_is_refused_and_creates_no_user(self, client):
        """D4: a refused name must leave no account behind and no brake spent."""
        too_long = "a" * (MAX_DISPLAY_NAME_LENGTH + 1)
        resp = _register(client, "toolong@example.com", too_long)
        assert resp.status_code == 422
        assert resp.json()["detail"]

        # The same address can still register afterwards: the refusal wrote
        # nothing and did not consume one of the account's attempts.
        retry = _register(client, "toolong@example.com")
        assert retry.status_code == 200
        assert retry.json()["name"] is None
