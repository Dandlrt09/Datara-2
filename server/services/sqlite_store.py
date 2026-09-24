"""SQLite store with aiosqlite connection management and CRUD operations.

Every user-scoped query filters by ``user_id`` to enforce
the cross-cutting multiuser isolation requirement.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from core.errors import DuplicateError, NotFoundError
from server.db_path import resolve_db_path
from server.services.crypto import SecretBox

logger = logging.getLogger(__name__)

DATARA_DB_PATH = resolve_db_path()


class SqliteStore:
    """Async SQLite store wrapping aiosqlite.

    Opens a single connection (WAL mode, foreign keys on) and provides
    CRUD helpers for every model.  All user-scoped queries include an
    ``AND user_id = ?`` filter.
    """

    def __init__(self, db_path: str | None = None) -> None:
        # Resolve here too, so a caller passing a raw unexpanded path directly
        # can never split the DB from its key file. ``resolve_db_path(None)``
        # would re-read the env var at call time, so keep the module constant
        # for the default and only expand an explicit path.
        self._db_path = resolve_db_path(db_path) if db_path else DATARA_DB_PATH
        # Resolve the encryption key from this store's own DB location, never
        # from a module-level path. API keys are encrypted/decrypted at this
        # boundary so consumers keep seeing plaintext.
        self._secret_box = SecretBox.for_store(self._db_path)
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

    async def delete_chat_session(self, session_id: str, user_id: int) -> int:
        """Delete a chat session owned by *user_id*.

        Returns the number of deleted rows: ``0`` when the session does not
        exist or belongs to another user (the caller uses that to decide
        whether a ``DELETED`` event should be published), ``1`` on success.
        """
        cursor = await self.conn.execute(
            "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount

    # ── User Settings ────────────────────────────────────────────────────────────

    async def get_user_settings(self, user_id: int) -> dict[str, Any] | None:
        rows = await self.conn.execute_fetchall(
            "SELECT user_id, api_key_enc, default_model, provider_type, base_url, updated_at "
            "FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        return self._decrypt_settings_row(dict(rows[0])) if rows else None

    def _decrypt_settings_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Return a settings row with ``api_key_enc`` decrypted in place.

        Keeps the dict shape/keys identical; callers keep receiving the API
        key in plaintext.
        """
        row["api_key_enc"] = self._secret_box.decrypt(row.get("api_key_enc"))
        return row

    async def upsert_user_settings(
        self,
        user_id: int,
        *,
        api_key_enc: str | None = None,
        default_model: str | None = None,
        provider_type: str | None = None,
        base_url: str | None = None,
        provider_type_provided: bool = False,
        base_url_provided: bool = False,
    ) -> dict[str, Any]:
        # None must keep meaning "leave the existing column untouched"; only a
        # provided key gets encrypted before it is bound to SQL. An empty
        # string is normalized to None so a caller passing "" cannot silently
        # overwrite a stored key with an encrypted empty value.
        if api_key_enc == "":
            api_key_enc = None
        encrypted_key = (
            self._secret_box.encrypt(api_key_enc)
            if api_key_enc is not None
            else None
        )
        await self.conn.execute(
            "INSERT INTO user_settings (user_id, api_key_enc, default_model, provider_type, base_url, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "  api_key_enc = COALESCE(?, api_key_enc),"
            "  default_model = COALESCE(?, default_model),"
            "  provider_type = CASE WHEN ? THEN ? ELSE provider_type END,"
            "  base_url = CASE WHEN ? THEN ? ELSE base_url END,"
            "  updated_at = datetime('now')",
            (
                user_id, encrypted_key, default_model, provider_type, base_url,
                encrypted_key, default_model,
                int(provider_type_provided), provider_type,
                int(base_url_provided), base_url,
            ),
        )
        await self.conn.commit()
        rows = await self.conn.execute_fetchall(
            "SELECT user_id, api_key_enc, default_model, provider_type, base_url, updated_at "
            "FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        return self._decrypt_settings_row(dict(rows[0]))

    async def encrypt_legacy_api_keys(self) -> int:
        """Encrypt any plaintext ``api_key_enc`` rows written before encryption.

        Idempotent: rows that already look like Fernet tokens are skipped, so
        this is safe to run on every boot. Returns the number of rows
        re-encrypted.
        """
        rows = await self.conn.execute_fetchall(
            "SELECT user_id, api_key_enc FROM user_settings "
            "WHERE api_key_enc IS NOT NULL"
        )
        re_encrypted = 0
        for row in rows:
            value = row["api_key_enc"]
            if self._secret_box.is_encrypted(value):
                continue
            await self.conn.execute(
                "UPDATE user_settings SET api_key_enc = ? WHERE user_id = ?",
                (self._secret_box.encrypt(value), row["user_id"]),
            )
            re_encrypted += 1
        if re_encrypted:
            await self.conn.commit()
        return re_encrypted

    # ── Messages ──────────────────────────────────────────────────────────────

    async def create_message(
        self,
        user_id: int,
        chat_session: str,
        role: str,
        content_text: str,
        *,
        code: str | None = None,
        artifacts_json: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
    ) -> dict[str, Any]:
        """Insert a message and return the full row."""
        cursor = await self.conn.execute(
            "INSERT INTO messages (user_id, chat_session, role, content_text, "
            "code, artifacts_json, model, provider, tokens_in, tokens_out, cost_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, chat_session, role, content_text, code, artifacts_json,
             model, provider, tokens_in, tokens_out, cost_usd),
        )
        await self.conn.commit()
        row_id = cursor.lastrowid
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, chat_session, role, content_text, code, "
            "artifacts_json, model, provider, tokens_in, tokens_out, cost_usd, created_at "
            "FROM messages WHERE id = ?",
            (row_id,),
        )
        return dict(rows[0])

    async def list_messages(
        self,
        user_id: int,
        chat_session: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List messages for a chat session with pagination.

        ``before_id``: return messages with id < before_id (earlier).
        Results are ordered by created_at DESC, id DESC (newest first; the
        id tiebreaker keeps same-second messages deterministic), so the
        client reverses them for display.
        """
        if before_id is not None:
            rows = await self.conn.execute_fetchall(
                "SELECT id, user_id, chat_session, role, content_text, code, "
                "artifacts_json, model, provider, tokens_in, tokens_out, cost_usd, created_at "
                "FROM messages "
                "WHERE user_id = ? AND chat_session = ? AND id < ? "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (user_id, chat_session, before_id, limit),
            )
        else:
            rows = await self.conn.execute_fetchall(
                "SELECT id, user_id, chat_session, role, content_text, code, "
                "artifacts_json, model, provider, tokens_in, tokens_out, cost_usd, created_at "
                "FROM messages "
                "WHERE user_id = ? AND chat_session = ? "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (user_id, chat_session, limit),
            )
        return [dict(r) for r in rows]

    async def delete_messages_from(
        self,
        user_id: int,
        chat_session: str,
        from_id: int,
    ) -> int:
        """Delete *from_id* and every later message in the session.

        Truncation for the edit flow: messages are ordered by id and a corrected
        question invalidates every answer that followed it. Returns the number of
        deleted rows.
        """
        cursor = await self.conn.execute(
            "DELETE FROM messages "
            "WHERE user_id = ? AND chat_session = ? AND id >= ?",
            (user_id, chat_session, from_id),
        )
        await self.conn.commit()
        return cursor.rowcount

    async def get_message(
        self,
        message_id: int,
        user_id: int,
    ) -> dict[str, Any] | None:
        """Get a single message, enforcing ownership."""
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, chat_session, role, content_text, code, "
            "artifacts_json, model, provider, tokens_in, tokens_out, cost_usd, created_at "
            "FROM messages WHERE id = ? AND user_id = ?",
            (message_id, user_id),
        )
        return dict(rows[0]) if rows else None

    async def update_chat_session_timestamp(
        self,
        session_id: str,
        user_id: int,
    ) -> str | None:
        """Bump ``updated_at`` for a chat session, returning the NEW value.

        Returns ``None`` when no row matched (missing or foreign session).
        The timestamp is read back from the DB inside this method so the DB
        stays the single source of truth — it is never computed in Python.
        """
        cursor = await self.conn.execute(
            "UPDATE chat_sessions SET updated_at = datetime('now') "
            "WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        await self.conn.commit()
        if cursor.rowcount == 0:
            return None
        rows = await self.conn.execute_fetchall(
            "SELECT updated_at FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        return rows[0]["updated_at"] if rows else None

    async def update_chat_session_title(
        self,
        session_id: str,
        user_id: int,
        title: str,
    ) -> None:
        """Set a chat session's display title (auto-name from first question)."""
        await self.conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE id = ? AND user_id = ?",
            (title, session_id, user_id),
        )
        await self.conn.commit()

    async def rename_chat_session(
        self,
        session_id: str,
        user_id: int,
        title: str,
    ) -> dict[str, Any] | None:
        """Rename a chat session owned by *user_id*.

        Ownership is enforced in the WHERE clause (same pattern as
        ``delete_chat_session``). Returns the updated row, or ``None`` when
        the session does not exist or belongs to another user — the caller
        maps that to 404 without leaking existence.
        """
        cursor = await self.conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE id = ? AND user_id = ?",
            (title, session_id, user_id),
        )
        await self.conn.commit()
        if cursor.rowcount == 0:
            return None
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, title, created_at, updated_at "
            "FROM chat_sessions WHERE id = ?",
            (session_id,),
        )
        return dict(rows[0])

    # ── Archives ─────────────────────────────────────────────────────────────

    async def create_archive(
        self,
        user_id: int,
        name: str,
        chat_session: str,
        payload_json: str,
    ) -> dict[str, Any]:
        """Create a new archive and return the full row."""
        cursor = await self.conn.execute(
            "INSERT INTO archives (user_id, name, chat_session, payload_json) "
            "VALUES (?, ?, ?, ?)",
            (user_id, name, chat_session, payload_json),
        )
        await self.conn.commit()
        row_id = cursor.lastrowid
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, name, chat_session, payload_json, created_at "
            "FROM archives WHERE id = ?",
            (row_id,),
        )
        return dict(rows[0])

    async def list_archives(
        self,
        user_id: int,
    ) -> list[dict[str, Any]]:
        """List archives for a user, newest first."""
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, name, chat_session, created_at "
            "FROM archives WHERE user_id = ? "
            "ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in rows]

    async def get_archive(
        self,
        archive_id: int,
        user_id: int,
    ) -> dict[str, Any] | None:
        """Get a single archive, enforcing ownership."""
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, name, chat_session, payload_json, created_at "
            "FROM archives WHERE id = ? AND user_id = ?",
            (archive_id, user_id),
        )
        return dict(rows[0]) if rows else None

    # ── Files (UploadedFile) ──────────────────────────────────────────────────

    async def create_file(
        self,
        user_id: int,
        chat_session: str,
        filename: str,
        storage_path: str,
        size_bytes: int,
        format_val: str,
        *,
        encoding: str | None = None,
        sheet_name: str | None = None,
        row_count: int | None = None,
    ) -> dict[str, Any]:
        try:
            cursor = await self.conn.execute(
                "INSERT INTO files (user_id, chat_session, filename, storage_path, "
                "size_bytes, format, encoding, sheet_name, row_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, chat_session, filename, storage_path, size_bytes,
                 format_val, encoding, sheet_name, row_count),
            )
            await self.conn.commit()
        except aiosqlite.IntegrityError:
            await self.conn.rollback()
            raise DuplicateError(
                f"file already exists: {filename} in session {chat_session}"
            )
        file_id = cursor.lastrowid
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, chat_session, filename, storage_path, "
            "size_bytes, format, encoding, sheet_name, row_count, created_at "
            "FROM files WHERE id = ?",
            (file_id,),
        )
        return dict(rows[0])

    async def create_file_with_profile(
        self,
        *,
        user_id: int,
        chat_session: str,
        filename: str,
        storage_path: str,
        size_bytes: int,
        format_val: str,
        schema_json: str,
        stats_json: str,
        sample_json: str,
        encoding: str | None = None,
        sheet_name: str | None = None,
        row_count: int | None = None,
    ) -> dict[str, Any]:
        """Insert a file AND its profile in ONE transaction.

        Either both rows are committed or neither is. This makes the
        upload path atomic: a file row can never become visible without
        its profile (the false ``session/no_dataset`` bug).
        """
        try:
            cursor = await self.conn.execute(
                "INSERT INTO files (user_id, chat_session, filename, storage_path, "
                "size_bytes, format, encoding, sheet_name, row_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, chat_session, filename, storage_path, size_bytes,
                 format_val, encoding, sheet_name, row_count),
            )
            file_id = cursor.lastrowid
            await self.conn.execute(
                "INSERT INTO profiles (file_id, schema_json, stats_json, sample_json) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(file_id) DO UPDATE SET "
                "  schema_json = excluded.schema_json,"
                "  stats_json = excluded.stats_json,"
                "  sample_json = excluded.sample_json,"
                "  generated_at = datetime('now')",
                (file_id, schema_json, stats_json, sample_json),
            )
            await self.conn.commit()
        except aiosqlite.IntegrityError:
            await self.conn.rollback()
            raise DuplicateError(
                f"file already exists: {filename} in session {chat_session}"
            )
        except Exception:
            await self.conn.rollback()
            raise
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, chat_session, filename, storage_path, "
            "size_bytes, format, encoding, sheet_name, row_count, created_at "
            "FROM files WHERE id = ?",
            (file_id,),
        )
        return dict(rows[0])

    async def list_files(
        self,
        user_id: int,
        chat_session: str | None = None,
    ) -> list[dict[str, Any]]:
        if chat_session:
            rows = await self.conn.execute_fetchall(
                "SELECT f.id, f.user_id, f.chat_session, f.filename, f.storage_path, "
                "f.size_bytes, f.format, f.encoding, f.sheet_name, f.row_count, f.created_at, "
                "(p.file_id IS NOT NULL) AS has_profile "
                "FROM files f LEFT JOIN profiles p ON p.file_id = f.id "
                "WHERE f.user_id = ? AND f.chat_session = ? ORDER BY f.created_at DESC",
                (user_id, chat_session),
            )
        else:
            rows = await self.conn.execute_fetchall(
                "SELECT f.id, f.user_id, f.chat_session, f.filename, f.storage_path, "
                "f.size_bytes, f.format, f.encoding, f.sheet_name, f.row_count, f.created_at, "
                "(p.file_id IS NOT NULL) AS has_profile "
                "FROM files f LEFT JOIN profiles p ON p.file_id = f.id "
                "WHERE f.user_id = ? ORDER BY f.created_at DESC",
                (user_id,),
            )
        return [dict(r) for r in rows]

    async def list_files_with_session(
        self, user_id: int
    ) -> list[dict[str, Any]]:
        """List files with session title via LEFT JOIN.

        Returns all files for the user across sessions, with the session
        title from chat_sessions (NULL when the session was deleted).
        """
        rows = await self.conn.execute_fetchall(
            "SELECT f.id, f.filename, f.format, f.row_count, "
            "       f.size_bytes, f.created_at, f.chat_session, "
            "       cs.title AS session_title, "
            "       (p.file_id IS NOT NULL) AS has_profile "
            "FROM files f "
            "LEFT JOIN chat_sessions cs "
            "  ON cs.id = f.chat_session AND cs.user_id = ? "
            "LEFT JOIN profiles p ON p.file_id = f.id "
            "WHERE f.user_id = ? "
            "ORDER BY f.created_at DESC",
            (user_id, user_id),
        )
        return [dict(r) for r in rows]

    async def get_file(self, file_id: int, user_id: int) -> dict[str, Any] | None:
        """Get a file by id, enforcing ownership via user_id filter."""
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, chat_session, filename, storage_path, "
            "size_bytes, format, encoding, sheet_name, row_count, created_at "
            "FROM files WHERE id = ? AND user_id = ?",
            (file_id, user_id),
        )
        return dict(rows[0]) if rows else None

    async def get_file_by_name(
        self,
        user_id: int,
        chat_session: str,
        filename: str,
    ) -> dict[str, Any] | None:
        """Get a file by exact filename within one session (ownership enforced).

        Used by the upload endpoint to reject same-name re-uploads in the
        same session (the Files UI provides deletion, so the user deletes
        the old file first instead of silently duplicating rows).
        """
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, chat_session, filename, storage_path, "
            "size_bytes, format, encoding, sheet_name, row_count, created_at "
            "FROM files WHERE user_id = ? AND chat_session = ? AND filename = ? "
            "LIMIT 1",
            (user_id, chat_session, filename),
        )
        return dict(rows[0]) if rows else None

    async def total_size_by_user(
        self,
        user_id: int,
        chat_session: str | None = None,
    ) -> int:
        """Return total stored bytes for a user, optionally in one session.

        Backs the upload route's best-effort quota check. An empty result
        yields 0 via ``COALESCE``.
        """
        if chat_session is not None:
            rows = await self.conn.execute_fetchall(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM files "
                "WHERE user_id = ? AND chat_session = ?",
                (user_id, chat_session),
            )
        else:
            rows = await self.conn.execute_fetchall(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM files WHERE user_id = ?",
                (user_id,),
            )
        return int(rows[0][0]) if rows else 0

    async def delete_file(self, file_id: int, user_id: int) -> bool:
        """Delete a file, enforcing ownership. Returns True if a row was deleted."""
        cursor = await self.conn.execute(
            "DELETE FROM files WHERE id = ? AND user_id = ?",
            (file_id, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    # ── Profiles ──────────────────────────────────────────────────────────────

    async def upsert_profile(
        self,
        file_id: int,
        schema_json: str,
        stats_json: str,
        sample_json: str,
    ) -> dict[str, Any]:
        await self.conn.execute(
            "INSERT INTO profiles (file_id, schema_json, stats_json, sample_json) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(file_id) DO UPDATE SET "
            "  schema_json = excluded.schema_json,"
            "  stats_json = excluded.stats_json,"
            "  sample_json = excluded.sample_json,"
            "  generated_at = datetime('now')",
            (file_id, schema_json, stats_json, sample_json),
        )
        await self.conn.commit()
        rows = await self.conn.execute_fetchall(
            "SELECT file_id, schema_json, stats_json, sample_json, generated_at "
            "FROM profiles WHERE file_id = ?",
            (file_id,),
        )
        return dict(rows[0]) if rows else {}

    async def get_profile_with_ownership(
        self,
        file_id: int,
        user_id: int,
    ) -> dict[str, Any] | None:
        """Get a profile by file_id, enforcing ownership via JOIN files.

        Decision #14: file_id alone is never trusted for ownership.
        Profile reads MUST JOIN files ON profiles.file_id = files.id
        AND filter by files.user_id = current_user.id.
        """
        rows = await self.conn.execute_fetchall(
            "SELECT p.file_id, p.schema_json, p.stats_json, p.sample_json, p.generated_at "
            "FROM profiles p "
            "JOIN files f ON f.id = p.file_id "
            "WHERE p.file_id = ? AND f.user_id = ?",
            (file_id, user_id),
        )
        return dict(rows[0]) if rows else None