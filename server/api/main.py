"""FastAPI application entrypoint for Datara server.

Sets up the app with lifespan management (migrations, session cleanup,
background tasks), CORS, static file serving, and all API routers.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.api import store as api_store
from server.api.routers import auth, sessions, settings
from server.migrate import apply_migrations
from server.services.session_cleanup import sweep_expired, start_background_sweep
from server.services.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

_cleanup_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run on startup and shutdown.

    Startup:
    1. Connect to SQLite and apply pending migrations
    2. Sweep expired auth sessions
    3. Start hourly background session sweep

    Shutdown:
    1. Cancel background sweep task
    2. Close database connection
    """
    global _cleanup_task

    # Step 1: database setup
    db_path = str(
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "datara.db"
    )
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

    # Step 3: start background hourly sweep
    try:
        _cleanup_task = await start_background_sweep(store)
        logger.info("Background session sweep started (interval: 3600s)")
    except Exception:
        logger.exception("Failed to start background sweep")

    yield

    # Shutdown
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
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

# Mount static files (for production, serve built frontend here)
static_dir = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
else:
    logger.info("Static directory not found at %s — frontend not mounted", static_dir)