"""Domain model dataclasses for Datara.

All models are pure dataclasses with no external dependencies.
Server-layer code converts between these models and SQLite rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class User:
    id: int
    email: str
    password_hash: str
    created_at: datetime


@dataclass(frozen=True)
class AuthSession:
    """Authentication session.

    ``id`` is a surrogate row id used internally for joins/cleanup only.
    It is NEVER sent to the client or used for session lookup.
    Session lookup is by ``token_hash`` only.
    """

    id: int
    user_id: int
    token_hash: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class ChatSession:
    id: str
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Message:
    id: int
    user_id: int
    chat_session: str
    role: str  # "user" | "assistant" | "system"
    content_text: str
    code: str | None = None
    artifacts_json: str | None = None
    model: str | None = None
    provider: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class UploadedFile:
    id: int
    user_id: int
    chat_session: str
    filename: str
    storage_path: str
    size_bytes: int
    format: str
    encoding: str | None = None
    sheet_name: str | None = None
    row_count: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class DataProfile:
    file_id: int
    schema_json: str
    stats_json: str
    sample_json: str
    generated_at: datetime | None = None


@dataclass(frozen=True)
class CodeArtifact:
    """A single artifact from sandbox execution output."""

    name: str
    kind: str  # "figure" | "table"
    payload_json: str


@dataclass(frozen=True)
class Archive:
    id: int
    user_id: int
    name: str
    chat_session: str
    payload_json: str
    created_at: datetime | None = None