"""Session cleanup service.

Runs expired-session sweep on startup and every hour via an asyncio
background task.
"""

from __future__ import annotations

import asyncio
import logging

from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

_SWEEP_INTERVAL_SECONDS = 3600  # 1 hour


async def sweep_expired(store: SqliteStore) -> int:
    """Delete all expired auth sessions. Returns count of deleted rows."""
    count = await store.sweep_expired_sessions()
    if count > 0:
        logger.info("Swept %d expired auth session(s)", count)
    return count


async def start_background_sweep(store: SqliteStore) -> asyncio.Task:
    """Start a background task that sweeps expired sessions every hour.

    The caller should store the returned task and cancel it on shutdown.
    """

    async def _loop():
        while True:
            await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
            try:
                await sweep_expired(store)
            except Exception:
                logger.exception("Background session sweep failed")

    task = asyncio.create_task(_loop(), name="session-sweep")
    return task