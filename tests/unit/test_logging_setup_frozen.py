"""Where the app's log records go when there is no console to write to.

A frozen windowed build has ``sys.stderr is None``: a stream handler would raise
on the first record, so the desktop build writes to a file in the data directory
instead. The 2026-11-03 logging incident (every ``logger.info`` silently
dropped) is the reason this destination is pinned by a test rather than trusted.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path

import pytest

from server import logging_setup


@contextlib.contextmanager
def _bare_root_logger():
    """Hand ``configure_logging`` a root logger with no handlers.

    pytest's logging plugin installs its own capture handler on the root logger
    for every test phase, which is precisely the condition that turns
    ``configure_logging`` into a no-op. Clearing it inside the test body is the
    only moment at which the precondition can be established.
    """
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers = []
    try:
        yield root
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved


@pytest.fixture
def frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("DATARA_DB_PATH", str(tmp_path / "datara.db"))
    return tmp_path


class TestFrozenDestination:
    def test_records_reach_a_file_in_the_data_dir(self, frozen):
        with _bare_root_logger():
            logging_setup.configure_logging()
            logging.getLogger("server.services.mailer").info(
                "mail (console backend): link %s", "http://localhost/verify?token=abc"
            )
            for handler in logging.getLogger().handlers:
                handler.flush()

        log_file = frozen / logging_setup.LOG_FILENAME
        assert log_file.exists()
        assert "token=abc" in log_file.read_text(encoding="utf-8")

    def test_the_handler_points_at_the_data_dir_file(self, frozen):
        with _bare_root_logger() as root:
            logging_setup.configure_logging()

            assert len(root.handlers) == 1
            handler = root.handlers[0]
            assert isinstance(handler, logging.FileHandler)
            assert Path(handler.baseFilename) == frozen / logging_setup.LOG_FILENAME

    def test_the_log_file_follows_the_database_location(self, monkeypatch, tmp_path):
        # The log has to live with the data it describes, not in the cwd: a
        # windowed app has no meaningful working directory.
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        elsewhere = tmp_path / "custom-data"
        monkeypatch.setenv("DATARA_DB_PATH", str(elsewhere / "datara.db"))

        with _bare_root_logger() as root:
            logging_setup.configure_logging()

            assert Path(root.handlers[0].baseFilename) == elsewhere / logging_setup.LOG_FILENAME


class TestSourceDestinationIsUnchanged:
    def test_source_runs_keep_the_stream_and_create_no_file(self, monkeypatch, tmp_path):
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.setenv("DATARA_DB_PATH", str(tmp_path / "datara.db"))

        with _bare_root_logger() as root:
            logging_setup.configure_logging()

            handler = root.handlers[0]
            assert not isinstance(handler, logging.FileHandler)
        assert not (tmp_path / logging_setup.LOG_FILENAME).exists()

    def test_an_interpreter_without_stderr_still_gets_a_file(self, monkeypatch, tmp_path):
        # pythonw.exe on Windows has no console but is not a frozen build.
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.setattr(sys, "stderr", None, raising=False)
        monkeypatch.setenv("DATARA_DB_PATH", str(tmp_path / "datara.db"))

        with _bare_root_logger() as root:
            logging_setup.configure_logging()

            assert isinstance(root.handlers[0], logging.FileHandler)

    def test_a_host_owned_root_logger_is_still_left_alone(self, frozen):
        with _bare_root_logger() as root:
            sentinel = logging.NullHandler()
            root.addHandler(sentinel)

            logging_setup.configure_logging()

            assert root.handlers == [sentinel]
        assert not (frozen / logging_setup.LOG_FILENAME).exists()
