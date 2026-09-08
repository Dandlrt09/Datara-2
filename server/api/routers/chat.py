"""Chat router: SSE chat stream and message history.

- ``POST /api/sessions/{id}/chat`` — returns ``text/event-stream``
  (SSE events: ``status``, ``token``, ``artifact``, ``done``, ``error``)
- ``GET /api/sessions/{id}/messages`` — paginated message history

Flow per design Chat Flow steps 1–9:
1. Validate ownership
2. Persist user message
3. Load context (profiles + message window)
4. Call LLM (non-streamed, json_schema)
5. Emit status(llm done) → token deltas
6. Run sandbox (single-shot)
7. Second-pass grounded narrative (pre-persist rewrite: replaces the
   streamed approach in the persisted message so the refetched
   answer carries only real computed numbers)
8. Persist assistant message BEFORE emitting artifacts (persist-then-emit)
9. Emit artifact → narrative deltas → status(done) → done {message_id}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
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
from server.api import event_bus as _event_bus_module
from server.api.deps import current_user, get_store
from server.services.chat_context import build_chat_context
from server.services.events import SessionEvent, SessionEventType
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
    # Retry re-runs the last failed turn: the question is NOT re-persisted
    # (it is already in history) and failed turns persist nothing.
    retry: bool = False


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


# Narrative decimals: models copy full-precision floats (e.g. profile means)
# into explanations despite prompt rules; enforce ≤6 places deterministically.
_FULL_PRECISION_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{7,}|\d+\.\d{7,}")


def _format_narrative_numbers(text: str) -> str:
    """Cap decimal places of numeric literals in narrative text to 6.

    Matches plain (``2500.8230981333336``) and thousands-grouped
    (``1,500,000.123456789``) decimals only — 7+ fractional digits — and
    rewrites them rounded to 6 places with thousands separators. Shorter
    decimals, integers, and non-numeric tokens (prod_004, dates) pass
    through untouched.
    """
    def _repl(match: re.Match[str]) -> str:
        value = float(match.group(0).replace(",", ""))
        return f"{value:,.6f}".rstrip("0").rstrip(".")

    return _FULL_PRECISION_NUMBER.sub(_repl, text)


def build_system_prompt(profiles: list[dict[str, Any]] | None = None) -> str:
    """Assemble the chat system prompt.

    Single source of truth shared by the chat router and the regression
    bench (scripts/bench.py). The bench previously used a hand-copied
    template that had drifted from this assembly AND never included the
    profile JSON, so it validated a prompt the app did not run.
    """
    system_prompt = (
        "You are a data analysis assistant. The user's datasets are described below. "
        "Generate Python code (pandas, numpy, plotly) to answer their question. "
        "For any chart or plot, use plotly (px or go) and assign the figure to a "
        "variable named fig — matplotlib does not exist in the sandbox and any "
        "matplotlib import fails. "
        "Return valid JSON with 'code' and 'explanation' fields only."
    )
    if profiles:
        system_prompt += f"\n\nAvailable datasets:\n{json.dumps(profiles, indent=2)}"
        system_prompt += (
            "\n\nIMPORTANT — file access: the code runs in a FRESH temporary "
            "working directory, so relative filenames do not exist. Read each "
            "dataset with EXACTLY its 'path' value above (absolute path), e.g. "
            "df = pd.read_csv('<path>'). Never invent paths."
        )
        system_prompt += (
            "\n\nIMPORTANT — dataset facts (citation discipline): each "
            "dataset has an authoritative 'row_count' = total data rows. "
            "When stating how many rows a dataset has, cite that number "
            "EXACTLY — never derive dataset size from per-column stats. "
            "In the stats, 'unique_count' is the number of DISTINCT values "
            "in that ONE column, not the dataset size. Describe date "
            "coverage only from explicit min/max when present, or from "
            "dates your code actually computed — never infer a range from "
            "the 5 sample values. Quote means/mins/maxes exactly as they "
            "appear in the profile; do not round or retype them."
        )
    system_prompt += (
        "\n\nIMPORTANT — execution model: every turn runs in a completely "
        "fresh sandbox. NOTHING persists between turns: no variables, no "
        "imports, no previous DataFrames. Your code must load the data "
        "itself and define every variable it uses, starting from scratch. "
        "Never reference df or any variable defined in a previous turn."
        "\n\nIMPORTANT — output size: keep 'explanation' under 120 words "
        "and never echo the question back. The JSON must always be "
        "complete and properly closed; prefer shorter code over an "
        "incomplete answer."
        "\n\nIMPORTANT — surfacing results: the chat UI only displays "
        "figures (variables named fig, fig1, fig2...), tables "
        "(DataFrames named df_result, df_<name>...) and printed output. "
        "The user NEVER sees console output unless it is printed or "
        "assigned to such variables. So: (1) assign every requested "
        "result table to a DataFrame variable named df_result (or "
        "df_<name>); (2) print() the key metrics; (3) state the main "
        "numbers directly in 'explanation' — never just describe what "
        "the code computes. Load the raw dataset into 'df' and do NOT "
        "reassign 'df' with a filtered/aggregated result: use a new "
        "df_<name> variable instead, so the raw dataset preview is not "
        "the table the user sees."
        "\n\nIMPORTANT — monthly aggregation: when grouping or "
        "resampling by month, anchor each label to the FIRST day of "
        "the month (resample('MS') or .dt.to_period('M').dt.start_time), "
        "never month-end ('M'), so chart bars align under the correct "
        "month label. On monthly charts force one tick per month: "
        "fig.update_xaxes(dtick='M1', tickformat='%b %Y')."
        "\n\nIMPORTANT — empty results: if a filter or groupby returns "
        "zero rows, SAY that plainly in 'explanation' (e.g. 'no hay "
        "ventas de ese producto en esas ciudades') and do NOT plot the "
"empty frame. NEVER invent, estimate or use placeholder values "
        "(no X, Y, Z, W): every number in 'explanation' must be one you "
        "actually computed. Write plain text: no Markdown, no **."
        "\n\nIMPORTANT — intent routing: First classify whether the user's question is descriptive or analytical. "
        "Descriptive questions ask about dataset characteristics (e.g., '¿De qué trata este dataset?', 'what are the columns?', 'how many rows?') "
        "— answer these with a narrative-only response citing row_count and key profile facts. Return empty code (\"code\": \"\") and emit zero artifacts. "
        "Analytical questions ask for computation, aggregation, filtering, or visualization — generate Python code to compute the answer, then "
        "write a grounded explanation that cites the computed numbers. "
        "IMPORTANT: in the pre-code explanation describe WHAT you will compute — NEVER invent or estimate specific result values; "
        "the exact numbers only exist after the code executes."
        "\n\nIMPORTANT — narrative quality: Write natural professional Spanish. Start with the conclusion or key finding. "
        "Format numeric values with ≤6 decimal places and thousands separators for readability (e.g., 5,035,600.021 — never full-precision floats like 2500.8230981333336). "
        "Never dump raw column listings or generate unsolicited charts. "
        "No Markdown formatting: use plain text, no **bold**, no bullet lists."
        "\n\nIMPORTANT — single result table: assign the final result to EXACTLY ONE df_ variable (df_result or df_<name>). "
        "Never store the same data under two df_ names (each df_ renders as a separate table): reuse and overwrite the same variable instead. "
        "Intermediate or filtered frames must use non-df names (aux, filtrado) so they don't render as tables."
    )
    return system_prompt


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

    # Step 2: Persist user message (skipped on retry — the failed turn's
    # question is already in history; re-persisting would duplicate it)
    if not body.retry:
        await store.create_message(
            user_id=user_id,
            chat_session=session_id,
            role="user",
            content_text=body.question,
        )
    # Auto-title: name the session after its first real question so the
    # sidebar is navigable (all sessions used to read "New chat").
    current_title = (session.get("title") or "").strip()
    if current_title in ("", "New chat"):
        new_title = body.question.strip()[:48] or "New chat"
        await store.update_chat_session_title(
            session_id, user_id, new_title
        )
        # Emit TITLED event after title write completes [R7]
        bus = _event_bus_module.bus
        if bus is not None:
            bus.publish(
                user_id,
                SessionEvent(
                    type=SessionEventType.TITLED,
                    session_id=session_id,
                    timestamp=time.time(),
                    payload={"title": new_title},
                ),
            )
    await store.update_chat_session_timestamp(session_id, user_id)

    def _publish_streaming_ended() -> None:
        # [R7] Every stream exit path must publish STREAMING_ENDED so other
        # tabs clear their streaming indicators. This includes the error
        # paths below, whose early `return` would otherwise skip the
        # generator's else-clause.
        bus = _event_bus_module.bus
        if bus is not None:
            bus.publish(
                user_id,
                SessionEvent(
                    type=SessionEventType.STREAMING_ENDED,
                    session_id=session_id,
                    timestamp=time.time(),
                    payload={"is_streaming": False},
                ),
            )

    async def _event_stream():
        # Emit STREAMING_STARTED at stream entry [R7]
        bus = _event_bus_module.bus
        if bus is not None:
            bus.publish(
                user_id,
                SessionEvent(
                    type=SessionEventType.STREAMING_STARTED,
                    session_id=session_id,
                    timestamp=time.time(),
                    payload={"is_streaming": True},
                ),
            )
        try:
            # Step 3: Load context
            context = await build_chat_context(store, user_id=user_id, chat_session=session_id)

            # Build the system prompt with profiles (single source of truth,
            # shared with the regression bench)
            system_prompt = build_system_prompt(context["profiles"])

            llm_messages = [{"role": "system", "content": system_prompt}]
            llm_messages.extend(context["messages"])
            # On retry the failed turn's question is already in history —
            # drop that trailing copy so the LLM receives it exactly once.
            if body.retry and llm_messages and llm_messages[-1]["role"] == "user":
                llm_messages.pop()
            llm_messages.append({"role": "user", "content": body.question})

            # Step 4: Resolve provider and call LLM
            provider = await _resolve_provider(store, user_id)

            try:
                llm_response = await provider.complete(
                    messages=llm_messages,
                    response_format=_CHAT_JSON_SCHEMA,
                    max_tokens=8192,
                    temperature=0.1,
                )
            except LLMError as e:
                yield _sse_event("error", {
                    "type": e.__class__.__name__,
                    "message": str(e),
                })
                yield _sse_event("status", {"stage": "error", "state": "error"})
                _publish_streaming_ended()
                return

            structured = llm_response.structured_data or {}
            explanation = _format_narrative_numbers(
                structured.get("explanation", llm_response.text) or ""
            )
            code = structured.get("code", "")

            # Step 5: Emit SSE — status(llm done) → token deltas → status(sandbox running)
            yield _sse_event("status", {"stage": "llm", "state": "done"})
            async for token_event in _emit_token_deltas(explanation):
                yield token_event
            yield _sse_event("status", {"stage": "sandbox", "state": "running"})

            # Step 6: Run sandbox (single-shot). Stage the session's uploads
            # into the sandbox cwd so generated code can read them by filename.
            # Memory default 1024MB: plotly.express + pandas virtual memory
            # exceeds the original 512MB budget (empirically verified).
            session_files = {
                p["filename"]: p["path"] for p in context["profiles"] if p.get("path")
            }
            sandbox_limits = {
                "cpu_seconds": 30,
                # 2048MB: RLIMIT_AS counts VIRTUAL memory; plotly.express +
                # pandas + numpy resident footprint pushes past 1024MB on
                # some systems and hard-kills the subprocess (empty stdout,
                # "possible hard OOM"). Empirically reproduced twice.
                "memory_mb": int(os.environ.get("DATARA_SANDBOX_MEMORY_MB", "2048")),
                "timeout_seconds": int(os.environ.get("DATARA_SANDBOX_TIMEOUT", "30")),
            }
            sandbox_result: dict[str, Any] = {}
            if code.strip():
                try:
                    sandbox_result = await run_code(code, limits=sandbox_limits, files=session_files or None)
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
                # Failed turns persist NOTHING: persisting here would render
                # the model's unverified explanation as if it were an answer
                # (the sandbox never computed it). History keeps the question;
                # the client offers Retry to re-run the turn.
                _publish_streaming_ended()
                return

            # Build artifacts JSON
            artifacts: list[dict] = []
            for fig in sandbox_result.get("figures", []):
                plotly_payload = fig.get("plotly", {})
                if isinstance(plotly_payload, str):
                    # plotly's figure.to_json() returns a JSON string; the
                    # browser's PlotlyChart expects the parsed object.
                    try:
                        plotly_payload = json.loads(plotly_payload)
                    except ValueError:
                        plotly_payload = {}
                artifacts.append({"kind": "figure", "name": fig.get("name", ""), "payload": plotly_payload})
            for tbl in sandbox_result.get("tables", []):
                artifacts.append({"kind": "table", "name": tbl.get("name", ""), "payload": {"columns": tbl.get("columns", []), "rows": tbl.get("rows", [])}})
            # Printed results reach the chat: the sandbox captures print()
            # stdout, but figures/tables alone left numeric answers invisible
            # ("los resultados se imprimen en consola"). Cap to keep the SSE
            # and persisted payloads bounded.
            # When a result table already renders the same data, the raw
            # stdout box is redundant noise for the user (scientific
            # notation, index numbers) — suppress it and keep the stdout
            # box only for stdout-only answers.
            stdout_text = ""
            if sandbox_result.get("status") == "ok":
                stdout_text = str(sandbox_result.get("text") or "").strip()
            has_table = any(a["kind"] == "table" for a in artifacts)
            if stdout_text and not has_table:
                artifacts.append({
                    "kind": "text",
                    "name": "stdout",
                    "payload": {"text": stdout_text[:4000]},
                })

            # Step 7: Second-pass grounded narrative for analytical turns.
            # Runs BEFORE persisting so the persisted message row is the
            # single source of truth: ChatView clears streaming text and
            # refetches messages on done, so a narrative emitted after
            # persist-but-not-persisted is discarded by the refetch.
            # The grounding call receives the EXACT table values: stdout
            # prints large floats in scientific notation (9.407413e+08),
            # which silently loses precision — narratives built from it
            # rounded (940,741,300 vs the table's 940,741,259.01).
            table_context = ""
            for tbl in artifacts:
                if tbl["kind"] != "table":
                    continue
                lines = [
                    f"{tbl['name']}: columns={tbl['payload']['columns']}",
                    *(
                        "  " + " | ".join(str(cell) for cell in row)
                        for row in tbl["payload"]["rows"]
                    ),
                ]
                table_context += "\nResult table (exact values):\n" + "\n".join(lines)
            grounded_narrative = ""
            grounding_usage = None
            if code.strip() and sandbox_result.get("status") == "ok":
                sandbox_output = str(sandbox_result.get("text") or "").strip()
                if sandbox_output:
                    try:
                        grounding_messages = [
                            {"role": "system", "content": (
                                "You are a data analysis assistant. The user asked a question and received an initial answer. "
                                "The code has now executed and produced results below. "
                                "Rewrite the explanation to be grounded in the ACTUAL computed numbers. "
                                "Copy numeric values EXACTLY as they appear in the provided results — never round them. "
                                "Format large numbers with thousands separators for readability (e.g. 76,036,762.77). "
                                "Keep every key computed value, do not drop any. For long results never enumerate every row: "
                                "highlight only the top 2-3 inline and refer to the table for the rest. "
                                "Do not keep the original estimates: the rewritten narrative must contain ONLY the real computed values. "
                                "Refer to results naturally (e.g. 'la tabla', 'el gráfico'), never by variable names like df_result. "
                                "Plain text only: no Markdown, no **bold**, no bullet lists. "
                                "Keep the response concise (under 80 words). Write in natural professional Spanish."
                            )},
                            {"role": "user", "content": f"Original question: {body.question}\n\nOriginal explanation: {explanation}\n\nExecution output:\n{sandbox_output}{table_context}"}
                        ]
                        grounding_response = await provider.complete(
                            messages=grounding_messages,
                            max_tokens=500,
                            temperature=0.1,
                        )
                        grounded_narrative = _format_narrative_numbers(
                            grounding_response.text.strip()
                        )
                        grounding_usage = grounding_response.usage
                        if grounded_narrative:
                            # Rewrite semantics (spec R2): the grounded
                            # narrative REPLACES the streamed approach in the
                            # persisted message. Appending both left the
                            # approach's invented estimates contradicting the
                            # computed numbers in the final message.
                            explanation = grounded_narrative
                    except Exception as e:
                        logger.warning("Second-pass LLM failed, continuing with original explanation: %s", e)
                        # Continue with original explanation if second-pass fails

            # Step 8: Persist assistant message BEFORE emitting artifacts (persist-then-emit)
            message = await store.create_message(
                user_id=user_id,
                chat_session=session_id,
                role="assistant",
                content_text=explanation,
                code=code,
                artifacts_json=json.dumps(artifacts, allow_nan=False) if artifacts else None,
                model=llm_response.model,
                provider=llm_response.provider,
                tokens_in=llm_response.usage.tokens_in + (grounding_usage.tokens_in if grounding_usage else 0),
                tokens_out=llm_response.usage.tokens_out + (grounding_usage.tokens_out if grounding_usage else 0),
                cost_usd=llm_response.usage.cost_usd + (grounding_usage.cost_usd if grounding_usage else 0.0),
            )

            # Step 9: Emit — artifact → grounded narrative deltas → status(done) → done
            if artifacts:
                yield _sse_event("artifact", {
                    "figures": sandbox_result.get("figures", []),
                    "tables": sandbox_result.get("tables", []),
                    "texts": [
                        a["payload"]["text"]
                        for a in artifacts
                        if a["kind"] == "text"
                    ],
                })

            if grounded_narrative:
                async for token_event in _emit_token_deltas("\n\n" + grounded_narrative):
                    yield token_event

            yield _sse_event("status", {"stage": "done", "state": "done"})
            yield _sse_event("done", {"message_id": message["id"]})

        except asyncio.CancelledError:
            # Emit STREAMING_ENDED before re-raise on client abort [R7]
            _publish_streaming_ended()
            raise
        except Exception as e:
            logger.exception("Unhandled error in chat stream")
            # Emit STREAMING_ENDED on the error path too: other tabs rely on
            # the events stream to clear their streaming indicators [R7].
            _publish_streaming_ended()
            yield _sse_event("error", {
                "type": "runtime_error",
                "message": f"Internal server error: {e}",
            })
        else:
            # Emit STREAMING_ENDED on normal completion [R7]
            _publish_streaming_ended()

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


