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

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from core.data.parser import parse_upload, parse_upload_sheet, xlsx_uncompressed_size
from core.data.profiler import build_profile
from core.errors import DuplicateError
from server.api.deps import current_user, get_store
from server.limits import get_limits
from server.services.profile_cache import get_profile, serialize_profile
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["files"])

_DEFAULT_UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"

# Streaming read chunk and the slack allowed over max_upload_bytes when
# interpreting Content-Length. Multipart bodies carry boundaries and part
# headers, so the raw body is slightly larger than the file: a 1 MB margin
# guarantees a file exactly at the cap is never falsely rejected.
_CHUNK_BYTES = 1024 * 1024
_CONTENT_LENGTH_MARGIN = 1024 * 1024

# Uploads root, resolved at import time. Override with DATARA_UPLOADS_DIR so
# deployments and test harnesses can relocate it (tests point this at a
# per-test tmp directory; no test may write into the real server/uploads/).
UPLOADS_DIR = Path(os.environ.get("DATARA_UPLOADS_DIR", str(_DEFAULT_UPLOADS_DIR)))


# ── Schemas ─────────────────────────────────────────────────────────────────


class FileResponse(BaseModel):
    id: int
    filename: str
    format: str
    size_bytes: int
    row_count: int | None = None
    created_at: str | None = None
    has_profile: bool = False


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


class FileListItem(BaseModel):
    id: int
    filename: str
    format: str
    row_count: int | None = None
    size_bytes: int
    created_at: str | None = None
    chat_session_id: str
    session_title: str | None
    has_profile: bool = False


# ── Routes ──────────────────────────────────────────────────────────────────


def _ensure_upload_dir(user_id: int, chat_session: str) -> Path:
    """Create upload directory structure if it doesn't exist."""
    upload_path = UPLOADS_DIR / str(user_id) / chat_session
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


def remove_session_uploads(user_id: int, chat_session: str) -> None:
    """Remove a session's upload directory from disk (best-effort).

    Called on session delete: the DB rows (files → profiles, messages)
    cascade via FK, but the stored files would otherwise be orphaned
    under ``UPLOADS_DIR/<user_id>/<session_id>/``. Never raises — a
    filesystem failure is logged and the caller's delete must still
    succeed.
    """
    session_dir = UPLOADS_DIR / str(user_id) / chat_session
    try:
        if session_dir.is_dir():
            shutil.rmtree(session_dir)
    except OSError:
        logger.warning(
            "Best-effort cleanup failed: could not remove upload dir for "
            "session %s (user %s)",
            chat_session,
            user_id,
            exc_info=True,
        )


_SUPPORTED_EXTENSIONS = frozenset({".csv", ".tsv", ".xlsx", ".json"})


