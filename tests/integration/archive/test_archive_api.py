"""Integration tests for the archive router (create, list, get).

Uses FastAPI TestClient with a fresh in-memory SQLite store per test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers import archive as archive_router
from server.api.routers import auth as auth_router
from server.api.routers import sessions as sessions_router
from server.services.sqlite_store import SqliteStore

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"


@pytest.fixture
def app():
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(archive_router.router)

    import asyncio

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        # Apply ALL migrations in sorted order so the tests exercise the real
        # schema (0005 makes archives survive session deletion).
        for sql_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            await s.conn.executescript(sql_path.read_text(encoding="utf-8"))
        await s.conn.commit()

    asyncio.run(_setup())
    api_store._store = s

    yield application

    asyncio.run(s.close())
    api_store._store = None


@pytest.fixture
def store(app):
    """The live SqliteStore backing the test app (for direct seeding)."""
    from server.api import store as api_store  # noqa: PLC0415

    return api_store._store


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_cookie(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "archive@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


@pytest.fixture
def other_cookie(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "other@archive.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


@pytest.fixture
def no_auth_client(app):
    """A client without any cookies (for testing auth failures)."""
    return TestClient(app)


@pytest.fixture
def session_id(client, auth_cookie):
    resp = client.post(
        "/api/sessions",
        json={"title": "Archive test session"},
        headers={"Cookie": auth_cookie},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestArchiveCreate:
    def test_create_archive(self, client, auth_cookie, session_id):
        """Create an archive from a chat session."""
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "My archive"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My archive"
        assert data["chat_session"] == session_id
        assert "id" in data
        assert data["payload"] is not None
        assert "messages" in data["payload"]
        assert "files" in data["payload"]
        assert "session" in data["payload"]
        assert data["payload"]["session"]["title"] == "Archive test session"

    def test_create_archive_nonexistent_session(self, client, auth_cookie):
        """Create archive with non-existent session → 404."""
        resp = client.post(
            "/api/archives",
            json={"chat_session": "ses_nonexistent", "name": "Fail"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 404

    def test_create_archive_requires_auth(self, client):
        """No auth → 401."""
        resp = client.post(
            "/api/archives",
            json={"chat_session": "ses_fake", "name": "No auth"},
        )
        assert resp.status_code == 401

    def test_create_archive_cross_user(self, client, session_id, auth_cookie, other_cookie):
        """Cross-user archive create → 404 (session not owned by other)."""
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Stolen"},
            headers={"Cookie": other_cookie},
        )
        assert resp.status_code == 404

    def test_create_archive_empty_name(self, client, auth_cookie, session_id):
        """Whitespace-only name → 422."""
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "   "},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 422

    def test_create_archive_name_too_long(self, client, auth_cookie, session_id):
        """Name above ARCHIVE_NAME_MAX_LENGTH → 422."""
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "x" * 201},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 422

    def test_create_archive_name_at_max_length(self, client, auth_cookie, session_id):
        """Exactly ARCHIVE_NAME_MAX_LENGTH chars is allowed (boundary)."""
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "x" * archive_router.ARCHIVE_NAME_MAX_LENGTH},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 201
        assert len(resp.json()["name"]) == archive_router.ARCHIVE_NAME_MAX_LENGTH

    def test_create_archive_name_is_trimmed(self, client, auth_cookie, session_id):
        """Leading/trailing whitespace is stripped before persistence."""
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "  Trimmed  "},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Trimmed"

    def test_create_archive_payload_too_large(self, client, auth_cookie, session_id, monkeypatch):
        """Serialized payload above ARCHIVE_PAYLOAD_MAX_BYTES → 413."""
        monkeypatch.setattr(archive_router, "ARCHIVE_PAYLOAD_MAX_BYTES", 1)
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Too big"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 413

    def test_snapshot_is_ascending_and_complete(self, client, auth_cookie, session_id, store):
        """Snapshot keeps every message in chronological order (no 500 cap)."""
        import asyncio

        total = 501  # above the old `limit=500`, proving the snapshot is complete

        async def _seed():
            user = await store.get_user_by_email("archive@example.com")
            for i in range(total):
                role = "user" if i % 2 == 0 else "assistant"
                await store.create_message(user["id"], session_id, role, f"m{i}")

        asyncio.run(_seed())

        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Snapshot"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 201
        payload = resp.json()["payload"]
        assert payload["message_count"] == total
        assert payload["truncated"] is False
        assert [m["content_text"] for m in payload["messages"]] == [
            f"m{i}" for i in range(total)
        ]

    def test_archive_survives_session_delete(self, client, auth_cookie, session_id):
        """Deleting the chat session keeps the archive and nulls chat_session."""
        create_resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Durable"},
            headers={"Cookie": auth_cookie},
        )
        assert create_resp.status_code == 201
        archive_id = create_resp.json()["id"]

        delete_resp = client.delete(
            f"/api/sessions/{session_id}", headers={"Cookie": auth_cookie}
        )
        assert delete_resp.status_code == 204

        listing = client.get("/api/archives", headers={"Cookie": auth_cookie})
        assert listing.status_code == 200
        items = listing.json()
        assert len(items) == 1
        assert items[0]["id"] == archive_id
        assert items[0]["chat_session"] is None

        detail = client.get(
            f"/api/archives/{archive_id}", headers={"Cookie": auth_cookie}
        )
        assert detail.status_code == 200
        assert detail.json()["chat_session"] is None


class TestArchiveList:
    def test_list_archives(self, client, auth_cookie, session_id):
        """List archives for a user."""
        # Create two archives
        client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Archive 1"},
            headers={"Cookie": auth_cookie},
        )
        client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Archive 2"},
            headers={"Cookie": auth_cookie},
        )

        resp = client.get("/api/archives", headers={"Cookie": auth_cookie})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] in ("Archive 1", "Archive 2")

    def test_list_archives_empty(self, client, auth_cookie):
        """No archives yet → empty list."""
        resp = client.get("/api/archives", headers={"Cookie": auth_cookie})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_archives_requires_auth(self, no_auth_client):
        """No auth → 401."""
        resp = no_auth_client.get("/api/archives")
        assert resp.status_code == 401

    def test_list_derives_card_fields_from_table_artifact(
        self, client, auth_cookie, session_id, store
    ):
        """List items carry files/row_count/column_count derived from the snapshot.

        The LAST table artifact wins for row/column counts; ``total_rows`` is
        preferred over the captured head length. The payload itself is never
        returned by the list endpoint.
        """
        import asyncio

        artifacts = [
            {"kind": "figure", "name": "fig1", "payload": {"data": []}},
            {
                "kind": "table",
                "name": "df_first",
                "payload": {
                    "columns": ["a", "b", "c"],
                    "rows": [[1, 2, 3], [4, 5, 6]],
                    "total_rows": 10,
                },
            },
            # This later table must win.
            {
                "kind": "table",
                "name": "df_result",
                "payload": {
                    "columns": ["region", "margen"],
                    "rows": [[1, 2], [3, 4]],
                    "total_rows": 42,
                },
            },
        ]

        async def _seed():
            user = await store.get_user_by_email("archive@example.com")
            await store.create_message(
                user["id"],
                session_id,
                "assistant",
                "done",
                artifacts_json=json.dumps(artifacts),
            )
            await store.create_file(
                user["id"],
                session_id,
                "ventas_q3.csv",
                "/tmp/ventas_q3.csv",
                1024,
                "csv",
                row_count=100,
            )

        asyncio.run(_seed())

        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Derived"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 201

        listing = client.get("/api/archives", headers={"Cookie": auth_cookie})
        assert listing.status_code == 200
        items = listing.json()
        assert len(items) == 1
        item = items[0]
        assert item["files"] == ["ventas_q3.csv"]
        assert item["row_count"] == 42
        assert item["column_count"] == 2
        assert "payload" not in item

    def test_list_row_count_falls_back_to_file_row_count(
        self, client, auth_cookie, session_id, store
    ):
        """With no table artifact, row_count falls back to files[].row_count."""
        import asyncio

        async def _seed():
            user = await store.get_user_by_email("archive@example.com")
            await store.create_message(
                user["id"], session_id, "user", "just text, no artifacts"
            )
            await store.create_file(
                user["id"],
                session_id,
                "inventario.csv",
                "/tmp/inventario.csv",
                2048,
                "csv",
                row_count=1234,
            )

        asyncio.run(_seed())

        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Fallback"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 201

        items = client.get("/api/archives", headers={"Cookie": auth_cookie}).json()
        assert len(items) == 1
        assert items[0]["row_count"] == 1234
        assert items[0]["column_count"] is None

    def test_list_survives_malformed_payload_json(
        self, client, auth_cookie, session_id, store
    ):
        """A malformed payload_json must not 500 the list; fields default empty."""
        import asyncio

        async def _seed():
            user = await store.get_user_by_email("archive@example.com")
            await store.conn.execute(
                "INSERT INTO archives (user_id, name, chat_session, payload_json) "
                "VALUES (?, ?, ?, ?)",
                (user["id"], "Broken", session_id, "{not valid json"),
            )
            await store.conn.commit()

        asyncio.run(_seed())

        resp = client.get("/api/archives", headers={"Cookie": auth_cookie})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["name"] == "Broken"
        assert items[0]["files"] == []
        assert items[0]["row_count"] is None
        assert items[0]["column_count"] is None

    def test_list_row_count_uses_len_rows_when_total_rows_absent(
        self, client, auth_cookie, session_id, store
    ):
        """A table artifact with `rows` but no `total_rows` yields len(rows)."""
        import asyncio

        artifacts = [
            {
                "kind": "table",
                "name": "df_result",
                "payload": {
                    "columns": ["a", "b"],
                    "rows": [[1, 2], [3, 4], [5, 6]],
                },
            },
        ]

        async def _seed():
            user = await store.get_user_by_email("archive@example.com")
            await store.create_message(
                user["id"],
                session_id,
                "assistant",
                "done",
                artifacts_json=json.dumps(artifacts),
            )

        asyncio.run(_seed())

        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "LenRows"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 201

        items = client.get("/api/archives", headers={"Cookie": auth_cookie}).json()
        assert len(items) == 1
        assert items[0]["row_count"] == 3
        assert items[0]["column_count"] == 2

    @pytest.mark.parametrize("payload_json", ["5", "[]", '"text"'])
    def test_list_survives_non_dict_payload_json(
        self, client, auth_cookie, session_id, store, payload_json
    ):
        """Non-dict JSON payloads default to empty fields and still 200."""
        import asyncio

        async def _seed():
            user = await store.get_user_by_email("archive@example.com")
            await store.conn.execute(
                "INSERT INTO archives (user_id, name, chat_session, payload_json) "
                "VALUES (?, ?, ?, ?)",
                (user["id"], "NonDict", session_id, payload_json),
            )
            await store.conn.commit()

        asyncio.run(_seed())

        resp = client.get("/api/archives", headers={"Cookie": auth_cookie})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["files"] == []
        assert items[0]["row_count"] is None
        assert items[0]["column_count"] is None


class TestArchiveGet:
    def test_get_archive(self, client, auth_cookie, session_id):
        """Get a single archive with full payload."""
        create_resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Detail test"},
            headers={"Cookie": auth_cookie},
        )
        archive_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/archives/{archive_id}",
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == archive_id
        assert data["name"] == "Detail test"
        assert data["payload"] is not None

    def test_get_archive_nonexistent(self, client, auth_cookie):
        """Non-existent archive → 404."""
        resp = client.get("/api/archives/99999", headers={"Cookie": auth_cookie})
        assert resp.status_code == 404

    def test_get_archive_cross_user(self, client, session_id, auth_cookie, other_cookie):
        """Cross-user archive get → 404."""
        create_resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Private"},
            headers={"Cookie": auth_cookie},
        )
        archive_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/archives/{archive_id}",
            headers={"Cookie": other_cookie},
        )
        assert resp.status_code == 404

    def test_get_archive_requires_auth(self, client, no_auth_client, session_id, auth_cookie):
        """No auth → 401."""
        create_resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Auth check"},
            headers={"Cookie": auth_cookie},
        )
        archive_id = create_resp.json()["id"]

        resp = no_auth_client.get(f"/api/archives/{archive_id}")
        assert resp.status_code == 401