"""Terms of use acceptance at registration (terms-of-use S1/S6/D5).

A checkbox nobody records is decoration. These probes pin the three promises the
server has to keep: an account cannot exist without the terms, the version
recorded is the one in force, and a refused request leaves nothing behind.
"""

import asyncio
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.rate_limit import MAX_ATTEMPTS
from server.api.routers.auth import router as auth_router
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
from tests.test_helpers import apply_all_migrations

OMIT = object()  # sentinel: leave the key out of the body entirely


@pytest.fixture
def store():
    store = SqliteStore(db_path=":memory:")
    asyncio.run(store.connect())
    asyncio.run(apply_all_migrations(store))
    api_store._store = store
    yield store
    asyncio.run(store.close())
    api_store._store = None


@pytest.fixture
def client(store):
    application = FastAPI()
    application.include_router(auth_router)
    return TestClient(application)


def _register(client, email: str, terms_version=TERMS_VERSION):
    body = {"email": email, "password": "password123"}
    if terms_version is not OMIT:
        body["terms_version"] = terms_version
    return client.post("/api/auth/register", json=body)


def _stored_acceptance(store, email: str):
    rows = asyncio.run(
        store.conn.execute_fetchall(
            "SELECT terms_version, terms_accepted_at FROM users WHERE email = ?",
            (email,),
        )
    )
    return dict(rows[0]) if rows else None


class TestTermsAcceptance:
    def test_registration_without_the_terms_key_is_refused(self, client, store):
        """S1: no acceptance, no account."""
        resp = _register(client, "no-terms@example.com", terms_version=OMIT)
        assert resp.status_code == 422
        assert resp.json()["detail"]
        assert _stored_acceptance(store, "no-terms@example.com") is None

    def test_a_stale_terms_version_is_refused_with_its_own_message(self, client):
        """D5: accepting an older text is not accepting the text in force.

        Both details are asserted as literals on purpose: the signup form
        matches the stale one to tell the person to reload (the text changed
        under an open tab), so renaming it has to be a decision, not a whisper.
        """
        stale = _register(client, "stale@example.com", terms_version="0.9")
        missing = _register(client, "missing@example.com", terms_version=OMIT)
        assert stale.status_code == 422
        assert stale.json()["detail"] == "Terms of use version has changed"
        assert missing.json()["detail"] == "Terms of use must be accepted"

    def test_acceptance_records_the_version_in_force_and_the_date(
        self, client, store
    ):
        """S6: the record says which text and when, not merely that a box was ticked."""
        resp = _register(client, "accepted@example.com")
        assert resp.status_code == 200
        record = _stored_acceptance(store, "accepted@example.com")
        assert record["terms_version"] == TERMS_VERSION
        # Same shape as users.created_at, so the two dates can be read together.
        datetime.strptime(record["terms_accepted_at"], "%Y-%m-%d %H:%M:%S")

    def test_an_account_created_before_the_terms_has_no_acceptance(self, store):
        """S6: NULL is history, not an error; the old write path stays valid."""
        asyncio.run(store.create_user("legacy@example.com", "hash"))
        assert _stored_acceptance(store, "legacy@example.com") == {
            "terms_version": None,
            "terms_accepted_at": None,
        }

    def test_a_refused_registration_does_not_spend_an_attempt(self, client):
        """S1: the terms check runs with the other body checks, before the brake.

        More refusals than the brake allows and then one honest registration: it
        only goes through if the refused requests were never counted.
        """
        for _ in range(MAX_ATTEMPTS + 1):
            refused = _register(client, "braked@example.com", terms_version=OMIT)
            assert refused.status_code == 422
        assert _register(client, "braked@example.com").status_code == 200
