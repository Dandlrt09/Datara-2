"""Profile cache service: read/write data profiles with ownership enforcement.

Profile reads MUST enforce user ownership per Decision #14 — every profile
query JOINs ``files`` on ``profiles.file_id = files.id`` and filters by
``files.user_id = current_user.id``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)


async def get_profile(
    store: SqliteStore,
    file_id: int,
    user_id: int,
) -> dict[str, Any] | None:
    """Get a cached profile for a file, enforcing ownership.

    Returns the profile dict (schema_data, stats, sample,
    generated_at) or None if not found.  Ownership is enforced by JOIN
    with ``files`` table and ``user_id`` filter.
    """
    row = await store.get_profile_with_ownership(file_id, user_id)
    if row is None:
        return None
    return {
        "file_id": row["file_id"],
        "schema_data": json.loads(row["schema_json"]),
        "stats": json.loads(row["stats_json"]),
        "sample": json.loads(row["sample_json"]),
        "generated_at": row["generated_at"],
    }


def serialize_profile(profile: Any) -> tuple[str, str, str]:
    """Serialize a DataProfile into (schema_json, stats_json, sample_json).

    Derived entirely from ``profile_to_json`` so every value is JSON-safe.
    The previous implementation rebuilt ``stats_json`` from raw column
    attributes, so a ``pd.Timestamp`` / ``Decimal`` / numpy scalar reached
    ``json.dumps`` and raised, leaving an uploaded file with no profile row
    (the false ``session/no_dataset`` bug).
    """
    from core.data.profiler import profile_to_json  # noqa: PLC0415

    data = profile_to_json(profile)
    columns = data.get("columns", [])
    schema_data = {"columns": [{"name": c["name"], "dtype": c["dtype"]} for c in columns]}
    stats_data = {
        c["name"]: {
            "null_count": c["null_count"],
            "unique_count": c["unique_count"],
            "sample_values": c["sample_values"],
            "min": c["min"],
            "max": c["max"],
            "mean": c["mean"],
            "std": c["std"],
        }
        for c in columns
    }
    return (
        json.dumps(schema_data),
        json.dumps(stats_data),
        json.dumps(data.get("sample_rows", [])),
    )


async def save_profile(
    store: SqliteStore,
    file_id: int,
    profile: Any,  # DataProfile from core.data.profiler
) -> dict[str, Any]:
    """Serialize and cache a DataProfile (JSON-safe)."""
    schema_json, stats_json, sample_json = serialize_profile(profile)
    return await store.upsert_profile(
        file_id=file_id,
        schema_json=schema_json,
        stats_json=stats_json,
        sample_json=sample_json,
    )
