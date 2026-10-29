"""Account export router: stream the caller's whole account as a zip (T5).

One endpoint, ``GET /api/export/account``, owner-scoped like every other route.
The zip is produced with the stdlib ``zipfile`` over a write-only sink and
streamed out chunk by chunk (D4): the whole archive is never held in memory,
and uploaded datasets are read from disk in fixed-size blocks.

Security (D3): the exported settings are built from explicit, non-secret
columns. The stored API key and the configurable ``base_url`` never enter the
archive.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from server.api.deps import current_user, get_store
from server.api.routers import files as files_router
from server.services.preferences import effective_preferences
from server.services.sqlite_store import SqliteStore

router = APIRouter(prefix="/api/export", tags=["export"])

# Block size for reading a raw dataset off disk. Bounds the resident memory of
# one export to roughly this value regardless of how large the file is.
_READ_BLOCK = 1024 * 1024  # 1 MiB

_CSV_COLUMNS = (
    "id",
    "session",
    "filename",
    "format",
    "row_count",
    "size_bytes",
    "created_at",
    "present",
)

# Leading characters a spreadsheet reads as the start of a formula.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: Any) -> Any:
    """Neutralize spreadsheet formula injection in one CSV cell.

    A filename like ``=cmd()`` would be executed as a formula by Excel or
    Sheets when the user opens their own ``archivos/index.csv``. Prefixing the
    text with an apostrophe keeps it literal without mangling normal names.
    """
    if isinstance(value, str) and value.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value



class _ChunkSink:
    """Write-only file object for ``zipfile`` that buffers produced chunks.

    It intentionally exposes no ``tell``/``seek``. ``zipfile.ZipFile`` then
    wraps it in its own ``_Tellable`` and writes data descriptors instead of
    seeking back to patch sizes, so the archive can be generated and consumed
    one piece at a time. ``drain`` hands the buffered bytes to the caller and
    clears the buffer.
    """

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def write(self, data: bytes) -> int:
        self._chunks.append(bytes(data))
        return len(data)

    def flush(self) -> None:  # pragma: no cover - zipfile may call it
        pass

    def drain(self) -> list[bytes]:
        chunks, self._chunks = self._chunks, []
        return chunks


def _json_bytes(value: Any) -> bytes:
    """Serialize an export entry as pretty UTF-8 JSON (readable in the zip)."""
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _try_load_json(raw: Any) -> Any:
    """Parse a stored JSON string without ever raising (mirror of archive.py)."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _safe_storage_path(storage_path: Any) -> Path | None:
    """Resolve a stored path to a readable file under ``UPLOADS_DIR``.

    Defense in depth (mirrors the download route): a path outside the uploads
    root, or one whose bytes are gone, yields ``None`` so the caller records it
    as missing instead of failing the download (D7). Resolution happens at call
    time against ``files_router.UPLOADS_DIR`` so tests keep monkeypatching it.
    """
    if not isinstance(storage_path, str) or not storage_path:
        return None
    try:
        resolved = Path(storage_path).resolve()
        root = files_router.UPLOADS_DIR.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root):
        return None
    return resolved if resolved.is_file() else None


def _message_entry(message: dict[str, Any]) -> dict[str, Any]:
    """Project a stored message onto the export shape (no internal columns)."""
    return {
        "id": message["id"],
        "role": message["role"],
        "content_text": message["content_text"],
        "code": message.get("code"),
        "artifacts": _try_load_json(message.get("artifacts_json")),
        "model": message.get("model"),
        "provider": message.get("provider"),
        "tokens_in": message.get("tokens_in"),
        "tokens_out": message.get("tokens_out"),
        "cost_usd": message.get("cost_usd"),
        "created_at": message.get("created_at"),
    }


