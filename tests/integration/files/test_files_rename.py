"""Integration tests for PATCH /api/files/{file_id} (file rename, F12).

Uses FastAPI TestClient with a fresh in-memory SQLite store per test, mirroring
``test_files_api.py``. The rename contract lives in
``odd/tasks/files-f12-rename.md``: same-extension requirement (D2), explicit
422 shape (D3/D3b), shared 409 detail text (D4), case-insensitive name
uniqueness (D7 revised by F12.1), ownership-only 404 (D1) and the
IntegrityError race mapping.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers import auth as auth_router
from server.api.routers import files as files_router
from server.api.routers import sessions as sessions_router
from server.api.upload_guard import install_upload_guard
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def app(tmp_path, monkeypatch):
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(files_router.router)
    install_upload_guard(application)

    # Isolation: uploads must land in a per-test tmp dir, never the real
    # server/uploads/ used by the live server.
    monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")

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
    """Register a user and return a client with valid session cookie."""
    resp = client.post(
        "/api/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    client.headers["Cookie"] = resp.headers["set-cookie"]
    return client


@pytest.fixture
def other_client(app):
    """A second, unrelated authenticated user (foreign-file 404 checks)."""
    client = TestClient(app)
    resp = client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    client.headers["Cookie"] = resp.headers["set-cookie"]
    return client


@pytest.fixture
def session_id(auth_client):
    """Create a chat session and return its id."""
    resp = auth_client.post("/api/sessions", json={"title": "Test session"})
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
def user_id(auth_client):
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.fixture
def store():
    from server.api import store as api_store  # noqa: PLC0415
    return api_store._store


def _upload(auth_client, session_id, filename, content=b"a\n1\n"):
    resp = auth_client.post(
        f"/api/sessions/{session_id}/files",
        files={"file": (filename, content, "text/csv")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _rename(auth_client, file_id, filename):
    return auth_client.patch(f"/api/files/{file_id}", json={"filename": filename})


def _names(auth_client, session_id):
    resp = auth_client.get(f"/api/sessions/{session_id}/files")
    assert resp.status_code == 200
    return [f["filename"] for f in resp.json()]


class TestRenameHappyPath:
    def test_rename_persists_new_name_and_keeps_metadata(self, auth_client, session_id, store):
        uploaded = _upload(auth_client, session_id, "old.csv", b"a,b\n1,2\n")
        # Fetch the persisted row before the rename (ownership enforced).
        me = auth_client.get("/api/auth/me").json()["id"]
        before = asyncio.run(store.get_file(uploaded["id"], me))
        assert before is not None

        resp = _rename(auth_client, uploaded["id"], "new.csv")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == uploaded["id"]
        assert body["filename"] == "new.csv"
        assert body["format"] == uploaded["format"]
        assert body["size_bytes"] == uploaded["size_bytes"]
        assert body["row_count"] == uploaded["row_count"]
        assert body["created_at"] == uploaded["created_at"]

        # Visible in a subsequent list; exactly one row.
        assert _names(auth_client, session_id) == ["new.csv"]

        after = asyncio.run(store.get_file(uploaded["id"], me))
        assert after is not None
        assert after["filename"] == "new.csv"
        # Nothing on disk changes: the storage_path (and thus the bytes) stay.
        assert after["storage_path"] == before["storage_path"]

    def test_trim_applied(self, auth_client, session_id):
        uploaded = _upload(auth_client, session_id, "old.csv")
        resp = _rename(auth_client, uploaded["id"], "  new.csv  ")
        assert resp.status_code == 200, resp.text
        assert resp.json()["filename"] == "new.csv"

    def test_download_still_works_and_carries_new_name(self, auth_client, session_id):
        content = b"a,b\n1,2\n"
        uploaded = _upload(auth_client, session_id, "old.csv", content)
        assert _rename(auth_client, uploaded["id"], "renamed.csv").status_code == 200

        download = auth_client.get(f"/api/files/{uploaded['id']}/download")
        assert download.status_code == 200
        assert download.content == content
        assert "renamed.csv" in download.headers["content-disposition"]


class TestRenameNoOp:
    def test_same_name_is_200_noop(self, auth_client, session_id):
        uploaded = _upload(auth_client, session_id, "same.csv")
        resp = _rename(auth_client, uploaded["id"], "same.csv")
        assert resp.status_code == 200, resp.text
        assert resp.json()["filename"] == "same.csv"
        assert _names(auth_client, session_id) == ["same.csv"]

    def test_case_variant_is_200_noop(self, auth_client, session_id):
        # F12.1/D7: uniqueness is case-insensitive, but the pre-check matches
        # the row itself and the NOCASE index does not conflict with a row's
        # own entry, so the rename is a 200 no-op (one row, new spelling).
        uploaded = _upload(auth_client, session_id, "Report.csv")
        resp = _rename(auth_client, uploaded["id"], "report.csv")
        assert resp.status_code == 200, resp.text
        assert resp.json()["filename"] == "report.csv"
        assert _names(auth_client, session_id) == ["report.csv"]

    def test_case_insensitive_same_extension_allowed(self, auth_client, session_id):
        uploaded = _upload(auth_client, session_id, "old.csv")
        resp = _rename(auth_client, uploaded["id"], "new.CSV")
        assert resp.status_code == 200, resp.text
        assert resp.json()["filename"] == "new.CSV"


class TestRenameValidation:
    @pytest.mark.parametrize(
        "bad_name",
        [
            "",
            "   ",
            "n" * 256,
            "dir/new.csv",
            "dir\\new.csv",
            "ctrl\x01.csv",
            "old.txt",  # extension change
        ],
    )
    def test_invalid_names_return_422_and_do_not_write(self, auth_client, session_id, bad_name):
        uploaded = _upload(auth_client, session_id, "old.csv")
        resp = _rename(auth_client, uploaded["id"], bad_name)
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "invalid_filename"
        assert detail["message"]
        # No write happened.
        assert _names(auth_client, session_id) == ["old.csv"]

    def test_separator_message_is_specific(self, auth_client, session_id):
        uploaded = _upload(auth_client, session_id, "old.csv")
        resp = _rename(auth_client, uploaded["id"], "dir/new.csv")
        assert resp.status_code == 422
        assert "separador" in resp.json()["detail"]["message"].lower()

    def test_extension_message_is_specific(self, auth_client, session_id):
        uploaded = _upload(auth_client, session_id, "old.csv")
        resp = _rename(auth_client, uploaded["id"], "new.txt")
        assert resp.status_code == 422
        assert "extensión" in resp.json()["detail"]["message"].lower()

    def test_length_cap_boundary_is_enforced_on_supported_extension(
        self, auth_client, session_id
    ):
        """The length guard must be exercised independently of the extension rule.

        The parametrized ``"n" * 256`` has no extension, so it is rejected by
        the same-extension rule before the length guard is ever reached. Both
        names below carry a VALID ``.csv`` extension, so only the >255 cap can
        reject the first one.
        """
        # 252 + len(".csv") == 256 > 255 -> rejected by the cap, the message
        # names the limit, and nothing is written.
        too_long = "n" * 252 + ".csv"
        assert len(too_long) == 256

        uploaded = _upload(auth_client, session_id, "old.csv")
        resp = _rename(auth_client, uploaded["id"], too_long)
        assert resp.status_code == 422, resp.text
        assert "caracteres" in resp.json()["detail"]["message"]
        assert _names(auth_client, session_id) == ["old.csv"]

        # 251 + len(".csv") == 255, exactly at the cap -> accepted and persisted.
        at_cap = "n" * 251 + ".csv"
        assert len(at_cap) == 255

        resp = _rename(auth_client, uploaded["id"], at_cap)
        assert resp.status_code == 200, resp.text
        assert resp.json()["filename"] == at_cap
        assert _names(auth_client, session_id) == [at_cap]

    def test_whitespace_name_hits_the_dedicated_empty_guard(self, auth_client, session_id):
        """The empty-after-strip guard owns its dedicated message.

        Without ``if not name: raise _invalid_filename(...)`` the whitespace
        name would fall through to the extension check and still be a 422, so
        only the "vacío" copy proves the guard is present.
        """
        uploaded = _upload(auth_client, session_id, "old.csv")
        resp = _rename(auth_client, uploaded["id"], "   ")
        assert resp.status_code == 422, resp.text
        assert "vacío" in resp.json()["detail"]["message"]
        assert _names(auth_client, session_id) == ["old.csv"]


class TestRenameDuplicates:
    def test_duplicate_in_same_session_is_409_with_shared_text(self, auth_client, session_id):
        first = _upload(auth_client, session_id, "a.csv")
        second = _upload(auth_client, session_id, "b.csv")

        resp = _rename(auth_client, second["id"], "a.csv")
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == files_router._duplicate_name_detail("a.csv")
        # The colliding row is untouched.
        assert sorted(_names(auth_client, session_id)) == ["a.csv", "b.csv"]
        assert first["id"] != second["id"]

    def test_case_variant_of_another_file_is_409_naming_existing(
        self, auth_client, session_id
    ):
        """F12.1: the user's exact report — a capital letter must not dodge it.

        Renaming ``other.csv`` to ``ventas.csv`` while ``Ventas.csv`` exists in
        the same session is a 409, and the detail names the spelling the table
        shows (``Ventas.csv``), not the typed one.
        """
        first = _upload(auth_client, session_id, "Ventas.csv")
        second = _upload(auth_client, session_id, "other.csv")

        resp = _rename(auth_client, second["id"], "ventas.csv")
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == files_router._duplicate_name_detail(
            "Ventas.csv"
        )
        # Neither row changed; exactly two rows remain.
        assert sorted(_names(auth_client, session_id)) == ["Ventas.csv", "other.csv"]
        assert first["id"] != second["id"]

    def test_same_name_in_other_session_of_same_user_is_200(self, auth_client, session_id):
        _upload(auth_client, session_id, "a.csv")
        other_session = auth_client.post(
            "/api/sessions", json={"title": "Other session"}
        ).json()["id"]
        second = _upload(auth_client, other_session, "b.csv")

        resp = _rename(auth_client, second["id"], "a.csv")
        assert resp.status_code == 200, resp.text
        assert resp.json()["filename"] == "a.csv"
        assert _names(auth_client, other_session) == ["a.csv"]


class TestRenameOwnership:
    def test_foreign_id_and_unknown_id_are_identical_404(
        self, auth_client, other_client
    ):
        other_session = other_client.post(
            "/api/sessions", json={"title": "Other"}
        ).json()["id"]
        foreign = _upload(other_client, other_session, "secret.csv")

        foreign_resp = _rename(auth_client, foreign["id"], "stolen.csv")
        unknown_resp = _rename(auth_client, 999_999, "ghost.csv")
        assert foreign_resp.status_code == 404
        assert unknown_resp.status_code == 404
        assert foreign_resp.json() == unknown_resp.json()

        # The foreign row is untouched.
        assert _names(other_client, other_session) == ["secret.csv"]

    def test_unauthenticated_returns_401(self, client):
        resp = client.patch("/api/files/1", json={"filename": "x.csv"})
        assert resp.status_code == 401

    def test_store_rename_file_rejects_foreign_owner_directly(
        self, auth_client, other_client, session_id, store
    ):
        """The route 404s before the UPDATE via ``store.get_file``, so the
        store's own ``AND user_id = ?`` clause is pure defense in depth. Call
        the store method directly with user B against user A's row: it must
        return ``None`` and leave A's filename untouched.
        """
        uploaded = _upload(auth_client, session_id, "mine.csv")
        owner_id = auth_client.get("/api/auth/me").json()["id"]
        other_id = other_client.get("/api/auth/me").json()["id"]
        assert owner_id != other_id

        result = asyncio.run(store.rename_file(uploaded["id"], other_id, "stolen.csv"))
        assert result is None

        row = asyncio.run(store.get_file(uploaded["id"], owner_id))
        assert row is not None
        assert row["filename"] == "mine.csv"


class TestRenameRace:
    def test_forced_integrity_error_returns_409_not_500(
        self, auth_client, session_id, monkeypatch
    ):
        """The pre-check is bypassed deterministically so the UPDATE itself
        hits ``idx_files_unique_name`` — the store must map IntegrityError to
        DuplicateError and the route to the same 409 the pre-check emits.
        """
        first = _upload(auth_client, session_id, "a.csv")
        second = _upload(auth_client, session_id, "b.csv")

        async def _no_existing(*args, **kwargs):
            return None

        monkeypatch.setattr(SqliteStore, "get_file_by_name", _no_existing)

        resp = _rename(auth_client, second["id"], "a.csv")
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == files_router._duplicate_name_detail("a.csv")

        # Both rows survive with their original names (the failed UPDATE
        # rolled back).
        assert sorted(_names(auth_client, session_id)) == ["a.csv", "b.csv"]
        assert first["id"] != second["id"]
