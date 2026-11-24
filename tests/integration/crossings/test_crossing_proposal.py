"""Integration tests for the LLM-guided crossing proposal (F5 / T4, S3).

S3 asks Datara to read every profile, PROPOSE the key columns and the join
kind, and let the analyst confirm or adjust before anything is crossed. These
tests pin exactly that: the proposal comes from the profiles of BOTH files,
an answer that names a column the dataset does not have is refused (never
silently accepted), and proposing stores NOTHING — the analyst still confirms
through ``POST /sessions/{id}/crossings``.

The LLM seam is the same one the chat integration tests use: patch the
``AsyncOpenAI`` constructor in ``server.services.llm_openai`` and stub
``chat.completions.create``. Everything the proposal adds on top (the prompt,
the provider resolution, the fence stripping and JSON parse) stays real.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.errors import LLMTimeoutError
from server.api.routers import auth as auth_router
from server.api.routers import crossings as crossings_router
from server.api.routers import files as files_router
from server.api.routers import sessions as sessions_router
from server.api.upload_guard import install_upload_guard
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations, register_verified

_CUSTOMERS_CSV = b"customer_id,name\n1,Ana\n2,Beto\n3,Caro\n4,Dani\n"
_ORDERS_CSV = b"order_id,customer_id,total\n10,1,100\n11,1,50\n12,2,75\n13,10,20\n"

_VALID_PROPOSAL = {
    "left_key": "customer_id",
    "right_key": "customer_id",
    "how": "inner",
    "reason": "Ambos datasets comparten customer_id.",
}


@pytest.fixture
def app(tmp_path, monkeypatch):
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(files_router.router)
    application.include_router(crossings_router.router)
    install_upload_guard(application)

    # Isolation: uploads land in a per-test tmp dir, never the real
    # server/uploads/.
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
def auth_client(client):
    """Register a verified user and return a client with a valid session cookie."""
    cookie = register_verified(client, "test@example.com").headers["set-cookie"]
    client.headers["Cookie"] = cookie
    return client


@pytest.fixture
def session_id(auth_client):
    resp = auth_client.post("/api/sessions", json={"title": "Proposal session"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _upload(auth_client, session_id, filename, content):
    resp = auth_client.post(
        f"/api/sessions/{session_id}/files",
        files={"file": (filename, content, "text/csv")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
def two_files(auth_client, session_id):
    """Two profiled CSVs in one session, sharing ``customer_id``."""
    left = _upload(auth_client, session_id, "customers.csv", _CUSTOMERS_CSV)
    right = _upload(auth_client, session_id, "orders.csv", _ORDERS_CSV)
    return left, right


def _url(session_id) -> str:
    return f"/api/sessions/{session_id}/crossings/propose"


def _body(left, right) -> dict:
    return {"left_file_id": left, "right_file_id": right}


def _make_openai_fake(content: str) -> MagicMock:
    """Build a MagicMock that looks like an OpenAI ChatCompletion response."""
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"

    usage = MagicMock()
    usage.prompt_tokens = 50
    usage.completion_tokens = 100

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model = "gpt-4o-2024-08-06"
    response.to_dict = MagicMock(return_value={"id": "fake"})
    return response


@pytest.fixture
def llm():
    """Stub the provider call exactly like the chat integration tests do.

    Only the OpenAI client constructor is patched; the provider resolution,
    the JSON parse and the fence stripping all run for real.
    """
    mock_create = AsyncMock(return_value=_make_openai_fake(json.dumps(_VALID_PROPOSAL)))
    with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        mock_client_cls.return_value = mock_client
        yield mock_create


def _prompt_of(mock_create) -> str:
    """The full prompt text the stub received, system + user messages joined."""
    messages = mock_create.call_args.kwargs["messages"]
    return "\n".join(message["content"] for message in messages)


class TestProposalHappyPath:
    def test_a_usable_answer_is_returned_as_the_proposal(
        self, auth_client, session_id, two_files, llm
    ):
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"proposal": _VALID_PROPOSAL, "code": None}

    def test_the_prompt_is_built_from_both_profiles(
        self, auth_client, session_id, two_files, llm
    ):
        """Both filenames, their columns and dtypes travel in the prompt."""
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text

        prompt = _prompt_of(llm)
        assert "customers.csv" in prompt
        assert "orders.csv" in prompt
        # Columns of both sides (the profile's schema_data).
        for column in ("customer_id", "name", "order_id", "total"):
            assert column in prompt
        # Dtypes and sample values the profile already carries.
        assert "int64" in prompt
        assert "Ana" in prompt
        # Exactly one LLM call: the proposal is its own single call.
        assert llm.call_count == 1

    def test_a_fenced_answer_is_parsed_by_the_provider(
        self, auth_client, session_id, two_files, llm
    ):
        """The provider's fence stripping is reused, not re-implemented."""
        llm.return_value = _make_openai_fake(
            "```json\n" + json.dumps(_VALID_PROPOSAL) + "\n```"
        )
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"proposal": _VALID_PROPOSAL, "code": None}


