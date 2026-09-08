"""RED tests for LLM cost guardrails (Phase 5, task 5.3).

Tests verify:
- Profile-only context (no raw DataFrame rows/JSON in LLM messages)
- Sliding window caps at 20 messages
- cost_usd persisted > 0 after a chat turn
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers import archive as archive_router
from server.api.routers import auth as auth_router
from server.api.routers import chat as chat_router
from server.api.routers import files as files_router
from server.api.routers import sessions as sessions_router
from server.services.chat_context import build_chat_context, DEFAULT_MESSAGE_WINDOW
from server.services.sqlite_store import SqliteStore

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "server" / "migrations"
INIT_SQL_PATH = MIGRATIONS_DIR / "0001_init.sql"


@pytest.fixture
def app():
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(chat_router.router)
    application.include_router(archive_router.router)
    application.include_router(files_router.router)

    import asyncio

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        init_sql = INIT_SQL_PATH.read_text(encoding="utf-8")
        await s.conn.executescript(init_sql)
        await s.conn.commit()

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
        json={"email": "costguard@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


@pytest.fixture
def session_id(client, auth_cookie):
    resp = client.post(
        "/api/sessions",
        json={"title": "Cost guard test"},
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


# ── Tests ─────────────────────────────────────────────────────────────────


class TestLLMContextGuardrails:
    """Task 5.3: LLM cost guardrail RED tests."""

    async def test_cost_usd_persisted_after_chat_turn(
        self, client, auth_cookie, session_id, store
    ):
        """Verify cost_usd is persisted and > 0 after a chat turn."""
        valid_response = {
            "code": "print('cost test')",
            "explanation": "Testing cost persistence.",
        }
        mock_create = AsyncMock(
            return_value=_make_openai_fake(json.dumps(valid_response))
        )

        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client

            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "test cost"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        # Check persisted message has cost_usd > 0 (query store directly,
        # since MessageResponse model does not expose cost_usd)
        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)

        # Find the assistant message
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) >= 1, "No assistant message found"

        # Verify cost_usd is persisted and > 0
        last_assistant = assistant_msgs[0]
        assert last_assistant["cost_usd"] is not None, "cost_usd should not be None"
        assert last_assistant["cost_usd"] > 0, (
            f"cost_usd should be > 0, got {last_assistant['cost_usd']}"
        )

    async def test_sliding_window_caps_at_20_messages(
        self, client, auth_cookie, session_id, store
    ):
        """Verify at most 20 messages are sent to the LLM when 30+ exist.

        Builds messages directly via the store to avoid SSE/sandbox overhead.
        """
        # Get user_id
        user = await store.get_user_by_email("costguard@example.com")
        assert user is not None
        user_id = user["id"]

        # Create 30 messages (15 user + 15 assistant) directly via store
        for i in range(15):
            await store.create_message(
                user_id=user_id,
                chat_session=session_id,
                role="user",
                content_text=f"turn {i}",
            )
            await store.create_message(
                user_id=user_id,
                chat_session=session_id,
                role="assistant",
                content_text=f"response {i}",
                code="print('ok')",
                model="gpt-4o",
                provider="openai",
                tokens_in=50,
                tokens_out=50,
                cost_usd=0.001,
            )

        # Verify 30 messages exist
        all_msgs = await store.list_messages(user_id, session_id)
        assert len(all_msgs) == 30, f"Expected 30 messages, got {len(all_msgs)}"

        # Build context and verify the message window is capped
        context = await build_chat_context(store, user_id=user_id, chat_session=session_id)
        assert "messages" in context
        msg_count = len(context["messages"])
        # The window should be at most DEFAULT_MESSAGE_WINDOW (20)
        assert msg_count <= DEFAULT_MESSAGE_WINDOW, (
            f"Expected at most {DEFAULT_MESSAGE_WINDOW} messages in context, "
            f"got {msg_count}"
        )

    async def test_profile_only_context_no_raw_dataframe(
        self, client, auth_cookie, session_id, store
    ):
        """Verify LLM context contains profile JSON, not raw DataFrame rows."""
        # Upload a CSV file to create a profile
        csv_content = (
            b"name,age,score\n"
            b"Alice,30,95.5\n"
            b"Bob,25,87.3\n"
            b"Charlie,35,92.1\n"
        )
        upload_resp = client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("test.csv", csv_content, "text/csv")},
            headers={"Cookie": auth_cookie},
        )
        assert upload_resp.status_code in (200, 201), f"Upload failed: {upload_resp.text}"

        # Now send a chat question and intercept the LLM context
        captured_system_prompt = None

        def _capture_context(*args, **kwargs):
            nonlocal captured_system_prompt
            # Capture only the FIRST (main generation) call. The analytical
            # second-pass grounding call is a separate, deliberately scoped
            # request whose system prompt does not carry profile context.
            if captured_system_prompt is None:
                messages = kwargs.get("messages", [])
                for msg in messages:
                    if msg["role"] == "system":
                        captured_system_prompt = msg["content"]
                        break
            return _make_openai_fake(json.dumps({
                "code": "print('profile test')",
                "explanation": "Testing profile-only context.",
            }))

        mock_create = AsyncMock(side_effect=_capture_context)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client

            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "analyze the data"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        # Verify the system prompt was captured
        assert captured_system_prompt is not None, "No system prompt captured"

        # Verify the system prompt contains profile-style data (schema/columns)
        assert "profile" in captured_system_prompt.lower() or "columns" in captured_system_prompt.lower(), \
            "System prompt should contain profile/column info"

        # The profile sample may contain "Alice" since profiles include 5 sample rows.
        # What we need to verify is that the FULL raw data is NOT present.
        # Check for signs of raw CSV serialization (all rows as a table)
        assert "name,age,score" not in captured_system_prompt, \
            "Raw CSV header should not be in system prompt"
        assert "30,95.5" not in captured_system_prompt, \
            "Raw data values should not be in system prompt as bare CSV"

    async def test_context_includes_authoritative_row_count(
        self, client, auth_cookie, session_id, store
    ):
        """Regression (Rigor mov-1): the LLM context must carry the dataset's
        authoritative row_count — without it the model once cited a column's
        unique_count as the row count."""
        csv_content = (
            b"name,age,score\n"
            b"Alice,30,95.5\n"
            b"Bob,25,87.3\n"
            b"Charlie,35,92.1\n"
        )
        upload_resp = client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("rows.csv", csv_content, "text/csv")},
            headers={"Cookie": auth_cookie},
        )
        assert upload_resp.status_code == 201

        user = await store.get_user_by_email("costguard@example.com")
        context = await build_chat_context(
            store, user_id=user["id"], chat_session=session_id
        )
        assert context["profiles"], "Expected at least one profile in context"
        profile_entry = context["profiles"][0]
        assert profile_entry["row_count"] == 3, (
            f"Expected authoritative row_count=3, got {profile_entry.get('row_count')}"
        )
        # And it must be at dataset level, not inside per-column stats
        assert "row_count" not in profile_entry["profile"]["stats"]