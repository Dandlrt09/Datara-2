"""Session cleanup service.

Runs expired-session sweep on startup and every hour via an asyncio
background task.
"""

from __future__ import annotations

import asyncio
import logging

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

    task = asyncio.create_task(_loop(), name="session-sweep")
    return task