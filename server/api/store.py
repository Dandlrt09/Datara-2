"""Shared global SqliteStore instance.

Set during app lifespan in ``server/api/main.py``.
Tests can override this directly.
"""

from __future__ import annotations

from typing import Optional

from server.services.sqlite_store import SqliteStore

_store: Optional[SqliteStore] = None