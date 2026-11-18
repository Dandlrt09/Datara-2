"""Single source of truth for resolving the SQLite database path.

Every consumer (the store, the API lifespan, the migration runner) must
resolve the DB path through :func:`resolve_db_path`. The encryption key file
is written next to the database, so if one consumer expanded ``~`` while
another did not, the DB and its key would silently land in different
directories.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The location every install used before F3. It is never migrated away from:
# an install that already keeps its database there goes on using it.
LEGACY_DB_PATH = "~/.datara/datara.db"

# Name of the per-user directory under each operating system's data convention.
APP_DIR_NAME = "Datara"

_DB_FILENAME = "datara.db"

# Name of the pointer file, written inside the OS default data directory (F3b
# D6). Plain text, one line: the absolute path of the data folder the analyst
# chose on first run. No JSON, no keys, no comments — it is read with
# ``read_text().strip()`` and written with ``write_text()``.
LOCATION_FILE_NAME = "data-location.txt"


def os_default_data_dir() -> Path:
    """The per-user data directory, following the operating system's convention.

    Windows keeps per-user application data in ``%LOCALAPPDATA%``; macOS in
    ``~/Library/Application Support``; Linux in ``$XDG_DATA_HOME``, which
    defaults to ``~/.local/share``.
    """
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base.expanduser() / APP_DIR_NAME


def legacy_db_path_if_present() -> Path | None:
    """The pre-F3 database, when this machine already has one.

    F3 moved the default location, but nothing is migrated: an existing database
    is data the user cannot rebuild, so it keeps being read where it already is.
    A leftover ``~/.datara`` directory with no database in it is not an install.
    """
    legacy = Path(LEGACY_DB_PATH).expanduser()
    return legacy if legacy.exists() else None


def location_file() -> Path:
    """The pointer file that records the chosen data folder (F3b / D6)."""
    return os_default_data_dir() / LOCATION_FILE_NAME


def read_data_location() -> Path | None:
    """The absolute data folder chosen on first run, or ``None``.

    ``None`` means "no decision yet" and is the only failure mode: a missing,
    empty, unreadable or nonsensical pointer falls through to the next step of
    :func:`resolve_db_path` and never raises. Startup runs through this on every
    boot, so a damaged pointer must degrade to the default instead of breaking
    the app. A relative line is treated as damaged too: the server may boot from
    any working directory, so "relative to what" has no stable answer.
    """
    try:
        raw = location_file().read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not raw:
        return None
    location = Path(raw).expanduser()
    if not location.is_absolute():
        return None
    return location


def write_data_location(path: str | os.PathLike[str]) -> Path:
    """Record *path* as the data folder and return the pointer file.

    The pointer's parent directory is created when missing: on a fresh machine
    nothing exists yet, and this file is the first thing the app ever writes.
    Validation (absolute, writable) belongs to the caller that takes the choice
    from a human; this function only persists what it is given.
    """
    location = Path(os.fspath(path)).expanduser()
    pointer = location_file()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(location), encoding="utf-8")
    return pointer


def resolve_db_path(explicit: str | None = None) -> str:
    """Resolve the database path and tilde-expand it.

    Precedence: *explicit* argument, then the ``DATARA_DB_PATH`` env var, then
    the pointer the analyst wrote on first run (:func:`read_data_location`),
    then the pre-F3 location when it already holds a database
    (:func:`legacy_db_path_if_present`), then the operating system's data
    directory (:func:`os_default_data_dir`). An empty *explicit* value is treated
    as not provided. The returned string never contains a literal ``~``
    component.

    The pointer deliberately ranks BELOW the env var: ``DATARA_DB_PATH`` is what
    isolates each test (and each embedded run), so a pointer left on a machine by
    the folder picker must never be able to hijack it.
    """
    if explicit:
        raw = explicit
    else:
        env = os.environ.get("DATARA_DB_PATH")
        if env:
            raw = env
        else:
            chosen = read_data_location()
            if chosen is not None:
                return str(chosen / _DB_FILENAME)
            legacy = legacy_db_path_if_present()
            if legacy is not None:
                return str(legacy)
            return str(os_default_data_dir() / _DB_FILENAME)
    return str(Path(raw).expanduser())
