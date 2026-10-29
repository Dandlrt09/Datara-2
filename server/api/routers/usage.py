"""Usage router: monthly consumption for the authenticated user (T4).

Read-only and owner-scoped: tokens, cost and stored analyses/archives, one
entry per UTC calendar month, newest first. The cost is never a partial sum:
a single message without a price makes the whole month "cost unknown".
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.api.deps import current_user, get_store
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api/usage", tags=["usage"])


class UsageMonth(BaseModel):
    month: str
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    cost_known: bool
    analyses: int
    archives: int


class UsageResponse(BaseModel):
    months: list[UsageMonth]


@router.get("", status_code=200)
async def get_usage(
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
) -> UsageResponse:
    """Return the caller's monthly consumption, newest first (D1)."""
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    months = await store.usage_months(user["id"], current_month)
    return UsageResponse(months=months)
