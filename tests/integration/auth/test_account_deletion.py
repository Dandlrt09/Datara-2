"""Tests for the account-deletion grace period at the store level.

Covers the deferred-deletion contract: requesting schedules a purge for seven
days out, cancelling clears it, the due-deletion query returns only expired
deadlines, purging a due user deletes the row (children cascade), and every
"nothing to do" case leaves stored data untouched.

Uses a fresh in-memory SQLite store per test, built from the real migrations.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.api.routers.files as files_router
import server.services.session_cleanup as session_cleanup
from server.api.routers.auth import router as auth_router
from server.services.session_cleanup import purge_due_deletions
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def store():
    """Fresh in-memory store wired into ``server.api.store._store``."""
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
    application = FastAPI()
    application.include_router(auth_router)
    return TestClient(application)


PASSWORD = "password123"


def _register(client, email="user@example.com"):
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


def _login(client, email="user@example.com"):
    resp = client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


def _make_user(store, email="user@example.com"):
    return asyncio.run(store.create_user(email, "hash"))


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


class TestRequestDeletion:
    def test_request_schedules_seven_days_out(self, store):
        user = _make_user(store)
        assert asyncio.run(store.get_user_by_id(user["id"]))["pending_deletion_at"] is None

        changed = asyncio.run(store.request_user_deletion(user["id"]))
        assert changed is True

        row = asyncio.run(store.get_user_by_id(user["id"]))
        deadline = _parse(row["pending_deletion_at"])
        expected = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
        assert abs((deadline - expected).total_seconds()) < 120

    def test_request_unknown_user_changes_nothing(self, store):
        assert asyncio.run(store.request_user_deletion(999)) is False
        assert asyncio.run(store.list_due_deletion_user_ids()) == []


class TestCancelDeletion:
    def test_cancel_clears_the_deadline(self, store):
        user = _make_user(store)
        asyncio.run(store.request_user_deletion(user["id"]))

        assert asyncio.run(store.cancel_user_deletion(user["id"])) is True
        assert asyncio.run(store.get_user_by_id(user["id"]))["pending_deletion_at"] is None

    def test_cancel_unknown_user_changes_nothing(self, store):
        assert asyncio.run(store.cancel_user_deletion(999)) is False


class TestSessions:
    def test_delete_all_sessions_only_touches_the_user(self, store):
        alice = _make_user(store, "alice@example.com")
        bob = _make_user(store, "bob@example.com")
        asyncio.run(store.create_auth_session(alice["id"], "hash-a1"))
        asyncio.run(store.create_auth_session(alice["id"], "hash-a2"))
        asyncio.run(store.create_auth_session(bob["id"], "hash-b1"))

        removed = asyncio.run(store.delete_all_auth_sessions(alice["id"]))
        assert removed == 2
        assert asyncio.run(store.get_auth_session_by_token_hash("hash-a1")) is None
        assert asyncio.run(store.get_auth_session_by_token_hash("hash-b1")) is not None


class TestDueDeletions:
    def test_only_expired_deadlines_are_due(self, store):
        due = _make_user(store, "due@example.com")
        future = _make_user(store, "future@example.com")
        none = _make_user(store, "none@example.com")

        asyncio.run(store.request_user_deletion(due["id"]))
        asyncio.run(store.request_user_deletion(future["id"]))
        # Move one deadline into the past and the other into the future.
        asyncio.run(
            store.conn.execute(
                "UPDATE users SET pending_deletion_at = datetime('now', '-1 hour') "
                "WHERE id = ?",
                (due["id"],),
            )
        )
        asyncio.run(
            store.conn.execute(
                "UPDATE users SET pending_deletion_at = datetime('now', '+1 hour') "
                "WHERE id = ?",
                (future["id"],),
            )
        )
        asyncio.run(store.conn.commit())

        assert asyncio.run(store.list_due_deletion_user_ids()) == [due["id"]]
        # A cancellable (future) account is not touched by the due query.
        assert asyncio.run(store.get_user_by_id(future["id"])) is not None
        assert asyncio.run(store.get_user_by_id(none["id"])) is not None


class TestPurgeUser:
    def test_purge_deletes_the_user_and_cascades(self, store):
        user = _make_user(store)
        asyncio.run(
            store.conn.execute(
                "INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)",
                ("chat-1", user["id"], "Hello"),
            )
        )
        asyncio.run(
            store.conn.execute(
                "INSERT INTO messages (user_id, chat_session, role, content_text) "
                "VALUES (?, ?, ?, ?)",
                (user["id"], "chat-1", "user", "hi"),
            )
        )
        asyncio.run(
            store.conn.execute(
                "INSERT INTO user_settings (user_id, api_key_enc) VALUES (?, ?)",
                (user["id"], "enc"),
            )
        )
        asyncio.run(store.conn.commit())

        assert asyncio.run(store.purge_user(user["id"])) is True
        assert asyncio.run(store.get_user_by_id(user["id"])) is None

        async def _counts():
            out = {}
            for table in ("chat_sessions", "messages", "user_settings"):
                rows = await store.conn.execute_fetchall(
                    f"SELECT COUNT(*) AS n FROM {table}"
                )
                out[table] = rows[0]["n"]
            return out

        assert asyncio.run(_counts()) == {
            "chat_sessions": 0,
            "messages": 0,
            "user_settings": 0,
        }

    def test_purge_unknown_user_changes_nothing(self, store):
        assert asyncio.run(store.purge_user(999)) is False


_DELETE_BODY = {"confirmation": "ELIMINAR", "current_password": PASSWORD}


class TestDeleteAccountEndpoint:
    def test_requires_authentication(self, client):
        resp = client.post("/api/auth/account/delete", json=_DELETE_BODY)
        assert resp.status_code == 401

    def test_wrong_password_is_401_and_changes_nothing(self, client, store):
        cookie = _register(client)
        resp = client.post(
            "/api/auth/account/delete",
            json={"confirmation": "ELIMINAR", "current_password": "wrong-password"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 401
        user = asyncio.run(store.get_user_by_email("user@example.com"))
        assert user["pending_deletion_at"] is None
        # A rejected request keeps the caller's session alive.
        assert client.get("/api/auth/me", headers={"Cookie": cookie}).status_code == 200

    def test_wrong_confirmation_word_is_422_and_changes_nothing(self, client, store):
        cookie = _register(client)
        resp = client.post(
            "/api/auth/account/delete",
            json={"confirmation": "eliminar", "current_password": PASSWORD},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 422
        user = asyncio.run(store.get_user_by_email("user@example.com"))
        assert user["pending_deletion_at"] is None
        assert client.get("/api/auth/me", headers={"Cookie": cookie}).status_code == 200

    def test_password_is_checked_before_the_confirmation_word(self, client):
        cookie = _register(client)
        # Both wrong: the password gate owns the answer (S9/D4), not the word.
        resp = client.post(
            "/api/auth/account/delete",
            json={"confirmation": "nope", "current_password": "wrong"},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 401

    def test_success_schedules_purge_and_closes_every_session(self, client, store):
        cookie_a = _register(client)
        cookie_b = _login(client)

        resp = client.post(
            "/api/auth/account/delete", json=_DELETE_BODY, headers={"Cookie": cookie_a}
        )
        assert resp.status_code == 204

        user = asyncio.run(store.get_user_by_email("user@example.com"))
        deadline = _parse(user["pending_deletion_at"])
        expected = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
        assert abs((deadline - expected).total_seconds()) < 120

        # Both sessions are dead, but the account and its data still exist: the
        # grace period is not a deletion (S3).
        assert client.get("/api/auth/me", headers={"Cookie": cookie_a}).status_code == 401
        assert client.get("/api/auth/me", headers={"Cookie": cookie_b}).status_code == 401
        assert asyncio.run(store.get_user_by_id(user["id"])) is not None

    def test_success_clears_the_session_cookie(self, client):
        cookie = _register(client)
        resp = client.post(
            "/api/auth/account/delete", json=_DELETE_BODY, headers={"Cookie": cookie}
        )
        assert resp.status_code == 204
        set_cookie = resp.headers.get("set-cookie", "")
        assert "session_id=" in set_cookie
        assert "Max-Age=0" in set_cookie

    def test_login_during_grace_succeeds_and_reports_the_deadline(self, client):
        cookie = _register(client)
        client.post(
            "/api/auth/account/delete", json=_DELETE_BODY, headers={"Cookie": cookie}
        )

        resp = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": PASSWORD},
        )
        assert resp.status_code == 200
        assert resp.json()["pending_deletion_at"] is not None

    def test_me_reports_no_deletion_normally(self, client):
        cookie = _register(client)
        resp = client.get("/api/auth/me", headers={"Cookie": cookie})
        assert resp.json()["pending_deletion_at"] is None


class TestCancelDeletionEndpoint:
    def test_requires_authentication(self, client):
        assert client.post("/api/auth/account/cancel-deletion").status_code == 401

    def test_cancel_clears_the_deadline_and_keeps_the_account(self, client, store):
        cookie = _register(client)
        client.post(
            "/api/auth/account/delete", json=_DELETE_BODY, headers={"Cookie": cookie}
        )

        # Requesting deletion killed every session, so log in again to cancel.
        cookie2 = _login(client)
        resp = client.post(
            "/api/auth/account/cancel-deletion", headers={"Cookie": cookie2}
        )
        assert resp.status_code == 204

        user = asyncio.run(store.get_user_by_email("user@example.com"))
        assert user["pending_deletion_at"] is None
        me = client.get("/api/auth/me", headers={"Cookie": cookie2})
        assert me.json()["pending_deletion_at"] is None

    def test_cancel_without_a_schedule_is_idempotent(self, client):
        cookie = _register(client)
        resp = client.post(
            "/api/auth/account/cancel-deletion", headers={"Cookie": cookie}
        )
        assert resp.status_code == 204


def _expire_now(store, user_id):
    """Move a user's deletion deadline into the past (already due)."""
    asyncio.run(
        store.conn.execute(
            "UPDATE users SET pending_deletion_at = datetime('now', '-1 hour') "
            "WHERE id = ?",
            (user_id,),
        )
    )
    asyncio.run(store.conn.commit())


