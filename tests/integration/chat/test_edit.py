"""Edit-question (truncate) semantics for the chat turn endpoint.

Editing a user question deletes that turn and every later turn from the
session before re-asking the edited text as a normal turn. A corrected
question invalidates every answer computed from the previous one, so
truncation is intentional. These tests pin the truncation, the guard
errors, the conditional retitle, and the failure path.
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
from tests.test_helpers import apply_all_migrations, upload_csv


@pytest.fixture
def app(tmp_path, monkeypatch):
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(chat_router.router)
    application.include_router(files_router.router)

    monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")

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
        json={"email": "edit@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


@pytest.fixture
def session_id(client, auth_cookie):
    """Session with an attached dataset, so the sandbox turns can succeed."""
    resp = client.post(
        "/api/sessions",
        json={"title": "Edit test"},
        headers={"Cookie": auth_cookie},
    )
    assert resp.status_code == 201
    sid = resp.json()["id"]
    upload_csv(client, auth_cookie, sid)
    return sid


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
        "code": "print('edit ok')",
        "explanation": "Edit turn succeeded.",
    })


def _working_client() -> MagicMock:
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_openai_fake(_valid_json_response())
    )
    return mock_client


class _CapturingBus:
    """Minimal bus double: records every published SessionEvent."""

    def __init__(self):
        self.events = []

    def publish(self, user_id, event):
        self.events.append(event)


def _chat(client, auth_cookie, session_id, payload):
    return client.post(
        f"/api/sessions/{session_id}/chat",
        json=payload,
        headers={"Cookie": auth_cookie},
    )


async def _history(store, user_id, session_id):
    msgs = await store.list_messages(user_id, session_id)
    return sorted(
        ((m["id"], m["role"], m["content_text"]) for m in msgs),
        key=lambda row: row[0],
    )


class TestEditQuestionTruncation:
    async def test_edit_last_question_truncates_its_turn(
        self, client, auth_cookie, session_id, store
    ):
        """Editing the last question replaces the turn, not appends to it."""
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            first = _chat(
                client, auth_cookie, session_id, {"question": "pregunta original"}
            )
            assert first.status_code == 200
            assert "event: done" in first.text

            user = await store.get_user_by_email("edit@example.com")
            before = await _history(store, user["id"], session_id)
            original_user_id = next(r[0] for r in before if r[1] == "user")

            edited = _chat(
                client,
                auth_cookie,
                session_id,
                {
                    "question": "pregunta corregida",
                    "edit_message_id": original_user_id,
                },
            )
            assert edited.status_code == 200
            assert "event: done" in edited.text

        user = await store.get_user_by_email("edit@example.com")
        after = await _history(store, user["id"], session_id)
        assert [role for _, role, _ in after] == ["user", "assistant"]
        assert after[0][2] == "pregunta corregida"
        # Every pre-edit row is gone: the new turn replaced the old one.
        assert all(row_id > original_user_id for row_id, _, _ in after)

    async def test_edit_middle_question_removes_later_turn(
        self, client, auth_cookie, session_id, store
    ):
        """Editing an earlier question deletes every turn after it."""
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            assert (
                _chat(client, auth_cookie, session_id, {"question": "primera"}).status_code
                == 200
            )
            assert (
                _chat(client, auth_cookie, session_id, {"question": "segunda"}).status_code
                == 200
            )

            user = await store.get_user_by_email("edit@example.com")
            before = await _history(store, user["id"], session_id)
            # Two full turns: user/assistant/user/assistant.
            assert [role for _, role, _ in before] == [
                "user",
                "assistant",
                "user",
                "assistant",
            ]
            first_user_id = before[0][0]

            edited = _chat(
                client,
                auth_cookie,
                session_id,
                {
                    "question": "primera corregida",
                    "edit_message_id": first_user_id,
                },
            )
            assert edited.status_code == 200
            assert "event: done" in edited.text

        user = await store.get_user_by_email("edit@example.com")
        after = await _history(store, user["id"], session_id)
        assert [role for _, role, _ in after] == ["user", "assistant"]
        assert after[0][2] == "primera corregida"
        assert all(row_id > first_user_id for row_id, _, _ in after)

    async def test_regenerate_same_question_replaces_the_answer(
        self, client, auth_cookie, session_id, store
    ):
        """Regenerate is the edit path with the SAME question text.

        The frontend regenerates by re-posting the last user question with
        edit_message_id pointing at it. The contract is: the old answer is
        deleted and the session is left with exactly one question (same text)
        and one fresh assistant answer, so the model never sees its previous
        reply in context.
        """
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            first = _chat(
                client, auth_cookie, session_id, {"question": "pregunta original"}
            )
            assert first.status_code == 200
            assert "event: done" in first.text

            user = await store.get_user_by_email("edit@example.com")
            before = await _history(store, user["id"], session_id)
            assert [role for _, role, _ in before] == ["user", "assistant"]
            original_user_id = next(r[0] for r in before if r[1] == "user")
            original_assistant_id = next(r[0] for r in before if r[1] == "assistant")

            regenerated = _chat(
                client,
                auth_cookie,
                session_id,
                {
                    "question": "pregunta original",
                    "edit_message_id": original_user_id,
                },
            )
            assert regenerated.status_code == 200
            assert "event: done" in regenerated.text

        user = await store.get_user_by_email("edit@example.com")
        after = await _history(store, user["id"], session_id)
        # Exactly one question (same text) + one fresh assistant answer.
        assert [role for _, role, _ in after] == ["user", "assistant"]
        assert after[0][2] == "pregunta original"
        # The previous answer is gone and the question was re-persisted: both
        # rows are newer than the old answer, so no stale reply survives.
        assert all(row_id > original_assistant_id for row_id, _, _ in after)


class TestEditQuestionGuards:
    async def test_retry_and_edit_together_is_rejected(
        self, client, auth_cookie, session_id, store
    ):
        """retry + edit_message_id is a contradiction: 422, nothing deleted."""
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            assert (
                _chat(client, auth_cookie, session_id, {"question": "hola"}).status_code
                == 200
            )
            user = await store.get_user_by_email("edit@example.com")
            before = await _history(store, user["id"], session_id)
            user_id = next(r[0] for r in before if r[1] == "user")

            resp = _chat(
                client,
                auth_cookie,
                session_id,
                {
                    "question": "hola",
                    "retry": True,
                    "edit_message_id": user_id,
                },
            )
            assert resp.status_code == 422
            assert resp.json()["detail"]["code"] == "invalid_request"

        user = await store.get_user_by_email("edit@example.com")
        after = await _history(store, user["id"], session_id)
        assert after == before

    async def test_editing_an_assistant_message_is_rejected(
        self, client, auth_cookie, session_id, store
    ):
        """Only user questions can be edited: 422 invalid_edit_target."""
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            assert (
                _chat(client, auth_cookie, session_id, {"question": "hola"}).status_code
                == 200
            )
            user = await store.get_user_by_email("edit@example.com")
            before = await _history(store, user["id"], session_id)
            assistant_id = next(r[0] for r in before if r[1] == "assistant")

            resp = _chat(
                client,
                auth_cookie,
                session_id,
                {"question": "no se puede", "edit_message_id": assistant_id},
            )
            assert resp.status_code == 422
            assert resp.json()["detail"]["code"] == "invalid_edit_target"

        user = await store.get_user_by_email("edit@example.com")
        after = await _history(store, user["id"], session_id)
        assert after == before

    async def test_unknown_message_and_foreign_session_are_404(
        self, client, auth_cookie, session_id, store
    ):
        """Unknown ids and messages of another session leak nothing: 404."""
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            # Unknown id.
            unknown = _chat(
                client,
                auth_cookie,
                session_id,
                {"question": "x", "edit_message_id": 999999},
            )
            assert unknown.status_code == 404

            # A message that belongs to a different session.
            other = client.post(
                "/api/sessions",
                json={"title": "Other"},
                headers={"Cookie": auth_cookie},
            )
            other_id = other.json()["id"]
            assert (
                _chat(
                    client, auth_cookie, other_id, {"question": "otra"}
                ).status_code
                == 200
            )
            user = await store.get_user_by_email("edit@example.com")
            other_before = await _history(store, user["id"], other_id)
            foreign_message_id = other_before[0][0]

            foreign = _chat(
                client,
                auth_cookie,
                session_id,
                {"question": "x", "edit_message_id": foreign_message_id},
            )
            assert foreign.status_code == 404

        user = await store.get_user_by_email("edit@example.com")
        # Neither session lost a row.
        assert await _history(store, user["id"], session_id) == []
        assert await _history(store, user["id"], other_id) == other_before


class TestEditQuestionHistoryTruncatedEvent:
    async def test_history_truncated_published_on_successful_edit(
        self, client, auth_cookie, session_id, store, monkeypatch
    ):
        """A committed truncation emits HISTORY_TRUNCATED naming the first
        deleted id, so every client drops its invalidated pagination chain."""
        cap = _CapturingBus()
        monkeypatch.setattr(event_bus, "bus", cap)

        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            assert (
                _chat(
                    client, auth_cookie, session_id, {"question": "pregunta original"}
                ).status_code
                == 200
            )
            user = await store.get_user_by_email("edit@example.com")
            before = await _history(store, user["id"], session_id)
            original_user_id = next(r[0] for r in before if r[1] == "user")

            edited = _chat(
                client,
                auth_cookie,
                session_id,
                {
                    "question": "pregunta corregida",
                    "edit_message_id": original_user_id,
                },
            )
            assert edited.status_code == 200

        truncated = [
            e for e in cap.events if e.type == SessionEventType.HISTORY_TRUNCATED
        ]
        assert len(truncated) == 1, (
            "A successful edit must publish exactly one HISTORY_TRUNCATED; "
            f"got types {[str(e.type) for e in cap.events]}"
        )
        assert truncated[0].session_id == session_id
        assert truncated[0].payload["from_message_id"] == original_user_id

    async def test_history_truncated_not_published_on_rejected_paths(
        self, client, auth_cookie, session_id, store, monkeypatch
    ):
        """Guard failures (422/404) never truncate, so they never signal it."""
        cap = _CapturingBus()
        monkeypatch.setattr(event_bus, "bus", cap)

        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            assert (
                _chat(client, auth_cookie, session_id, {"question": "hola"}).status_code
                == 200
            )
            user = await store.get_user_by_email("edit@example.com")
            before = await _history(store, user["id"], session_id)
            user_id = next(r[0] for r in before if r[1] == "user")
            assistant_id = next(r[0] for r in before if r[1] == "assistant")

            cap.events.clear()

            # Editing an assistant message -> 422.
            assistant_target = _chat(
                client,
                auth_cookie,
                session_id,
                {"question": "x", "edit_message_id": assistant_id},
            )
            assert assistant_target.status_code == 422
            # Unknown id -> 404.
            unknown = _chat(
                client,
                auth_cookie,
                session_id,
                {"question": "x", "edit_message_id": 999999},
            )
            assert unknown.status_code == 404
            # retry + edit -> 422.
            retry_edit = _chat(
                client,
                auth_cookie,
                session_id,
                {
                    "question": "x",
                    "retry": True,
                    "edit_message_id": user_id,
                },
            )
            assert retry_edit.status_code == 422

        truncated = [
            e for e in cap.events if e.type == SessionEventType.HISTORY_TRUNCATED
        ]
        assert truncated == [], (
            "Rejected edit paths must never publish HISTORY_TRUNCATED; "
            f"got {truncated}"
        )


class TestEditQuestionRetitle:
    def _new_chat(self, client, auth_cookie):
        """A session with the default 'New chat' title (auto-title eligible)."""
        resp = client.post(
            "/api/sessions",
            json={},
            headers={"Cookie": auth_cookie},
        )
        assert resp.status_code == 201
        sid = resp.json()["id"]
        upload_csv(client, auth_cookie, sid)
        return sid

    async def test_editing_the_auto_titled_question_retitles_the_session(
        self, client, auth_cookie, store
    ):
        sid = self._new_chat(client, auth_cookie)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            assert (
                _chat(client, auth_cookie, sid, {"question": "pregunta vieja"}).status_code
                == 200
            )
            user = await store.get_user_by_email("edit@example.com")
            history = await _history(store, user["id"], sid)
            first_user_id = history[0][0]

            session = await store.get_chat_session(sid, user["id"])
            assert session["title"] == "pregunta vieja"

            assert (
                _chat(
                    client,
                    auth_cookie,
                    sid,
                    {"question": "pregunta nueva", "edit_message_id": first_user_id},
                ).status_code
                == 200
            )

        user = await store.get_user_by_email("edit@example.com")
        session = await store.get_chat_session(sid, user["id"])
        assert session["title"] == "pregunta nueva"

    async def test_editing_after_a_manual_rename_keeps_the_title(
        self, client, auth_cookie, store
    ):
        sid = self._new_chat(client, auth_cookie)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client_cls.return_value = _working_client()

            assert (
                _chat(client, auth_cookie, sid, {"question": "pregunta vieja"}).status_code
                == 200
            )
            user = await store.get_user_by_email("edit@example.com")
            history = await _history(store, user["id"], sid)
            first_user_id = history[0][0]

            renamed = client.patch(
                f"/api/sessions/{sid}",
                json={"title": "Mi título manual"},
                headers={"Cookie": auth_cookie},
            )
            assert renamed.status_code == 200

            assert (
                _chat(
                    client,
                    auth_cookie,
                    sid,
                    {"question": "pregunta nueva", "edit_message_id": first_user_id},
                ).status_code
                == 200
            )

        user = await store.get_user_by_email("edit@example.com")
        session = await store.get_chat_session(sid, user["id"])
        assert session["title"] == "Mi título manual"


class TestEditQuestionFailure:
    async def test_llm_failure_during_edit_keeps_only_the_new_question(
        self, client, auth_cookie, session_id, store
    ):
        """A failed edit persists only the new question, so Retry stays offered."""
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = _working_client()
            mock_client_cls.return_value = mock_client

            assert (
                _chat(client, auth_cookie, session_id, {"question": "original"}).status_code
                == 200
            )
            user = await store.get_user_by_email("edit@example.com")
            history = await _history(store, user["id"], session_id)
            first_user_id = history[0][0]

            mock_client.chat.completions.create = AsyncMock(
                side_effect=openai.APITimeoutError("timeout")
            )
            failed = _chat(
                client,
                auth_cookie,
                session_id,
                {"question": "corregida", "edit_message_id": first_user_id},
            )
            assert failed.status_code == 200
            assert "event: error" in failed.text
            assert "event: done" not in failed.text

        user = await store.get_user_by_email("edit@example.com")
        after = await _history(store, user["id"], session_id)
        assert [role for _, role, _ in after] == ["user"]
        assert after[0][2] == "corregida"
