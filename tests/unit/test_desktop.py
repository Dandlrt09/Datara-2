"""The desktop entry point: two hats, a free port, and a window that owns the process.

``run_desktop`` is tested against a real uvicorn server on a real loopback
socket, with the window replaced by a callable. That is the seam that matters:
the promise being pinned is "when the window closes, the server is gone", and
the only honest way to check it is to watch the port afterwards.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from server import desktop
from server import sandbox_runner
from server.services.mailer import resolve_app_url

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """Keep the server away from the developer's real database and uploads."""

    def _apply():
        monkeypatch.setenv("DATARA_DB_PATH", str(tmp_path / "datara.db"))
        monkeypatch.setenv("DATARA_UPLOADS_DIR", str(tmp_path / "uploads"))
        return tmp_path

    return _apply


def _port_is_free(port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((desktop.HOST, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


class TestSocketSelection:
    def test_binds_a_free_port_on_the_loopback_interface(self):
        sock = desktop.bind_loopback_socket()
        try:
            host, port = sock.getsockname()
            assert host == "127.0.0.1"
            assert port != 0
        finally:
            sock.close()

    def test_url_uses_the_port_that_was_actually_bound(self):
        sock = desktop.bind_loopback_socket()
        try:
            assert desktop.local_url(sock).endswith(f":{sock.getsockname()[1]}")
            assert desktop.local_url(sock).startswith("http://127.0.0.1:")
        finally:
            sock.close()

    def test_two_sockets_do_not_collide(self):
        # The whole reason for binding instead of guessing a port number.
        first = desktop.bind_loopback_socket()
        second = desktop.bind_loopback_socket()
        try:
            assert first.getsockname()[1] != second.getsockname()[1]
        finally:
            first.close()
            second.close()


class TestWindowOwnsTheProcess:
    def test_serves_the_app_and_stops_when_the_window_closes(self, isolated_env):
        isolated_env()
        seen: dict[str, object] = {}

        def fake_window(url: str) -> None:
            # The window is a browser: it has to actually reach the server.
            with urllib.request.urlopen(url + "/", timeout=10) as response:
                seen["status"] = response.status

        assert desktop.run_desktop(open_window=fake_window) is True
        assert seen["status"] == 200

    def test_the_port_is_released_once_the_window_closes(self, isolated_env):
        isolated_env()
        ports: list[int] = []

        def fake_window(url: str) -> None:
            ports.append(int(url.rsplit(":", 1)[1]))

        desktop.run_desktop(open_window=fake_window)
        assert _port_is_free(ports[0])

    def test_a_window_that_dies_still_takes_the_server_with_it(self, isolated_env):
        isolated_env()
        ports: list[int] = []

        def exploding_window(url: str) -> None:
            ports.append(int(url.rsplit(":", 1)[1]))
            raise RuntimeError("window crashed")

        with pytest.raises(RuntimeError, match="window crashed"):
            desktop.run_desktop(open_window=exploding_window)

        # The exception leaves run_desktop, but the server must not survive it:
        # otherwise the user's next launch collides with a zombie on the port.
        assert _port_is_free(ports[0])


class TestMailedLinksUseTheRealPort:
    """A desktop build picks its port at runtime, so the links it mails must follow it.

    The mailer builds every verification and reset link from DATARA_APP_URL. When
    that is left at its placeholder the packaged app mails links to
    ``http://localhost:8000`` while it is actually serving somewhere else, and a
    new user can never prove their address. Found in the T7 acceptance run on
    Windows (06/11/2026): the link only worked after editing the port by hand.
    """

    def test_the_mailed_link_uses_the_port_the_app_serves_on(self, isolated_env, monkeypatch):
        isolated_env()
        monkeypatch.delenv("DATARA_APP_URL", raising=False)
        seen: dict[str, str] = {}

        def fake_window(url: str) -> None:
            seen["served"] = url
            # Exactly what the mailer would put in the verification mail.
            seen["mailed"] = resolve_app_url()

        assert desktop.run_desktop(open_window=fake_window) is True
        assert seen["mailed"] == seen["served"]

    def test_a_configured_app_url_is_not_overwritten(self, isolated_env, monkeypatch):
        # A hosted deployment behind a proxy knows its public URL; the loopback
        # bind must not talk it out of that.
        isolated_env()
        monkeypatch.setenv("DATARA_APP_URL", "https://datara.app/")
        seen: dict[str, str] = {}

        def fake_window(url: str) -> None:
            seen["mailed"] = resolve_app_url()

        desktop.run_desktop(open_window=fake_window)
        assert seen["mailed"] == "https://datara.app"


class TestArgumentDispatch:
    def test_the_runner_flag_runs_the_sandbox_child(self, monkeypatch):
        called: list[bool] = []
        monkeypatch.setattr(sandbox_runner, "main", lambda: called.append(True))

        assert desktop.main([desktop.SANDBOX_RUNNER_FLAG]) == 0
        assert called == [True]

    def test_no_flag_runs_the_application(self, monkeypatch):
        called: list[bool] = []
        monkeypatch.setattr(desktop, "run_desktop", lambda **_: called.append(True) or True)

        assert desktop.main([]) == 0
        assert called == [True]

    def test_the_runner_flag_is_recognised_next_to_other_arguments(self, monkeypatch):
        called: list[bool] = []
        monkeypatch.setattr(sandbox_runner, "main", lambda: called.append(True))

        assert desktop.main(["--verbose", desktop.SANDBOX_RUNNER_FLAG]) == 0
        assert called == [True]

    def test_importing_the_entry_point_does_not_pull_the_web_stack(self):
        # In a frozen build the sandbox child *is* this module, and it is spawned
        # for every code execution. Importing FastAPI, uvicorn or a GUI toolkit
        # here would be paid on the user's own machine, on every question.
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import server.desktop, sys; "
                "print('fastapi' in sys.modules, 'uvicorn' in sys.modules, "
                "'webview' in sys.modules)",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert probe.returncode == 0, probe.stderr
        assert probe.stdout.strip() == "False False False"


class TestServerOnlyMode:
    def test_serves_without_touching_the_window_toolkit(self, monkeypatch, isolated_env):
        # The mode exists so a frozen build can be exercised where there is no
        # display: it must therefore never reach for pywebview.
        isolated_env()

        def forbidden(url: str) -> None:
            raise AssertionError("the window toolkit must not be used here")

        monkeypatch.setattr(desktop, "_open_webview_window", forbidden)
        monkeypatch.setattr(desktop, "_serve_until_interrupted", lambda url: None)

        assert desktop.run_server_only() is True

    def test_the_flag_replaces_the_window_instead_of_joining_it(self, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(desktop, "run_server_only", lambda: True)
        monkeypatch.setattr(desktop, "run_desktop", lambda **_: calls.append("window") or True)

        assert desktop.main([desktop.SERVE_ONLY_FLAG]) == 0
        assert calls == []
