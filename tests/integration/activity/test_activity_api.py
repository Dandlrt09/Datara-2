"""Integration tests for ``GET /api/activity`` (T6, personal activity log).

The log is computed live from existing tables: a short mixed feed plus a
calendar-month summary. Everything is owner-scoped; requests without a session
are rejected. Rows are seeded with raw SQL so timestamps are deterministic.
"""

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.activity import router as activity_router
from server.api.routers.auth import router as auth_router
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
from tests.test_helpers import apply_all_migrations

PASSWORD = "password123"


@pytest.fixture
def store():
    from server.api import store as api_store

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        await apply_all_migrations(s)

    asyncio.run(_setup())
    previous = api_store._store
    api_store._store = s
    yield s
    asyncio.run(s.close())
    api_store._store = previous


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(activity_router)
    return TestClient(app)


def _register(client, email):
    resp = client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.json()["id"], resp.headers["set-cookie"]


def _run(store, sql, params=()):
    async def go():
        await store.conn.execute(sql, params)
        await store.conn.commit()

    asyncio.run(go())


def _month_start():
    return datetime.now(timezone.utc).strftime("%Y-%m-01 00:00:00")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _seed_chat(store, user_id, chat_id, title, created_at):
    _run(
        store,
        "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
        (chat_id, user_id, title, created_at, created_at),
    )


def _seed_file(store, user_id, chat_id, name, rows, created_at):
    _run(
        store,
        "INSERT INTO files (user_id, chat_session, filename, storage_path, size_bytes, format, row_count, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (user_id, chat_id, name, f"/x/{name}", 10, "csv", rows, created_at),
    )


def _seed_message(store, user_id, chat_id, role, code, created_at):
    _run(
        store,
        "INSERT INTO messages (user_id, chat_session, role, content_text, code, created_at) VALUES (?,?,?,?,?,?)",
        (user_id, chat_id, role, "t", code, created_at),
    )


def _seed_archive(store, user_id, chat_id, name, created_at):
    _run(
        store,
        "INSERT INTO archives (user_id, name, chat_session, payload_json, created_at) VALUES (?,?,?,?,?)",
        (user_id, name, chat_id, "{}", created_at),
    )


def test_requires_authentication(client):
    assert client.get("/api/activity").status_code == 401


def test_empty_account_returns_zeros_and_no_events(client):
    _, cookie = _register(client, "a@example.com")
    body = client.get("/api/activity", headers={"cookie": cookie}).json()
    assert body["events"] == []
    assert body["month"] == {"chats": 0, "analyses": 0, "files": 0, "rows": 0, "archives": 0}


def test_month_summary_counts_only_this_month_and_owner(client, store):
    uid, cookie = _register(client, "a@example.com")
    other, _ = _register(client, "b@example.com")
    now = _now()
    _seed_chat(store, uid, "c1", "Ventas", now)
    _seed_chat(store, uid, "c0", "Viejo", "2020-01-05 10:00:00")
    _seed_chat(store, other, "o1", "Ajeno", now)
    _seed_file(store, uid, "c1", "a.csv", 100, now)
    _seed_file(store, uid, "c1", "b.csv", 50, now)
    _seed_file(store, uid, "c0", "old.csv", 999, "2020-01-05 10:00:00")
    _seed_file(store, other, "o1", "x.csv", 7, now)
    _seed_message(store, uid, "c1", "assistant", "print(1)", now)
    _seed_message(store, uid, "c1", "assistant", None, now)  # prose only: not an analysis
    _seed_message(store, uid, "c1", "user", "print(2)", now)  # user rows never count
    _seed_message(store, other, "o1", "assistant", "print(3)", now)
    _seed_archive(store, uid, "c1", "Informe", now)
    _seed_archive(store, other, "o1", "Ajeno", now)

    body = client.get("/api/activity", headers={"cookie": cookie}).json()
    assert body["month"] == {"chats": 1, "analyses": 1, "files": 2, "rows": 150, "archives": 1}


def test_feed_is_mixed_newest_first_capped_at_ten_and_owner_scoped(client, store):
    uid, cookie = _register(client, "a@example.com")
    other, _ = _register(client, "b@example.com")
    _seed_chat(store, uid, "c1", "Ventas", "2025-03-01 09:00:00")
    _seed_file(store, uid, "c1", "a.csv", 1, "2025-03-02 09:00:00")
    _seed_archive(store, uid, "c1", "Informe", "2025-03-03 09:00:00")
    _seed_chat(store, other, "o1", "Ajeno", "2025-03-04 09:00:00")

    events = client.get("/api/activity", headers={"cookie": cookie}).json()["events"]
    assert events == [
        {"kind": "archive", "title": "Informe", "at": "2025-03-03 09:00:00"},
        {"kind": "file", "title": "a.csv", "at": "2025-03-02 09:00:00"},
        {"kind": "chat", "title": "Ventas", "at": "2025-03-01 09:00:00"},
    ]

    for i in range(12):
        _seed_chat(store, uid, f"n{i}", f"Chat {i}", f"2025-04-{i + 1:02d} 09:00:00")
    events = client.get("/api/activity", headers={"cookie": cookie}).json()["events"]
    assert len(events) == 10
    assert events[0]["title"] == "Chat 11"
