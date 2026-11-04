# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: the Datara desktop build.

What "frozen" changes, and what this file has to answer for:

* **Read-only data must be declared.** ``web/dist`` (the built SPA) and
  ``server/migrations`` (the schema) used to be found by walking up from
  ``__file__``. Inside the bundle those paths do not exist, so both are listed in
  ``datas`` and ``server/resources.py`` finds them through ``sys._MEIPASS``. The
  destinations must match the arguments ``resource_path`` is called with, or the
  app boots to a blank window and an empty schema.

* **Dynamically imported modules are invisible to the analyzer.** uvicorn picks
  its loop, HTTP protocol and websocket implementation at runtime, and the
  sandbox worker plus the window toolkit are imported inside functions, so they
  are declared explicitly below. A missing entry shows up as a runtime
  ImportError in the frozen app only.

* **``server/sandbox_runner.py`` is NOT a data file.** When frozen it is not run
  as a script any more; the executable re-enters itself through
  ``--sandbox-runner`` (see ``server/desktop.py``), so the module is bundled as
  code like any other.

Build (onedir, the default chosen for first-arranque speed)::

    .venv/bin/pyinstaller datara.spec --noconfirm

Set ``DATARA_BUILD_CONSOLE=1`` to get a console build, which prints the logs to
the terminal instead of hiding them and is the fastest way to debug a frozen
build. ``--onefile`` can be produced by collapsing ``EXE``/``COLLECT`` below; it
is deliberately not the default because it unpacks the whole bundle on every
launch.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

REPO_ROOT = Path(SPECPATH).resolve()

# A bundle without these is not a smaller app, it is a broken one: the SPA
# 404s and the database is created empty forever. Fail the build instead.
_REQUIRED = {
    "frontend": REPO_ROOT / "web" / "dist",
    "migrations": REPO_ROOT / "server" / "migrations",
}
_missing = [name for name, path in _REQUIRED.items() if not path.is_dir()]
if _missing:
    raise SystemExit(
        "Refusing to build: missing " + ", ".join(_missing)
        + ". Run `cd web && npm run build` first."
    )

# On Windows the window *is* the product: a bundle without the toolkit would
# install cleanly and fail the moment the user opens it, which is the worst
# place to discover a missing dependency. Other platforms are allowed to build
# without it -- that is how the frozen bundle is exercised on a machine with no
# display, through `--serve-only`.
if sys.platform == "win32":
    try:
        import webview  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Refusing to build on Windows without pywebview: "
            "run `uv sync --all-extras` first."
        )

datas = [
    (str(REPO_ROOT / "web" / "dist"), "web/dist"),
    (str(REPO_ROOT / "server" / "migrations"), "server/migrations"),
]

hiddenimports = [
    # The second hat: the executable spawns itself with this flag to run code,
    # and the import happens inside a function.
    "server.sandbox_runner",
    # uvicorn resolves these by name at startup.
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # Imported inside a function so the sandbox child never loads the GUI stack.
    "webview",
    # Imported inside a function so the child never loads the database layer.
    "server.api.main",
    "server.desktop",
]

# The window toolkit is a package with platform-specific backends it locates by
# import at runtime; collecting the submodules is what pywebview's own packaging
# guidance calls for.
hiddenimports += collect_submodules("webview")

a = Analysis(
    [str(REPO_ROOT / "server" / "desktop.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Pinned deliberately: a frozen app has no place for a user site-packages
    # directory to sneak code into.
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="datara",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # The frozen-windowed case is the one that has no console at all; the app
    # writes to <data_dir>/datara.log instead (server/logging_setup.py).
    console=os.environ.get("DATARA_BUILD_CONSOLE") == "1",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="datara",
)
