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
"""

from __future__ import annotations

import logging

#: Readable and greppable: the console mailer's body arrives as extra lines.
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"
LOG_LEVEL = logging.INFO


def configure_logging() -> None:
    """Make application log records visible, once per process.

    No-op when the root logger already has a handler, so a host that configured
    logging itself keeps whatever level and destinations it chose.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(LOG_LEVEL)
