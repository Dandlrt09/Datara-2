"""Desktop entry point: one binary that wears two hats.

**Hat one, no arguments: the application.** Start the API on a free loopback
port, show it in its own window, and stop the server when the window closes.

**Hat two, ``--sandbox-runner``: the sandbox child.** The parent spawns the
*executable itself* to run the code the model wrote. Running from source this is
not needed — the parent can spawn ``python -I -B server/sandbox_runner.py`` —
but inside a frozen bundle ``sys.executable`` *is* the application, so spawning
it without a flag would start a second copy of the server instead of the child.
See ``server/services/sandbox_local.py`` for the parent side.

The flag is checked before anything expensive is imported, so the child pays for
pandas and FastAPI only when it needs them (which is: pandas yes, FastAPI no).
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Passed to the frozen executable to make it behave as the sandbox child.
SANDBOX_RUNNER_FLAG = "--sandbox-runner"

# Serve without opening a window, until interrupted. This is the headless half of
# the same entry point: it makes a frozen build testable on a machine with no
# display (which is how the packaging is verified before it ever reaches
# Windows), and it is what a hosted deployment would run.
SERVE_ONLY_FLAG = "--serve-only"

# Loopback only. A desktop app that listened on 0.0.0.0 would publish the user's
# data and API to their whole network.
HOST = "127.0.0.1"

STARTUP_TIMEOUT_SECONDS = 15.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0
_POLL_SECONDS = 0.05


def bind_loopback_socket(host: str = HOST) -> socket.socket:
    """Return a socket bound to a free port on the loopback interface.

    The socket comes back bound but **not** listening: uvicorn adopts it through
    ``run(sockets=[...])`` and calls ``listen()`` itself. Asking the OS for port
    0, closing the socket and handing the *number* to a second binder would leave
    a window in which another process can take the port; holding the socket the
    whole time closes that window.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, 0))
    return sock


def local_url(sock: socket.socket) -> str:
    """The URL the window should open, taken from the socket that is already bound."""
    return f"http://{HOST}:{sock.getsockname()[1]}"


def _open_webview_window(url: str) -> None:
    """Show the app in its own window and block until the user closes it.

    ``webview`` is imported here rather than at module level so that the sandbox
    child never drags a GUI toolkit (or its system libraries) into a headless
    subprocess.
    """
    import webview

    webview.create_window("Datara", url, width=1280, height=860)
    webview.start()


def _wait_for_startup(server: object, timeout: float = STARTUP_TIMEOUT_SECONDS) -> bool:
    """Block until uvicorn reports itself started, or give up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if getattr(server, "started", False):
            return True
        if getattr(server, "should_exit", False):
            return False
        time.sleep(_POLL_SECONDS)
    return False


def _stop_server(server: object, thread: threading.Thread, timeout: float = SHUTDOWN_TIMEOUT_SECONDS) -> bool:
    """Ask uvicorn to stop and wait for it. Returns False if it refuses to die.

    A graceful uvicorn shutdown hangs on open keep-alive connections — the
    webview holds exactly those — which is why the caller still has a hard exit
    in reserve instead of trusting this to return.
    """
    server.should_exit = True
    thread.join(timeout=timeout)
    return not thread.is_alive()


def run_desktop(*, open_window: Callable[[str], None] | None = None) -> bool:
    """Serve the app on a free port, show the window, and stop when it closes.

    ``open_window`` is the seam the tests use: it receives the URL and must block
    until the user closes the window (or return immediately, to simulate that).

    Returns True when the server stopped cleanly. False means the process should
    not wait around for it.
    """
    import uvicorn

    from server.api.main import app
    from server.logging_setup import configure_logging

    # Before uvicorn, and before anything can log: a frozen windowed build has no
    # usable stderr, so the app's records have to reach a file or they vanish.
    # uvicorn is told not to install its own logging config so it cannot undo this
    # (the lifespan's configure_logging call then finds a configured root and
    # stays a no-op, which is what its guard is for).
    configure_logging()

    sock = bind_loopback_socket()
    url = local_url(sock)
    config = uvicorn.Config(app, log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        name="datara-server",
        daemon=True,
    )
    thread.start()

    if not _wait_for_startup(server):
        logger.error("Server did not start within %.0fs — closing", STARTUP_TIMEOUT_SECONDS)
        _stop_server(server, thread)
        return False

    logger.info("Datara is serving on %s", url)
    try:
        (open_window or _open_webview_window)(url)
    finally:
        # Runs even if the window blew up: the window is the app's whole life, so
        # whatever happens to it, the server must not outlive it.
        stopped = _stop_server(server, thread)
        if not stopped:
            logger.warning("Server did not stop within %.0fs", SHUTDOWN_TIMEOUT_SECONDS)
    return stopped


def _serve_until_interrupted(url: str) -> None:
    """Stand-in for the window in server-only mode: block until Ctrl+C.

    Kept as its own function so it can be substituted the same way the window is
    in tests.
    """
    logger.info("Serving on %s — server-only mode, stop with Ctrl+C", url)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down")


def run_server_only() -> bool:
    """Serve the application with no window, until interrupted."""
    return run_desktop(open_window=_serve_until_interrupted)


def main(argv: list[str] | None = None) -> int:
    """Dispatch on the command line and return a process exit code."""
    args = sys.argv[1:] if argv is None else list(argv)

    if SANDBOX_RUNNER_FLAG in args:
        from server.sandbox_runner import main as sandbox_main

        sandbox_main()
        return 0

    started = run_server_only() if SERVE_ONLY_FLAG in args else run_desktop()
    if not started:
        # uvicorn is stuck on connections the webview left open. The user closed
        # the window, so the process has to die now: leaving it alive in the
        # background is the exact failure that was already suffered here by hand.
        os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
