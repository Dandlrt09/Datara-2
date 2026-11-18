"""Data-folder router: where the analyst's data lives (F3b / T1).

The location is an *at-boot* decision, not a settings row: the store is opened
from :func:`server.db_path.resolve_db_path` in the lifespan, before any account
exists. The choice itself is the one-line pointer file in the OS default data
directory, so this router only reads and writes that pointer.

Both routes are deliberately UNAUTHENTICATED: the screen that makes the choice
runs on first start, before registration, when there is no session to present.

Changing the folder takes effect on the next boot (enfoque A: pointer +
restart). Nothing here re-opens the store or migrates data.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from server.db_path import (
    legacy_db_path_if_present,
    os_default_data_dir,
    read_data_location,
    resolve_db_path,
    write_data_location,
)
from server.synced_folders import detect_synced_client

router = APIRouter(prefix="/api/data-folder", tags=["data-folder"])

_ALREADY_DECIDED = (
    "La carpeta de datos ya está decidida: solo se puede elegir en el primer "
    "arranque."
)


class DataFolderResponse(BaseModel):
    decided: bool
    path: str
    default_path: str


class DataFolderUpdateResponse(DataFolderResponse):
    # Name of the cloud client that synchronises the chosen folder, or null.
    # Returned with the decision so the UI warns (S6) without a second call.
    synced_client: str | None = None


class DataFolderUpdateRequest(BaseModel):
    path: str


def _decided() -> bool:
    """Whether a data location is already decided.

    A pointer is the decision itself. A database in the pre-F3 location is a
    live install: S3 keeps reassigning one out of scope, and since the pointer
    outranks the legacy shim at the next boot, offering the picker there would
    silently move the analyst's data. The OS default's database is deliberately
    NOT a signal — under enfoque A the app creates an empty one at every boot,
    so counting it would hide the picker forever.
    """
    return read_data_location() is not None or legacy_db_path_if_present() is not None


def _current_folder() -> Path:
    """The data folder the server would use right now, same precedence as boot."""
    return Path(resolve_db_path()).parent


def _invalid_path(message: str) -> HTTPException:
    """Build the 422 rejection for a path the endpoint cannot accept."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "invalid_path", "message": message},
    )


def _unusable_folder(message: str) -> HTTPException:
    """Build the 422 rejection for a folder that cannot hold the data."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "path_not_writable", "message": message},
    )


def _chosen_folder(raw: str) -> Path:
    """Expand ``~`` and require an absolute folder path.

    The pointer stores an absolute path because the server may boot from any
    working directory; a relative one would mean different folders depending on
    how it was started.
    """
    candidate = raw.strip()
    if not candidate:
        raise _invalid_path("La ruta de la carpeta de datos no puede estar vacía.")
    folder = Path(candidate).expanduser()
    if not folder.is_absolute():
        raise _invalid_path(
            "La ruta de la carpeta de datos debe ser absoluta "
            f"(se recibió: {candidate})."
        )
    return folder


def _prepare_folder(folder: Path) -> None:
    """Create *folder* when missing and prove it can be written to.

    A folder that exists but rejects writes fails on the first chat, long after
    the analyst has moved on, so the write is probed here with an empty file the
    function removes before returning.
    """
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except FileExistsError as exc:
        raise _unusable_folder(
            f"La ruta elegida no es una carpeta: {folder}. Elige otra ruta."
        ) from exc
    except OSError as exc:
        raise _unusable_folder(
            f"No se pudo crear la carpeta de datos: {folder}. Elige otra ruta."
        ) from exc
    if not folder.is_dir():
        raise _unusable_folder(
            f"La ruta elegida no es una carpeta: {folder}. Elige otra ruta."
        )
    try:
        fd, probe = tempfile.mkstemp(prefix=".datara-write-probe-", dir=folder)
    except OSError as exc:
        raise _unusable_folder(
            f"No se puede escribir en la carpeta de datos: {folder}. "
            "Elige otra ruta."
        ) from exc
    os.close(fd)
    try:
        os.unlink(probe)
    except OSError:
        # A leftover probe file is cosmetic; the write itself succeeded.
        pass


@router.get("", response_model=DataFolderResponse)
async def get_data_folder():
    """Report the current data folder and whether the choice is still open."""
    return DataFolderResponse(
        decided=_decided(),
        path=str(_current_folder()),
        default_path=str(os_default_data_dir()),
    )


@router.put("", response_model=DataFolderUpdateResponse)
async def update_data_folder(body: DataFolderUpdateRequest):
    """Decide the data folder (first run only) and report its sync client."""
    if _decided():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "already_decided", "message": _ALREADY_DECIDED},
        )
    folder = _chosen_folder(body.path)
    _prepare_folder(folder)
    write_data_location(folder)
    return DataFolderUpdateResponse(
        decided=True,
        path=str(folder),
        default_path=str(os_default_data_dir()),
        synced_client=detect_synced_client(folder),
    )