"""Where the application reads its files from, and where it may write.

There are two worlds, and the whole point of this module is that they agree.

**From the repository** (development, the test suite) the app's read-only files
live in the checkout: ``web/dist`` for the built frontend, ``server/migrations``
for the schema, ``server/sandbox_runner.py`` for the sandbox child. Uploads land
in ``<repo>/uploads``, which is where every existing development install keeps
them.

**From a frozen binary** (the desktop app) none of those paths exist. PyInstaller
ships the declared data files inside the bundle and unpacks them next to the
executable at runtime, in the directory ``sys._MEIPASS`` points to. That same
directory is usually read-only (an app installed under ``Program Files`` cannot
write beside itself), so uploads move to the per-user data directory.

Every path the app resolves must come from here, and ``sys.frozen`` is asked in
exactly one place. When the frontend, the migrations, the runner and the uploads
each rolled their own ``Path(__file__)`` there were four chances to forget one;
the frozen app then boots with a blank window or an empty schema and looks like a
broken install rather than a packaging mistake.
"""

from __future__ import annotations

import sys
from pathlib import Path

from server.db_path import resolve_db_path

# This module lives in ``server/``, so the repository root is one level up.
# Frozen, it is only used as a fallback that should never be reached.
_SOURCE_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle rather than the source tree."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Directory holding the app's read-only files, bundled or not.

    Frozen, that is the directory PyInstaller unpacked (``sys._MEIPASS``). The
    fallback to the executable's own directory covers a frozen build that does
    not expose ``_MEIPASS``: both ``onedir`` and ``onefile`` do, so it is a guard
    rather than a path we expect to walk.
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return _SOURCE_ROOT


def resource_path(*parts: str) -> Path:
    """Absolute path to a read-only file shipped with the application.

    The same call works from the repository and from a frozen bundle, which is
    the reason this helper exists instead of per-module path arithmetic.
    """
    return bundle_root().joinpath(*parts)


def data_dir() -> Path:
    """The per-user directory that holds the database, its key and the uploads.

    Taken from the resolved database path so the three can never drift apart:
    ``~/.datara`` by default, and whatever ``DATARA_DB_PATH`` points at when it
    is set (which is how tests isolate themselves).
    """
    return Path(resolve_db_path()).parent


def default_uploads_dir() -> Path:
    """Where uploads go when ``DATARA_UPLOADS_DIR`` is not set.

    From source this is the historical ``<repo>/uploads``: relocating it would
    orphan the files of every existing development install, and a development
    install can write to its own checkout.

    Frozen, it is ``<data_dir>/uploads``: the executable's directory belongs to
    the installer or to the operating system, so writing the user's data there
    either fails or lands somewhere invisible and gets wiped by an update.
    """
    if is_frozen():
        return data_dir() / "uploads"
    return _SOURCE_ROOT / "uploads"
