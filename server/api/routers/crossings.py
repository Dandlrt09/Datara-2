"""Dataset crossing router (F5): the recipe that joins two files of a session.

A crossing is stored as a RECIPE (S4) — which two files, which key on each side,
how they are joined — never as a derived dataset: the merge itself is written by
the model inside the sandbox on every turn, from the recipe carried in that
turn's system prompt (T3). This router owns the recipe's lifecycle only.

One crossing stays active per session (S5), so confirming a new one replaces the
previous recipe in place instead of accumulating a list of half-decisions.

Every endpoint enforces ownership twice, per Decision #14: the session must
belong to the caller, and both files must belong to the caller AND to that
session. A key is validated against the dataset's profile (A4), so a key that is
not a column of that file is an explicit refusal and never a silently empty
merge.

Confirming a crossing also reports its imbalance (S6): the diagnostics are
counted on the server with pandas (A2, ``crossing_diagnostics``) BEFORE the
recipe is stored, so a crossing that cannot run is refused while the session
still has no crossing, and the analyst sees how many rows fell out of each side
in the same answer.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from server.api.deps import current_user, get_store
from server.services.crossing_diagnostics import (
    DatasetRef,
    DatasetUnreadableError,
    KeysNotComparableError,
    compute_crossing_diagnostics,
)
from server.services.profile_cache import get_profile
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["crossings"])

# The join kinds pandas offers and the model can be told to write. Kept narrow
# to what pd.merge understands by name.
JoinKind = Literal["inner", "left", "right", "outer"]


class CrossingRequest(BaseModel):
    """The recipe the analyst confirms."""

    model_config = ConfigDict(extra="forbid")

    left_file_id: int
    right_file_id: int
    left_key: str
    right_key: str
    how: JoinKind = "inner"


async def _require_session(
    store: SqliteStore, session_id: str, user_id: int
) -> None:
    """404 unless *session_id* exists and belongs to the caller."""
    session = await store.get_chat_session(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")


async def _require_session_file(
    store: SqliteStore, file_id: int, session_id: str, user_id: int
) -> dict[str, Any]:
    """Return the file row, or 404 unless it belongs to the caller and the session.

    A file of another session is refused with the same answer as a file that does
    not exist: from this route's point of view it simply is not a file of this
    session, and naming the difference would leak which ids exist.
    """
    row = await store.get_file(file_id, user_id)
    if row is None or row["chat_session"] != session_id:
        raise HTTPException(status_code=404, detail="File not found")
    return row


async def _require_key_in_dataset(
    store: SqliteStore,
    *,
    file_id: int,
    user_id: int,
    filename: str,
    key: str,
) -> None:
    """422 unless *key* is a column of that file's profile (A4).

    Validating against the profile (not by opening the file again) keeps this
    check to one query and agrees with what the prompt tells the model the
    dataset contains. A file without a stored profile cannot have a key
    validated at all, so it is refused with the same code: the rule is one,
    "the key must be a column of this dataset".
    """
    profile = await get_profile(store, file_id, user_id)
    columns = [
        column["name"]
        for column in (profile or {}).get("schema_data", {}).get("columns", [])
    ]
    if key in columns:
        return
    if columns:
        message = (
            f"Column '{key}' is not in '{filename}'. "
            f"Available columns: {', '.join(columns)}."
        )
    else:
        message = (
            f"Column '{key}' cannot be checked against '{filename}': "
            "the dataset has no profile yet. Re-upload the file."
        )
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "crossing_key_not_in_dataset", "message": message},
    )


async def _compute_diagnostics(
    left: dict[str, Any],
    right: dict[str, Any],
    body: CrossingRequest,
) -> dict[str, int]:
    """Count the crossing's imbalance now, or refuse it with an explicit 422.

    S6 reports what the merge left out; A2 puts that count on the server, where
    it is deterministic. A dataset that cannot be parsed, or two keys pandas
    cannot compare, is refused here — before the recipe is stored — so the
    analyst never gets a crossing that only fails later, at query time.
    """
    try:
        return await compute_crossing_diagnostics(
            left=DatasetRef.from_file_row(left),
            right=DatasetRef.from_file_row(right),
            left_key=body.left_key,
            right_key=body.right_key,
            how=body.how,
        )
    except DatasetUnreadableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "crossing_dataset_unreadable", "message": str(exc)},
        ) from exc
    except KeysNotComparableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "crossing_keys_not_comparable", "message": str(exc)},
        ) from exc


@router.post("/sessions/{session_id}/crossings")
async def create_crossing(
    session_id: str,
    body: CrossingRequest,
    store: SqliteStore = Depends(get_store),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """Confirm the session's active crossing, replacing a previous one."""
    user_id = user["id"]
    await _require_session(store, session_id, user_id)

    if body.left_file_id == body.right_file_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "crossing_same_file",
                "message": "A dataset cannot be crossed with itself.",
            },
        )

    left = await _require_session_file(store, body.left_file_id, session_id, user_id)
    right = await _require_session_file(store, body.right_file_id, session_id, user_id)

    await _require_key_in_dataset(
        store,
        file_id=left["id"],
        user_id=user_id,
        filename=left["filename"],
        key=body.left_key,
    )
    await _require_key_in_dataset(
        store,
        file_id=right["id"],
        user_id=user_id,
        filename=right["filename"],
        key=body.right_key,
    )

    diagnostics = await _compute_diagnostics(left, right, body)

    crossing = await store.upsert_crossing(
        user_id=user_id,
        chat_session=session_id,
        left_file_id=left["id"],
        right_file_id=right["id"],
        left_key=body.left_key,
        right_key=body.right_key,
        how=body.how,
    )
    if crossing is None:
        # The session was deleted while the checks above were running.
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {**crossing, "diagnostics": diagnostics}


@router.get("/sessions/{session_id}/crossings")
async def get_crossing(
    session_id: str,
    store: SqliteStore = Depends(get_store),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """Return the session's active crossing, or ``null`` when there is none."""
    await _require_session(store, session_id, user["id"])
    return {"crossing": await store.get_crossing(user["id"], session_id)}


@router.delete("/sessions/{session_id}/crossings", status_code=204)
async def delete_crossing(
    session_id: str,
    store: SqliteStore = Depends(get_store),
    user: dict[str, Any] = Depends(current_user),
) -> None:
    """Remove the session's active crossing. Idempotent: 204 either way."""
    await _require_session(store, session_id, user["id"])
    await store.delete_crossing(user["id"], session_id)
