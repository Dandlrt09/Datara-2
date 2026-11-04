"""The one place where Datara decides how it logs.

Every module logs through ``logging.getLogger(__name__)`` and none of those
loggers carries a handler. Under uvicorn only uvicorn's own loggers are
configured, so application records propagate to the root logger, which has no
handler and defaults to WARNING: every ``logger.info`` in Datara was dropped in
silence.

Live validation (2026-11-03) surfaced it. Registration and the resend both
reached the server and ``ConsoleMailer`` logged the verification link at INFO,
but the link never appeared anywhere -- and the journal stores only the token
hash, so it was unrecoverable. The console backend exists precisely to hand the
link to a developer who has no SMTP configured; a mute console backend is worse
than no fallback at all.

The guard is deliberate: when a host already installed handlers (pytest, an
embedder), the host owns the log stream and this becomes a no-op.

The desktop build adds a second destination. A frozen windowed executable has no
console at all -- PyInstaller leaves ``sys.stderr`` as ``None`` -- so a stream
handler would raise on the first record and the app's own logs would be lost
again, in the one build where nobody can attach a debugger. Frozen, the log goes
to ``<data_dir>/datara.log`` instead.
"""

from __future__ import annotations

import logging
import sys

from server.resources import data_dir, is_frozen

#: Readable and greppable: the console mailer's body arrives as extra lines.
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"
LOG_LEVEL = logging.INFO

#: Name of the log file the frozen desktop build writes, inside the data dir
#: (next to the database, so it follows ``DATARA_DB_PATH``).
LOG_FILENAME = "datara.log"


def _build_handler() -> logging.Handler:
    """Pick where records go, given whether a console exists at all.

    Frozen, or any interpreter without a usable stderr, writes to the data
    directory: there is no console to write to, and a file is the only way the
    user -- or whoever supports them -- can see why something failed.
    """
    if is_frozen() or sys.stderr is None:
        log_path = data_dir() / LOG_FILENAME
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return logging.FileHandler(log_path, encoding="utf-8")
    return logging.StreamHandler()


def configure_logging() -> None:
    """Make application log records visible, once per process.

    No-op when the root logger already has a handler, so a host that configured
    logging itself keeps whatever level and destinations it chose.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    handler = _build_handler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(LOG_LEVEL)