def _seed_uploads(root, user_id):
    """Create ``root/<user_id>/<session>/f.csv`` and return its path."""
    d = root / str(user_id) / "session-1"
    d.mkdir(parents=True)
    (d / "f.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    return d


class TestRemoveUserUploads:
    def test_removes_only_the_target_user_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")
        root = files_router.UPLOADS_DIR
        _seed_uploads(root, 1)
        _seed_uploads(root, 2)

        files_router.remove_user_uploads(1)

        assert not (root / "1").exists()
        assert (root / "2" / "session-1" / "f.csv").exists()

    def test_missing_directory_never_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")
        files_router.remove_user_uploads(42)  # must be a silent no-op


class TestPurgeDueDeletions:
    def test_purges_only_due_accounts_and_their_uploads(
        self, store, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")
        due = _make_user(store, "due@example.com")
        future = _make_user(store, "future@example.com")
        asyncio.run(store.request_user_deletion(due["id"]))
        asyncio.run(store.request_user_deletion(future["id"]))
        _expire_now(store, due["id"])
        _seed_uploads(files_router.UPLOADS_DIR, due["id"])
        _seed_uploads(files_router.UPLOADS_DIR, future["id"])

        purged = asyncio.run(purge_due_deletions(store))

        assert purged == 1
        assert asyncio.run(store.get_user_by_id(due["id"])) is None
        assert asyncio.run(store.get_user_by_id(future["id"])) is not None
        assert not (files_router.UPLOADS_DIR / str(due["id"])).exists()
        # A still-cancellable account keeps both row and bytes (S3).
        assert (files_router.UPLOADS_DIR / str(future["id"])).exists()

    def test_one_failure_does_not_stop_the_others(self, store, tmp_path, monkeypatch):
        monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")
        first = _make_user(store, "a@example.com")
        second = _make_user(store, "b@example.com")
        _expire_now(store, first["id"])
        _expire_now(store, second["id"])
        _seed_uploads(files_router.UPLOADS_DIR, first["id"])

        original = store.purge_user

        async def flaky(user_id):
            if user_id == first["id"]:
                raise RuntimeError("simulated failure")
            return await original(user_id)

        monkeypatch.setattr(store, "purge_user", flaky)

        purged = asyncio.run(purge_due_deletions(store))

        assert purged == 1
        # The failed account survives with its bytes; the healthy one is gone.
        assert asyncio.run(store.get_user_by_id(first["id"])) is not None
        assert (files_router.UPLOADS_DIR / str(first["id"])).exists()
        assert asyncio.run(store.get_user_by_id(second["id"])) is None

    def test_without_due_accounts_is_a_noop(self, store):
        _make_user(store)
        assert asyncio.run(purge_due_deletions(store)) == 0

    def test_deadline_exactly_now_is_due(self, store):
        """The due comparison is inclusive: a deadline equal to now purges."""
        user = _make_user(store)
        asyncio.run(
            store.conn.execute(
                "UPDATE users SET pending_deletion_at = datetime('now') "
                "WHERE id = ?",
                (user["id"],),
            )
        )
        asyncio.run(store.conn.commit())

        assert asyncio.run(store.list_due_deletion_user_ids()) == [user["id"]]

    def test_requesting_again_pushes_the_deadline_out(self, store):
        """A second request reschedules the purge further into the future (D1)."""
        user = _make_user(store)
        asyncio.run(store.request_user_deletion(user["id"]))
        first = asyncio.run(store.get_user_by_id(user["id"]))["pending_deletion_at"]

        # datetime('now') has one-second resolution; wait past it.
        time.sleep(1.2)
        asyncio.run(store.request_user_deletion(user["id"]))
        second = asyncio.run(store.get_user_by_id(user["id"]))["pending_deletion_at"]

        assert second > first


def test_hourly_sweep_survives_a_failing_purge(monkeypatch):
    """S10: a purge that raises must never kill the hourly loop.

    The loop calls the sweep first, so a purge explosion is isolated to its own
    try/except and the next sweep still runs.
    """

    async def _run():
        s = SqliteStore(db_path=":memory:")
        await s.connect()
        await apply_all_migrations(s)
        calls = {"sweeps": 0}

        async def fake_sweep(_store):
            calls["sweeps"] += 1
            return 0

        async def exploding_purge(_store):
            raise RuntimeError("purge exploded")

        monkeypatch.setattr(session_cleanup, "_SWEEP_INTERVAL_SECONDS", 0.05)
        monkeypatch.setattr(session_cleanup, "sweep_expired", fake_sweep)
        monkeypatch.setattr(session_cleanup, "purge_due_deletions", exploding_purge)

        task = await session_cleanup.start_background_sweep(s)
        try:
            await asyncio.sleep(0.3)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await s.close()

        assert calls["sweeps"] >= 2

    asyncio.run(_run())
