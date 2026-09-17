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

from core.errors import LLMTimeoutError
from server.api.routers import archive as archive_router
from server.api.routers import auth as auth_router
from server.api.routers import chat as chat_router
from server.api.routers import files as files_router
from server.api.routers import sessions as sessions_router
from server.services.chat_context import build_chat_context, DEFAULT_MESSAGE_WINDOW
from server.services.sqlite_store import SqliteStore
from tests.test_helpers import apply_all_migrations, upload_csv


@pytest.fixture
def app(tmp_path, monkeypatch):
    from server.api import store as api_store  # noqa: PLC0415

    application = FastAPI()
    application.include_router(auth_router.router)
    application.include_router(sessions_router.router)
    application.include_router(chat_router.router)
    application.include_router(archive_router.router)
    application.include_router(files_router.router)

    # Isolation: uploads must land in a per-test tmp dir, never the real
    # server/uploads/ used by the live server.
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
        json={"email": "costguard@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.headers["set-cookie"]


@pytest.fixture
def session_id(client, auth_cookie):
    """Session with an attached dataset.

    The chat router refuses to run the sandbox in a session with no files
    (no-dataset guard), so every sandbox-exercising test here needs a
    dataset; tests that assert on profiles still upload their own file.
    """
    resp = client.post(
        "/api/sessions",
        json={"title": "Cost guard test"},
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


def _parse_sse_events(response_text: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) tuples."""
    events: list[tuple[str, dict]] = []
    for frame in response_text.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in frame.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data_lines.append(line[len("data: "):])
        events.append((event_name, json.loads("\n".join(data_lines))))
    return events


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
        # to test the persisted value itself rather than the API projection)
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

        # Regression (sandbox locale): the prompt must declare the C/POSIX-only
        # environment — without it the model generates locale.setlocale for
        # localized names and the sandbox crashes with locale.Error.
        assert "locale" in captured_system_prompt.lower(), \
            "System prompt should declare the locale restriction"

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


class TestGroundedNarrativePersistence:
    """rigor-mov2 live-validation findings, fixed:

    1. The second-pass grounded narrative ran AFTER persist, so the
       persisted message (the source of truth ChatView refetches on done)
       never contained it — the narrative flashed and vanished. It must
       run BEFORE persist.
    2. REWRITE semantics (spec R2): the grounded narrative REPLACES the
       streamed approach in the persisted message — appending both left
       the approach's invented estimates contradicting the computed
       numbers in the final message (B1-R finding).
    3. Full-precision floats (e.g. 2500.8230981333336) leaked into
       narratives despite the ≤6-decimals prompt rule — formatting is now
       enforced deterministically on the explanation.
    """

    async def test_second_pass_persisted_with_formatted_numbers(
        self, client, auth_cookie, session_id, store
    ):
        csv_content = (
            b"name,age,score\n"
            b"Alice,30,95.5\n"
            b"Bob,25,87.3\n"
        )
        upload_resp = client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("grounded.csv", csv_content, "text/csv")},
            headers={"Cookie": auth_cookie},
        )
        assert upload_resp.status_code in (200, 201)

        call_count = 0

        def _two_phase_fake(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Main structured call: full-precision float in explanation
                return _make_openai_fake(json.dumps({
                    "code": "print('grounded test')",
                    "explanation": "La media es 2500.8230981333336 segun el perfil.",
                }))
            # Second-pass grounding call (no response_format): plain prose
            # carrying another full-precision float that must be formatted.
            return _make_openai_fake(
                "El promedio exacto es 10.507123333333332 unidades."
            )

        mock_create = AsyncMock(side_effect=_two_phase_fake)
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

        # Main call + grounding call both hit the provider
        assert call_count == 2, f"expected main+grounding calls, got {call_count}"

        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert assistant_msgs, "No assistant message persisted"

        content = assistant_msgs[0]["content_text"]
        # REWRITE: the persisted message is ONLY the grounded narrative —
        # the approach's (invented) numbers must not survive beside it
        assert content == "El promedio exacto es 10.507123 unidades.", (
            f"Persisted message should be the formatted grounded rewrite: {content!r}"
        )
        assert "2500.8230981333336" not in content
        assert "10.507123333333332" not in content
        # Usage merged from both calls (fake: 50 in / 100 out each)
        assert assistant_msgs[0]["tokens_in"] == 100
        assert assistant_msgs[0]["tokens_out"] == 200

class TestStdoutSuppression:
    """rigor-mov2 validation round 3: the raw stdout box (scientific
    notation, index numbers) is redundant noise when a result table
    already renders the same data. Keep the stdout box only for
    stdout-only answers."""

    async def test_stdout_suppressed_when_table_present(
        self, client, auth_cookie, session_id, store
    ):
        csv_content = (
            b"name,age,score\n"
            b"Alice,30,95.5\n"
            b"Bob,25,87.3\n"
        )
        upload_resp = client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("sup.csv", csv_content, "text/csv")},
            headers={"Cookie": auth_cookie},
        )
        assert upload_resp.status_code in (200, 201)

        valid_response = {
            "code": (
                "import pandas as pd\n"
                "df_result = pd.DataFrame({'categoria': ['A', 'B'], 'monto_total': [940.0, 936.0]})\n"
                "print(df_result)"
            ),
            "explanation": "Total por categoria.",
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
                json={"question": "total por categoria"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert assistant_msgs, "No assistant message persisted"
        artifacts = json.loads(assistant_msgs[0]["artifacts_json"])
        kinds = [a["kind"] for a in artifacts]
        assert "table" in kinds, f"expected a table artifact, got {kinds}"
        assert "text" not in kinds, (
            f"stdout box must be suppressed when a table renders: {kinds}"
        )


class TestGroundingTableContext:
    """rigor-mov2 validation round 4: the grounding call must receive the
    exact table values. stdout prints large floats in scientific notation
    (9.407413e+08), which silently loses precision — narratives built only
    from it cited rounded numbers (940,741,300 vs the table's
    940,741,259.01)."""

    async def test_grounding_call_receives_exact_table_values(
        self, client, auth_cookie, session_id, store
    ):
        csv_content = (
            b"name,age,score\n"
            b"Alice,30,95.5\n"
            b"Bob,25,87.3\n"
        )
        upload_resp = client.post(
            f"/api/sessions/{session_id}/files",
            files={"file": ("tbl.csv", csv_content, "text/csv")},
            headers={"Cookie": auth_cookie},
        )
        assert upload_resp.status_code in (200, 201)

        captured_calls: list[list[dict]] = []
        call_count = 0

        def _two_phase_fake(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            captured_calls.append(kwargs.get("messages", []))
            if call_count == 1:
                return _make_openai_fake(json.dumps({
                    "code": (
                        "import pandas as pd\n"
                        "df_result = pd.DataFrame({'categoria': ['A'], 'monto_total': [940741259.01]})\n"
                        "print(df_result)"
                    ),
                    "explanation": "Total por categoria.",
                }))
            return _make_openai_fake("La categoria A totaliza 940741259.01.")

        mock_create = AsyncMock(side_effect=_two_phase_fake)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "total por categoria"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        assert call_count == 2, f"expected main+grounding calls, got {call_count}"
        grounding_user_content = captured_calls[1][-1]["content"]
        # The grounding context carries the table's EXACT value (the stdout
        # print alone only has e-notation 9.407413e+08)
        assert "940741259.01" in grounding_user_content, (
            f"Grounding context must include exact table values: {grounding_user_content!r}"
        )
        assert "Result table (exact values)" in grounding_user_content


class TestBuildRepairFeedback:
    """Task 3.1: unit tests on the repair feedback message structure.

    The feedback is LLM-directed prompt content (English per repo
    convention); it must carry the taxonomy code, the error message and
    the traceback when present — and NEVER the failed attempt's
    explanation or generated code (spec automatic-repair REQ-3/REQ-4).
    """

    def test_includes_code_message_and_trailing_instruction(self):
        feedback = chat_router._build_repair_feedback(
            {"type": "runtime_error", "message": "NameError: name 'df' is not defined"}
        )
        assert "sandbox/runtime_error" in feedback
        assert "NameError: name 'df' is not defined" in feedback
        assert "Generate corrected Python code" in feedback
        assert "same JSON format" in feedback

    def test_includes_traceback_when_present(self):
        feedback = chat_router._build_repair_feedback(
            {
                "type": "runtime_error",
                "message": "boom",
                "traceback": "Traceback (most recent call last):\nValueError: boom",
            }
        )
        assert "Traceback:" in feedback
        assert "ValueError: boom" in feedback

    def test_omits_traceback_section_when_absent(self):
        feedback = chat_router._build_repair_feedback(
            {"type": "runtime_error", "message": "hard crash"}
        )
        assert "Traceback:" not in feedback
        assert "hard crash" in feedback

    def test_carries_no_failed_outputs(self):
        feedback = chat_router._build_repair_feedback(
            {"type": "runtime_error", "message": "boom"}
        )
        # The feedback template itself contains no slot for a failed
        # explanation or code block — only error context.
        assert "explanation" not in feedback.split("same JSON format")[0]


class TestSandboxRepairPass:
    """Task 3.2/3.3: bounded sandbox repair pass (WU3).

    Spec coverage: automatic-repair REQ-1 (bounded to one), REQ-2 (only
    runtime_error triggers), REQ-3 (fresh repair context), REQ-4
    (persist-nothing on failure / successful repair indistinguishable),
    chat-execution second-failure exact SSE sequence, Enmienda 1 (code
    maps the second run's ACTUAL payload type).
    """

    @staticmethod
    def _error_payload(error_type: str, message: str, traceback: str | None = None):
        payload = {"status": "error", "figures": [], "tables": [], "text": ""}
        error: dict = {"type": error_type, "message": message}
        if traceback is not None:
            error["traceback"] = traceback
        payload["error"] = error
        return payload

    @staticmethod
    def _ok_payload(text: str, table: bool = False):
        payload = {
            "status": "ok",
            "figures": [],
            "tables": [],
            "text": text,
        }
        if table:
            payload["tables"] = [
                {
                    "name": "df_result",
                    "columns": ["categoria", "total"],
                    "rows": [["A", 42]],
                }
            ]
        return payload

    @staticmethod
    def _classify_llm_call(kwargs: dict) -> str:
        """Distinguish main / repair / grounding provider calls."""
        messages = kwargs.get("messages", [])
        last = messages[-1]["content"] if messages else ""
        if "response_format" in kwargs:
            if "failed during execution" in last:
                return "repair"
            return "main"
        return "grounding"

    @pytest.mark.parametrize(
        ("code", "question", "expected_code"),
        [
            ("def broken(:", "rompe la sintaxis", "sandbox/syntax_error"),
            ("import os", "importa prohibido", "sandbox/import_error"),
        ],
    )
    async def test_non_repairable_terminates_without_repair(
        self, client, auth_cookie, session_id, store, code, question, expected_code
    ):
        """Spec REQ-2: non-runtime_error payloads (syntax_error,
        blocked_import) terminate immediately with their typed code and
        ZERO additional LLM calls."""
        call_count = 0

        def _main_only_fake(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _make_openai_fake(json.dumps({
                "code": code,
                "explanation": "EXPLICACION INVENTADA",
            }))

        mock_create = AsyncMock(side_effect=_main_only_fake)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": question},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        events = _parse_sse_events(resp.text)
        error_events = [d for name, d in events if name == "error"]
        assert len(error_events) == 1
        assert error_events[0]["type"] == "sandbox"
        assert error_events[0]["code"] == expected_code
        assert error_events[0]["traceback"], "sandbox payloads carry a traceback"
        terminal = [d for name, d in events if name == "status"][-1]
        assert terminal == {"stage": "done", "state": "error"}
        assert call_count == 1, "non-repairable failure must not trigger repair"
        # Nothing persisted: only the user question is in history.
        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)
        assert all(m["role"] != "assistant" for m in messages)

    async def test_second_failure_terminal_exact_sse_order(
        self, client, auth_cookie, session_id, store, monkeypatch
    ):
        """Spec: second sandbox failure emits exactly one error event (code
        from the SECOND run's payload per Enmienda 1) then status
        done/error, then the stream ends; nothing is persisted."""
        run_calls: list[str] = []

        async def _fake_run_code(code, limits=None, files=None):
            run_calls.append(code)
            if len(run_calls) == 1:
                return self._error_payload(
                    "runtime_error",
                    "primer fallo",
                    traceback="Traceback (most recent call last):\nValueError: primer fallo",
                )
            return self._error_payload(
                "runtime_error",
                "segundo fallo",
                traceback="Traceback (most recent call last):\nNameError: segundo fallo",
            )

        monkeypatch.setattr(chat_router, "run_code", _fake_run_code)

        llm_calls: list[str] = []

        def _two_attempt_fake(*args, **kwargs):
            kind = self._classify_llm_call(kwargs)
            llm_calls.append(kind)
            if kind == "main":
                return _make_openai_fake(json.dumps({
                    "code": "raise ValueError('primer intento')",
                    "explanation": "EXPLICACION INVENTADA",
                }))
            return _make_openai_fake(json.dumps({
                "code": "raise ValueError('segundo intento')",
                "explanation": "EXPLICACION REPARADA",
            }))

        mock_create = AsyncMock(side_effect=_two_attempt_fake)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "falla dos veces"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        assert llm_calls == ["main", "repair"], llm_calls
        assert len(run_calls) == 2, "exactly one repair sandbox run"

        events = _parse_sse_events(resp.text)
        names = [name for name, _ in events]
        # Exact terminal sequence: one error, then one status done/error,
        # then the stream ends (no further events).
        assert names[-2:] == ["error", "status"], names
        error_data = events[-2][1]
        assert error_data == {
            "type": "sandbox",
            "code": "sandbox/runtime_error",
            "message": "segundo fallo",
            "traceback": "Traceback (most recent call last):\nNameError: segundo fallo",
        }
        assert events[-1][1] == {"stage": "done", "state": "error"}
        # No artifact/done events after the failure.
        assert "artifact" not in names and "done" not in names
        # Failed repair persists NOTHING.
        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)
        assert all(m["role"] != "assistant" for m in messages)

    async def test_repair_status_and_fresh_context(
        self, client, auth_cookie, session_id, store, monkeypatch
    ):
        """Spec REQ-3 + first-failure non-terminal: a repair/running status
        sits between the first failure and the outcome; the repair call's
        context is fresh (no failed explanation/code block)."""
        run_calls: list[str] = []

        async def _fake_run_code(code, limits=None, files=None):
            run_calls.append(code)
            if len(run_calls) == 1:
                return self._error_payload(
                    "runtime_error",
                    "NameError: primer intento",
                    traceback=(
                        'Traceback (most recent call last):\n  File "<string>", '
                        "line 2, in <module>\nNameError: primer intento"
                    ),
                )
            return self._ok_payload("42", table=True)

        monkeypatch.setattr(chat_router, "run_code", _fake_run_code)

        captured: dict[str, list[list[dict]]] = {"main": [], "repair": [], "grounding": []}

        def _three_phase_fake(*args, **kwargs):
            kind = self._classify_llm_call(kwargs)
            captured[kind].append(kwargs.get("messages", []))
            if kind == "main":
                return _make_openai_fake(json.dumps({
                    "code": "import pandas as pd\nraise ValueError('primer intento')",
                    "explanation": "EXPLICACION INVENTADA",
                }))
            if kind == "repair":
                return _make_openai_fake(json.dumps({
                    "code": "print('42')",
                    "explanation": "EXPLICACION REPARADA",
                }))
            return _make_openai_fake("El resultado es 42.")

        mock_create = AsyncMock(side_effect=_three_phase_fake)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "repara esto"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        events = _parse_sse_events(resp.text)
        # Exactly one non-terminal repair status, positioned after the
        # sandbox-running status and before the outcome.
        repair_statuses = [
            (i, d) for i, (name, d) in enumerate(events)
            if name == "status" and d.get("stage") == "repair"
        ]
        assert len(repair_statuses) == 1, events
        repair_idx = repair_statuses[0][0]
        assert events[repair_idx][1] == {"stage": "repair", "state": "running"}
        prior_stages = [
            d.get("stage") for name, d in events[:repair_idx] if name == "status"
        ]
        assert "sandbox" in prior_stages and "done" not in prior_stages
        # No terminal error was emitted for the FIRST failure.
        assert all(
            d.get("code") != "sandbox/runtime_error"
            for name, d in events
            if name == "error"
        )
        # Stream completed normally.
        assert events[-1][0] == "done"

        # Fresh repair context: system prompt first, original question,
        # feedback message last — and NO failed explanation/code block.
        repair_msgs = captured["repair"][0]
        assert repair_msgs[0]["role"] == "system"
        assert repair_msgs[-1]["role"] == "user"
        feedback = repair_msgs[-1]["content"]
        assert "sandbox/runtime_error" in feedback
        assert "NameError: primer intento" in feedback
        assert "EXPLICACION INVENTADA" not in json.dumps(repair_msgs)
        assert "import pandas as pd" not in json.dumps(repair_msgs)
        # Repair messages end with the original user question + feedback —
        # exactly one new message beyond the main call's list.
        main_msgs = captured["main"][0]
        assert len(repair_msgs) == len(main_msgs) + 1

        # Successful repair: persisted exactly once, stream done.
        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        done_events = [d for name, d in events if name == "done"]
        assert len(done_events) == 1
        assert done_events[0]["message_id"] == assistant_msgs[0]["id"]

    async def test_repair_llm_failure_typed_code(
        self, client, auth_cookie, session_id, store, monkeypatch
    ):
        """A repair LLM failure terminates with the typed llm code and no
        second sandbox run."""
        run_calls: list[str] = []

        async def _fake_run_code(code, limits=None, files=None):
            run_calls.append(code)
            return self._error_payload("runtime_error", "primer fallo")

        monkeypatch.setattr(chat_router, "run_code", _fake_run_code)

        def _repair_raises(*args, **kwargs):
            if self._classify_llm_call(kwargs) == "repair":
                raise LLMTimeoutError("Provider timed out after 120s")
            return _make_openai_fake(json.dumps({
                "code": "raise ValueError('x')",
                "explanation": "EXPLICACION INVENTADA",
            }))

        mock_create = AsyncMock(side_effect=_repair_raises)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "reparacion que falla"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        events = _parse_sse_events(resp.text)
        error_data = [d for name, d in events if name == "error"]
        assert error_data == [
            {"type": "llm", "code": "llm/timeout", "message": "Provider timed out after 120s"}
        ]
        terminal = [d for name, d in events if name == "status"][-1]
        assert terminal == {"stage": "done", "state": "error"}
        assert len(run_calls) == 1, "no second sandbox run after repair LLM failure"
        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)
        assert all(m["role"] != "assistant" for m in messages)

    async def test_repair_empty_code_terminal_with_first_failure(
        self, client, auth_cookie, session_id, store, monkeypatch
    ):
        """An empty code from the repair call terminates with the FIRST
        failure's message+traceback (no second sandbox run to reflect)."""
        run_calls: list[str] = []

        async def _fake_run_code(code, limits=None, files=None):
            run_calls.append(code)
            return self._error_payload(
                "runtime_error",
                "primer fallo",
                traceback="Traceback (most recent call last):\nValueError: primer fallo",
            )

        monkeypatch.setattr(chat_router, "run_code", _fake_run_code)

        def _empty_repair(*args, **kwargs):
            if self._classify_llm_call(kwargs) == "repair":
                return _make_openai_fake(json.dumps({
                    "code": "",
                    "explanation": "No puedo repararlo.",
                }))
            return _make_openai_fake(json.dumps({
                "code": "raise ValueError('x')",
                "explanation": "EXPLICACION INVENTADA",
            }))

        mock_create = AsyncMock(side_effect=_empty_repair)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "sin codigo"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        events = _parse_sse_events(resp.text)
        error_data = [d for name, d in events if name == "error"]
        assert len(error_data) == 1
        assert error_data[0]["code"] == "sandbox/runtime_error"
        assert error_data[0]["message"] == "primer fallo"
        assert error_data[0]["traceback"] == (
            "Traceback (most recent call last):\nValueError: primer fallo"
        )
        assert len(run_calls) == 1, "empty repair code: no second sandbox run"
        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)
        assert all(m["role"] != "assistant" for m in messages)

    async def test_hard_crash_without_traceback_repairs(
        self, client, auth_cookie, session_id, store, monkeypatch
    ):
        """Spec edge case: a hard crash (runtime_error, no traceback field)
        still repairs — the feedback carries the message (stderr tail)."""
        run_calls: list[str] = []

        async def _fake_run_code(code, limits=None, files=None):
            run_calls.append(code)
            if len(run_calls) == 1:
                return self._error_payload(
                    "runtime_error",
                    "Sandbox process produced no output (crashed or hard OOM) — segfault tail",
                )
            return self._ok_payload("ok")

        monkeypatch.setattr(chat_router, "run_code", _fake_run_code)

        captured_feedback: list[str] = []

        def _three_phase_fake(*args, **kwargs):
            kind = self._classify_llm_call(kwargs)
            if kind == "repair":
                captured_feedback.append(kwargs["messages"][-1]["content"])
                return _make_openai_fake(json.dumps({
                    "code": "print('ok')",
                    "explanation": "EXPLICACION REPARADA",
                }))
            if kind == "main":
                return _make_openai_fake(json.dumps({
                    "code": "raise ValueError('crash')",
                    "explanation": "EXPLICACION INVENTADA",
                }))
            return _make_openai_fake("Listo.")

        mock_create = AsyncMock(side_effect=_three_phase_fake)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "hard crash"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        assert len(run_calls) == 2, "repair proceeds on a traceback-less crash"
        assert captured_feedback, "repair LLM call was made"
        assert "hard OOM" in captured_feedback[0]
        assert "Traceback:" not in captured_feedback[0]
        # Turn completes successfully.
        events = _parse_sse_events(resp.text)
        assert events[-1][0] == "done"
        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)
        assert any(m["role"] == "assistant" for m in messages)

    async def test_successful_repair_indistinguishable_and_usage_sum(
        self, client, auth_cookie, session_id, store, monkeypatch
    ):
        """Spec REQ-4: a successful repair persists exactly once with its
        artifacts and receives done like any normal turn; the persisted
        meta line sums usage across main + repair + grounding calls."""
        run_calls: list[str] = []

        async def _fake_run_code(code, limits=None, files=None):
            run_calls.append(code)
            if len(run_calls) == 1:
                return self._error_payload(
                    "runtime_error",
                    "NameError: df_result is not defined",
                    traceback="Traceback (most recent call last):\nNameError: df_result",
                )
            return self._ok_payload("42", table=True)

        monkeypatch.setattr(chat_router, "run_code", _fake_run_code)

        llm_kinds: list[str] = []

        def _three_phase_fake(*args, **kwargs):
            kind = self._classify_llm_call(kwargs)
            llm_kinds.append(kind)
            if kind == "main":
                return _make_openai_fake(json.dumps({
                    "code": "raise NameError('df_result')",
                    "explanation": "EXPLICACION INVENTADA",
                }))
            if kind == "repair":
                return _make_openai_fake(json.dumps({
                    "code": (
                        "import pandas as pd\n"
                        "df_result = pd.DataFrame({'categoria': ['A'], 'total': [42]})\n"
                        "print(df_result)"
                    ),
                    "explanation": "EXPLICACION REPARADA",
                }))
            return _make_openai_fake("El total es 42.")

        mock_create = AsyncMock(side_effect=_three_phase_fake)
        with patch("server.services.llm_openai.AsyncOpenAI") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_client_cls.return_value = mock_client
            resp = client.post(
                f"/api/sessions/{session_id}/chat",
                json={"question": "reparacion exitosa"},
                headers={"Cookie": auth_cookie},
            )
            assert resp.status_code == 200

        assert llm_kinds == ["main", "repair", "grounding"], llm_kinds
        assert len(run_calls) == 2

        events = _parse_sse_events(resp.text)
        names = [name for name, _ in events]
        # Normal-turn wire shape: artifacts emitted, narrative deltas, done.
        assert "artifact" in names
        assert names[-1] == "done"
        done_events = [d for name, d in events if name == "done"]
        assert len(done_events) == 1

        user_id = (await store.get_user_by_email("costguard@example.com"))["id"]
        messages = await store.list_messages(user_id, session_id)
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1, "assistant persisted exactly once"
        assert done_events[0]["message_id"] == assistant_msgs[0]["id"]
        artifacts = json.loads(assistant_msgs[0]["artifacts_json"])
        assert any(a["kind"] == "table" for a in artifacts)
        # The persisted narrative is the grounded rewrite, not the failed
        # first attempt's explanation.
        assert assistant_msgs[0]["content_text"] == "El total es 42."
        # Meta-line usage honesty: main (50/100) + repair (50/100) +
        # grounding (50/100) — the fake returns identical usage per call.
        assert assistant_msgs[0]["tokens_in"] == 150
        assert assistant_msgs[0]["tokens_out"] == 300
        assert assistant_msgs[0]["cost_usd"] > 0
