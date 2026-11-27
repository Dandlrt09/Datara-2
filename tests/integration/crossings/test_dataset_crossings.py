"""Integration tests for the dataset crossing recipe (F5 / T1, S4).

A crossing is the persisted answer to "these two files of this session are
crossed on these keys, this way". The rule under test is not the merge math
(that is T2): it is that the recipe is stored once per session, that only the
session's own files can take part, and that a key which is not a column of the
dataset is refused instead of silently merging nothing.
"""

from __future__ import annotations

import asyncio
import io

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers import auth as auth_router
from server.api.routers import crossings as crossings_router
from server.api.routers import files as files_router
from server.api.routers import sessions as sessions_router
from server.api.routers.chat import build_system_prompt
from server.api.upload_guard import install_upload_guard
from server.services.chat_context import build_chat_context
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations, register_verified

# The two fixtures are deliberately unbalanced (S6): customer 3 and customer 4
# never place an order, and order 13 belongs to customer 10, who is not in the
# customers file. Exact counts: matched pairs 3, left-only 2, right-only 1.
_CUSTOMERS_CSV = b"customer_id,name\n1,Ana\n2,Beto\n3,Caro\n4,Dani\n"
_ORDERS_CSV = b"order_id,customer_id,total\n10,1,100\n11,1,50\n12,2,75\n13,10,20\n"
_STRING_KEYS_CSV = b"customer_id,name\n" + b"x,Ana\n"

