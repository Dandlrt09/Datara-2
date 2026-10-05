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
        """Serialized payload above ARCHIVE_PAYLOAD_MAX_BYTES → 413.

        The detail keeps the stable ``payload_too_large`` code and carries the
        human-readable 32 MB copy (never the raw byte count).
        """
        monkeypatch.setattr(archive_router, "ARCHIVE_PAYLOAD_MAX_BYTES", 1)
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": "Too big"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert detail["code"] == "payload_too_large"
        assert detail["message"] == (
            "El análisis supera el tamaño máximo permitido (32 MB). No se guardó."
        )

    def test_payload_cap_is_32_mib(self):
        """The configured ceiling is exactly 32 MiB."""
        assert archive_router.ARCHIVE_PAYLOAD_MAX_BYTES == 32 * 1024 * 1024

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

    @pytest.mark.parametrize("payload_json", ["{not valid json", "5", "[]"])
    def test_get_survives_malformed_payload_json(
        self, client, auth_cookie, session_id, store, payload_json
    ):
        """A malformed/non-dict payload_json must not 500 the detail endpoint."""
        import asyncio

        async def _seed():
            user = await store.get_user_by_email("archive@example.com")
            cursor = await store.conn.execute(
                "INSERT INTO archives (user_id, name, chat_session, payload_json) "
                "VALUES (?, ?, ?, ?)",
                (user["id"], "Broken", session_id, payload_json),
            )
            await store.conn.commit()
            return cursor.lastrowid

        archive_id = asyncio.run(_seed())

        resp = client.get(
            f"/api/archives/{archive_id}", headers={"Cookie": auth_cookie}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Broken"
        assert data["payload"] is None


class TestArchiveRename:
    def _create(self, client, cookie, session_id, name="Original"):
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": name},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_rename_updates_name_and_list(self, client, auth_cookie, session_id):
        """PATCH updates the name and the list reflects it."""
        archive_id = self._create(client, auth_cookie, session_id)

        resp = client.patch(
            f"/api/archives/{archive_id}",
            json={"name": "Renamed"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == archive_id
        assert data["name"] == "Renamed"

        items = client.get("/api/archives", headers={"Cookie": auth_cookie}).json()
        assert [i["name"] for i in items] == ["Renamed"]

    def test_rename_trims_whitespace(self, client, auth_cookie, session_id):
        """PATCH trims surrounding whitespace before persistence."""
        archive_id = self._create(client, auth_cookie, session_id)
        resp = client.patch(
            f"/api/archives/{archive_id}",
            json={"name": "  Trimmed  "},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Trimmed"

    def test_rename_empty_name(self, client, auth_cookie, session_id):
        """Whitespace-only rename → 422 invalid_name."""
        archive_id = self._create(client, auth_cookie, session_id)
        resp = client.patch(
            f"/api/archives/{archive_id}",
            json={"name": "   "},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_name"

    def test_rename_name_too_long(self, client, auth_cookie, session_id):
        """Name above ARCHIVE_NAME_MAX_LENGTH → 422 invalid_name."""
        archive_id = self._create(client, auth_cookie, session_id)
        resp = client.patch(
            f"/api/archives/{archive_id}",
            json={"name": "x" * (archive_router.ARCHIVE_NAME_MAX_LENGTH + 1)},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_name"

    def test_rename_name_at_max_length(self, client, auth_cookie, session_id):
        """Exactly ARCHIVE_NAME_MAX_LENGTH chars is allowed (boundary)."""
        archive_id = self._create(client, auth_cookie, session_id)
        resp = client.patch(
            f"/api/archives/{archive_id}",
            json={"name": "x" * archive_router.ARCHIVE_NAME_MAX_LENGTH},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 200
        assert len(resp.json()["name"]) == archive_router.ARCHIVE_NAME_MAX_LENGTH

    def test_rename_unknown_id(self, client, auth_cookie):
        """Unknown archive id → 404."""
        resp = client.patch(
            "/api/archives/99999",
            json={"name": "Nope"},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 404

    def test_rename_cross_user(self, client, auth_cookie, other_cookie, session_id):
        """Another user's archive id → 404 and the owner's name is untouched."""
        archive_id = self._create(client, auth_cookie, session_id)
        resp = client.patch(
            f"/api/archives/{archive_id}",
            json={"name": "Stolen"},
            headers={"Cookie": other_cookie},
        )
        assert resp.status_code == 404

        detail = client.get(
            f"/api/archives/{archive_id}", headers={"Cookie": auth_cookie}
        ).json()
        assert detail["name"] == "Original"

    def test_rename_requires_auth(self, client, no_auth_client, auth_cookie, session_id):
        """No auth → 401."""
        archive_id = self._create(client, auth_cookie, session_id)
        resp = no_auth_client.patch(
            f"/api/archives/{archive_id}", json={"name": "Anon"}
        )
        assert resp.status_code == 401


class TestArchiveDelete:
    def _create(self, client, cookie, session_id, name="Doomed"):
        resp = client.post(
            "/api/archives",
            json={"chat_session": session_id, "name": name},
            headers={"Cookie": cookie},
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_delete_removes_row(self, client, auth_cookie, session_id):
        """DELETE removes the archive: 204, detail 404, gone from the list."""
        archive_id = self._create(client, auth_cookie, session_id)

        resp = client.delete(
            f"/api/archives/{archive_id}", headers={"Cookie": auth_cookie}
        )
        assert resp.status_code == 204
        assert resp.content == b""

        detail = client.get(
            f"/api/archives/{archive_id}", headers={"Cookie": auth_cookie}
        )
        assert detail.status_code == 404

        listing = client.get("/api/archives", headers={"Cookie": auth_cookie})
        assert listing.status_code == 200
        assert listing.json() == []

    def test_delete_unknown_id(self, client, auth_cookie):
        """Unknown archive id → 404."""
        resp = client.delete("/api/archives/99999", headers={"Cookie": auth_cookie})
        assert resp.status_code == 404

    def test_delete_cross_user(self, client, auth_cookie, other_cookie, session_id):
        """Another user's archive id → 404 and the archive survives."""
        archive_id = self._create(client, auth_cookie, session_id)

        resp = client.delete(
            f"/api/archives/{archive_id}", headers={"Cookie": other_cookie}
        )
        assert resp.status_code == 404

        detail = client.get(
            f"/api/archives/{archive_id}", headers={"Cookie": auth_cookie}
        )
        assert detail.status_code == 200

    def test_delete_requires_auth(self, client, no_auth_client, auth_cookie, session_id):
        """No auth → 401."""
        archive_id = self._create(client, auth_cookie, session_id)
        resp = no_auth_client.delete(f"/api/archives/{archive_id}")
        assert resp.status_code == 401


class TestArchivePagination:
    @staticmethod
    def _seed(store, email, session_id, count):
        """Seed ``count`` archives with distinct, ascending created_at.

        Returns the inserted ids in creation order (so the last id is the
        newest and must come first under ``created_at DESC, id DESC``).
        """
        import asyncio

        ids: list[int] = []

        async def _run():
            user = await store.get_user_by_email(email)
            for i in range(count):
                cursor = await store.conn.execute(
                    "INSERT INTO archives "
                    "(user_id, name, chat_session, payload_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        user["id"],
                        f"arch-{i}",
                        session_id,
                        "{}",
                        f"2026-01-0{i + 1} 00:00:00",
                    ),
                )
                ids.append(cursor.lastrowid)
            await store.conn.commit()

        asyncio.run(_run())
        return ids

    @staticmethod
    def _seed_equal_time(store, email, session_id, count):
        """Seed ``count`` archives that all share one ``created_at``.

        Returns the inserted ids in creation order. Because ``created_at`` is
        identical, only the ``id DESC`` tiebreaker can produce a stable order —
        removing it makes the assertions in
        ``test_equal_created_at_uses_id_desc_tiebreaker`` fail.
        """
        import asyncio

        ids: list[int] = []

        async def _run():
            user = await store.get_user_by_email(email)
            for i in range(count):
                cursor = await store.conn.execute(
                    "INSERT INTO archives "
                    "(user_id, name, chat_session, payload_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        user["id"],
                        f"same-{i}",
                        session_id,
                        "{}",
                        "2026-01-01 00:00:00",
                    ),
                )
                ids.append(cursor.lastrowid)
            await store.conn.commit()

        asyncio.run(_run())
        return ids

    def test_page_size_and_desc_order(self, client, auth_cookie, session_id, store):
        """limit caps the page and rows are newest-first."""
        ids = self._seed(store, "archive@example.com", session_id, 5)

        resp = client.get("/api/archives?limit=2", headers={"Cookie": auth_cookie})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 2
        assert [i["id"] for i in items] == [ids[4], ids[3]]

    def test_before_returns_strictly_older(self, client, auth_cookie, session_id, store):
        """before=<oldest page id> returns the next, strictly older page."""
        ids = self._seed(store, "archive@example.com", session_id, 5)

        first = client.get(
            "/api/archives?limit=2", headers={"Cookie": auth_cookie}
        ).json()
        before = first[-1]["id"]

        nxt = client.get(
            f"/api/archives?limit=2&before={before}", headers={"Cookie": auth_cookie}
        ).json()
        assert [i["id"] for i in nxt] == [ids[2], ids[1]]
        assert all(i["id"] < before for i in nxt)

    def test_before_beyond_oldest_is_empty(self, client, auth_cookie, session_id, store):
        """before=oldest id → empty next page."""
        ids = self._seed(store, "archive@example.com", session_id, 3)
        resp = client.get(
            f"/api/archives?limit=2&before={ids[0]}", headers={"Cookie": auth_cookie}
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_equal_created_at_uses_id_desc_tiebreaker(
        self, client, auth_cookie, session_id, store
    ):
        """Equal ``created_at`` rows order by ``id DESC``, and paging with
        ``before=<id>`` neither duplicates nor omits equal-timestamp rows.

        Honest scope: this pins the *contract* (order + no dup/omit at the
        page boundary), but it is documentary rather than discriminating under
        the current schema. ``idx_archives_user_created (user_id, created_at)``
        makes SQLite satisfy the tie with a reverse index scan that already
        yields ``id DESC``, so removing ``, id DESC`` from ``list_archives``
        would still pass here. The tiebreaker stays as defensive correctness
        for a plan without that index (e.g. a future migration).
        """
        ids = self._seed_equal_time(store, "archive@example.com", session_id, 5)

        first = client.get(
            "/api/archives?limit=2", headers={"Cookie": auth_cookie}
        ).json()
        assert [i["id"] for i in first] == [ids[4], ids[3]]

        before = first[-1]["id"]
        second = client.get(
            f"/api/archives?limit=2&before={before}", headers={"Cookie": auth_cookie}
        ).json()
        assert [i["id"] for i in second] == [ids[2], ids[1]]
        assert all(i["id"] < before for i in second)

        before_second = second[-1]["id"]
        third = client.get(
            f"/api/archives?limit=2&before={before_second}",
            headers={"Cookie": auth_cookie},
        ).json()
        assert [i["id"] for i in third] == [ids[0]]

        collected = [i["id"] for page in (first, second, third) for i in page]
        assert collected == [ids[4], ids[3], ids[2], ids[1], ids[0]]
        assert len(set(collected)) == len(ids)

    def test_limit_clamps(self, client, auth_cookie):
        """limit outside 1..200 → 422; the bounds themselves are accepted."""
        assert client.get(
            "/api/archives?limit=0", headers={"Cookie": auth_cookie}
        ).status_code == 422
        assert client.get(
            "/api/archives?limit=201", headers={"Cookie": auth_cookie}
        ).status_code == 422
        assert client.get(
            "/api/archives?limit=1", headers={"Cookie": auth_cookie}
        ).status_code == 200
        assert client.get(
            "/api/archives?limit=200", headers={"Cookie": auth_cookie}
        ).status_code == 200


class TestArchiveSearchOrder:
    @staticmethod
    def _seed(store, email, session_id, names):
        """Seed archives for ``email`` with ascending, distinct created_at.

        Returns the inserted ids in creation order.
        """
        import asyncio

        ids: list[int] = []

        async def _run():
            user = await store.get_user_by_email(email)
            for i, name in enumerate(names):
                cursor = await store.conn.execute(
                    "INSERT INTO archives "
                    "(user_id, name, chat_session, payload_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        user["id"],
                        name,
                        session_id,
                        "{}",
                        f"2026-03-0{i + 1} 00:00:00",
                    ),
                )
                ids.append(cursor.lastrowid)
            await store.conn.commit()

        asyncio.run(_run())
        return ids

    @pytest.mark.parametrize("term", ["REGION", "region", "región", "RegiÓn"])
    def test_search_is_case_and_accent_insensitive(
        self, client, auth_cookie, session_id, store, term
    ):
        """The name search folds case and Spanish diacritics (all four match)."""
        self._seed(
            store,
            "archive@example.com",
            session_id,
            ["Margen por región", "Clientes sin compra"],
        )

        resp = client.get(
            "/api/archives", params={"q": term}, headers={"Cookie": auth_cookie}
        )
        assert resp.status_code == 200
        assert [i["name"] for i in resp.json()] == ["Margen por región"]

    def test_search_matches_literal_special_characters(
        self, client, auth_cookie, session_id, store
    ):
        """`insert` search is literal: `%` is a character, not a wildcard."""
        self._seed(
            store, "archive@example.com", session_id, ["cien% real", "cienX real"]
        )

        items = client.get(
            "/api/archives", params={"q": "%"}, headers={"Cookie": auth_cookie}
        ).json()
        assert [i["name"] for i in items] == ["cien% real"]

    def test_blank_q_is_ignored(self, client, auth_cookie, session_id, store):
        """A whitespace-only q returns the full list."""
        self._seed(store, "archive@example.com", session_id, ["Uno", "Dos"])

        resp = client.get(
            "/api/archives", params={"q": "   "}, headers={"Cookie": auth_cookie}
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_search_is_user_scoped(
        self, client, auth_cookie, other_cookie, session_id, store
    ):
        """A search never leaks another user's archives."""
        self._seed(store, "archive@example.com", session_id, ["Margen visible"])
        self._seed(store, "other@archive.com", session_id, ["Margen ajeno"])

        resp = client.get(
            "/api/archives", params={"q": "margen"}, headers={"Cookie": auth_cookie}
        )
        assert resp.status_code == 200
        assert [i["name"] for i in resp.json()] == ["Margen visible"]

    def test_search_composes_with_newest_keyset(
        self, client, auth_cookie, session_id, store
    ):
        """q narrows the set and still pages newest-first with `before`."""
        self._seed(
            store,
            "archive@example.com",
            session_id,
            ["dato uno", "dato dos", "dato tres", "otro"],
        )

        first = client.get(
            "/api/archives",
            params={"q": "dato", "limit": 2},
            headers={"Cookie": auth_cookie},
        ).json()
        assert [i["name"] for i in first] == ["dato tres", "dato dos"]

        nxt = client.get(
            "/api/archives",
            params={"q": "dato", "limit": 2, "before": first[-1]["id"]},
            headers={"Cookie": auth_cookie},
        ).json()
        assert [i["name"] for i in nxt] == ["dato uno"]

    def test_search_composes_with_oldest_keyset(
        self, client, auth_cookie, session_id, store
    ):
        """q narrows the set and still pages oldest-first with `after`."""
        self._seed(
            store,
            "archive@example.com",
            session_id,
            ["dato uno", "dato dos", "dato tres", "otro"],
        )

        first = client.get(
            "/api/archives",
            params={"q": "dato", "order": "oldest", "limit": 2},
            headers={"Cookie": auth_cookie},
        ).json()
        assert [i["name"] for i in first] == ["dato uno", "dato dos"]

        nxt = client.get(
            "/api/archives",
            params={
                "q": "dato",
                "order": "oldest",
                "limit": 2,
                "after": first[-1]["id"],
            },
            headers={"Cookie": auth_cookie},
        ).json()
        assert [i["name"] for i in nxt] == ["dato tres"]

    def test_order_oldest_pages_with_after(
        self, client, auth_cookie, session_id, store
    ):
        """order=oldest returns ascending rows and `after` pages forward."""
        ids = self._seed(store, "archive@example.com", session_id, ["a", "b", "c"])

        first = client.get(
            "/api/archives",
            params={"order": "oldest", "limit": 2},
            headers={"Cookie": auth_cookie},
        ).json()
        assert [i["id"] for i in first] == [ids[0], ids[1]]

        nxt = client.get(
            "/api/archives",
            params={"order": "oldest", "limit": 2, "after": ids[1]},
            headers={"Cookie": auth_cookie},
        ).json()
        assert [i["id"] for i in nxt] == [ids[2]]

    @pytest.mark.parametrize(
        "params",
        [
            {"before": 1, "after": 2},
            {"before": 1, "order": "oldest"},
            {"after": 1, "order": "newest"},
        ],
    )
    def test_invalid_cursor_combinations(self, client, auth_cookie, params):
        """Mismatched cursor/order pairs → 422 invalid_cursor."""
        resp = client.get(
            "/api/archives", params=params, headers={"Cookie": auth_cookie}
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_cursor"

    def test_q_over_max_length_is_rejected(self, client, auth_cookie):
        """q above the 200-char bound → 422."""
        resp = client.get(
            "/api/archives",
            params={"q": "x" * 201},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 422