def _duplicate_name_detail(safe_filename: str) -> str:
    """Shared 409 detail for a same-name collision.

    Both the pre-check and the insert-time UNIQUE violation use this so the
    two collision paths can never drift apart.
    """
    return (
        f"A file named '{safe_filename}' already exists in this session. "
        "Delete it first before uploading a file with the same name."
    )


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
    request: Request,
    file: UploadFile,
    user: dict = Depends(current_user),
    store: SqliteStore = Depends(get_store),
):
    """Upload a file to a chat session.

    Parses the file (CSV/TSV/XLSX/JSON), auto-profiles it, and caches
    the profile. For XLSX, returns the sheet list for UI picker.

    Cancellation: the client may abort the upload (AbortController).
    The disconnect is checked after the body is received and again
    before persisting, so a cancelled upload never leaves a file row
    or an orphaned file on disk. 499 is the nginx convention for
    "client closed request".
    """
    user_id = user["id"]

    ext = _validate_extension(file.filename or "unknown")
    format_hint = ext.lstrip(".")

    # Verify session ownership
    session = await store.get_chat_session(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    safe_filename = Path(file.filename or f"upload{ext}").name

    limits = get_limits()

    # Content-Length fast reject, before touching disk. Accepting the part
    # means Starlette has already buffered the multipart body, but this avoids
    # the extra copy to the destination file when the declared size is clearly
    # over the cap. The margin covers multipart boundaries/headers.
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            declared_bytes = int(declared_length)
        except ValueError:
            declared_bytes = None
        if (
            declared_bytes is not None
            and declared_bytes > limits.max_upload_bytes + _CONTENT_LENGTH_MARGIN
        ):
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"File too large: request body of {declared_bytes} bytes exceeds "
                    f"the {limits.max_upload_bytes}-byte per-file limit."
                ),
            )

    # Same-name guard: file deletion exists (DELETE /api/files/{id} and the
    # Files UI), so a repeated basename in the same session is rejected
    # instead of silently overwriting the stored file and duplicating the
    # files/profiles rows. The user deletes the old file first.
    duplicate = await store.get_file_by_name(user_id, session_id, safe_filename)
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_duplicate_name_detail(safe_filename),
        )

    # Quota check (best-effort soft cap, checked before any disk write). Two
    # concurrent uploads can race past this; the per-file byte cap is the hard
    # bound. Session quota is checked first so the message is more specific.
    session_bytes = await store.total_size_by_user(user_id, chat_session=session_id)
    if session_bytes >= limits.max_session_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"Session storage quota exceeded: {session_bytes} bytes already "
                f"stored, limit {limits.max_session_bytes} bytes."
            ),
        )
    user_bytes = await store.total_size_by_user(user_id)
    if user_bytes >= limits.max_user_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"User storage quota exceeded: {user_bytes} bytes already "
                f"stored, limit {limits.max_user_bytes} bytes."
            ),
        )

    # Stream to disk in bounded chunks so a huge upload never becomes one
    # in-memory buffer, and the per-file cap is enforced as bytes arrive.
    upload_dir = _ensure_upload_dir(user_id, session_id)
    dest_path = upload_dir / safe_filename

    size_bytes = 0
    try:
        with dest_path.open("wb") as dest:
            while True:
                chunk = await file.read(_CHUNK_BYTES)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > limits.max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=(
                            f"File too large: exceeds the "
                            f"{limits.max_upload_bytes}-byte per-file limit."
                        ),
                    )
                dest.write(chunk)
    except Exception:
        # Never leave a truncated orphan behind (including the 413 above).
        dest_path.unlink(missing_ok=True)
        raise

    # The client may have aborted while the body streamed in.
    if await request.is_disconnected():
        dest_path.unlink(missing_ok=True)
        return Response(status_code=499)

    # XLSX is a zip container: reject a zip bomb by the archive's declared
    # uncompressed total BEFORE openpyxl inflates it. A non-zip payload falls
    # through to parse_upload, which reports the real 400.
    if format_hint == "xlsx":
        try:
            expanded_bytes = xlsx_uncompressed_size(str(dest_path))
        except Exception:
            expanded_bytes = None
        if expanded_bytes is not None and expanded_bytes > limits.max_expanded_bytes:
            dest_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"XLSX expands to {expanded_bytes} bytes, over the "
                    f"{limits.max_expanded_bytes}-byte expanded limit."
                ),
            )

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

    # Post-parse backstop for NON-xlsx formats: this runs AFTER parse, so it
    # cannot prevent the memory spike — the raw byte cap above is what bounds
    # the input. It catches a DataFrame whose in-memory footprint is still
    # over the expanded-size budget.
    footprint_bytes = int(df.memory_usage(deep=True).sum())
    if footprint_bytes > limits.max_expanded_bytes:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"Parsed data uses {footprint_bytes} bytes in memory, over the "
                f"{limits.max_expanded_bytes}-byte expanded limit."
            ),
        )

    # Build AND serialize the profile BEFORE any DB write: a serialization
    # failure must never leave a committed file row without its profile.
    profile = build_profile(df, size_bytes=size_bytes)
    schema_json, stats_json, sample_json = serialize_profile(profile)

    # The client may have cancelled while parsing/profiling a large file —
    # do not persist a file the user no longer wants.
    if await request.is_disconnected():
        dest_path.unlink(missing_ok=True)
        return Response(status_code=499)

    # Persist the file row and its profile atomically (one transaction).
    try:
        file_record = await store.create_file_with_profile(
            user_id=user_id,
            chat_session=session_id,
            filename=safe_filename,
            storage_path=str(dest_path),
            size_bytes=size_bytes,
            format_val=meta.format,
            encoding=meta.encoding,
            sheet_name=meta.sheet_name,
            row_count=meta.row_count,
            schema_json=schema_json,
            stats_json=stats_json,
            sample_json=sample_json,
        )
    except DuplicateError:
        # Lost the insert race against a concurrent same-name upload: the row
        # that won owns dest_path, so keep the bytes on disk and answer with
        # the same 409 the pre-check returns.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_duplicate_name_detail(safe_filename),
        )
    except Exception:
        dest_path.unlink(missing_ok=True)
        logger.exception("Failed to persist uploaded file and profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist uploaded file",
        )

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
            has_profile=bool(f.get("has_profile")),
        )
        for f in files
    ]


@router.get("/files", response_model=list[FileListItem])
async def list_all_files(
    user: dict = Depends(current_user),
    store: SqliteStore = Depends(get_store),
):
    """List ALL files for the current user across all chat sessions."""
    rows = await store.list_files_with_session(user["id"])
    return [
        FileListItem(
            id=r["id"],
            filename=r["filename"],
            format=r["format"],
            row_count=r.get("row_count"),
            size_bytes=r["size_bytes"],
            created_at=r.get("created_at"),
            chat_session_id=r["chat_session"],
            session_title=r.get("session_title"),
            has_profile=bool(r.get("has_profile")),
        )
        for r in rows
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