@router.get("/account")
async def export_account(
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
) -> StreamingResponse:
    """Stream the caller's account as a zip attachment.

    The manifest is read up front (D5): the response reflects the state at the
    moment the download starts, not a database-locked snapshot. An empty
    account still yields a valid archive (D9).
    """
    user_id = user["id"]

    settings = await store.get_export_settings(user_id)
    sessions = await store.list_chat_sessions(user_id)
    chats: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for session in sessions:
        messages = await store.list_messages(
            user_id, session["id"], limit=None, ascending=True
        )
        chats.append((session, messages))
    archives = await store.list_archives(user_id)
    files = await store.list_files(user_id)

    now = datetime.now(timezone.utc)
    exported_at = now.strftime("%Y-%m-%d %H:%M:%S")
    filename = f"datara-export-{now.strftime('%Y-%m-%d')}.zip"

    account = {
        "exported_at": exported_at,
        "user": {
            "id": user_id,
            "email": user["email"],
            "name": user.get("name"),
            "created_at": user.get("created_at"),
        },
        "preferences": effective_preferences(settings),
        "settings": {
            "default_model": (settings or {}).get("default_model"),
            "provider_type": (settings or {}).get("provider_type"),
        },
    }

    # Resolve disk presence once, so the CSV and the missing list agree.
    file_entries: list[tuple[dict[str, Any], Path | None]] = []
    missing: list[str] = []
    for record in files:
        resolved = _safe_storage_path(record.get("storage_path"))
        file_entries.append((record, resolved))
        if resolved is None:
            missing.append(f"{record['id']}-{Path(record['filename']).name}")

    def _iter_zip() -> Iterator[bytes]:
        sink = _ChunkSink()
        archive = zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED, allowZip64=True)
        try:
            archive.writestr("cuenta.json", _json_bytes(account))
            yield from sink.drain()

            archive.writestr(
                "chats/index.json",
                _json_bytes(
                    [
                        {
                            "id": session["id"],
                            "title": session["title"],
                            "created_at": session["created_at"],
                            "updated_at": session["updated_at"],
                        }
                        for session, _ in chats
                    ]
                ),
            )
            yield from sink.drain()
            for session, messages in chats:
                archive.writestr(
                    f"chats/{session['id']}.json",
                    _json_bytes(
                        {
                            "session": {
                                "id": session["id"],
                                "title": session["title"],
                                "created_at": session["created_at"],
                            },
                            "messages": [_message_entry(m) for m in messages],
                            "message_count": len(messages),
                        }
                    ),
                )
                yield from sink.drain()

            archive.writestr(
                "analisis/index.json",
                _json_bytes(
                    [
                        {
                            "id": item["id"],
                            "name": item["name"],
                            "chat_session": item["chat_session"],
                            "created_at": item["created_at"],
                        }
                        for item in archives
                    ]
                ),
            )
            yield from sink.drain()
            for item in archives:
                raw_payload = item.get("payload_json") or "{}"
                archive.writestr(f"analisis/{item['id']}.json", raw_payload)
                yield from sink.drain()

            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(_CSV_COLUMNS)
            for record, resolved in file_entries:
                writer.writerow(
                    [
                        _csv_safe(value)
                        for value in (
                            record["id"],
                            record["chat_session"],
                            record["filename"],
                            record["format"],
                            record.get("row_count"),
                            record["size_bytes"],
                            record["created_at"],
                            str(resolved is not None).lower(),
                        )
                    ]
                )
            archive.writestr("archivos/index.csv", csv_buffer.getvalue().encode("utf-8"))
            yield from sink.drain()

            for record, resolved in file_entries:
                if resolved is None:
                    continue
                info = zipfile.ZipInfo(
                    f"archivos/{record['id']}-{Path(record['filename']).name}"
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                with archive.open(info, "w") as dest:
                    with open(resolved, "rb") as source:
                        while True:
                            block = source.read(_READ_BLOCK)
                            if not block:
                                break
                            dest.write(block)
                yield from sink.drain()

            if missing:
                archive.writestr(
                    "archivos/faltantes.txt",
                    ("\n".join(missing) + "\n").encode("utf-8"),
                )
                yield from sink.drain()
        finally:
            # Idempotent: writes the central directory on the normal path and
            # releases the handle if the client disconnects mid-stream.
            archive.close()
        yield from sink.drain()

    return StreamingResponse(
        _iter_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
