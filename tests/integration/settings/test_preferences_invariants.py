"""Regression invariants for the profile preference write path (T7a / D4).

A rejected write must never touch storage: the settings endpoint validates the
request body before it reaches the store, so an invalid preference comes back
as 422 and the ``user_settings`` row stays byte-identical. A request that mixes
one valid and one invalid preference is rejected as a unit, so the valid half
is not stored either. Omitted fields keep their stored value because the store
upsert uses COALESCE.

The stored row is hashed (SHA-256 over its raw SQL values) before and after
each rejected request; any accidental write, including a bumped ``updated_at``,
changes the digest. The database is a real file under pytest's ``tmp_path`` so
the row can be read back from a separate connection.
"""

import asyncio
import hashlib
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import store as api_store
from server.api.routers.auth import router as auth_router
from server.api.routers.settings import router as settings_router
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
from tests.test_helpers import apply_all_migrations

# Values the API must reject on write: unknown labels for each preference plus
# a wrong type and an empty string.
INVALID_VALUES = [
    ("number_format", "fr"),
    ("date_format", "whenever"),
    ("currency_symbol", "ARS"),
    ("open_behavior", "random"),
    ("number_format", 7),
    ("currency_symbol", ""),
]


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "settings.db")


@pytest.fixture
def app(db_path):
    application = FastAPI()
    application.include_router(auth_router)
    application.include_router(settings_router)

    s = SqliteStore(db_path=db_path)

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
        json={"terms_version": TERMS_VERSION, "email": "invariants@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


def _row_fingerprint(db_path: str) -> str:
    """SHA-256 over the raw ``user_settings`` rows; any write changes it."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM user_settings ORDER BY user_id"
        ).fetchall()
    finally:
        conn.close()
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def _seed_valid_preferences(client, cookie) -> None:
    resp = client.put(
        "/api/settings",
        json={
            "number_format": "intl",
            "date_format": "absolute",
            "currency_symbol": "USD",
            "open_behavior": "last_session",
        },
        headers={"Cookie": cookie},
    )
    assert resp.status_code == 200, resp.text


class TestRejectedWritesAreAtomic:
    @pytest.mark.parametrize("field, bad", INVALID_VALUES)
    def test_invalid_value_is_rejected_and_row_unchanged(
        self, client, auth_client, db_path, field, bad
    ):
        _seed_valid_preferences(client, auth_client)
        before = _row_fingerprint(db_path)

        resp = client.put(
            "/api/settings",
            json={field: bad},
            headers={"Cookie": auth_client},
        )

        assert resp.status_code == 422, (field, bad, resp.status_code, resp.text)
        assert _row_fingerprint(db_path) == before, (field, bad)

    def test_mixed_valid_and_invalid_request_stores_nothing(
        self, client, auth_client, db_path
    ):
        _seed_valid_preferences(client, auth_client)
        before = _row_fingerprint(db_path)

        resp = client.put(
            "/api/settings",
            json={"date_format": "relative", "number_format": "fr"},
            headers={"Cookie": auth_client},
        )

        assert resp.status_code == 422, resp.text
        assert _row_fingerprint(db_path) == before

        # The valid half of the rejected request did not leak through either.
        data = client.get("/api/settings", headers={"Cookie": auth_client}).json()
        assert data["date_format"] == "absolute"


class TestOmittedFields:
    def test_omitted_field_keeps_its_stored_value(self, client, auth_client):
        _seed_valid_preferences(client, auth_client)

        resp = client.put(
            "/api/settings",
            json={"number_format": "es"},
            headers={"Cookie": auth_client},
        )

        assert resp.status_code == 200, resp.text
        data = client.get("/api/settings", headers={"Cookie": auth_client}).json()
        assert data["number_format"] == "es"
        assert data["date_format"] == "absolute"
        assert data["currency_symbol"] == "USD"
        assert data["open_behavior"] == "last_session"
