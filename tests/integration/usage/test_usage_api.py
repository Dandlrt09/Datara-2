"""Integration tests for ``GET /api/usage`` (T4, monthly consumption panel).

Read-only and owner-scoped: the endpoint reports, month by month, the stored
tokens, the cost (never a partial sum: a single unpriced message makes the
month "cost unknown") and the number of analyses/archives. Rows are seeded with
raw SQL so timestamps and costs are deterministic.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers.auth import router as auth_router
from server.api.routers.usage import router as usage_router
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
    app.include_router(usage_router)
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


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _current_month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _month_ts(offset: int, day: int = 5) -> str:
    """Timestamp for the first day of the month ``offset`` months from now.

    Computed relative to the current UTC month so the suite does not rot: the
    current month must always be present in the response, so a fixed literal
    would break every month after it was written.
    """
    now = datetime.now(timezone.utc)
    month_index = now.year * 12 + (now.month - 1) + offset
    year, month = divmod(month_index, 12)
    month += 1
    return f"{year:04d}-{month:02d}-{day:02d} 10:00:00"


def _ensure_chat(store, user_id):
    _run(
        store,
        "INSERT OR IGNORE INTO chat_sessions (id, user_id, title) VALUES (?,?,?)",
        (f"c{user_id}", user_id, "seed"),
    )


def _seed_message(
    store,
    user_id,
    role,
    created_at,
    code=None,
    tokens_in=0,
    tokens_out=0,
    cost_usd=None,
):
    _ensure_chat(store, user_id)
    _run(
        store,
        "INSERT INTO messages"
        " (user_id, chat_session, role, content_text, code, tokens_in, tokens_out, cost_usd, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (
            user_id,
            f"c{user_id}",
            role,
            "t",
            code,
            tokens_in,
            tokens_out,
            cost_usd,
            created_at,
        ),
    )


def _seed_archive(store, user_id, name, created_at):
    _ensure_chat(store, user_id)
    _run(
        store,
        "INSERT INTO archives (user_id, name, chat_session, payload_json, created_at) VALUES (?,?,?,?,?)",
        (user_id, name, f"c{user_id}", "{}", created_at),
    )


def test_requires_authentication(client):
    assert client.get("/api/usage").status_code == 401


def test_empty_account_returns_only_the_current_month_at_zero(client):
    _, cookie = _register(client, "a@example.com")
    body = client.get("/api/usage", headers={"cookie": cookie}).json()
    assert body == {
        "months": [
            {
                "month": _current_month(),
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "cost_known": True,
                "analyses": 0,
                "archives": 0,
            }
        ]
    }


def test_month_metrics_count_tokens_analyses_and_archives(client, store):
    uid, cookie = _register(client, "a@example.com")
    at = _month_ts(0)
    _seed_message(store, uid, "assistant", at, code="print(1)", tokens_in=100, tokens_out=20, cost_usd=0.5)
    _seed_message(store, uid, "assistant", at, code=None, tokens_in=10, tokens_out=5, cost_usd=0.1)
    _seed_message(store, uid, "user", at, code="print(2)", tokens_in=7, tokens_out=0, cost_usd=0.0)
    _seed_archive(store, uid, "Informe", at)

    month = client.get("/api/usage", headers={"cookie": cookie}).json()["months"][0]
    assert month == {
        "month": _current_month(),
        "tokens_in": 117,
        "tokens_out": 25,
        "cost_usd": 0.6,
        "cost_known": True,
        "analyses": 1,
        "archives": 1,
    }


def test_cost_is_none_propagating_when_any_message_has_no_price(client, store):
    uid, cookie = _register(client, "a@example.com")
    # Priced month: the sum is reported.
    _seed_message(store, uid, "assistant", _month_ts(-1), tokens_in=10, cost_usd=1.5)
    _seed_message(store, uid, "assistant", _month_ts(-1), tokens_in=10, cost_usd=2.5)
    # Unpriced month: one message without a price poisons the total.
    _seed_message(store, uid, "assistant", _month_ts(-2), tokens_in=10, cost_usd=3.0)
    _seed_message(store, uid, "assistant", _month_ts(-2), tokens_in=10, cost_usd=None)

    months = client.get("/api/usage", headers={"cookie": cookie}).json()["months"]
    by_month = {m["month"]: m for m in months}
    assert by_month[_month_ts(-1)[:7]]["cost_known"] is True
    assert by_month[_month_ts(-1)[:7]]["cost_usd"] == 4.0
    assert by_month[_month_ts(-2)[:7]]["cost_known"] is False
    assert by_month[_month_ts(-2)[:7]]["cost_usd"] is None


def test_unpriced_message_without_tokens_does_not_poison_the_total(client, store):
    uid, cookie = _register(client, "a@example.com")
    at = _month_ts(-1)
    _seed_message(store, uid, "assistant", at, tokens_in=10, cost_usd=2.0)
    # cost_usd NULL but zero tokens: cannot have a price, and does not hide the
    # known total (D3 says "with tokens > 0").
    _seed_message(store, uid, "assistant", at, tokens_in=0, tokens_out=0, cost_usd=None)

    by_month = {
        m["month"]: m
        for m in client.get("/api/usage", headers={"cookie": cookie}).json()["months"]
    }
    assert by_month[_month_ts(-1)[:7]]["cost_known"] is True
    assert by_month[_month_ts(-1)[:7]]["cost_usd"] == 2.0


def test_months_are_owner_scoped_with_two_users(client, store):
    uid, cookie = _register(client, "a@example.com")
    other, _ = _register(client, "b@example.com")
    at = _month_ts(-1)
    _seed_message(store, uid, "assistant", at, code="print(1)", tokens_in=100, tokens_out=10, cost_usd=1.0)
    _seed_archive(store, uid, "Propio", at)
    _seed_message(store, other, "assistant", at, code="print(2)", tokens_in=999, tokens_out=999, cost_usd=9.0)
    _seed_archive(store, other, "Ajeno", at)

    month = {
        m["month"]: m
        for m in client.get("/api/usage", headers={"cookie": cookie}).json()["months"]
    }[_month_ts(-1)[:7]]
    assert month == {
        "month": _month_ts(-1)[:7],
        "tokens_in": 100,
        "tokens_out": 10,
        "cost_usd": 1.0,
        "cost_known": True,
        "analyses": 1,
        "archives": 1,
    }


def test_series_is_newest_first_capped_at_twelve_months(client, store):
    uid, cookie = _register(client, "a@example.com")
    # 13 earlier months with data + the current month = 14 candidates.
    for offset in range(-13, 0):
        _seed_message(store, uid, "assistant", _month_ts(offset), tokens_in=1, cost_usd=0.0)

    months = client.get("/api/usage", headers={"cookie": cookie}).json()["months"]
    assert len(months) == 12
    assert months[0]["month"] == _current_month()
    labels = [m["month"] for m in months]
    assert labels == sorted(labels, reverse=True)
    # Both oldest data months (offset -13 and -12) are dropped by the 12 cap.
    assert _month_ts(-13)[:7] not in labels
    assert _month_ts(-12)[:7] not in labels


def test_current_month_with_unpriced_tokens_is_unknown_not_zero(client, store):
    # D3 boundary: the always-present current month must not be reported as a
    # known 0.0 (or a fake number) when it has an unpriced message.
    uid, cookie = _register(client, "cur-poison@example.com")
    _seed_message(store, uid, "assistant", _month_ts(0), tokens_in=5, cost_usd=None)

    first = client.get("/api/usage", headers={"cookie": cookie}).json()["months"][0]
    assert first["month"] == _current_month()
    assert first["tokens_in"] == 5
    assert first["cost_known"] is False
    assert first["cost_usd"] is None


def test_archive_only_month_appears_with_zero_tokens(client, store):
    # D1/D2: a month with saved analyses but no messages still shows up.
    uid, cookie = _register(client, "archonly@example.com")
    _seed_archive(store, uid, "Solo", _month_ts(-3))

    by_month = {
        m["month"]: m
        for m in client.get("/api/usage", headers={"cookie": cookie}).json()["months"]
    }
    assert by_month[_month_ts(-3)[:7]] == {
        "month": _month_ts(-3)[:7],
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "cost_known": True,
        "analyses": 0,
        "archives": 1,
    }
