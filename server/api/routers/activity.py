"""Activity router: the personal activity log (T6).

Read-only and owner-scoped: a short mixed feed plus a calendar-month summary,
computed live from existing tables (no migration, no new writes).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.api.deps import current_user, get_store
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api/activity", tags=["activity"])


class ActivityEvent(BaseModel):
    kind: Literal["chat", "file", "archive"]
    title: str
    at: str


class MonthSummary(BaseModel):
    chats: int
    analyses: int
    files: int
    rows: int
    archives: int


class ActivityResponse(BaseModel):
    events: list[ActivityEvent]
    month: MonthSummary


@router.get("", status_code=200)
async def get_activity(
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
) -> ActivityResponse:
    """Return the caller's recent activity and current-month (UTC) totals."""
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01 00:00:00")
    data = await store.activity_summary(user["id"], month_start)
    return ActivityResponse(**data)
