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
from server.services.auth_service import normalize_email
from server.services.crypto import SecretBox

logger = logging.getLogger(__name__)

DATARA_DB_PATH = resolve_db_path()

# D2 (T2): the user-agent header is caller-controlled and unbounded, and the
# sessions list only needs enough of it to say "Chrome en Windows".
USER_AGENT_MAX_LENGTH = 120

# D8 (T2): a session's last activity is rewritten at most once per this many
# seconds, so a polling page (the chat) cannot turn every request into a write.
ACTIVITY_TOUCH_SECONDS = 300

# ── Accent folding ───────────────────────────────────────────────────────────
# SQLite's ``lower()`` is ASCII-only and SQLite has no ``unaccent``; migrations
# here are ``.sql``-only, so an accent-folded column cannot be backfilled in
# SQL. Archive name search instead calls this Python UDF, which preserves the
# previous client-side behavior ("REGION" matches "región").
_ACCENT_FOLD_TABLE = str.maketrans(
    {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
        "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u", "Ü": "u", "Ñ": "n",
    }
)


def _unaccent(value: Any) -> Any:
    """Lowercase plus strip Spanish diacritics; other characters unchanged.

    Registered as the deterministic SQLite UDF ``unaccent`` in ``connect()``.
    ``None`` passes through so scanning a NULL name never raises.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    return value.translate(_ACCENT_FOLD_TABLE).lower()


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
        # Accent folding for archive name search (see `_unaccent`). The SQLite
        # build has no `unaccent`, so the fold is a Python UDF.
        await self._conn.create_function(
            "unaccent", 1, _unaccent, deterministic=True
        )

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

    async def create_user(
        self, email: str, password_hash: str, name: str | None = None
    ) -> dict[str, Any]:
        """Insert a new user and return the full row.

        The email is normalized first (S4/S5), so the stored identity never
        depends on capitalization or surrounding spaces. ``name`` is the
        optional display name chosen at signup (register-experience S2),
        already normalized by the caller; ``None`` stores SQL NULL, which reads
        back as the email-derived fallback. Raises ``DuplicateError`` if the
        email already exists.
        """
        email = normalize_email(email)
        try:
            cursor = await self.conn.execute(
                "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
                (email, password_hash, name),
            )
            await self.conn.commit()
            row_id = cursor.lastrowid
            row = await self.conn.execute_fetchall(
                "SELECT id, email, name, password_hash, created_at, "
                "pending_deletion_at FROM users WHERE id = ?",
                (row_id,),
            )
            return dict(row[0])
        except aiosqlite.IntegrityError:
            raise DuplicateError(f"email already exists: {email}")

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Look up a user by email, case- and space-insensitively (S4/S5).

        Normalizes the input and matches with ``COLLATE NOCASE``: the first
        guard is the write-side normalization, the second is the query, so a
        row written outside the router boundary still resolves. Returns None if
        not found.
        """
        rows = await self.conn.execute_fetchall(
            "SELECT id, email, name, password_hash, created_at, "
            "pending_deletion_at FROM users WHERE email = ? COLLATE NOCASE",
            (normalize_email(email),),
        )
        return dict(rows[0]) if rows else None

    async def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        rows = await self.conn.execute_fetchall(
            "SELECT id, email, name, password_hash, created_at, "
            "pending_deletion_at FROM users WHERE id = ?",
            (user_id,),
        )
        return dict(rows[0]) if rows else None

    async def update_user_name(self, user_id: int, name: str | None) -> bool:
        """Write the user-chosen display name (T1/D3).

        ``name`` is already normalized by the caller and is ``None`` when the
        user cleared it, which restores the email-derived fallback. Returns
        True if the user existed.
        """
        cursor = await self.conn.execute(
            "UPDATE users SET name = ? WHERE id = ?",
            (name, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def update_user_password(self, user_id: int, password_hash: str) -> bool:
        """Replace a user's stored password hash.

        Returns True if a row changed, False if the user does not exist.
        """
        cursor = await self.conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def request_user_deletion(
        self, user_id: int, grace_days: int = 7
    ) -> bool:
        """Schedule an account purge ``grace_days`` from now (S3).

        Writes the PURGE DEADLINE into ``pending_deletion_at`` (D1). Calling it
        again pushes the deadline out. Returns True if the user existed.
        """
        cursor = await self.conn.execute(
            "UPDATE users SET pending_deletion_at = datetime('now', ? || ' days') "
            "WHERE id = ?",
            (str(grace_days), user_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def cancel_user_deletion(self, user_id: int) -> bool:
        """Clear a scheduled purge so the account survives (S3).

        Returns True if the user existed.
        """
        cursor = await self.conn.execute(
            "UPDATE users SET pending_deletion_at = NULL WHERE id = ?",
            (user_id,),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def list_due_deletion_user_ids(self) -> list[int]:
        """User ids whose deletion deadline already passed (D1)."""
        rows = await self.conn.execute_fetchall(
            "SELECT id FROM users "
            "WHERE pending_deletion_at IS NOT NULL "
            "AND pending_deletion_at <= datetime('now') "
            "ORDER BY id",
        )
        return [row[0] for row in rows]

    async def purge_due_user(self, user_id: int) -> bool:
        """Delete a user row only while its deletion is still due (S10, D1).

        The ``DELETE`` re-checks the deadline in the same statement instead of
        trusting the sweep's earlier listing, so an account that was cancelled
        or rescheduled in between is kept (cancel-vs-purge race). Every child
        table cascades; the caller removes uploads from disk separately and
        best-effort (D5/D7). Returns True if a row was deleted.
        """
        cursor = await self.conn.execute(
            "DELETE FROM users "
            "WHERE id = ? "
            "AND pending_deletion_at IS NOT NULL "
            "AND pending_deletion_at <= datetime('now')",
            (user_id,),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def delete_all_auth_sessions(self, user_id: int) -> int:
        """Delete every auth session of a user (D3). Returns rows deleted."""
        cursor = await self.conn.execute(
            "DELETE FROM auth_sessions WHERE user_id = ?", (user_id,)
        )
        await self.conn.commit()
        return cursor.rowcount

    # ── Auth Sessions ────────────────────────────────────────────────────────────

    async def create_auth_session(
        self,
        user_id: int,
        token_hash: str,
        ttl_seconds: int = 28800,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Create a new auth session row.

        ``user_agent`` is stored truncated to ``USER_AGENT_MAX_LENGTH`` (D2);
        an empty value is stored as NULL, since it says no more than a missing
        one. No IP address is ever stored.

        Returns the full row (id, user_id, token_hash, created_at, expires_at,
        last_seen_at, user_agent).
        """
        stored_user_agent = user_agent[:USER_AGENT_MAX_LENGTH] if user_agent else None
        cursor = await self.conn.execute(
            "INSERT INTO auth_sessions "
            "(user_id, token_hash, expires_at, user_agent) "
            "VALUES (?, ?, datetime('now', ? || ' seconds'), ?)",
            (user_id, token_hash, str(ttl_seconds), stored_user_agent),
        )
        await self.conn.commit()
        row_id = cursor.lastrowid
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, token_hash, created_at, expires_at, last_seen_at, "
            "user_agent "
            "FROM auth_sessions WHERE id = ?",
            (row_id,),
        )
        return dict(rows[0])

    async def get_auth_session_by_id(
        self,
        user_id: int,
        session_id: int,
    ) -> dict[str, Any] | None:
        """Return one session of that user, or None.

        Owner-scoped: an id owned by somebody else is indistinguishable from an
        id that does not exist, so the caller cannot probe for other users'
        sessions (the router answers 404 either way).
        """
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, token_hash, user_agent, created_at, expires_at, "
            "last_seen_at "
            "FROM auth_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        return dict(rows[0]) if rows else None

    async def list_auth_sessions(
        self,
        user_id: int,
        current_token_hash: str,
    ) -> list[dict[str, Any]]:
        """List a user's live sessions, most recent activity first.

        ``token_hash`` is deliberately never returned: the caller identifies the
        row it is asking from through ``is_current`` (D3), which is the only
        thing the API needs to expose. Expired rows are filtered here as well as
        by the hourly sweep, so a session can never be listed as usable when it
        is not.
        """
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_agent, created_at, last_seen_at, "
            "(token_hash = ?) AS is_current "
            "FROM auth_sessions "
            "WHERE user_id = ? AND expires_at > datetime('now') "
            "ORDER BY last_seen_at DESC, id DESC",
            (current_token_hash, user_id),
        )
        return [{**dict(row), "is_current": bool(row["is_current"])} for row in rows]

    async def activity_summary(
        self, user_id: int, month_start: str, feed_limit: int = 10
    ) -> dict[str, Any]:
        """Read-only activity log for one user (T6): a mixed feed + month counts.

        Computed live from existing tables, so rows deleted with their chat
        disappear from it (S6). ``month_start`` is a ``YYYY-MM-DD HH:MM:SS`` UTC
        string compared lexically, the same format SQLite stores.
        """
        feed = await self.conn.execute_fetchall(
            "SELECT kind, title, at FROM ("
            " SELECT 'chat' AS kind, title, created_at AS at"
            "   FROM chat_sessions WHERE user_id = ?"
            " UNION ALL"
            " SELECT 'file', filename, created_at FROM files WHERE user_id = ?"
            " UNION ALL"
            " SELECT 'archive', name, created_at FROM archives WHERE user_id = ?"
            ") ORDER BY at DESC, kind LIMIT ?",
            (user_id, user_id, user_id, feed_limit),
        )
        counts = await self.conn.execute_fetchall(
            "SELECT"
            " (SELECT COUNT(*) FROM chat_sessions"
            "   WHERE user_id = :u AND created_at >= :m) AS chats,"
            " (SELECT COUNT(*) FROM messages"
            "   WHERE user_id = :u AND role = 'assistant' AND code IS NOT NULL"
            "   AND created_at >= :m) AS analyses,"
            " (SELECT COUNT(*) FROM files"
            "   WHERE user_id = :u AND created_at >= :m) AS files,"
            " (SELECT COALESCE(SUM(row_count), 0) FROM files"
            "   WHERE user_id = :u AND created_at >= :m) AS rows,"
            " (SELECT COUNT(*) FROM archives"
            "   WHERE user_id = :u AND created_at >= :m) AS archives",
            {"u": user_id, "m": month_start},
        )
        return {
            "events": [dict(r) for r in feed],
            "month": dict(counts[0]),
        }

    async def usage_months(
        self, user_id: int, current_month: str
    ) -> list[dict[str, Any]]:
        """Read-only monthly consumption for one user (T4), newest first.

        The series always carries ``current_month`` (``YYYY-MM``) plus every
        earlier month that has messages or archives, capped at 12 entries.
        Tokens and analyses come from ``messages`` (an analysis is an assistant
        message with non-null ``code``, the same criterion as ``activity_summary``);
        archives count every ``archives`` row of the month. The cost is
        none-propagating: one message with ``cost_usd IS NULL`` and tokens > 0
        makes the month ``cost_known=false`` with ``cost_usd=null``, never a
        partial sum. ``created_at`` is compared lexically on its ``YYYY-MM``
        prefix, the same format SQLite stores (D7).
        """
        rows = await self.conn.execute_fetchall(
            "WITH per_message AS ("
            " SELECT substr(created_at, 1, 7) AS month,"
            "   COALESCE(SUM(tokens_in), 0) AS tokens_in,"
            "   COALESCE(SUM(tokens_out), 0) AS tokens_out,"
            "   COALESCE(SUM(cost_usd), 0) AS cost_sum,"
            "   SUM(CASE WHEN role = 'assistant' AND code IS NOT NULL"
            "     THEN 1 ELSE 0 END) AS analyses,"
            "   SUM(CASE WHEN cost_usd IS NULL"
            "     AND (COALESCE(tokens_in, 0) > 0 OR COALESCE(tokens_out, 0) > 0)"
            "     THEN 1 ELSE 0 END) AS unpriced"
            " FROM messages WHERE user_id = :u GROUP BY month"
            "),"
            "per_archive AS ("
            " SELECT substr(created_at, 1, 7) AS month, COUNT(*) AS archives"
            " FROM archives WHERE user_id = :u GROUP BY month"
            "),"
            "months AS ("
            " SELECT month FROM per_message"
            " UNION SELECT month FROM per_archive"
            " UNION SELECT :cur"
            ")"
            " SELECT months.month AS month,"
            "   COALESCE(per_message.tokens_in, 0) AS tokens_in,"
            "   COALESCE(per_message.tokens_out, 0) AS tokens_out,"
            "   COALESCE(per_message.cost_sum, 0) AS cost_sum,"
            "   COALESCE(per_message.analyses, 0) AS analyses,"
            "   COALESCE(per_archive.archives, 0) AS archives,"
            "   COALESCE(per_message.unpriced, 0) AS unpriced"
            " FROM months"
            " LEFT JOIN per_message ON per_message.month = months.month"
            " LEFT JOIN per_archive ON per_archive.month = months.month"
            " ORDER BY months.month DESC LIMIT 12",
            {"u": user_id, "cur": current_month},
        )
        return [
            {
                "month": row["month"],
                "tokens_in": row["tokens_in"],
                "tokens_out": row["tokens_out"],
                "cost_usd": None if row["unpriced"] else row["cost_sum"],
                "cost_known": not row["unpriced"],
                "analyses": row["analyses"],
                "archives": row["archives"],
            }
            for row in rows
        ]

    async def touch_auth_session(
        self,
        token_hash: str,
        min_interval_seconds: int = ACTIVITY_TOUCH_SECONDS,
    ) -> bool:
        """Record activity on a session, at most once per interval (D8).

        The threshold lives in the UPDATE itself, so two concurrent requests
        cannot read-modify-write the same row and an unknown or expired token
        simply matches nothing instead of raising. Returns True when the row was
        actually rewritten.
        """
        cursor = await self.conn.execute(
            "UPDATE auth_sessions SET last_seen_at = datetime('now') "
            "WHERE token_hash = ? "
            "AND last_seen_at < datetime('now', ?)",
            (token_hash, f"{int(min_interval_seconds) * -1} seconds"),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def delete_auth_session_row(self, user_id: int, session_id: int) -> int:
        """Delete one session by id, owner-scoped (D5). Returns rows deleted.

        The row is what makes the closed browser fail: its next authenticated
        request finds no session and gets a 401.
        """
        cursor = await self.conn.execute(
            "DELETE FROM auth_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount

    async def pending_new_session_at(
        self,
        user_id: int,
        current_token_hash: str,
    ) -> str | None:
        """Return when the newest unacknowledged *other* live session that was
        created after this one was created, or None (D4/D9).

        Only younger sessions count (S6: "a session created after mine"): the
        mark is per user, so on the newest session every older one would
        otherwise be announced as a new session, dated before it existed.

        The acknowledgement mark is a session id, not a timestamp: ids are
        monotonic (``AUTOINCREMENT`` never reuses one), while these timestamps
        only have second granularity, so a login in the same second as an
        acknowledgement would otherwise be invisible forever. A NULL mark means
        the user never acknowledged anything, so any younger live session
        counts.
        """
        rows = await self.conn.execute_fetchall(
            "SELECT id, created_at FROM auth_sessions "
            "WHERE user_id = ? AND token_hash != ? "
            "AND expires_at > datetime('now') "
            "AND id > (SELECT id FROM auth_sessions WHERE token_hash = ?) "
            "ORDER BY id DESC LIMIT 1",
            (user_id, current_token_hash, current_token_hash),
        )
        if not rows:
            return None
        newest_id = rows[0]["id"]
        newest_at = rows[0]["created_at"]

        seen = await self.conn.execute_fetchall(
            "SELECT sessions_notice_seen_session_id AS seen_id FROM users WHERE id = ?",
            (user_id,),
        )
        seen_id = seen[0]["seen_id"] if seen else None
        if seen_id is not None and newest_id <= seen_id:
            return None
        return newest_at

    async def mark_sessions_notice_seen(
        self,
        user_id: int,
        current_token_hash: str,
    ) -> None:
        """Acknowledge the new-session notice up to the newest other live
        session (D9).

        Storing the observed id rather than ``now`` keeps the acknowledgement
        idempotent and race-free: a session created after this call still has a
        higher id and will warn again, even inside the same second.
        """
        rows = await self.conn.execute_fetchall(
            "SELECT COALESCE(MAX(id), 0) AS newest_id FROM auth_sessions "
            "WHERE user_id = ? AND token_hash != ? "
            "AND expires_at > datetime('now')",
            (user_id, current_token_hash),
        )
        await self.conn.execute(
            "UPDATE users SET sessions_notice_seen_session_id = ? WHERE id = ?",
            (rows[0]["newest_id"], user_id),
        )
        await self.conn.commit()

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

    async def delete_other_auth_sessions(
        self,
        user_id: int,
        keep_token_hash: str,
    ) -> int:
        """Delete a user's auth sessions except the one identified by token_hash.

        Used at password change: closes every other session while keeping the
        session that made the change alive. Returns the deleted row count.
        """
        cursor = await self.conn.execute(
            "DELETE FROM auth_sessions WHERE user_id = ? AND token_hash != ?",
            (user_id, keep_token_hash),
        )
        await self.conn.commit()
        return cursor.rowcount

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
            "SELECT user_id, api_key_enc, default_model, provider_type, base_url, "
            "number_format, date_format, currency_symbol, open_behavior, updated_at "
            "FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        return self._decrypt_settings_row(dict(rows[0])) if rows else None

    async def get_export_settings(self, user_id: int) -> dict[str, Any] | None:
        """Return the caller's *non-secret* settings for the account export (T5).

        Deliberately narrower than :meth:`get_user_settings`: the encrypted API
        key and the configurable ``base_url`` are never selected, so a future
        refactor cannot accidentally stream credentials into the export zip.
        The stored preferences come back raw (NULL = not chosen); callers
        resolve them with ``effective_preferences``.
        """
        rows = await self.conn.execute_fetchall(
            "SELECT default_model, provider_type, number_format, date_format, "
            "currency_symbol, open_behavior "
            "FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        return dict(rows[0]) if rows else None

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
        number_format: str | None = None,
        date_format: str | None = None,
        currency_symbol: str | None = None,
        open_behavior: str | None = None,
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
            "INSERT INTO user_settings (user_id, api_key_enc, default_model, provider_type, base_url, "
            "number_format, date_format, currency_symbol, open_behavior, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "  api_key_enc = COALESCE(?, api_key_enc),"
            "  default_model = COALESCE(?, default_model),"
            "  provider_type = CASE WHEN ? THEN ? ELSE provider_type END,"
            "  base_url = CASE WHEN ? THEN ? ELSE base_url END,"
            "  number_format = COALESCE(?, number_format),"
            "  date_format = COALESCE(?, date_format),"
            "  currency_symbol = COALESCE(?, currency_symbol),"
            "  open_behavior = COALESCE(?, open_behavior),"
            "  updated_at = datetime('now')",
            (
                user_id, encrypted_key, default_model, provider_type, base_url,
                number_format, date_format, currency_symbol, open_behavior,
                encrypted_key, default_model,
                int(provider_type_provided), provider_type,
                int(base_url_provided), base_url,
                number_format, date_format, currency_symbol, open_behavior,
            ),
        )
        await self.conn.commit()
        rows = await self.conn.execute_fetchall(
            "SELECT user_id, api_key_enc, default_model, provider_type, base_url, "
            "number_format, date_format, currency_symbol, open_behavior, updated_at "
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
        limit: int | None = 50,
        before_id: int | None = None,
        ascending: bool = False,
    ) -> list[dict[str, Any]]:
        """List messages for a chat session with pagination.

        ``before_id``: return messages with id < before_id (earlier).
        Default results are ordered by created_at DESC, id DESC (newest first;
        the id tiebreaker keeps same-second messages deterministic), so the
        client reverses them for display. ``ascending=True`` flips both the
        ordering and its id tiebreaker to ASC (oldest first). ``limit=None``
        omits the LIMIT clause entirely, returning every matching row.
        """
        order = "created_at ASC, id ASC" if ascending else "created_at DESC, id DESC"
        if before_id is not None:
            sql = (
                "SELECT id, user_id, chat_session, role, content_text, code, "
                "artifacts_json, model, provider, tokens_in, tokens_out, cost_usd, created_at "
                "FROM messages "
                "WHERE user_id = ? AND chat_session = ? AND id < ? "
                f"ORDER BY {order}"
            )
            params: list[Any] = [user_id, chat_session, before_id]
        else:
            sql = (
                "SELECT id, user_id, chat_session, role, content_text, code, "
                "artifacts_json, model, provider, tokens_in, tokens_out, cost_usd, created_at "
                "FROM messages "
                "WHERE user_id = ? AND chat_session = ? "
                f"ORDER BY {order}"
            )
            params = [user_id, chat_session]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = await self.conn.execute_fetchall(sql, params)
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
        *,
        limit: int | None = None,
        before_id: int | None = None,
        after_id: int | None = None,
        query: str | None = None,
        newest_first: bool = True,
    ) -> list[dict[str, Any]]:
        """List archives for a user, with optional search and ordering.

        ``limit``/``before_id``/``after_id`` are the keyset-pagination knobs and
        are keyword-only. All default to ``None``, so callers that need the FULL
        list keep today's behavior; only the API route bounds the query.

        - ``newest_first=True`` (default): ``ORDER BY created_at DESC, id DESC``
          and ``before_id`` returns archives with ``id < before_id`` (the oldest
          id of the previous page).
        - ``newest_first=False``: ``ORDER BY created_at ASC, id ASC`` and
          ``after_id`` returns archives with ``id > after_id`` (the newest id of
          the previous page).

        ``query`` filters by literal, case- and accent-insensitive substring on
        the name. It is folded here with the same ``unaccent`` UDF logic and
        bound to ``instr(unaccent(name), ?) > 0`` — ``instr`` (not ``LIKE``)
        means ``%``/``_`` in the query need no escaping.
        """
        sql = (
            "SELECT id, user_id, name, chat_session, payload_json, created_at "
            "FROM archives WHERE user_id = ?"
        )
        params: list[Any] = [user_id]
        if query:
            sql += " AND instr(unaccent(name), ?) > 0"
            params.append(_unaccent(query))
        order = (
            "created_at DESC, id DESC" if newest_first
            else "created_at ASC, id ASC"
        )
        if newest_first:
            if before_id is not None:
                sql += " AND id < ?"
                params.append(before_id)
        elif after_id is not None:
            sql += " AND id > ?"
            params.append(after_id)
        sql += f" ORDER BY {order}"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = await self.conn.execute_fetchall(sql, tuple(params))
        return [dict(r) for r in rows]

    async def delete_archive(self, archive_id: int, user_id: int) -> bool:
        """Delete an archive owned by the user; return whether a row went."""
        cursor = await self.conn.execute(
            "DELETE FROM archives WHERE id = ? AND user_id = ?",
            (archive_id, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def rename_archive(
        self,
        archive_id: int,
        user_id: int,
        name: str,
    ) -> dict[str, Any] | None:
        """Rename an archive owned by the user; return the updated row or None."""
        cursor = await self.conn.execute(
            "UPDATE archives SET name = ? WHERE id = ? AND user_id = ?",
            (name, archive_id, user_id),
        )
        await self.conn.commit()
        if cursor.rowcount == 0:
            return None
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, name, chat_session, payload_json, created_at "
            "FROM archives WHERE id = ?",
            (archive_id,),
        )
        return dict(rows[0])

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

    async def reselect_sheet(
        self,
        *,
        file_id: int,
        user_id: int,
        sheet_name: str,
        row_count: int | None,
        schema_json: str,
        stats_json: str,
        sample_json: str,
    ) -> dict[str, Any] | None:
        """Re-profile a file against a different sheet in ONE transaction.

        Updates ``files.sheet_name``/``row_count`` (ownership enforced in the
        WHERE clause) and upserts the file's single ``profiles`` row, with a
        single ``commit()``. Doing the two writes separately would open a
        window where the profile is sheet B while ``files.sheet_name`` still
        says sheet A.

        Returns the updated file row (same column list as ``get_file``), or
        ``None`` when no row belongs to this user (the route answers 404).
        Any failure rolls back and re-raises, so a failed switch leaves both
        rows exactly as they were.
        """
        try:
            cursor = await self.conn.execute(
                "UPDATE files SET sheet_name = ?, row_count = ? "
                "WHERE id = ? AND user_id = ?",
                (sheet_name, row_count, file_id, user_id),
            )
            if cursor.rowcount == 0:
                await self.conn.rollback()
                return None
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
        except Exception:
            await self.conn.rollback()
            raise
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, chat_session, filename, storage_path, "
            "size_bytes, format, encoding, sheet_name, row_count, created_at "
            "FROM files WHERE id = ?",
            (file_id,),
        )
        return dict(rows[0]) if rows else None

    async def rename_file(
        self,
        file_id: int,
        user_id: int,
        new_filename: str,
    ) -> dict[str, Any] | None:
        """Rename an uploaded file owned by *user_id*.

        Ownership is enforced in the WHERE clause (same pattern as
        ``rename_chat_session``). Returns the updated row, or ``None`` when the
        file does not exist or belongs to another user — the caller maps that
        to 404 without leaking existence. A collision with
        ``idx_files_unique_name`` (same session + name) is mapped to
        ``DuplicateError`` exactly like ``create_file``, so the insert-race path
        answers the same 409 the route's pre-check does.

        ``storage_path`` and the bytes on disk are never touched: only the
        persisted ``filename`` changes.
        """
        try:
            cursor = await self.conn.execute(
                "UPDATE files SET filename = ? WHERE id = ? AND user_id = ?",
                (new_filename, file_id, user_id),
            )
            await self.conn.commit()
        except aiosqlite.IntegrityError:
            await self.conn.rollback()
            raise DuplicateError(
                f"file already exists: {new_filename}"
            )
        if cursor.rowcount == 0:
            return None
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, chat_session, filename, storage_path, "
            "size_bytes, format, encoding, sheet_name, row_count, created_at "
            "FROM files WHERE id = ?",
            (file_id,),
        )
        return dict(rows[0]) if rows else None

    async def list_files(
        self,
        user_id: int,
        chat_session: str | None = None,
        *,
        limit: int | None = None,
        before_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List files for a user, optionally scoped to one chat session.

        ``limit``/``before_id`` are the F10 keyset-pagination knobs and are
        keyword-only. Both default to ``None`` = unlimited, so internal
        callers that need the FULL list (``chat_context``, the archive
        export) keep today's behavior; only the API routes bound the query.
        ``before_id`` returns files with ``id < before_id`` (the oldest id of
        the previous page) and ordering is ``created_at DESC, id DESC`` so the
        id tiebreaker keeps rows deterministic across pages.
        """
        sql = (
            "SELECT f.id, f.user_id, f.chat_session, f.filename, f.storage_path, "
            "f.size_bytes, f.format, f.encoding, f.sheet_name, f.row_count, f.created_at, "
            "(p.file_id IS NOT NULL) AS has_profile "
            "FROM files f LEFT JOIN profiles p ON p.file_id = f.id "
            "WHERE f.user_id = ?"
        )
        params: list[Any] = [user_id]
        if chat_session:
            sql += " AND f.chat_session = ?"
            params.append(chat_session)
        if before_id is not None:
            sql += " AND f.id < ?"
            params.append(before_id)
        sql += " ORDER BY f.created_at DESC, f.id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = await self.conn.execute_fetchall(sql, tuple(params))
        return [dict(r) for r in rows]

    async def list_files_with_session(
        self,
        user_id: int,
        *,
        limit: int | None = None,
        before_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List files with session title via LEFT JOIN.

        Returns all files for the user across sessions, with the session
        title from chat_sessions (NULL when the session was deleted).

        ``limit``/``before_id`` mirror ``list_files`` (F10 keyset
        pagination) and both default to ``None`` = unlimited, so callers that
        need the full list are unaffected.
        """
        sql = (
            "SELECT f.id, f.filename, f.format, f.row_count, "
            "       f.size_bytes, f.created_at, f.chat_session, "
            "       cs.title AS session_title, "
            "       (p.file_id IS NOT NULL) AS has_profile "
            "FROM files f "
            "LEFT JOIN chat_sessions cs "
            "  ON cs.id = f.chat_session AND cs.user_id = ? "
            "LEFT JOIN profiles p ON p.file_id = f.id "
            "WHERE f.user_id = ?"
        )
        params: list[Any] = [user_id, user_id]
        if before_id is not None:
            sql += " AND f.id < ?"
            params.append(before_id)
        sql += " ORDER BY f.created_at DESC, f.id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = await self.conn.execute_fetchall(sql, tuple(params))
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
        """Get a file by case-insensitive filename within one session.

        The name match uses :meth:`str.casefold` (Unicode-correct) rather than
        SQL ``COLLATE NOCASE``/``lower()``: SQLite folds ASCII only and has no
        ICU, so a NOCASE comparison would not collide ``AÑO.csv`` with
        ``año.csv``. This method is the single choke point shared by the upload
        and rename pre-checks, so both paths enforce the same broader rule.

        Layering: this application rule is a SUPERSET of the DB's ASCII-only
        ``NOCASE`` unique index (migration 0004), which is the race backstop.
        The app therefore never ALLOWS a name the index would reject.

        Ownership is enforced by the ``user_id`` filter. Used to reject a
        same-name re-upload/rename in the same session (the Files UI provides
        deletion, so the user deletes the old file first instead of silently
        duplicating rows).
        """
        rows = await self.conn.execute_fetchall(
            "SELECT id, user_id, chat_session, filename, storage_path, "
            "size_bytes, format, encoding, sheet_name, row_count, created_at "
            "FROM files WHERE user_id = ? AND chat_session = ?",
            (user_id, chat_session),
        )
        wanted = filename.casefold()
        for row in rows:
            if row["filename"].casefold() == wanted:
                return dict(row)
        return None

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