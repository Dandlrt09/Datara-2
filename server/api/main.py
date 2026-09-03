"""FastAPI application entrypoint for Datara server.

Sets up the app with lifespan management (migrations, session cleanup,
background tasks), CORS, static file serving, and all API routers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from server.api import store as api_store
from server.api.routers import auth, chat, files, sessions, settings, archive
from server.migrate import apply_migrations
from server.services.sandbox_local import sweep_orphan_sandbox_dirs
from server.services.session_cleanup import sweep_expired, start_background_sweep
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

_cleanup_task: asyncio.Task | None = None
_sandbox_sweep_task: asyncio.Task | None = None


def _start_background_orphan_sweep() -> asyncio.Task:
    """Start a background task that sweeps orphan sandbox dirs every hour."""

    async def _loop():
        while True:
            await asyncio.sleep(3600)
            try:
                removed = sweep_orphan_sandbox_dirs()
                if removed:
                    logger.info("Background sandbox sweep removed %d dir(s)", removed)
            except Exception:
                logger.exception("Background sandbox orphan sweep failed")

    return asyncio.create_task(_loop(), name="sandbox-orphan-sweep")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run on startup and shutdown.

    Startup:
    1. Connect to SQLite and apply pending migrations
    2. Sweep expired auth sessions
    3. Sweep orphan sandbox temp dirs
    4. Start hourly background session sweep and sandbox orphan sweep

    Shutdown:
    1. Cancel background tasks
    2. Close database connection
    """
    global _cleanup_task, _sandbox_sweep_task

    # Step 1: database setup
    # Design: local DB lives at ~/.datara/datara.db (outside the repo),
    # configurable via DATARA_DB_PATH. The parent directory may not exist
    # on a fresh machine — create it before connecting.
    db_path = os.environ.get("DATARA_DB_PATH") or os.path.expanduser(
        "~/.datara/datara.db"
    )
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(db_path=db_path)
    await store.connect()
    api_store._store = store

    # Apply pending migrations (sync — uses sqlite3 directly)
    try:
        apply_migrations(db_path)
        logger.info("Migrations applied successfully")
    except Exception:
        logger.exception("Migration failed — continuing with existing schema")

    # Step 2: sweep expired sessions
    try:
        swept = await sweep_expired(store)
        if swept:
            logger.info("Swept %d expired session(s) on startup", swept)
    except Exception:
        logger.exception("Startup session sweep failed")

    # Step 3: sweep orphan sandbox temp dirs
    try:
        removed = sweep_orphan_sandbox_dirs()
        if removed:
            logger.info("Swept %d orphan sandbox dir(s) on startup", removed)
    except Exception:
        logger.exception("Startup sandbox orphan sweep failed")

    # Step 4: start background hourly tasks
    try:
        _cleanup_task = await start_background_sweep(store)
        logger.info("Background session sweep started (interval: 3600s)")
    except Exception:
        logger.exception("Failed to start background session sweep")

    try:
        _sandbox_sweep_task = _start_background_orphan_sweep()
        logger.info("Background sandbox orphan sweep started (interval: 3600s)")
    except Exception:
        logger.exception("Failed to start background sandbox orphan sweep")

    yield

    # Shutdown
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    if _sandbox_sweep_task is not None:
        _sandbox_sweep_task.cancel()
        try:
            await _sandbox_sweep_task
        except asyncio.CancelledError:
            pass
    await store.close()
    api_store._store = None


app = FastAPI(
    title="Datara",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow localhost origins for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(settings.router)
app.include_router(files.router)
app.include_router(chat.router)
app.include_router(archive.router)

# Mount static files (for production, serve built frontend here)
static_dir = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


class SPAStaticFiles(StaticFiles):
    """StaticFiles with an SPA fallback.

    Client-side routes (/login, /app/files, ...) don't exist on disk, so a
    full reload or deep link would 404. Any unknown NON-API path is answered
    with index.html so the SPA boots and the router takes over. Unknown API
    paths still return their normal 404.
    """

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            # StaticFiles RAISES HTTPException(404) when the file is missing.
            if exc.status_code == 404 and not path.startswith("api/"):
                return await super().get_response("index.html", scope)
            raise
        if response.status_code == 404 and not path.startswith("api/"):
            response = await super().get_response("index.html", scope)
        return response


if static_dir.exists():
    app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="static")
else:
    logger.info("Static directory not found at %s — frontend not mounted", static_dir)