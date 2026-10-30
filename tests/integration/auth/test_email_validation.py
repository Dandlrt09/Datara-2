"""Register rejects a malformed email with 422 (S5).

A valid address keeps working; the shape check only stops garbage that would
otherwise become an account nobody can log into.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(auth_router)

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        await apply_all_migrations(s)

    asyncio.run(_setup())
    api_store._store = s

    yield application

    asyncio.run(s.close())
    api_store._store = None


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def store():
    return api_store._store


class TestRegisterValidatesEmailShape:
    @pytest.mark.parametrize(
        "email",
        ["notanemail", "a@", "@example.com", "a@b", "a b@example.com", "a@.com"],
    )
    def test_malformed_email_is_rejected(self, client, email):
        resp = client.post(
            "/api/auth/register", json={"email": email, "password": "password123"}
        )
        assert resp.status_code == 422

    def test_rejection_creates_no_account(self, client, store):
        client.post(
            "/api/auth/register", json={"email": "notanemail", "password": "password123"}
        )

        async def _count():
            rows = await store.conn.execute_fetchall("SELECT COUNT(*) FROM users")
            return rows[0][0]

        assert asyncio.run(_count()) == 0

    def test_well_formed_email_still_registers(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "user+tag@example.com", "password": "password123"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "user+tag@example.com"
