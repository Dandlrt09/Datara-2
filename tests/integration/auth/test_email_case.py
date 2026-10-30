"""Register and login treat the email as case- and space-insensitive (S4/S5).

An account created as ``Alice@Example.COM`` is the same account as
``alice@example.com``: one login identity, not two.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
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


class TestRegisterNormalizes:
    def test_register_stores_and_returns_lowercased_email(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"terms_version": TERMS_VERSION, "email": "  Alice@Example.COM  ", "password": "password123"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"

    def test_duplicate_email_different_case_is_a_conflict(self, client):
        client.post(
            "/api/auth/register",
            json={"terms_version": TERMS_VERSION, "email": "CaseDup@example.com", "password": "password123"},
        )
        resp = client.post(
            "/api/auth/register",
            json={"terms_version": TERMS_VERSION, "email": "casedup@example.com", "password": "password456"},
        )
        assert resp.status_code == 409


class TestLoginIsCaseInsensitive:
    def test_login_with_different_case_succeeds(self, client):
        client.post(
            "/api/auth/register",
            json={"terms_version": TERMS_VERSION, "email": "bob@example.com", "password": "password123"},
        )
        resp = client.post(
            "/api/auth/login",
            json={"email": "BOB@EXAMPLE.COM", "password": "password123"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "bob@example.com"

    def test_login_with_surrounding_whitespace_succeeds(self, client):
        client.post(
            "/api/auth/register",
            json={"terms_version": TERMS_VERSION, "email": "dave@example.com", "password": "password123"},
        )
        resp = client.post(
            "/api/auth/login",
            json={"email": "  dave@example.com  ", "password": "password123"},
        )
        assert resp.status_code == 200