class TestProposalRefusals:
    def test_a_proposed_key_that_is_not_a_column_is_refused(
        self, auth_client, session_id, two_files, llm
    ):
        """A4's spirit: an invented key is refused, never silently accepted."""
        llm.return_value = _make_openai_fake(
            json.dumps(
                {
                    "left_key": "no_such_column",
                    "right_key": "customer_id",
                    "how": "inner",
                    "reason": "Parece la mejor llave.",
                }
            )
        )
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["proposal"] is None
        assert data["code"] == "proposal_not_found"
        assert "no_such_column" in data["reason"]

    def test_a_right_key_that_is_not_a_column_is_refused(
        self, auth_client, session_id, two_files, llm
    ):
        llm.return_value = _make_openai_fake(
            json.dumps(
                {
                    "left_key": "customer_id",
                    "right_key": "no_such_column",
                    "how": "inner",
                    "reason": "Parece la mejor llave.",
                }
            )
        )
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        data = resp.json()
        assert data["proposal"] is None
        assert data["code"] == "proposal_not_found"
        assert "no_such_column" in data["reason"]

    def test_a_malformed_answer_is_not_a_proposal(
        self, auth_client, session_id, two_files, llm
    ):
        llm.return_value = _make_openai_fake("```json\nthis is not json\n```")
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["proposal"] is None
        assert data["code"] == "proposal_not_found"
        assert data["reason"]

    def test_the_model_saying_there_is_no_shared_column(
        self, auth_client, session_id, two_files, llm
    ):
        llm.return_value = _make_openai_fake(
            json.dumps(
                {
                    "left_key": None,
                    "right_key": None,
                    # The schema still demands a join kind; the validator
                    # ignores it because there is no key to join on.
                    "how": "inner",
                    "reason": "No hay columnas en común.",
                }
            )
        )
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "proposal": None,
            "code": "proposal_not_found",
            "reason": "No hay columnas en común.",
        }

    def test_a_file_against_itself_is_refused_with_the_confirm_shape(
        self, auth_client, session_id, two_files
    ):
        """Same 422 the confirm POST uses, so proposing cannot set up a trap."""
        left, _ = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, left))
        assert resp.status_code == 422
        assert resp.json()["detail"] == {
            "code": "crossing_same_file",
            "message": "A dataset cannot be crossed with itself.",
        }


class TestProposalStoresNothing:
    def test_get_still_reports_no_crossing_after_a_proposal(
        self, auth_client, session_id, two_files, llm
    ):
        left, right = two_files
        assert auth_client.post(_url(session_id), json=_body(left, right)).status_code == 200
        resp = auth_client.get(f"/api/sessions/{session_id}/crossings")
        assert resp.status_code == 200
        assert resp.json() == {"crossing": None}

    def test_a_refused_proposal_also_stores_nothing(
        self, auth_client, session_id, two_files, llm
    ):
        llm.return_value = _make_openai_fake(
            json.dumps(
                {
                    "left_key": "no_such_column",
                    "right_key": "customer_id",
                    "how": "inner",
                    "reason": "Parece la mejor llave.",
                }
            )
        )
        left, right = two_files
        auth_client.post(_url(session_id), json=_body(left, right))
        assert auth_client.get(f"/api/sessions/{session_id}/crossings").json() == {
            "crossing": None
        }


