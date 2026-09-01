"""SQLite store with aiosqlite connection management and CRUD operations.

Every user-scoped query filters by ``user_id`` to enforce
the cross-cutting multiuser isolation requirement.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from core.errors import DuplicateError, NotFoundError

logger = logging.getLogger(__name__)

DATARA_DB_PATH = os.environ.get("DATARA_DB_PATH", os.path.expanduser("~/.datara/datara.db"))


class SqliteStore:
    """Async SQLite store wrapping aiosqlite.

    Opens a single connection (WAL mode, foreign keys on) and provides
    CRUD helpers for every model.  All user-scoped queries include an
    ``AND user_id = ?`` filter.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or DATARA_DB_PATH
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the database connection and set PRAGMAs."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SqliteStore not connected — call connect() first")
        return self._conn

    # ── Users ────────────────────────────────────────────────────────────────────

    async def create_user(self, email: str, password_hash: str) -> dict[str, Any]:
        """Insert a new user and return the full row.

        Raises ``DuplicateError`` if the email already exists.
        """
        try:
            cursor = await self.conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email, password_hash),
            )
            await self.conn.commit()
            row_id = cursor.lastrowid
            row = await self.conn.execute_fetchall(
                "SELECT id, email, password_hash, created_at FROM users WHERE id = ?",
                (row_id,),
            )
            return dict(row[0])
        except aiosqlite.IntegrityError:
            raise DuplicateError(f"email already exists: {email}")

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Look up a user by email. Returns None if not found."""
        rows = await self.conn.execute_fetchall(
            "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
            (email,),
        )
        return dict(rows[0]) if rows else None

    async def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        rows = await self.conn.execute_fetchall(
            "SELECT id, email, password_hash, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        return dict(rows[0]) if rows else None

    # ── Auth Sessions ────────────────────────────────────────────────────────────

    async def create_auth_session(
        self,
        user_id: int,
        token_hash: str,
        ttl_seconds: int = 28800,
    ) -> dict[str, Any]:
        """Create a new auth session row.

        Returns the full row (id, user_id, token_hash, created_at, expires_at,
        last_seen_at).
        """
        cursor = await self.conn.execute(
            "INSERT INTO auth_sessions (user_id, token_hash, expires_at) "
            "VALUES (?, ?, datetime('now', ? || ' seconds'))",
            (user_id, token_hash, str(ttl_seconds)),
        )
        await self.conn.commit()
        row_id = cursor.lastrowid
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, token_hash, created_at, expires_at, last_seen_at "
            "FROM auth_sessions WHERE id = ?",
            (row_id,),
        )
        return dict(rows[0])

    async def get_auth_session_by_token_hash(
        self,
        token_hash: str,
    ) -> dict[str, Any] | None:
        """Look up a non-expired auth session by token_hash.

        Returns None if not found or expired.  This is the ONLY session
        lookup path — ``auth_sessions.id`` is never used for lookup.
        """
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, token_hash, created_at, expires_at, last_seen_at "
            "FROM auth_sessions "
            "WHERE token_hash = ? AND expires_at > datetime('now')",
            (token_hash,),
        )
        return dict(rows[0]) if rows else None

    async def delete_auth_session(self, token_hash: str) -> None:
        """Delete one auth session by token_hash (used at logout)."""
        await self.conn.execute(
            "DELETE FROM auth_sessions WHERE token_hash = ?",
            (token_hash,),
        )
        await self.conn.commit()

    async def sweep_expired_sessions(self) -> int:
        """Delete all expired auth sessions. Returns count of deleted rows."""
        cursor = await self.conn.execute(
            "DELETE FROM auth_sessions WHERE expires_at < datetime('now')",
        )
        await self.conn.commit()
        return cursor.rowcount

    # ── Chat Sessions ───────────────────────────────────────────────────────────

    async def list_chat_sessions(self, user_id: int) -> list[dict[str, Any]]:
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, title, created_at, updated_at "
            "FROM chat_sessions WHERE user_id = ? "
            "ORDER BY updated_at DESC",
            (user_id,),
        )
        return [dict(r) for r in rows]

    async def create_chat_session(
        self,
        session_id: str,
        user_id: int,
        title: str = "New chat",
    ) -> dict[str, Any]:
        cursor = await self.conn.execute(
            "INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)",
            (session_id, user_id, title),
        )
        await self.conn.commit()
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, title, created_at, updated_at "
            "FROM chat_sessions WHERE id = ?",
            (session_id,),
        )
        return dict(rows[0])

    async def get_chat_session(
        self,
        session_id: str,
        user_id: int,
    ) -> dict[str, Any] | None:
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, title, created_at, updated_at "
            "FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        return dict(rows[0]) if rows else None

    async def delete_chat_session(self, session_id: str, user_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        await self.conn.commit()

    # ── User Settings ────────────────────────────────────────────────────────────

    async def get_user_settings(self, user_id: int) -> dict[str, Any] | None:
        rows = await self.conn.execute_fetchall(
            "SELECT user_id, api_key_enc, default_model, updated_at "
            "FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        return dict(rows[0]) if rows else None

    async def upsert_user_settings(
        self,
        user_id: int,
        *,
        api_key_enc: str | None = None,
        default_model: str | None = None,
    ) -> dict[str, Any]:
        await self.conn.execute(
            "INSERT INTO user_settings (user_id, api_key_enc, default_model, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "  api_key_enc = COALESCE(?, api_key_enc),"
            "  default_model = COALESCE(?, default_model),"
            "  updated_at = datetime('now')",
            (user_id, api_key_enc, default_model, api_key_enc, default_model),
        )
        await self.conn.commit()
        rows = await self.conn.execute_fetchall(
            "SELECT user_id, api_key_enc, default_model, updated_at "
            "FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        return dict(rows[0])