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


def resolve_db_path(explicit: str | None = None) -> str:
    """Resolve the database path and tilde-expand it.

    Precedence: *explicit* argument, then the ``DATARA_DB_PATH`` env var, then the
    pre-F3 location when it already holds a database
    (:func:`legacy_db_path_if_present`), then the operating system's data
    directory (:func:`os_default_data_dir`). An empty *explicit* value is treated
    as not provided. The returned string never contains a literal ``~``
    component.
    """
    if explicit:
        raw = explicit
    else:
        env = os.environ.get("DATARA_DB_PATH")
        if env:
            raw = env
        else:
            legacy = legacy_db_path_if_present()
            if legacy is not None:
                return str(legacy)
            return str(os_default_data_dir() / _DB_FILENAME)
    return str(Path(raw).expanduser())
