"""Tests for profile_cache.serialize_profile / save_profile JSON safety."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pandas as pd

from core.data.profiler import build_profile
from server.migrate import apply_migrations
from server.services.profile_cache import get_profile, save_profile, serialize_profile
from server.services.sqlite_store import SqliteStore


def test_serialize_profile_datetime_is_json_safe():
    df = pd.DataFrame(
        {"fecha": pd.to_datetime(["2024-01-01", "2024-02-01"]), "v": [1.0, 2.0]}
    )
    profile = build_profile(df)
    schema_json, stats_json, sample_json = serialize_profile(profile)
    # none of the three payloads may raise
    json.loads(schema_json)
    json.loads(stats_json)
    json.loads(sample_json)
    stats = json.loads(stats_json)
    assert stats["fecha"]["sample_values"] == [
        str(pd.Timestamp("2024-01-01")),
        str(pd.Timestamp("2024-02-01")),
    ]


async def test_save_profile_persists_datetime_profile():
    tmp = tempfile.mktemp(suffix=".db")
    try:
        apply_migrations(tmp)
        raw = sqlite3.connect(tmp)
        raw.execute("INSERT INTO users (id,email,password_hash) VALUES (1,'u@e.com','h')")
        raw.execute("INSERT INTO chat_sessions (id,user_id,title) VALUES ('s1',1,'t')")
        raw.commit()
        raw.close()
        store = SqliteStore(tmp)
        await store.connect()
        fr = await store.create_file(
            user_id=1,
            chat_session="s1",
            filename="v.xlsx",
            storage_path="/tmp/v.xlsx",
            size_bytes=10,
            format_val="xlsx",
            row_count=2,
        )
        await save_profile(
            store,
            fr["id"],
            build_profile(pd.DataFrame({"d": pd.to_datetime(["2024-01-01"])})),
        )
        assert await get_profile(store, fr["id"], 1) is not None
        await store.close()
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
