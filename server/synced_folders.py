"""Detect whether a directory sits inside a cloud-synced folder.

F3 / S3 requires the analyst's data folder to live *"fuera de cualquier carpeta
sincronizada (OneDrive/Dropbox)"*: a synchronising client copies the SQLite
database while Datara writes to it and replicates uploaded data to the cloud.
This module answers that one question and nothing else.

Detection uses local signals only -- no network, no dependency:

* the client's own environment variables (``OneDrive``, ``OneDriveConsumer``,
  ``OneDriveCommercial``);
* well-known path segments (``OneDrive``, ``Dropbox``, ``Google Drive``,
  ``iCloud Drive``, ``Mobile Documents``);
* the marker files the clients leave behind (``.dropbox``, ``.dropbox.cache``,
  ``desktop.ini`` inside an OneDrive root).

The path need not exist yet: the analyst may be choosing a brand-new folder.
The check is purely advisory -- S8 decided *"avisar y permitir"*, so the caller
warns and lets the user continue; nothing here refuses a path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Environment variables the OneDrive client sets on Windows, in the order we
# prefer them when reporting the client name.
_ONEDRIVE_ENV_VARS = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")

# Well-known directory names, keyed by the client they belong to. Compared in
# the platform's case convention (see :func:`_normalise_part`): exact on a
# case-sensitive filesystem, case-folded where the platform folds case.
_KNOWN_SEGMENTS = {
    "OneDrive": "OneDrive",
    "Dropbox": "Dropbox",
    "Google Drive": "Google Drive",
    "iCloud Drive": "iCloud Drive",
    "Mobile Documents": "iCloud Drive",
}

# Marker files the clients drop in the root of the folder they manage.
_DROPBOX_MARKERS = (".dropbox", ".dropbox.cache")
_ONEDRIVE_MARKER = "desktop.ini"


def _case_insensitive() -> bool:
    """Whether this platform compares paths case-insensitively by default."""
    return sys.platform in ("win32", "darwin")


def _normalise(path: os.PathLike[str] | str) -> str:
    """Expand ``~`` and collapse ``.``/``..``/redundant separators.

    ``normpath`` is purely lexical: it does not require the path to exist and
    never touches the filesystem, so a brand-new folder normalises the same as
    an existing one.
    """
    return os.path.normpath(os.path.expanduser(os.fspath(path)))


def _normalise_part(part: str) -> str:
    return part.casefold() if _case_insensitive() else part


def _same_path(left: str, right: str) -> bool:
    left_norm = _normalise(left)
    right_norm = _normalise(right)
    if _case_insensitive():
        left_norm = left_norm.casefold()
        right_norm = right_norm.casefold()
    return left_norm == right_norm


def _is_within(root: str, path: str) -> bool:
    """Whether *path* is *root* itself or nested below it."""
    root_norm = _normalise(root)
    path_norm = _normalise(path)
    if _case_insensitive():
        root_norm = root_norm.casefold()
        path_norm = path_norm.casefold()
    if path_norm == root_norm:
        return True
    return path_norm.startswith(root_norm.rstrip(os.sep) + os.sep)


def _onedrive_roots() -> list[str]:
    return [value for value in (os.environ.get(v) for v in _ONEDRIVE_ENV_VARS) if value]


def _segment_client(path: str) -> str | None:
    for part in Path(_normalise(path)).parts:
        normalised = _normalise_part(part)
        for known, client in _KNOWN_SEGMENTS.items():
            if normalised == _normalise_part(known):
                return client
    return None


def _ancestors(path: Path):
    current = path
    while True:
        yield current
        parent = current.parent
        if parent == current:
            break
        current = parent


def _is_onedrive_root(directory: Path) -> bool:
    if _normalise_part(directory.name) == "onedrive":
        return True
    return any(_same_path(root, str(directory)) for root in _onedrive_roots())


def _marker_client(path: str) -> str | None:
    """Walk up from *path* looking for a client marker in an existing ancestor.

    A path that does not exist yet still has existing ancestors, so a chosen
    folder inside a synced root is detected before it is created. ``desktop.ini``
    only counts inside an OneDrive root, since Windows scatters that file
    everywhere.
    """
    for directory in _ancestors(Path(_normalise(path))):
        if not directory.is_dir():
            continue
        if any((directory / marker).exists() for marker in _DROPBOX_MARKERS):
            return "Dropbox"
        if (directory / _ONEDRIVE_MARKER).exists() and _is_onedrive_root(directory):
            return "OneDrive"
    return None


def detect_synced_client(path: os.PathLike[str] | str) -> str | None:
    """Name the sync client that manages *path*, or ``None`` when there is none.

    Cheap and local: environment variables first, then path segments, then the
    marker files an existing ancestor holds. Never raises for an ordinary path.
    """
    try:
        for root in _onedrive_roots():
            if _is_within(root, path):
                return "OneDrive"
        client = _segment_client(path)
        if client is not None:
            return client
        return _marker_client(path)
    except (OSError, ValueError, TypeError):
        return None


def is_synced_folder(path: os.PathLike[str] | str) -> bool:
    """Whether *path* sits inside a folder a cloud client synchronises."""
    return detect_synced_client(path) is not None
