"""The app must make its own log records visible (regression: the console mailer was mute).

Discovered in live validation (2026-11-03). Registration and the resend both
reached the server, and ``ConsoleMailer`` logged the verification link at INFO,
but nothing printed it anywhere: no module configured logging, so application
records fell through to the root logger, which has no handler and defaults to
WARNING. Every ``logger.info`` in Datara was dropped in silence, and the raw
token cannot be recovered from the journal (only its hash is stored).

``configure_logging`` is the single place that decides. The guard is deliberate:
a host that already installed handlers (pytest, an embedder) owns the log
stream, and this must not fight it.
"""

from __future__ import annotations

import logging

from server.logging_setup import configure_logging


def _clear_root(level: int = logging.WARNING) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(level)


def test_info_records_become_visible(capsys):
    """The regression: a mail the console backend logged must reach the stream."""
    _clear_root()
    try:
        configure_logging()
        logging.getLogger("server.services.mailer").info(
            "mail (console backend) to=%s\n%s",
            "ana@example.com",
            "http://localhost:8000/verify-email?token=abc",
        )
        captured = capsys.readouterr()
        assert "http://localhost:8000/verify-email?token=abc" in captured.err
    finally:
        _clear_root()


def test_installs_exactly_one_handler_when_called_twice(capsys):
    _clear_root()
    try:
        configure_logging()
        configure_logging()
        assert len(logging.getLogger().handlers) == 1
    finally:
        _clear_root()


def test_leaves_a_hosts_handlers_and_level_alone(capsys):
    """pytest installs its own root handler; configure_logging must not touch it."""
    _clear_root()
    sentinel = logging.NullHandler()
    root = logging.getLogger()
    root.addHandler(sentinel)
    try:
        configure_logging()
        assert root.handlers == [sentinel]
        assert root.level == logging.WARNING
    finally:
        _clear_root()
