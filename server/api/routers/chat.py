"""Chat router: SSE chat stream and message history.

- ``POST /api/sessions/{id}/chat`` — returns ``text/event-stream``
  (SSE events: ``status``, ``token``, ``artifact``, ``done``, ``error``)
- ``GET /api/sessions/{id}/messages`` — paginated message history

Flow per design Chat Flow steps 1–8:
1. Validate ownership
2. Persist user message
3. Load context (profiles + message window)
4. Call LLM (non-streamed, json_schema)
5. Emit status(llm done) → token deltas
6. Run sandbox (single-shot)
7. Persist assistant message BEFORE emitting artifacts (persist-then-emit)
8. Emit artifact → status(done) → done {message_id}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.errors import (
    LLMError,
    SandboxError,
    SandboxImportError,
    SandboxMemoryError,
    SandboxRuntimeError,
    SandboxSyntaxError,
    SandboxTimeoutError,
)
from server.api.deps import current_user, get_store
from server.services.chat_context import build_chat_context
from server.services.llm_openai import OpenAIProvider
from server.services.sandbox_local import run_code
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["chat"])

# JSON schema for chat LLM responses (Decision #6)
_CHAT_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "code_gen",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "explanation": {"type": "string"},
            },
            "required": ["code", "explanation"],
            "additionalProperties": False,
        },
    },
}

# Default LLM model
_DEFAULT_MODEL = "gpt-4o-2024-08-06"


# ── Request / Response schemas ─────────────────────────────────────────────────


class ChatRequest(BaseModel):
    question: str


class MessageResponse(BaseModel):
    id: int
    role: str
    content_text: str
    code: str | None = None
    artifacts: list[dict] | None = None
    model: str | None = None
    created_at: str | None = None


# ── Provider resolution ────────────────────────────────────────────────────────


async def _resolve_provider(
    store: SqliteStore,
    user_id: int,
) -> OpenAIProvider:
    """Resolve the LLM provider for a user.

    Uses ``user_settings.api_key_enc`` as the API key if set, otherwise
    falls back to the ``OPENAI_API_KEY`` env var.
    Uses ``user_settings.default_model`` if set, otherwise the default model.
    """
    settings = await store.get_user_settings(user_id)
    api_key = None
    model = _DEFAULT_MODEL

    if settings:
        if settings.get("api_key_enc"):
            api_key = settings["api_key_enc"]
        if settings.get("default_model"):
            model = settings["default_model"]

    return OpenAIProvider(api_key=api_key, model=model)


# ── SSE helpers ────────────────────────────────────────────────────────────────


def _sse_event(event: str, data: object) -> str:
    """Format a single SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _emit_token_deltas(
    text: str,
    chunk_size: int = 80,
) -> AsyncIterator[str]:
    """Yield progressive token deltas of the already-complete explanation text.

    Per Decision #11: the LLM call is non-streamed (json_schema), but the
    explanation text is delivered as progressive ``token`` SSE deltas so
    the user sees reasoning as it's "typed out."
    """
    for i in range(0, len(text), chunk_size):
        yield _sse_event("token", text[i : i + chunk_size])
        await asyncio.sleep(0.01)  # small delay for human-readable pacing


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/{session_id}/chat")
async def chat_stream(
    session_id: str,
    body: ChatRequest,
    request: Request,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Chat endpoint — returns a ``text/event-stream`` SSE response.

    The client sends a question and receives a stream of SSE events:
    ``status``, ``token``, ``artifact``, ``done``, ``error``.
    """
    user_id = user["id"]

    # Step 1: Validate chat session ownership
    session = await store.get_chat_session(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Step 2: Persist user message
    await store.create_message(
        user_id=user_id,
        chat_session=session_id,
        role="user",
        content_text=body.question,
    )
    await store.update_chat_session_timestamp(session_id, user_id)

    async def _event_stream():
        try:
            # Step 3: Load context
            context = await build_chat_context(store, user_id=user_id, chat_session=session_id)

            # Build the system prompt with profiles
            system_prompt = (
                "You are a data analysis assistant. The user's datasets are described below. "
                "Generate Python code (pandas, numpy, plotly) to answer their question. "
                "Return valid JSON with 'code' and 'explanation' fields only."
            )
            if context["profiles"]:
                system_prompt += f"\n\nAvailable datasets:\n{json.dumps(context['profiles'], indent=2)}"
                system_prompt += (
                    "\n\nIMPORTANT — file access: the code runs in a FRESH temporary "
                    "working directory, so relative filenames do not exist. Read each "
                    "dataset with EXACTLY its 'path' value above (absolute path), e.g. "
                    "df = pd.read_csv('<path>'). Never invent paths."
                )

            llm_messages = [{"role": "system", "content": system_prompt}]
            llm_messages.extend(context["messages"])
            llm_messages.append({"role": "user", "content": body.question})

            # Step 4: Resolve provider and call LLM
            provider = await _resolve_provider(store, user_id)

            try:
                llm_response = await provider.complete(
                    messages=llm_messages,
                    response_format=_CHAT_JSON_SCHEMA,
                    max_tokens=4096,
                    temperature=0.1,
                )
            except LLMError as e:
                yield _sse_event("error", {
                    "type": e.__class__.__name__,
                    "message": str(e),
                })
                yield _sse_event("status", {"stage": "error", "state": "error"})
                return

            structured = llm_response.structured_data or {}
            explanation = structured.get("explanation", llm_response.text)
            code = structured.get("code", "")

            # Step 5: Emit SSE — status(llm done) → token deltas → status(sandbox running)
            yield _sse_event("status", {"stage": "llm", "state": "done"})
            async for token_event in _emit_token_deltas(explanation):
                yield token_event
            yield _sse_event("status", {"stage": "sandbox", "state": "running"})

            # Step 6: Run sandbox (single-shot). Stage the session's uploads
            # into the sandbox cwd so generated code can read them by filename.
            session_files = {
                p["filename"]: p["path"] for p in context["profiles"] if p.get("path")
            }
            sandbox_result: dict[str, Any] = {}
            if code.strip():
                try:
                    sandbox_result = await run_code(code, limits={
                        "cpu_seconds": 30,
                        "memory_mb": 512,
                        "timeout_seconds": 30,
                    }, files=session_files or None)
                except Exception as e:
                    sandbox_result = {
                        "status": "error",
                        "error": {"type": "runtime_error", "message": str(e)},
                        "figures": [], "tables": [], "text": "",
                    }

            # Handle sandbox errors
            sandbox_error: dict | None = sandbox_result.get("error")
            if sandbox_result.get("status") == "error" and sandbox_error:
                sandbox_type = sandbox_error.get("type", "runtime_error")
                yield _sse_event("error", {
                    "type": sandbox_type,
                    "message": sandbox_error.get("message", "Sandbox execution failed"),
                })
                yield _sse_event("status", {"stage": "done", "state": "error"})

            # Build artifacts JSON
            artifacts: list[dict] = []
            for fig in sandbox_result.get("figures", []):
                artifacts.append({"kind": "figure", "name": fig.get("name", ""), "payload": fig.get("plotly", {})})
            for tbl in sandbox_result.get("tables", []):
                artifacts.append({"kind": "table", "name": tbl.get("name", ""), "payload": {"columns": tbl.get("columns", []), "rows": tbl.get("rows", [])}})

            # Step 7: Persist assistant message BEFORE emitting artifacts (persist-then-emit)
            message = await store.create_message(
                user_id=user_id,
                chat_session=session_id,
                role="assistant",
                content_text=explanation,
                code=code,
                artifacts_json=json.dumps(artifacts) if artifacts else None,
                model=llm_response.model,
                provider=llm_response.provider,
                tokens_in=llm_response.usage.tokens_in,
                tokens_out=llm_response.usage.tokens_out,
                cost_usd=llm_response.usage.cost_usd,
            )

            # Step 8: Emit — artifact → status(done) → done {message_id}
            if artifacts:
                yield _sse_event("artifact", {"figures": sandbox_result.get("figures", []), "tables": sandbox_result.get("tables", [])})
            yield _sse_event("status", {"stage": "done", "state": "done"})
            yield _sse_event("done", {"message_id": message["id"]})

        except Exception as e:
            logger.exception("Unhandled error in chat stream")
            yield _sse_event("error", {
                "type": "runtime_error",
                "message": f"Internal server error: {e}",
            })

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: int | None = Query(None, alias="before"),
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """List messages for a chat session (ownership enforced).

    Supports cursor-based pagination: pass ``before=<message_id>`` to get
    older messages. Results are newest-first in the raw response; the
    client reverses them for display.
    """
    user_id = user["id"]

    # Verify ownership
    session = await store.get_chat_session(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = await store.list_messages(
        user_id,
        session_id,
        limit=limit,
        before_id=before,
    )

    return [
        MessageResponse(
            id=m["id"],
            role=m["role"],
            content_text=m["content_text"],
            code=m.get("code"),
            artifacts=json.loads(m["artifacts_json"]) if m.get("artifacts_json") else None,
            model=m.get("model"),
            created_at=m.get("created_at"),
        )
        for m in messages
    ]