class TestProposalOwnership:
    def test_a_file_of_another_session_is_refused(
        self, auth_client, session_id, two_files
    ):
        left, _ = two_files
        other = auth_client.post("/api/sessions", json={"title": "Other"}).json()["id"]
        foreign = _upload(auth_client, other, "foreign.csv", _ORDERS_CSV)
        resp = auth_client.post(_url(session_id), json=_body(left, foreign))
        assert resp.status_code == 404
        assert resp.json()["detail"] == "File not found"

    def test_a_file_of_another_user_is_refused(self, client, session_id, two_files):
        left, _ = two_files
        client.headers.pop("Cookie", None)
        other_cookie = register_verified(client, "other@example.com").headers["set-cookie"]
        client.headers["Cookie"] = other_cookie
        their_session = client.post("/api/sessions", json={"title": "Theirs"}).json()["id"]
        their_file = _upload(client, their_session, "theirs.csv", _ORDERS_CSV)
        resp = client.post(_url(their_session), json=_body(left, their_file))
        assert resp.status_code == 404
        assert resp.json()["detail"] == "File not found"

    def test_an_unknown_session_is_refused(self, auth_client, two_files):
        left, right = two_files
        resp = auth_client.post(_url("no-such-session"), json=_body(left, right))
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chat session not found"

    def test_proposing_requires_a_session(self, app):
        """No cookie: the same 401 the chat path answers with."""
        anonymous = TestClient(app)
        resp = anonymous.post(_url("whatever"), json=_body(1, 2))
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Not authenticated"


class TestProposalProviderFailures:
    def test_a_provider_call_failure_never_becomes_a_proposal_or_a_500(
        self, auth_client, session_id, two_files, llm
    ):
        llm.side_effect = LLMTimeoutError("OpenAI call timed out after 120s")
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["proposal"] is None
        assert data["code"] == "proposal_unavailable"
        assert data["reason"]

    def test_no_provider_configured_answers_like_the_chat_path(
        self, auth_client, session_id, two_files
    ):
        """No provider/key: 200 with no proposal, never a 500.

        The chat path builds the provider inside its stream and answers the
        resulting failure with an HTTP 200 error payload; a JSON endpoint
        keeps that status and the same refusal shape (``proposal: null`` plus
        the reason).
        """
        left, right = two_files
        with patch(
            "server.services.llm_openai.AsyncOpenAI",
            side_effect=openai.OpenAIError(
                "Missing credentials. Please pass an `api_key` or set the "
                "`OPENAI_API_KEY` environment variable."
            ),
        ):
            resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["proposal"] is None
        assert data["code"] == "proposal_unavailable"
        assert data["reason"]


class TestProposalCodes:
    """The refusal code splits "we could not ask" from "nothing came out"."""

    def test_provider_unavailable_code_when_the_provider_cannot_be_consulted(
        self, auth_client, session_id, two_files, llm
    ):
        llm.side_effect = LLMTimeoutError("OpenAI call timed out after 120s")
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == "proposal_unavailable"

    def test_proposal_not_found_code_when_the_model_answer_is_unusable(
        self, auth_client, session_id, two_files, llm
    ):
        llm.return_value = _make_openai_fake(
            json.dumps(
                {
                    "left_key": "no_such_column",
                    "right_key": "customer_id",
                    "how": "inner",
                    "reason": "Parece la mejor llave.",
                }
            )
        )
        left, right = two_files
        resp = auth_client.post(_url(session_id), json=_body(left, right))
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == "proposal_not_found"
