"""Session cleanup service.

Runs expired-session sweep on startup and every hour via an asyncio
background task.
"""

from __future__ import annotations

import asyncio
import logging
import time

from server.api.rate_limit import WINDOW_SECONDS
from server.api.routers.files import remove_user_uploads
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

_SWEEP_INTERVAL_SECONDS = 3600  # 1 hour


async def sweep_expired(store: SqliteStore) -> int:
    """Delete all expired auth sessions. Returns count of deleted rows."""
    count = await store.sweep_expired_sessions()
    if count > 0:
        logger.info("Swept %d expired auth session(s)", count)
    return count


async def sweep_expired_tokens(store: SqliteStore) -> int:
    """Delete unredeemable mailed tokens (D11). Returns rows deleted.

    Hygiene, not correctness: redemption re-checks expiry itself (D12), so a
    token left in the table is already refused. This only stops the table from
    growing forever.
    """
    count = await store.sweep_expired_auth_tokens()
    if count > 0:
        logger.info("Swept %d expired auth token(s)", count)
    return count


async def sweep_expired_attempts(store: SqliteStore) -> int:
    """Delete auth attempt counters older than the rate-limit window (S4).

    Hygiene, not correctness: the persistent limiter already ignores events
    outside its window, so a stale row only wastes space. Purging stops the
    table from growing forever, mirroring ``sweep_expired_tokens``.
    """
    count = await store.purge_auth_attempts(time.time() - WINDOW_SECONDS)
    if count > 0:
        logger.info("Swept %d expired auth attempt(s)", count)
    return count


async def purge_due_deletions(store: SqliteStore) -> int:
    """Purge every account whose deletion deadline has passed (D1/D4).

    The database is the source of truth (D7): each user row is deleted first
    (every child table cascades), then that user's upload bytes are removed
    best-effort. A failure on one account is logged and the rest still run, so
    a single bad row can never break the hourly sweep or the login path.
    Returns the number of accounts actually purged.
    """
    user_ids = await store.list_due_deletion_user_ids()
    purged = 0
    for user_id in user_ids:
        try:
            deleted = await store.purge_due_user(user_id)
        except Exception:
            logger.exception("Failed to purge account %s; skipping", user_id)
            continue
        # A False here means the account cancelled or rescheduled between the
        # listing and this delete (race): keep its bytes too.
        if deleted:
            purged += 1
            remove_user_uploads(user_id)
    if purged:
        logger.info("Purged %d account(s) past their deletion deadline", purged)
    return purged


async def start_background_sweep(store: SqliteStore) -> asyncio.Task:
    """Start a background task that sweeps expired sessions and due account
    purges every hour.

    The caller should store the returned task and cancel it on shutdown.
    """

    async def _loop():
        while True:
            await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
            try:
                await sweep_expired(store)
            except Exception:
                logger.exception("Background session sweep failed")
            try:
                await purge_due_deletions(store)
            except Exception:
                logger.exception("Background account purge failed")
            try:
                await sweep_expired_tokens(store)
            except Exception:
                logger.exception("Background auth token sweep failed")
            try:
                await sweep_expired_attempts(store)
            except Exception:
                logger.exception("Background auth attempt sweep failed")

    task = asyncio.create_task(_loop(), name="session-sweep")
    return task