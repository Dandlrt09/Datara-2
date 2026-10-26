"""Integration tests for the profile preferences (T7a).

Contract under test: GET /api/settings always returns *effective* preference
values (never null), PUT updates only the provided ones, and invalid values
are rejected with 422 before anything is stored.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.api.routers.settings import router as settings_router
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations

DEFAULTS = {
    "number_format": "es",
    "date_format": "relative",
    "currency_symbol": "US$",
    "open_behavior": "new_session",
}


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(auth_router)
    application.include_router(settings_router)

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
def auth_client(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


class TestPreferenceDefaults:
    def test_get_returns_effective_defaults_without_a_row(self, client, auth_client):
        """No settings row yet → GET still answers with the effective defaults."""
        data = client.get("/api/settings", headers={"Cookie": auth_client}).json()
        assert data["number_format"] == "es"
        assert data["date_format"] == "relative"
        assert data["currency_symbol"] == "US$"
        assert data["open_behavior"] == "new_session"

    def test_get_after_saving_only_api_key_keeps_defaults(self, client, auth_client):
        """Storing an unrelated setting must not blank the preferences."""
        client.put(
            "/api/settings",
            json={"api_key": "sk-abc", "default_model": "gpt-4o"},
            headers={"Cookie": auth_client},
        )
        data = client.get("/api/settings", headers={"Cookie": auth_client}).json()
        for field, expected in DEFAULTS.items():
            assert data[field] == expected, field


class TestPreferenceUpdate:
    def test_update_all_preferences(self, client, auth_client):
        resp = client.put(
            "/api/settings",
            json={
                "number_format": "intl",
                "date_format": "absolute",
                "currency_symbol": "$",
                "open_behavior": "last_session",
            },
            headers={"Cookie": auth_client},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["number_format"] == "intl"
        assert data["date_format"] == "absolute"
        assert data["currency_symbol"] == "$"
        assert data["open_behavior"] == "last_session"

        # Persisted, not just echoed.
        fetched = client.get("/api/settings", headers={"Cookie": auth_client}).json()
        assert fetched["number_format"] == "intl"
        assert fetched["date_format"] == "absolute"
        assert fetched["currency_symbol"] == "$"
        assert fetched["open_behavior"] == "last_session"

    def test_partial_update_keeps_other_preferences(self, client, auth_client):
        client.put(
            "/api/settings",
            json={
                "number_format": "intl",
                "date_format": "absolute",
                "currency_symbol": "USD",
                "open_behavior": "last_session",
            },
            headers={"Cookie": auth_client},
        )
        client.put(
            "/api/settings",
            json={"number_format": "es"},
            headers={"Cookie": auth_client},
        )
        data = client.get("/api/settings", headers={"Cookie": auth_client}).json()
        assert data["number_format"] == "es"
        assert data["date_format"] == "absolute"
        assert data["currency_symbol"] == "USD"
        assert data["open_behavior"] == "last_session"

    def test_currency_symbol_none_is_allowed(self, client, auth_client):
        """'none' is the legitimate "sin símbolo" choice, not an invalid one."""
        resp = client.put(
            "/api/settings",
            json={"currency_symbol": "none"},
            headers={"Cookie": auth_client},
        )
        assert resp.status_code == 200
        data = client.get("/api/settings", headers={"Cookie": auth_client}).json()
        assert data["currency_symbol"] == "none"

    def test_preferences_are_isolated_between_users(self, client):
        a = client.post(
            "/api/auth/register",
            json={"email": "a@example.com", "password": "password123"},
        ).headers["set-cookie"]
        b = client.post(
            "/api/auth/register",
            json={"email": "b@example.com", "password": "password123"},
        ).headers["set-cookie"]

        client.put(
            "/api/settings", json={"number_format": "intl"}, headers={"Cookie": a}
        )
        assert client.get("/api/settings", headers={"Cookie": a}).json()["number_format"] == "intl"
        assert client.get("/api/settings", headers={"Cookie": b}).json()["number_format"] == "es"


class TestPreferenceValidation:
    @pytest.mark.parametrize(
        "field, value",
        [
            ("number_format", "fr"),
            ("date_format", "whenever"),
            ("currency_symbol", "ARS"),
            ("open_behavior", "random"),
        ],
    )
    def test_rejects_unknown_values(self, client, auth_client, field, value):
        resp = client.put(
            "/api/settings",
            json={field: value},
            headers={"Cookie": auth_client},
        )
        assert resp.status_code == 422
        # Nothing stored: the field keeps its default.
        data = client.get("/api/settings", headers={"Cookie": auth_client}).json()
        assert data[field] == DEFAULTS[field]

    def test_rejects_unknown_value_without_touching_the_others(self, client, auth_client):
        client.put(
            "/api/settings", json={"date_format": "absolute"}, headers={"Cookie": auth_client}
        )
        resp = client.put(
            "/api/settings", json={"number_format": "fr"}, headers={"Cookie": auth_client}
        )
        assert resp.status_code == 422
        data = client.get("/api/settings", headers={"Cookie": auth_client}).json()
        assert data["number_format"] == "es"
        assert data["date_format"] == "absolute"

    def test_preferences_require_auth(self, client):
        assert client.get("/api/settings").status_code == 401
        assert (
            client.put("/api/settings", json={"number_format": "intl"}).status_code == 401
        )
