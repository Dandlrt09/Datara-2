"""Integration tests for the privacy API and the outgoing-payload preview
(F6 / T5, S2/S3/S5, D1-D6).

The unit tests cover the redaction math. These tests cover the contract the
client sees: a session default plus per-file override, the alias knob, the
409 when a file has no profile to validate an alias against, ownership, and
the promise that the preview is the EXACT payload the chat ships -- built by
``build_outgoing_datasets``, with the real storage path replaced by a staged
neutral name at every level.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers import auth as auth_router
from server.api.routers import files as files_router
from server.api.routers import privacy as privacy_router
from server.api.routers import sessions as sessions_router
from server.api.upload_guard import install_upload_guard
from server.services.chat_context import build_outgoing_datasets
from server.services.privacy import PRIVACY_LEVELS
from server.services.profile_cache import get_profile
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations, register_verified

_CUSTOMERS_CSV = b"customer_id,name\n1,Ana\n2,Beto\n3,Caro\n4,Dani\n"
_ORDERS_CSV = b"order_id,customer_id,total\n10,1,100\n11,1,50\n12,2,75\n13,10,20\n"


@pytest.fixture
def app(tmp_path, monkeypatch):
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(files_router.router)
    application.include_router(privacy_router.router)
    install_upload_guard(application)

    # Isolation: uploads must land in a per-test tmp dir, never the real
    # server/uploads/. The preview staging test relies on this to know which
    # absolute path must NOT survive.
    monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        await apply_all_migrations(s)

    asyncio.run(_setup())
    api_store._store = s

    yield application

    asyncio.run(s.close())


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def store():
    from server.api import store as api_store  # noqa: PLC0415
    return api_store._store


@pytest.fixture
def user_id(auth_client):
    """The authenticated user's id (for direct store seeding)."""
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.fixture
def auth_client(client):
    """Register a verified user and return a client with a valid session cookie."""
    cookie = register_verified(client, "test@example.com").headers["set-cookie"]
    client.headers["Cookie"] = cookie
    return client


@pytest.fixture
def other_client(app):
    """A second, independent logged-in user sharing the same store."""
    other = TestClient(app)
    cookie = register_verified(other, "other@example.com").headers["set-cookie"]
    other.headers["Cookie"] = cookie
    return other


