"""Outbound email: one contract, two backends (S2, S5, D9).

Datara had no way to reach a person's inbox until now, and both new flows --
verifying an address and recovering a password -- depend on it. The design keeps
the *delivery* behind a single contract so the rest of the code never learns
which server sent the mail:

- ``SmtpMailer`` speaks the classic mail protocol with the standard library's
  ``smtplib`` (no new dependency). It is used when the environment names a
  server and a sender.
- ``ConsoleMailer`` writes the message to the log and sends nothing. It is the
  default, which is what keeps a test run off the network (S5) and lets a
  developer read the link without configuring a mailbox.

The choice is resolved at call time, not import time, so setting an environment
variable is enough -- the same convention the rest of the server follows
(``server/services/crypto.py``, ``server/limits.py``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger(__name__)

DEFAULT_SMTP_PORT = 587
DEFAULT_APP_URL = "http://localhost:8000"

# Frontend routes the mailed links point at (D9). They are deliberately NOT API
# endpoints: a link prefetcher that fetches a mail URL would otherwise consume a
# one-shot token before the person ever clicked. The screen behind the route is
# what issues the actual POST.
VERIFICATION_PATH = "/verify-email"
RESET_PATH = "/reset-password"


class Mailer(Protocol):
    """The single contract every backend honours."""

    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleMailer:
    """Development and test backend: log the message, send nothing (S5).

    The body carries the link, so the server log is where a developer reads it.
    ``sender`` is only for the log line -- there is no envelope to set.
    """

    def __init__(self, sender: str | None = None) -> None:
        self._sender = sender

    async def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info(
            "mail (console backend) from=%s to=%s subject=%s\n%s",
            self._sender or "(unset)",
            to,
            subject,
            body,
        )


@dataclass(frozen=True)
class SmtpConfig:
    """Everything ``SmtpMailer`` needs, already resolved from the environment."""

    host: str
    port: int
    sender: str
    user: str | None = None
    password: str | None = None
    starttls: bool = True


class SmtpMailer:
    """Deliver over SMTP via the standard library.

    ``smtplib`` is blocking, so the handshake and delivery run in a worker
    thread: a slow mail server must never stall the event loop that is serving
    every other request.
    """

    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    async def send(self, *, to: str, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_blocking, to, subject, body)

    def _send_blocking(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._config.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self._config.host, self._config.port, timeout=30) as smtp:
            if self._config.starttls:
                smtp.starttls()
            if self._config.user and self._config.password:
                smtp.login(self._config.user, self._config.password)
            smtp.send_message(message)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Ignoring non-numeric %s=%r", name, raw)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_smtp_config() -> SmtpConfig | None:
    """Resolve the SMTP backend's config, or ``None`` when it is not configured.

    A host and a sender are the minimum: without both, there is nothing to
    connect to or no address to send from, and the console backend takes over
    (S2, S5).
    """
    host = os.environ.get("DATARA_SMTP_HOST")
    sender = os.environ.get("DATARA_MAIL_FROM")
    if not host or not sender:
        return None

    port = _env_int("DATARA_SMTP_PORT", DEFAULT_SMTP_PORT)
    return SmtpConfig(
        host=host,
        port=port,
        sender=sender,
        user=os.environ.get("DATARA_SMTP_USER") or None,
        password=os.environ.get("DATARA_SMTP_PASSWORD") or None,
        # STARTTLS is on for the submission port by default, and can be forced
        # either way explicitly: a plain local relay (e.g. MailHog on 1025) has
        # no TLS at all.
        starttls=_env_bool("DATARA_SMTP_STARTTLS", port == DEFAULT_SMTP_PORT),
    )


def resolve_mailer() -> Mailer:
    """Pick the backend from the environment (S2, S5)."""
    config = resolve_smtp_config()
    if config is None:
        return ConsoleMailer(sender=os.environ.get("DATARA_MAIL_FROM"))
    return SmtpMailer(config)


def get_mailer() -> Mailer:
    """FastAPI dependency.

    Routes depend on this rather than on a concrete backend, which is what lets
    a test override it with a recorder (``app.dependency_overrides``).
    """
    return resolve_mailer()


def resolve_app_url() -> str:
    """The public base URL mailed links are built from, without a trailing slash."""
    return (os.environ.get("DATARA_APP_URL") or DEFAULT_APP_URL).rstrip("/")


def verification_link(app_url: str, raw_token: str) -> str:
    """The link that proves the person controls the address."""
    return f"{app_url.rstrip('/')}{VERIFICATION_PATH}?token={raw_token}"


def reset_link(app_url: str, raw_token: str) -> str:
    """The link that lets the person set a new password."""
    return f"{app_url.rstrip('/')}{RESET_PATH}?token={raw_token}"


def render_verification_email(link: str, *, ttl_hours: int = 24) -> tuple[str, str]:
    """Return ``(subject, body)`` for the verification mail, in plain text."""
    subject = "Verifica tu correo en Datara"
    body = (
        "Bienvenido a Datara.\n\n"
        "Confirma que este correo es tuyo abriendo este enlace:\n"
        f"{link}\n\n"
        f"El enlace vence en {ttl_hours} horas. "
        "Si no creaste una cuenta, ignora este mensaje.\n"
    )
    return subject, body


def render_reset_email(link: str, *, ttl_hours: int = 1) -> tuple[str, str]:
    """Return ``(subject, body)`` for the password-recovery mail, in plain text."""
    subject = "Restablece tu contraseña en Datara"
    body = (
        "Pediste restablecer tu contraseña.\n\n"
        "Elige una nueva abriendo este enlace:\n"
        f"{link}\n\n"
        f"El enlace vence en {ttl_hours} hora(s). "
        "Si no lo pediste, ignora este mensaje: tu contraseña sigue igual.\n"
    )
    return subject, body
