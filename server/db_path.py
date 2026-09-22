"""Single source of truth for resolving the SQLite database path.

Every consumer (the store, the API lifespan, the migration runner) must
resolve the DB path through :func:`resolve_db_path`. The encryption key file
is written next to the database, so if one consumer expanded ``~`` while
another did not, the DB and its key would silently land in different
directories.
"""

from __future__ import annotations

import os
from pathlib import Path

# Default location when neither an explicit path nor DATARA_DB_PATH is given.
DEFAULT_DB_PATH = "~/.datara/datara.db"


def resolve_db_path(explicit: str | None = None) -> str:
    """Resolve the database path and tilde-expand it.

    Precedence: *explicit* argument, then the ``DATARA_DB_PATH`` env var,
    then :data:`DEFAULT_DB_PATH`. An empty *explicit* value is treated as not
    provided. The returned string never contains a literal ``~`` component.
    """
    if explicit:
        raw = explicit
    else:
        raw = os.environ.get("DATARA_DB_PATH") or DEFAULT_DB_PATH
    return str(Path(raw).expanduser())