"""Files router: upload, list, profile, delete.

All endpoints enforce ownership via the ``current_user`` dependency and
query-level user_id filtering (Decision #14).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from core.data.parser import parse_upload, parse_upload_sheet
from core.data.profiler import build_profile
from server.api.deps import current_user, get_store
from server.services.profile_cache import get_profile, save_profile
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["files"])

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


# ── Schemas ─────────────────────────────────────────────────────────────────


class FileResponse(BaseModel):
    id: int
    filename: str
    format: str
    size_bytes: int
    row_count: int | None = None
    created_at: str | None = None


class ProfileResponse(BaseModel):
    file_id: int
    schema_data: dict = Field(..., alias="schema")
    stats: dict
    sample: list
    generated_at: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class SheetListResponse(BaseModel):
    sheets: list[str]
    default_sheet: str


class FileCreateResponse(BaseModel):
    id: int
    filename: str
    format: str
    size_bytes: int
    row_count: int | None = None
    encoding: str | None = None
    sheet_name: str | None = None
    sheets: list[str] | None = None
    created_at: str | None = None


# ── Routes ──────────────────────────────────────────────────────────────────


def _ensure_upload_dir(user_id: int, chat_session: str) -> Path:
    """Create upload directory structure if it doesn't exist."""
    upload_path = UPLOADS_DIR / str(user_id) / chat_session
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


_SUPPORTED_EXTENSIONS = frozenset({".csv", ".tsv", ".xlsx", ".json"})


def _validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {ext}. Supported: csv, tsv, xlsx, json",
        )
    return ext


@router.post("/sessions/{session_id}/files", status_code=201)
async def upload_file(
    session_id: str,
    file: UploadFile,
    user: dict = Depends(current_user),
    store: SqliteStore = Depends(get_store),
):
    """Upload a file to a chat session.

    Parses the file (CSV/TSV/XLSX/JSON), auto-profiles it, and caches
    the profile. For XLSX, returns the sheet list for UI picker.
    """
    user_id = user["id"]

    # Verify session ownership
    session = await store.get_chat_session(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    ext = _validate_extension(file.filename or "unknown")
    format_hint = ext.lstrip(".")

    # Save to disk
    upload_dir = _ensure_upload_dir(user_id, session_id)
    safe_filename = Path(file.filename or f"upload{ext}").name
    dest_path = upload_dir / safe_filename

    content = await file.read()
    dest_path.write_bytes(content)
    size_bytes = len(content)

    # Parse (CPU-bound — would be offloaded via run_in_executor in production)
    try:
        df, meta = parse_upload(str(dest_path), format_hint=format_hint)
    except Exception as e:
        # Clean up the file on parse failure
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {e}",
        )

    # Build profile
    profile = build_profile(df, size_bytes=size_bytes)

    # Persist file record
    file_record = await store.create_file(
        user_id=user_id,
        chat_session=session_id,
        filename=safe_filename,
        storage_path=str(dest_path),
        size_bytes=size_bytes,
        format_val=meta.format,
        encoding=meta.encoding,
        sheet_name=meta.sheet_name,
        row_count=meta.row_count,
    )

    # Cache profile
    await save_profile(store, file_record["id"], profile)

    return FileCreateResponse(
        id=file_record["id"],
        filename=file_record["filename"],
        format=file_record["format"],
        size_bytes=file_record["size_bytes"],
        row_count=file_record["row_count"],
        encoding=file_record.get("encoding"),
        sheet_name=file_record.get("sheet_name"),
        sheets=meta.sheets,
        created_at=file_record.get("created_at"),
    )


@router.get("/sessions/{session_id}/files", response_model=list[FileResponse])
async def list_files(
    session_id: str,
    user: dict = Depends(current_user),
    store: SqliteStore = Depends(get_store),
):
    """List files for a chat session (ownership enforced)."""
    user_id = user["id"]

    # Verify session ownership
    session = await store.get_chat_session(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    files = await store.list_files(user_id, chat_session=session_id)
    return [
        FileResponse(
            id=f["id"],
            filename=f["filename"],
            format=f["format"],
            size_bytes=f["size_bytes"],
            row_count=f.get("row_count"),
            created_at=f.get("created_at"),
        )
        for f in files
    ]


@router.get("/files/{file_id}/profile", response_model=ProfileResponse)
async def get_file_profile(
    file_id: int,
    user: dict = Depends(current_user),
    store: SqliteStore = Depends(get_store),
):
    """Get a file's profile (ownership enforced via JOIN in query).

    Decision #14: Profiles are read through a JOIN with the files table
    that filters by ``files.user_id = current_user.id``.
    """
    user_id = user["id"]
    profile = await get_profile(store, file_id, user_id)
    if profile is None:
        # Could be missing profile OR cross-user access — return 404 either way
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileResponse(
        file_id=profile["file_id"],
        schema=profile["schema_data"],
        stats=profile["stats"],
        sample=profile["sample"],
        generated_at=profile.get("generated_at"),
    )


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: int,
    user: dict = Depends(current_user),
    store: SqliteStore = Depends(get_store),
):
    """Delete a file (ownership enforced)."""
    user_id = user["id"]
    file_record = await store.get_file(file_id, user_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found")

    # Delete from disk
    storage_path = file_record.get("storage_path")
    if storage_path and os.path.exists(storage_path):
        os.unlink(storage_path)

    # Delete from DB
    await store.delete_file(file_id, user_id)
    return None