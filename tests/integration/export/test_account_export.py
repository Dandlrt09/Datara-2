"""Integration tests for ``GET /api/export/account`` (T5, full account export).

The endpoint streams a zip with the caller's whole account: profile and
preferences, every chat, every saved analysis and the raw uploaded datasets.
Everything is owner-scoped, the stored API key must never leave, and a missing
byte on disk is reported instead of breaking the download.

Rows are seeded with raw SQL so the content assertions are deterministic.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.routers import auth as auth_router
from server.api.routers import export as export_router
from server.api.routers import files as files_router
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION
from tests.test_helpers import apply_all_migrations

PASSWORD = "password123"
RAW_BYTES = b"name,age\nAlice,30\nBob,25\n"


@pytest.fixture
def store():
    from server.api import store as api_store

    s = SqliteStore(db_path=":memory:")

    async def _setup():
        await s.connect()
        await apply_all_migrations(s)

    asyncio.run(_setup())
    previous = api_store._store
    api_store._store = s
    yield s
    asyncio.run(s.close())
    api_store._store = previous


@pytest.fixture
def client(store, tmp_path, monkeypatch):
    monkeypatch.setattr(files_router, "UPLOADS_DIR", tmp_path / "uploads")
    app = FastAPI()
    app.include_router(auth_router.router)
    app.include_router(export_router.router)
    return TestClient(app)


def _register(client, email):
    resp = client.post("/api/auth/register", json={"terms_version": TERMS_VERSION, "email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.json()["id"], resp.headers["set-cookie"]


def _run(store, sql, params=()):
    async def go():
        await store.conn.execute(sql, params)
        await store.conn.commit()

    asyncio.run(go())


def _seed_chat(store, user_id, chat_id, title="Ventas"):
    _run(
        store,
        "INSERT INTO chat_sessions (id, user_id, title) VALUES (?,?,?)",
        (chat_id, user_id, title),
    )


def _seed_message(store, user_id, chat_id, role, text):
    _run(
        store,
        "INSERT INTO messages (user_id, chat_session, role, content_text) VALUES (?,?,?,?)",
        (user_id, chat_id, role, text),
    )


def _seed_archive(store, user_id, chat_id, name, payload):
    _run(
        store,
        "INSERT INTO archives (user_id, name, chat_session, payload_json) VALUES (?,?,?,?)",
        (user_id, name, chat_id, json.dumps(payload)),
    )


def _seed_file(store, user_id, chat_id, filename, storage_path, size, fmt="csv"):
    _run(
        store,
        "INSERT INTO files (user_id, chat_session, filename, storage_path, size_bytes, format)"
        " VALUES (?,?,?,?,?,?)",
        (user_id, chat_id, filename, storage_path, size, fmt),
    )


def _write_raw(tmp_path, user_id, chat_id, filename):
    path = tmp_path / "uploads" / str(user_id) / chat_id
    path.mkdir(parents=True, exist_ok=True)
    dest = path / filename
    dest.write_bytes(RAW_BYTES)
    return str(dest)


def _download(client, cookie):
    resp = client.get("/api/export/account", headers={"cookie": cookie})
    assert resp.status_code == 200, resp.text
    return resp, zipfile.ZipFile(io.BytesIO(resp.content))


# ── Rules ───────────────────────────────────────────────────────────────────


def test_requires_authentication(client):
    assert client.get("/api/export/account").status_code == 401


def test_response_is_a_zip_attachment(client):
    _, cookie = _register(client, "a@example.com")
    resp, zf = _download(client, cookie)
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert ".zip" in resp.headers["content-disposition"]
    assert zf.testzip() is None


def test_empty_account_is_a_valid_zip(client):
    _, cookie = _register(client, "a@example.com")
    _, zf = _download(client, cookie)
    assert zf.testzip() is None
    assert "cuenta.json" in zf.namelist()
    assert json.loads(zf.read("chats/index.json")) == []


def test_zip_contains_the_expected_layout(client, store, tmp_path):
    uid, cookie = _register(client, "a@example.com")
    _seed_chat(store, uid, "c1", "Ventas")
    _seed_message(store, uid, "c1", "user", "¿cuánto vendimos?")
    _seed_message(store, uid, "c1", "assistant", "Vendimos 30.")
    _seed_archive(store, uid, "c1", "Informe", {"message_count": 2})
    storage_path = _write_raw(tmp_path, uid, "c1", "ventas.csv")
    _seed_file(store, uid, "c1", "ventas.csv", storage_path, len(RAW_BYTES))

    _, zf = _download(client, cookie)
    names = set(zf.namelist())
    assert "cuenta.json" in names
    assert "chats/index.json" in names
    assert "chats/c1.json" in names
    assert "analisis/index.json" in names
    assert "archivos/index.csv" in names
    assert any(n.startswith("archivos/") and n.endswith("ventas.csv") for n in names)

    # The chat snapshot is complete and chronological.
    chat = json.loads(zf.read("chats/c1.json"))
    assert [m["content_text"] for m in chat["messages"]] == [
        "¿cuánto vendimos?",
        "Vendimos 30.",
    ]
    # cuenta.json carries the profile without any secret.
    account = json.loads(zf.read("cuenta.json"))
    assert account["user"]["email"] == "a@example.com"
    assert "preferences" in account


def test_raw_dataset_bytes_are_exported_verbatim(client, store, tmp_path):
    uid, cookie = _register(client, "a@example.com")
    _seed_chat(store, uid, "c1")
    storage_path = _write_raw(tmp_path, uid, "c1", "ventas.csv")
    _seed_file(store, uid, "c1", "ventas.csv", storage_path, len(RAW_BYTES))

    _, zf = _download(client, cookie)
    raw_name = next(n for n in zf.namelist() if n.endswith("ventas.csv"))
    assert zf.read(raw_name) == RAW_BYTES

    rows = list(csv.DictReader(io.StringIO(zf.read("archivos/index.csv").decode())))
    assert len(rows) == 1
    assert rows[0]["filename"] == "ventas.csv"
    assert rows[0]["present"] == "true"


def test_export_is_owner_scoped(client, store, tmp_path):
    mine, cookie = _register(client, "a@example.com")
    other, _ = _register(client, "b@example.com")
    _seed_chat(store, mine, "mine")
    _seed_chat(store, other, "theirs")
    _seed_message(store, other, "theirs", "user", "secreto ajeno")
    _seed_archive(store, other, "theirs", "Ajeno", {"x": 1})
    other_path = _write_raw(tmp_path, other, "theirs", "ajeno.csv")
    _seed_file(store, other, "theirs", "ajeno.csv", other_path, len(RAW_BYTES))

    _, zf = _download(client, cookie)
    joined = "\n".join(zf.read(n).decode("utf-8", "replace") for n in zf.namelist())
    assert "secreto ajeno" not in joined
    assert "Ajeno" not in joined
    assert "ajeno.csv" not in joined
    assert json.loads(zf.read("chats/index.json"))[0]["id"] == "mine"


def test_never_exports_the_api_key_or_base_url(client, store):
    uid, cookie = _register(client, "a@example.com")

    async def _set():
        await store.upsert_user_settings(
            uid,
            api_key_enc="sk-super-secret-key",
            base_url="https://internal.example.com/v1?token=leak",
            default_model="gpt-4o",
            number_format="intl",
        )

    asyncio.run(_set())

    _, zf = _download(client, cookie)
    joined = "\n".join(zf.read(n).decode("utf-8", "replace") for n in zf.namelist())
    assert "sk-super-secret-key" not in joined
    assert "token=leak" not in joined
    account = json.loads(zf.read("cuenta.json"))
    assert account["settings"]["default_model"] == "gpt-4o"
    assert account["preferences"]["number_format"] == "intl"


def test_missing_bytes_are_reported_not_fatal(client, store, tmp_path):
    uid, cookie = _register(client, "a@example.com")
    _seed_chat(store, uid, "c1")
    _seed_file(store, uid, "c1", "gone.csv", str(tmp_path / "uploads" / "nope.csv"), 10)

    _, zf = _download(client, cookie)
    rows = list(csv.DictReader(io.StringIO(zf.read("archivos/index.csv").decode())))
    assert rows[0]["present"] == "false"
    assert "gone.csv" in zf.read("archivos/faltantes.txt").decode()


def test_storage_paths_outside_uploads_are_reported_not_leaked(client, store, tmp_path):
    # D7 defense in depth: a traversal, an absolute path outside the uploads
    # root, a directory and a missing file are all reported as missing — never
    # streamed, and never a 500.
    uid, cookie = _register(client, "a@example.com")
    _seed_chat(store, uid, "c1")
    (tmp_path / "uploads").mkdir(parents=True, exist_ok=True)
    _seed_file(store, uid, "c1", "abs.csv", "/etc/passwd", 5)
    _seed_file(store, uid, "c1", "rel.csv", "../../etc/passwd", 5)
    _seed_file(store, uid, "c1", "dir.csv", str(tmp_path / "uploads"), 5)
    _seed_file(store, uid, "c1", "gone.csv", str(tmp_path / "uploads" / "nope.csv"), 5)

    _, zf = _download(client, cookie)
    rows = list(csv.DictReader(io.StringIO(zf.read("archivos/index.csv").decode())))
    assert [r["present"] for r in rows] == ["false"] * 4
    joined = b"".join(zf.read(n) for n in zf.namelist())
    assert b"root:" not in joined  # /etc/passwd was never read
    faltantes = zf.read("archivos/faltantes.txt").decode()
    for name in ("abs.csv", "rel.csv", "dir.csv", "gone.csv"):
        assert name in faltantes


def test_csv_formula_injection_is_neutralized(client, store, tmp_path):
    # A user filename that starts a spreadsheet formula must stay literal text
    # in the export CSV.
    uid, cookie = _register(client, "a@example.com")
    _seed_chat(store, uid, "c1")
    storage_path = _write_raw(tmp_path, uid, "c1", "=cmd().csv")
    _seed_file(store, uid, "c1", "=cmd().csv", storage_path, len(RAW_BYTES))

    _, zf = _download(client, cookie)
    rows = list(csv.DictReader(io.StringIO(zf.read("archivos/index.csv").decode())))
    assert rows[0]["filename"] == "'=cmd().csv"