@pytest.fixture
def session_id(auth_client):
    resp = auth_client.post("/api/sessions", json={"title": "Privacy session"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _upload(auth_client, session_id, filename, content):
    resp = auth_client.post(
        f"/api/sessions/{session_id}/files",
        files={"file": (filename, content, "text/csv")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture
def two_files(auth_client, session_id):
    """Two profiled CSVs in one session, so "one entry per file" is visible."""
    first = _upload(auth_client, session_id, "customers.csv", _CUSTOMERS_CSV)
    second = _upload(auth_client, session_id, "orders.csv", _ORDERS_CSV)
    return first, second


def _set_session_level(auth_client, session_id, level):
    resp = auth_client.put(
        f"/api/sessions/{session_id}/privacy", json={"privacy_level": level}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _columns(store, file_id, user_id):
    profile = asyncio.run(get_profile(store, file_id, user_id))
    assert profile is not None
    return [
        column["name"]
        for column in profile["schema_data"].get("columns", [])
        if column.get("name")
    ]


def _preview(auth_client, session_id):
    resp = auth_client.get(f"/api/sessions/{session_id}/privacy/preview")
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestSessionPrivacy:
    def test_get_defaults_to_full_with_one_entry_per_file(
        self, auth_client, session_id, two_files
    ):
        resp = auth_client.get(f"/api/sessions/{session_id}/privacy")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["privacy_level"] == "full"
        assert data["levels"] == list(PRIVACY_LEVELS)
        assert {entry["file_id"] for entry in data["files"]} == set(two_files)
        for entry in data["files"]:
            # S2/S4: no override yet, so the file inherits the session.
            assert entry["privacy_level"] is None
            assert entry["effective_level"] == "full"
            assert entry["column_aliases"] is None

    def test_put_sets_the_level_and_every_file_follows(
        self, auth_client, session_id, two_files
    ):
        data = _set_session_level(auth_client, session_id, "schema")
        assert data["privacy_level"] == "schema"
        for entry in data["files"]:
            assert entry["effective_level"] == "schema"
        # The write is durable, not just echoed back.
        assert (
            auth_client.get(f"/api/sessions/{session_id}/privacy").json()[
                "privacy_level"
            ]
            == "schema"
        )

    def test_put_an_unknown_level_is_a_422_and_changes_nothing(
        self, auth_client, session_id
    ):
        resp = auth_client.put(
            f"/api/sessions/{session_id}/privacy", json={"privacy_level": "nope"}
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_privacy_level"
        # D1: a refusal, never a silent fallback.
        stored = auth_client.get(f"/api/sessions/{session_id}/privacy").json()
        assert stored["privacy_level"] == "full"

    def test_put_an_unknown_session_is_a_404(self, auth_client):
        resp = auth_client.put(
            "/api/sessions/no-such-session/privacy",
            json={"privacy_level": "full"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chat session not found"

    def test_another_users_session_is_a_404(self, other_client, session_id):
        resp = other_client.get(f"/api/sessions/{session_id}/privacy")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chat session not found"
        resp = other_client.put(
            f"/api/sessions/{session_id}/privacy",
            json={"privacy_level": "schema"},
        )
        assert resp.status_code == 404


class TestFilePrivacy:
    def test_patch_sets_the_override_and_effective_follows(
        self, auth_client, session_id, two_files
    ):
        first, second = two_files
        resp = auth_client.patch(
            f"/api/files/{first}/privacy", json={"privacy_level": "schema"}
        )
        assert resp.status_code == 200, resp.text
        entry = resp.json()
        assert entry["file_id"] == first
        assert entry["privacy_level"] == "schema"
        assert entry["effective_level"] == "schema"
        # The sibling with no override still inherits the session default.
        listed = {
            item["file_id"]: item
            for item in auth_client.get(
                f"/api/sessions/{session_id}/privacy"
            ).json()["files"]
        }
        assert listed[first]["effective_level"] == "schema"
        assert listed[second]["effective_level"] == "full"

    def test_patch_null_clears_the_override_and_falls_back_to_the_session(
        self, auth_client, session_id, two_files
    ):
        first, _ = two_files
        _set_session_level(auth_client, session_id, "aggregates")
        auth_client.patch(
            f"/api/files/{first}/privacy", json={"privacy_level": "schema"}
        )
        resp = auth_client.patch(
            f"/api/files/{first}/privacy", json={"privacy_level": None}
        )
        assert resp.status_code == 200, resp.text
        entry = resp.json()
        assert entry["privacy_level"] is None
        assert entry["effective_level"] == "aggregates"

    def test_aliases_for_a_real_column_round_trip(
        self, auth_client, session_id, two_files, store, user_id
    ):
        first, _ = two_files
        source = _columns(store, first, user_id)[1]
        resp = auth_client.patch(
            f"/api/files/{first}/privacy",
            json={"column_aliases": {source: "col_renamed"}},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["column_aliases"] == {source: "col_renamed"}
        listed = auth_client.get(f"/api/sessions/{session_id}/privacy").json()["files"]
        stored = next(item for item in listed if item["file_id"] == first)
        assert stored["column_aliases"] == {source: "col_renamed"}

    def test_an_alias_source_that_is_not_a_column_is_a_422(
        self, auth_client, session_id, two_files
    ):
        first, _ = two_files
        resp = auth_client.patch(
            f"/api/files/{first}/privacy",
            json={"column_aliases": {"no_such_column": "col_1"}},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_column_alias"
        # Rejected input leaves the stored override untouched.
        listed = auth_client.get(f"/api/sessions/{session_id}/privacy").json()["files"]
        stored = next(item for item in listed if item["file_id"] == first)
        assert stored["column_aliases"] is None

    def test_an_unknown_level_is_a_422(self, auth_client, two_files):
        first, _ = two_files
        resp = auth_client.patch(
            f"/api/files/{first}/privacy", json={"privacy_level": "nope"}
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_privacy_level"

    def test_another_users_file_is_a_404(self, auth_client, other_client):
        their_session = other_client.post(
            "/api/sessions", json={"title": "Theirs"}
        ).json()["id"]
        their_file = _upload(other_client, their_session, "theirs.csv", _ORDERS_CSV)
        resp = auth_client.patch(
            f"/api/files/{their_file}/privacy", json={"privacy_level": "schema"}
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "File not found"

    def test_patch_null_clears_the_aliases(
        self, auth_client, session_id, two_files, store, user_id
    ):
        first, _ = two_files
        source = _columns(store, first, user_id)[1]
        auth_client.patch(
            f"/api/files/{first}/privacy",
            json={"column_aliases": {source: "col_renamed"}},
        )
        resp = auth_client.patch(
            f"/api/files/{first}/privacy", json={"column_aliases": None}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["column_aliases"] is None
        # The outgoing copy goes back to the real column name.
        preview = _preview(auth_client, session_id)
        target = next(
            entry for entry in preview["profiles"] if entry["file_id"] == first
        )
        assert source in [c["name"] for c in target["profile"]["columns"]]

    def test_a_duplicate_alias_is_a_422(
        self, auth_client, session_id, two_files, store, user_id
    ):
        """D6: two source columns cannot collapse into one outgoing key."""
        first, _ = two_files
        columns = _columns(store, first, user_id)
        resp = auth_client.patch(
            f"/api/files/{first}/privacy",
            json={"column_aliases": {columns[0]: "col_x", columns[1]: "col_x"}},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_column_alias"

    def test_an_empty_alias_is_a_422(
        self, auth_client, session_id, two_files, store, user_id
    ):
        first, _ = two_files
        source = _columns(store, first, user_id)[0]
        resp = auth_client.patch(
            f"/api/files/{first}/privacy",
            json={"column_aliases": {source: "   "}},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_column_alias"

    def test_a_file_without_a_profile_cannot_take_aliases(
        self, auth_client, session_id, store, user_id
    ):
        """A file row with no profile row (legacy/failed upload) has no columns
        to validate an alias against, so the API answers 409 -- not a 422 that
        would blame the alias, and not a 500.

        The row is seeded directly so the atomic upload path (file + profile)
        cannot hide this state.
        """
        row = asyncio.run(
            store.create_file(
                user_id=user_id,
                chat_session=session_id,
                filename="no-profile.csv",
                storage_path=f"/nonexistent/{session_id}/no-profile.csv",
                size_bytes=10,
                format_val="csv",
            )
        )
        resp = auth_client.patch(
            f"/api/files/{row['id']}/privacy",
            json={"column_aliases": {"a": "col_1"}},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "profile_unavailable"


class TestPreview:
    def test_preview_equals_the_outgoing_dataset_block(
        self, auth_client, session_id, two_files, store, user_id
    ):
        """S5: the viewer is the SAME code path the chat ships, not a copy."""
        preview = _preview(auth_client, session_id)
        outgoing = asyncio.run(
            build_outgoing_datasets(store, user_id=user_id, chat_session=session_id)
        )
        assert preview["profiles"] == outgoing["profiles"]
        assert preview["unprofiled_files"] == outgoing["unprofiled_files"]
        # The sandbox map never leaves the server.
        assert set(preview) == {"profiles", "unprofiled_files"}

    def test_no_absolute_storage_path_survives_at_any_level(
        self, auth_client, session_id, two_files, store, user_id
    ):
        """D3/S3: the outgoing path is a staged name, never the real location."""
        for level in PRIVACY_LEVELS:
            _set_session_level(auth_client, session_id, level)
            preview = _preview(auth_client, session_id)
            blob = json.dumps(preview)
            for file_id in two_files:
                real = asyncio.run(store.get_file(file_id, user_id))["storage_path"]
                assert real not in blob
            for profile in preview["profiles"]:
                assert profile["path"].startswith("dataset_")
                assert "/" not in profile["path"]

    @pytest.mark.parametrize("level", ["aggregates", "schema", "masked", "full"])
    def test_preview_per_level(
        self, auth_client, session_id, two_files, store, user_id, level
    ):
        _set_session_level(auth_client, session_id, level)
        preview = _preview(auth_client, session_id)
        assert len(preview["profiles"]) == 2
        for entry in preview["profiles"]:
            redacted = entry["profile"]
            raw = asyncio.run(get_profile(store, entry["file_id"], user_id))
            if level == "aggregates":
                # S1: no sample values and no sample rows; aggregates stay.
                assert redacted["sample"] == []
                for name, values in redacted["stats"].items():
                    assert "sample_values" not in values
                    assert values["mean"] == raw["stats"][name]["mean"]
            elif level == "schema":
                # S1: only columns survive.
                assert redacted["stats"] == {}
                assert redacted["sample"] == []
                assert redacted["columns"]
            elif level == "masked":
                # S1/D4/D5: masked values with their shape, dropping the
                # aggregates that would disclose the hidden content.
                assert redacted["sample"]
                for values in redacted["stats"].values():
                    assert values["sample_values"]
                    for key in ("min", "max", "mean", "std"):
                        assert key not in values
                for row in redacted["sample"]:
                    assert all(
                        not isinstance(value, (int, float))
                        for value in row.values()
                    )
            else:
                # S1/S7: full is the original payload.
                assert redacted == {
                    "columns": raw["schema_data"]["columns"],
                    "stats": raw["stats"],
                    "sample": raw["sample"][:5],
                }

    def test_a_stored_alias_renames_the_outgoing_columns_only(
        self, auth_client, session_id, two_files, store, user_id
    ):
        """S6/D6: aliases live in the outgoing copy; the DB keeps the real name."""
        first, _ = two_files
        source = _columns(store, first, user_id)[1]
        auth_client.patch(
            f"/api/files/{first}/privacy",
            json={"column_aliases": {source: "col_renamed"}},
        )
        preview = _preview(auth_client, session_id)
        target = next(
            entry for entry in preview["profiles"] if entry["file_id"] == first
        )
        assert "col_renamed" in [c["name"] for c in target["profile"]["columns"]]
        assert source not in [c["name"] for c in target["profile"]["columns"]]
        assert "col_renamed" in target["profile"]["stats"]
        # The real name is still the one the API and the DB report.
        assert source in _columns(store, first, user_id)

    @pytest.mark.parametrize("level", ["full", "aggregates", "schema", "masked"])
    def test_an_alias_applies_at_every_level(
        self, auth_client, session_id, two_files, store, user_id, level
    ):
        """D6: aliases apply to columns AND to the stats/sample keys so the
        outgoing payload stays internally consistent at every level."""
        first, _ = two_files
        _set_session_level(auth_client, session_id, level)
        source = _columns(store, first, user_id)[1]
        auth_client.patch(
            f"/api/files/{first}/privacy",
            json={"column_aliases": {source: "col_renamed"}},
        )
        preview = _preview(auth_client, session_id)
        target = next(
            entry for entry in preview["profiles"] if entry["file_id"] == first
        )
        redacted = target["profile"]
        assert "col_renamed" in [c["name"] for c in redacted["columns"]]
        assert source not in [c["name"] for c in redacted["columns"]]
        if level != "schema":
            assert "col_renamed" in redacted["stats"]
            assert source not in redacted["stats"]
        if level in ("full", "masked"):
            assert redacted["sample"]
            assert all("col_renamed" in row for row in redacted["sample"])

    def test_preview_lists_a_file_without_a_profile_as_unprofiled(
        self, auth_client, session_id, store, user_id
    ):
        """A file row that cannot be profiled is reported to the viewer instead
        of being silently dropped from the outgoing block."""
        row = asyncio.run(
            store.create_file(
                user_id=user_id,
                chat_session=session_id,
                filename="no-profile.csv",
                storage_path=f"/nonexistent/{session_id}/no-profile.csv",
                size_bytes=10,
                format_val="csv",
            )
        )
        preview = _preview(auth_client, session_id)
        assert preview["profiles"] == []
        assert preview["unprofiled_files"] == [
            {"file_id": row["id"], "filename": "no-profile.csv", "format": "csv"}
        ]

    def test_preview_of_another_users_session_is_a_404(self, other_client, session_id):
        resp = other_client.get(f"/api/sessions/{session_id}/privacy/preview")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chat session not found"
