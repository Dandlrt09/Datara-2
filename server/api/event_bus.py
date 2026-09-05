"""Shared global EventBus instance.

Set during app lifespan in ``server/api/main.py``.
Tests can override this directly.
"""

from __future__ import annotations

from typing import Optional

from server.services.events import EventBus

bus: Optional[EventBus] = None