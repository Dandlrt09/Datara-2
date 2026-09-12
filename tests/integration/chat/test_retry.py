"""Retry semantics for the chat turn endpoint.

Failed turns (LLM error, sandbox error) must persist nothing — a
persisted text-only assistant bubble would show the model's unverified
explanation as if it were an answer — and ``retry: true`` must re-run
the last question without duplicating the user message. Every stream
exit path must publish STREAMING_ENDED [R7].
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import event_bus
from server.api.routers import auth as auth_router
from server.api.routers import chat as chat_router
from server.api.routers import files as files_router
from server.api.routers import sessions as sessions_router
from server.services.events import SessionEventType
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations


@pytest.fixture
def app():
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(chat_router.router)
    application.include_router(files_router.router)

    import asyncio

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
def store():
    from server.api import store as api_store  # noqa: PLC0415
    return api_store._store


@pytest.fixture
def auth_cookie(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "retry@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


@pytest.fixture
def session_id(client, auth_cookie):
    resp = client.post(
        "/api/sessions",
        json={"title": "Retry test"},
        headers={"Cookie": auth_cookie},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_openai_fake(content: str) -> MagicMock:
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


def _valid_json_response() -> str:
    return json.dumps({
        "code": "print('retry ok')",
        "explanation": "Retry turn succeeded.",
    })


class _CapturingBus:
    def __init__(self):
        self.events = []

    def publish(self, user_id, event):
        self.events.append(event)


class TestRetrySemantics:
    async def test_retry_does_not_duplicate_user_message(
        self, client, auth_cookie, session_id, store
    ):
        """retry:true re-runs the turn without persisting a second question."""
        mock_create = AsyncMock(return_value=_make_openai_fake(_valid_json_response()))
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client

            first = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "hola"},
                headers={"Cookie": auth_cookie},
            )
            retry = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "hola", "retry": True},
                headers={"Cookie": auth_cookie},
            )
        assert first.status_code == 200
        assert retry.status_code == 200

        user = await store.get_user_by_email("retry@example.com")
        msgs = await store.list_messages(user["id"], session_id)
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
        assert len(user_msgs) == 1, (
            f"Expected exactly 1 user message, got {len(user_msgs)}"
        )
        assert len(assistant_msgs) == 2  # one per streamed turn

    async def test_llm_error_persists_nothing_and_retry_recovers(
        self, client, auth_cookie, session_id, store
    ):
        """LLM-error turn persists nothing; a later retry succeeds cleanly."""
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=openai.APITimeoutError("timeout")
            )
            mock_client_cls.return_value = mock_client

            failed = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "pregunta que falla"},
                headers={"Cookie": auth_cookie},
            )
            assert failed.status_code == 200
            assert "event: error" in failed.text
            assert "event: done" not in failed.text

            user = await store.get_user_by_email("retry@example.com")
            msgs = await store.list_messages(user["id"], session_id)
            assert [m["role"] for m in msgs] == ["user"], (
                "Failed LLM turn must persist only the user message"
            )

            # Retry with a working provider
            mock_client.chat.completions.create = AsyncMock(
                return_value=_make_openai_fake(_valid_json_response())
            )
            retry = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "pregunta que falla", "retry": True},
                headers={"Cookie": auth_cookie},
            )
            assert retry.status_code == 200
            assert "event: done" in retry.text

            msgs = await store.list_messages(user["id"], session_id)
            roles = sorted(m["role"] for m in msgs)
            assert roles == ["assistant", "user"], (
                "Retry must not duplicate the question; it must add one answer"
            )

    async def test_sandbox_error_persists_nothing(
        self, client, auth_cookie, session_id, store
    ):
        """A sandbox-error turn persists no assistant bubble (no lying text)."""
        lying_response = json.dumps({
            "code": "raise ValueError('boom')",
            "explanation": "The average is 42 (never computed).",
        })
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=_make_openai_fake(lying_response)
            )
            mock_client_cls.return_value = mock_client

            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "rompe el sandbox"},
                headers={"Cookie": auth_cookie},
            )
        assert resp.status_code == 200
        assert "event: error" in resp.text
        assert "event: done" not in resp.text

        user = await store.get_user_by_email("retry@example.com")
        msgs = await store.list_messages(user["id"], session_id)
        assert [m["role"] for m in msgs] == ["user"], (
            "Sandbox-error turn must persist only the user message — "
            "the model's explanation was never computed"
        )

    def test_streaming_ended_published_on_llm_error_path(
        self, client, auth_cookie, session_id, monkeypatch
    ):
        """Early `return` error paths must still emit STREAMING_ENDED [R7]."""
        cap = _CapturingBus()
        monkeypatch.setattr(event_bus, "bus", cap)

        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=openai.APITimeoutError("timeout")
            )
            mock_client_cls.return_value = mock_client

            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "timeout turn"},
                headers={"Cookie": auth_cookie},
            )
        assert resp.status_code == 200
        ended = [e for e in cap.events if e.type == SessionEventType.STREAMING_ENDED]
        assert ended, (
            "STREAMING_ENDED must be published on the LLM error path; "
            f"got types {[str(e.type) for e in cap.events]}"
        )