_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(files_router.router)
    application.include_router(crossings_router.router)
    install_upload_guard(application)

    # Isolation: uploads must land in a per-test tmp dir, never the real
    # server/uploads/. The crossing route reads the stored file to validate
    # its keys, so the path has to be real for the tests that cross files.
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
def session_id(auth_client):
    resp = auth_client.post("/api/sessions", json={"title": "Crossing session"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _upload(auth_client, session_id, filename, content):
    resp = auth_client.post(
        f"/api/sessions/{session_id}/files",
        files={"file": (filename, content, "text/csv")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def _upload_xlsx(auth_client, session_id, filename, sheets):
    resp = auth_client.post(
        f"/api/sessions/{session_id}/files",
        files={"file": (filename, _xlsx_bytes(sheets), _XLSX_MIME)},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
def two_files(auth_client, session_id):
    """Two profiled CSVs in one session, sharing ``customer_id``."""
    left = _upload(auth_client, session_id, "customers.csv", _CUSTOMERS_CSV)
    right = _upload(auth_client, session_id, "orders.csv", _ORDERS_CSV)
    return left, right


def _body(left, right, left_key="customer_id", right_key="customer_id", how="inner"):
    return {
        "left_file_id": left,
        "right_file_id": right,
        "left_key": left_key,
        "right_key": right_key,
        "how": how,
    }


class TestCreateCrossing:
    def test_create_returns_the_stored_recipe(self, auth_client, session_id, two_files):
        left, right = two_files
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(left, right)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["chat_session"] == session_id
        assert data["left_file_id"] == left
        assert data["right_file_id"] == right
        assert data["left_filename"] == "customers.csv"
        assert data["right_filename"] == "orders.csv"
        assert data["left_key"] == "customer_id"
        assert data["right_key"] == "customer_id"
        assert data["how"] == "inner"
        assert data["id"] > 0
        assert data["created_at"]

    def test_get_returns_the_created_recipe(self, auth_client, session_id, two_files):
        left, right = two_files
        auth_client.post(f"/api/sessions/{session_id}/crossings", json=_body(left, right))
        resp = auth_client.get(f"/api/sessions/{session_id}/crossings")
        assert resp.status_code == 200
        crossing = resp.json()["crossing"]
        assert crossing is not None
        assert crossing["left_key"] == "customer_id"
        assert crossing["how"] == "inner"

    def test_get_is_null_when_no_crossing_was_confirmed(self, auth_client, session_id):
        resp = auth_client.get(f"/api/sessions/{session_id}/crossings")
        assert resp.status_code == 200
        assert resp.json() == {"crossing": None}

    def test_only_one_crossing_stays_active_per_session(
        self, auth_client, session_id, two_files
    ):
        """S5: one crossing. Confirming a second one replaces the first."""
        left, right = two_files
        auth_client.post(
            f"/api/sessions/{session_id}/crossings",
            json=_body(left, right, how="inner"),
        )
        second = auth_client.post(
            f"/api/sessions/{session_id}/crossings",
            json=_body(left, right, how="left"),
        )
        assert second.status_code == 200, second.text
        crossing = auth_client.get(f"/api/sessions/{session_id}/crossings").json()["crossing"]
        assert crossing["how"] == "left"
        assert crossing["id"] == second.json()["id"]

    def test_a_second_session_keeps_its_own_crossing(
        self, auth_client, session_id, two_files
    ):
        """The "one active" rule is per session, not per user."""
        left, right = two_files
        auth_client.post(f"/api/sessions/{session_id}/crossings", json=_body(left, right))
        other = auth_client.post("/api/sessions", json={"title": "Other"}).json()["id"]
        assert auth_client.get(f"/api/sessions/{other}/crossings").json() == {"crossing": None}

    def test_delete_removes_the_active_crossing(self, auth_client, session_id, two_files):
        left, right = two_files
        auth_client.post(f"/api/sessions/{session_id}/crossings", json=_body(left, right))
        resp = auth_client.delete(f"/api/sessions/{session_id}/crossings")
        assert resp.status_code == 204
        assert auth_client.get(f"/api/sessions/{session_id}/crossings").json() == {
            "crossing": None
        }

    def test_a_failed_delete_rolls_back_and_keeps_the_crossing(
        self, auth_client, session_id, two_files, store, user_id, monkeypatch
    ):
        """R4-delete-no-rollback (F5 review): when the delete cannot commit, the
        crossing must survive. Without the rollback the removal stays pending in
        the open transaction, so the connection's NEXT commit persists it: a
        failed "quitar cruce" would silently take effect later.

        The commit is forced to raise, the only way to reach the rollback path;
        monkeypatching the connection keeps the test at the real transaction
        boundary instead of mocking the store method.
        """
        left, right = two_files
        created = auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(left, right)
        )
        assert created.status_code == 200

        attempts = {"commit": 0}

        async def flaky_commit():
            attempts["commit"] += 1
            raise RuntimeError("forced failure at the delete's commit")

        monkeypatch.setattr(store.conn, "commit", flaky_commit)

        with pytest.raises(RuntimeError, match="forced failure"):
            asyncio.run(store.delete_crossing(user_id, session_id))

        # The commit was really attempted: the failure hit where intended.
        assert attempts["commit"] == 1
        # Rolled back, so the crossing the analyst had is still the active one.
        assert asyncio.run(store.get_crossing(user_id, session_id)) is not None


class TestCrossingPromptUsesStagedLabels:
    """S7: the F5 crossing survives the F6 filename neutralization.

    The stored recipe still carries the real filenames (it is user-facing), so
    the guard matches by ``file_id`` and the prompt prints the staged label
    ('dataset_N.ext'), never the human name.
    """

    def test_prompt_renders_the_staged_labels_not_the_real_names(
        self, auth_client, session_id, two_files, store, user_id
    ):
        left, right = two_files
        auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(left, right)
        )
        context = asyncio.run(
            build_chat_context(store, user_id=user_id, chat_session=session_id)
        )
        prompt = build_system_prompt(context["profiles"], crossing=context["crossing"])
        staged = {p["file_id"]: p["path"] for p in context["profiles"]}
        assert (
            f"- left dataset: '{staged[left]}' (read it from its 'path' above), "
            "key 'customer_id'"
        ) in prompt
        assert (
            f"- right dataset: '{staged[right]}' (read it from its 'path' above), "
            "key 'customer_id'"
        ) in prompt
        assert "customers.csv" not in prompt
        assert "orders.csv" not in prompt


class TestCreateCrossingRejections:
    def test_a_key_that_is_not_a_column_is_refused(
        self, auth_client, session_id, two_files
    ):
        """A4: an unknown key is explicit, never a silently empty merge."""
        left, right = two_files
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings",
            json=_body(left, right, left_key="no_such_column"),
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "crossing_key_not_in_dataset"
        assert "no_such_column" in detail["message"]
        # Rejected input must leave the stored state untouched.
        assert auth_client.get(f"/api/sessions/{session_id}/crossings").json() == {
            "crossing": None
        }

    def test_the_right_key_is_validated_too(self, auth_client, session_id, two_files):
        left, right = two_files
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings",
            json=_body(left, right, right_key="total_amount"),
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "crossing_key_not_in_dataset"

    def test_a_file_of_another_session_is_refused(
        self, auth_client, session_id, two_files
    ):
        left, _ = two_files
        other = auth_client.post("/api/sessions", json={"title": "Other"}).json()["id"]
        foreign = _upload(auth_client, other, "foreign.csv", _ORDERS_CSV)
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(left, foreign)
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "File not found"

    def test_a_file_of_another_user_is_refused(self, client, session_id, two_files):
        left, _ = two_files
        client.headers.pop("Cookie", None)
        other_cookie = register_verified(client, "other@example.com").headers["set-cookie"]
        client.headers["Cookie"] = other_cookie
        # Their own session, with their own file.
        their_session = client.post("/api/sessions", json={"title": "Theirs"}).json()["id"]
        their_file = _upload(client, their_session, "theirs.csv", _ORDERS_CSV)
        resp = client.post(
            f"/api/sessions/{their_session}/crossings",
            json=_body(left, their_file),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "File not found"

    def test_the_same_file_on_both_sides_is_refused(
        self, auth_client, session_id, two_files
    ):
        left, _ = two_files
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(left, left)
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "crossing_same_file"

    def test_an_unknown_session_is_refused(self, auth_client, two_files):
        left, right = two_files
        resp = auth_client.post("/api/sessions/no-such-session/crossings", json=_body(left, right))
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chat session not found"

    def test_an_unknown_join_kind_is_refused(self, auth_client, session_id, two_files):
        left, right = two_files
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings",
            json=_body(left, right, how="sideways"),
        )
        assert resp.status_code == 422

    def test_crossing_requires_a_session(self, app):
        """Ownership is per caller: no session cookie, no crossing answer.

        A fresh client is used instead of dropping the header off the shared
        one: the shared TestClient was registered with a cookie, and only a
        client that never had one proves the anonymous path.
        """
        anonymous = TestClient(app)
        resp = anonymous.get("/api/sessions/whatever/crossings")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Not authenticated"
        resp = anonymous.post(
            "/api/sessions/whatever/crossings",
            json={
                "left_file_id": 1,
                "right_file_id": 2,
                "left_key": "a",
                "right_key": "b",
            },
        )
        assert resp.status_code == 401
        resp = anonymous.delete("/api/sessions/whatever/crossings")
        assert resp.status_code == 401


class TestCrossingDiagnostics:
    """S6: the crossing reports what it matched and what fell out on each side."""

    def test_reports_the_exact_imbalance_on_both_sides(
        self, auth_client, session_id, two_files
    ):
        left, right = two_files
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(left, right)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["diagnostics"] == {
            "left_rows": 4,
            "right_rows": 4,
            "matched_rows": 3,
            "left_only_rows": 2,
            "right_only_rows": 1,
            "result_rows": 3,
        }

    def test_the_imbalance_does_not_depend_on_the_join_kind(
        self, auth_client, session_id, two_files
    ):
        """An inner join drops the orphans; the report must not.

        Matched and orphan counts describe the DATA and the keys, so they read
        the same whichever join the analyst picks; only ``result_rows`` follows
        the join kind. That is the difference between reporting the imbalance
        and letting the chosen join hide it.
        """
        left, right = two_files
        reports = []
        for how in ("inner", "outer"):
            resp = auth_client.post(
                f"/api/sessions/{session_id}/crossings", json=_body(left, right, how=how)
            )
            assert resp.status_code == 200, resp.text
            reports.append(resp.json()["diagnostics"])
        inner, outer = reports
        assert inner["left_only_rows"] == outer["left_only_rows"] == 2
        assert inner["right_only_rows"] == outer["right_only_rows"] == 1
        assert inner["matched_rows"] == outer["matched_rows"] == 3
        assert inner["result_rows"] == 3
        assert outer["result_rows"] == 6

    @pytest.mark.parametrize(
        ("how", "result_rows"),
        [("inner", 3), ("left", 5), ("right", 4), ("outer", 6)],
    )
    def test_result_rows_follow_the_chosen_join_kind(
        self, auth_client, session_id, two_files, how, result_rows
    ):
        left, right = two_files
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(left, right, how=how)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["diagnostics"]["result_rows"] == result_rows

    def test_a_dataset_missing_from_disk_is_refused(
        self, auth_client, session_id, two_files, store, user_id
    ):
        """A recipe that cannot run is refused now, not at query time."""
        _, right = two_files
        ghost = asyncio.run(
            store.create_file_with_profile(
                user_id=user_id,
                chat_session=session_id,
                filename="ghost.csv",
                storage_path=f"/nonexistent/{session_id}/ghost.csv",
                size_bytes=10,
                format_val="csv",
                schema_json='{"columns": [{"name": "customer_id", "dtype": "int64"}]}',
                stats_json="{}",
                sample_json="[]",
            )
        )
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(ghost["id"], right)
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "crossing_dataset_unreadable"
        assert "ghost.csv" in detail["message"]
        assert auth_client.get(f"/api/sessions/{session_id}/crossings").json() == {
            "crossing": None
        }

    def test_the_report_counts_the_active_sheet_of_a_workbook(
        self, auth_client, session_id, two_files
    ):
        """F3 crossed with F5: an XLSX is counted on its ACTIVE sheet.

        The first sheet holds four customers and the chosen one holds two, so a
        read that silently fell back to the first sheet would report 4 rows and
        2 orphans instead of 2 and 0.
        """
        _, right = two_files
        workbook = _upload_xlsx(
            auth_client,
            session_id,
            "customers.xlsx",
            {
                "Todos": pd.DataFrame({"customer_id": [1, 2, 3, 4]}),
                "Pares": pd.DataFrame({"customer_id": [1, 2]}),
            },
        )
        selected = auth_client.post(
            f"/api/files/{workbook}/sheet", json={"sheet_name": "Pares"}
        )
        assert selected.status_code == 200, selected.text

        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(workbook, right)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["diagnostics"] == {
            "left_rows": 2,
            "right_rows": 4,
            "matched_rows": 3,
            "left_only_rows": 0,
            "right_only_rows": 1,
            "result_rows": 3,
        }

    def test_keys_that_cannot_be_compared_are_refused(
        self, auth_client, session_id, two_files
    ):
        """Numbers on one side, text on the other: a refusal, not a traceback."""
        left, _ = two_files
        strings = _upload(auth_client, session_id, "strings.csv", _STRING_KEYS_CSV)
        resp = auth_client.post(
            f"/api/sessions/{session_id}/crossings", json=_body(left, strings)
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "crossing_keys_not_comparable"
        assert auth_client.get(f"/api/sessions/{session_id}/crossings").json() == {
            "crossing": None
        }
