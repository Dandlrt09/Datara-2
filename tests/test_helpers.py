"""Shared test utilities for database bootstrap and migrations.

This module provides helpers to apply the full migration set in test fixtures.
"""

from pathlib import Path
import asyncio
import re

from keyring.backend import KeyringBackend

from server.services.auth_service import normalize_email
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "server" / "migrations"


class InMemoryKeyring(KeyringBackend):
    """A keyring backend that lives in the process (F9/S11).

    The store now asks the OS keyring for its at-rest key on every file-backed
    boot, so no test may ever reach the real one: a suite run would otherwise
    read and write the developer's own secret store. ``tests/conftest.py``
    installs this backend automatically for every test.
    """

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


async def apply_all_migrations(store: SqliteStore) -> None:
    """Apply all SQL migration files in sorted order to the given store.
    
    Args:
        store: An already-connected SqliteStore instance.
    """
    # Find all .sql files in migrations directory
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        raise RuntimeError(f"No migration files found in {MIGRATIONS_DIR}")
    
    # Apply each migration file in order
    for sql_file in sql_files:
        sql = sql_file.read_text(encoding="utf-8")
        await store.conn.executescript(sql)
    
    # Commit the changes
    await store.conn.commit()


async def create_test_store() -> SqliteStore:
    """Create and initialize a test store with all migrations applied.

    Returns:
        SqliteStore: A connected store ready for testing.
    """
    s = SqliteStore(db_path=":memory:")
    await s.connect()
    await apply_all_migrations(s)
    return s


# ── Outbound-mail seam (T3/T7) ────────────────────────────────────────────────
#
# Every auth route resolves its mailer through ``resolve_mailer()`` at call time,
# so patching that one function swaps the real backend for a recorder in every
# route without touching a single app fixture. ``install_recording_mailer`` is
# wired autouse from ``tests/integration/conftest.py`` so the whole integration
# suite stays off the network and every test can read the token that
# registration mailed.

_TOKEN_RE = re.compile(r"token=([^&\s]+)")


class RecordingMailer:
    """In-memory mailer: records every message instead of sending it (S5)."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.messages.append({"to": to, "subject": subject, "body": body})

    def last_token(self, email: str) -> str | None:
        """Extract ``token=`` from the last body sent to *email*.

        Compares normalized addresses because the account stores the email
        lowercased while a test may register it in any case.
        """
        normalized = normalize_email(email)
        for message in reversed(self.messages):
            if normalize_email(message["to"]) == normalized:
                match = _TOKEN_RE.search(message["body"])
                if match:
                    return match.group(1)
        return None

    def clear(self) -> None:
        self.messages.clear()


_recorder = RecordingMailer()


def get_recorder() -> RecordingMailer:
    """The recorder installed by the autouse mailer fixture."""
    return _recorder


def install_recording_mailer(monkeypatch) -> RecordingMailer:
    """Swap the mailer factory for the shared recorder (S3/S5/D4).

    The route dependency ``get_mailer`` calls ``resolve_mailer()`` at call
    time, so patching the module attribute is enough to keep every request in
    the run off the network. The recorder is cleared first so a test never sees
    a sibling test's mail.
    """
    _recorder.clear()
    monkeypatch.setattr("server.services.mailer.resolve_mailer", lambda: _recorder)
    return _recorder


def _register_body(
    email: str,
    password: str,
    name: str | None,
    terms_version: str,
) -> dict[str, object]:
    body: dict[str, object] = {
        "email": email,
        "password": password,
        "terms_version": terms_version,
    }
    if name is not None:
        body["name"] = name
    return body


def verify_email(
    client,
    email: str,
    password: str = "password123",
    *,
    name: str | None = None,
    terms_version: str = TERMS_VERSION,
):
    """Register then verify the address, returning the REGISTER response.

    Use this in tests that assert on the register payload (or need the user id
    before logging in); ``register_verified`` covers the tests that only need a
    session cookie.
    """
    registered = client.post(
        "/api/auth/register",
        json=_register_body(email, password, name, terms_version),
    )
    assert registered.status_code == 200, registered.text

    token = get_recorder().last_token(registered.json()["email"])
    assert token is not None, f"no verification mail for {email}"

    verified = client.post("/api/auth/verify-email", json={"token": token})
    assert verified.status_code == 204, verified.text
    return registered


def register_verified(
    client,
    email: str,
    password: str = "password123",
    *,
    name: str | None = None,
    terms_version: str = TERMS_VERSION,
    user_agent: str | None = None,
):
    """Walk the hard-gate contract and return the successful login response.

    Register creates the account but opens no session (D4); the token printed
    into the recorded mail proves the address through ``/verify-email``; only
    then does login succeed. This is the shared replacement for every old
    ``register and use the cookie`` step across the integration suite.
    """
    verify_email(
        client, email, password, name=name, terms_version=terms_version
    )

    headers = {"User-Agent": user_agent} if user_agent is not None else {}
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )
    assert login.status_code == 200, login.text
    return login


def upload_csv(
    client,
    cookie: str,
    session_id: str,
    *,
    filename: str = "dataset.csv",
) -> None:
    """Attach a small CSV to a chat session via the files endpoint.

    The chat router refuses to run the sandbox when a session has no
    attached files (no-dataset guard), so integration tests that exercise
    the sandbox path must attach a dataset first. The CSV is fixed (3 rows)
    so profile-related assertions stay stable across callers.
    """
    content = b"name,age,score\nAlice,30,95.5\nBob,25,87.3\nCharlie,35,92.1\n"
    resp = client.post(
        f"/api/sessions/{session_id}/files",
        files={"file": (filename, content, "text/csv")},
        headers={"Cookie": cookie},
    )
    assert resp.status_code in (200, 201), resp.text