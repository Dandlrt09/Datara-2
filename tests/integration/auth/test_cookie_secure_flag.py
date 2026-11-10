"""F9/S3: the session cookie carries ``Secure`` only when served over HTTPS.

The desktop build runs on ``http://localhost``, where a ``Secure`` cookie is
never sent -- marking it always would break desktop login. The deployment
publishes its scheme in ``DATARA_APP_URL`` (the desktop sets ``http://...``,
a hosted deployment sets ``https://...``), which is the signal used here.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.api.routers.sessions import router as sessions_router
from server.services.sqlite_store import SqliteStore
from tests.integration.auth.conftest import register_verified
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(auth_router)
    application.include_router(sessions_router)

    store = SqliteStore(db_path=":memory:")

    async def _setup():
        await store.connect()
        await apply_all_migrations(store)

    asyncio.run(_setup())
    api_store._store = store

    yield application

    asyncio.run(store.close())
    api_store._store = None


@pytest.fixture
def client(app):
    return TestClient(app)


def test_http_deployment_has_no_secure_flag(client, monkeypatch):
    monkeypatch.delenv("DATARA_APP_URL", raising=False)
    response = register_verified(client, "http@datara.local")
    assert "Secure" not in response.headers["set-cookie"]


def test_https_deployment_has_secure_flag(client, monkeypatch):
    monkeypatch.setenv("DATARA_APP_URL", "https://datara.example")
    response = register_verified(client, "https@datara.local")
    assert "Secure" in response.headers["set-cookie"]


def test_logout_expire_cookie_is_secure_over_https(client, monkeypatch):
    monkeypatch.setenv("DATARA_APP_URL", "https://datara.example")
    login = register_verified(client, "logout@datara.local")
    cookie = login.headers["set-cookie"]
    response = client.post("/api/auth/logout", headers={"Cookie": cookie.split(";")[0]})
    assert response.status_code == 204
    assert "Secure" in response.headers["set-cookie"]


def test_logout_expire_cookie_is_plain_over_http(client, monkeypatch):
    monkeypatch.delenv("DATARA_APP_URL", raising=False)
    login = register_verified(client, "logout2@datara.local")
    cookie = login.headers["set-cookie"]
    response = client.post("/api/auth/logout", headers={"Cookie": cookie.split(";")[0]})
    assert response.status_code == 204
    assert "Secure" not in response.headers["set-cookie"]
