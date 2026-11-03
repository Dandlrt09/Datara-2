"""The outbound email service: one contract, two backends (S2, S5, D9).

What these tests pin:

- The dev/test default is the console backend, so a test run never opens a
  socket and still shows the link (S5).
- The SMTP backend is chosen only when the environment actually names a server
  and a sender, and it speaks to it through ``smtplib`` with STARTTLS and login.
- The link the mail carries points at the *frontend* route, never at the API
  (D9): a link prefetcher must not be able to consume a one-shot token.
"""

from __future__ import annotations

import smtplib

import pytest

from server.services.mailer import (
    ConsoleMailer,
    SmtpMailer,
    get_mailer,
    render_reset_email,
    render_verification_email,
    reset_link,
    resolve_app_url,
    resolve_mailer,
    verification_link,
)

_ENV_VARS = (
    "DATARA_SMTP_HOST",
    "DATARA_SMTP_PORT",
    "DATARA_SMTP_USER",
    "DATARA_SMTP_PASSWORD",
    "DATARA_SMTP_STARTTLS",
    "DATARA_MAIL_FROM",
    "DATARA_APP_URL",
)


@pytest.fixture(autouse=True)
def _clean_mail_env(monkeypatch):
    """Start every test from an unconfigured mailer (S5)."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


class _FakeSmtp:
    """Records what the SMTP backend did, without leaving the process."""

    instances: list["_FakeSmtp"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_calls: list[tuple[str, str]] = []
        self.sent_messages: list = []
        _FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.login_calls.append((user, password))

    def send_message(self, message):
        self.sent_messages.append(message)


@pytest.fixture
def fake_smtp(monkeypatch):
    _FakeSmtp.instances = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    return _FakeSmtp


class TestConsoleBackend:
    async def test_logs_the_link_and_sends_nothing(self, caplog):
        link = verification_link("http://localhost:8000", "tok-123")
        console = ConsoleMailer()

        with caplog.at_level("INFO", logger="server.services.mailer"):
            await console.send(
                to="ana@example.com",
                subject="Verifica tu correo",
                body=f"Abre este link: {link}",
            )

        assert "ana@example.com" in caplog.text
        assert link in caplog.text


class TestResolveMailer:
    def test_defaults_to_console_when_unconfigured(self):
        assert isinstance(resolve_mailer(), ConsoleMailer)

    def test_uses_smtp_when_host_and_sender_are_configured(self, monkeypatch):
        monkeypatch.setenv("DATARA_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("DATARA_MAIL_FROM", "no-reply@datara.app")

        assert isinstance(resolve_mailer(), SmtpMailer)

    def test_a_host_without_a_sender_is_not_enough(self, monkeypatch):
        monkeypatch.setenv("DATARA_SMTP_HOST", "smtp.example.com")

        assert isinstance(resolve_mailer(), ConsoleMailer)


class TestSmtpBackend:
    async def test_delivers_through_smtplib_with_starttls_and_login(
        self, monkeypatch, fake_smtp
    ):
        monkeypatch.setenv("DATARA_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("DATARA_SMTP_PORT", "587")
        monkeypatch.setenv("DATARA_SMTP_USER", "datara")
        monkeypatch.setenv("DATARA_SMTP_PASSWORD", "app-password")
        monkeypatch.setenv("DATARA_MAIL_FROM", "no-reply@datara.app")

        await resolve_mailer().send(
            to="ana@example.com",
            subject="Verifica tu correo",
            body="hola",
        )

        assert len(fake_smtp.instances) == 1
        sent = fake_smtp.instances[0]
        assert (sent.host, sent.port) == ("smtp.example.com", 587)
        assert sent.started_tls is True
        assert sent.login_calls == [("datara", "app-password")]
        message = sent.sent_messages[0]
        assert message["From"] == "no-reply@datara.app"
        assert message["To"] == "ana@example.com"
        assert message["Subject"] == "Verifica tu correo"
        assert "hola" in message.get_content()

    async def test_starttls_can_be_turned_off_explicitly(self, monkeypatch, fake_smtp):
        monkeypatch.setenv("DATARA_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("DATARA_SMTP_PORT", "1025")
        monkeypatch.setenv("DATARA_SMTP_STARTTLS", "0")
        monkeypatch.setenv("DATARA_MAIL_FROM", "no-reply@datara.app")

        await resolve_mailer().send(to="ana@example.com", subject="s", body="b")

        assert fake_smtp.instances[0].started_tls is False

    async def test_starttls_defaults_on_for_the_submission_port(
        self, monkeypatch, fake_smtp
    ):
        monkeypatch.setenv("DATARA_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("DATARA_SMTP_PORT", "587")
        monkeypatch.setenv("DATARA_MAIL_FROM", "no-reply@datara.app")

        await resolve_mailer().send(to="ana@example.com", subject="s", body="b")

        assert fake_smtp.instances[0].started_tls is True


class TestGetMailerDependency:
    def test_returns_a_mailer(self):
        assert isinstance(get_mailer(), (ConsoleMailer, SmtpMailer))


class TestLinks:
    def test_verification_link_points_at_the_frontend_route(self):
        assert (
            verification_link("http://localhost:8000", "tok-123")
            == "http://localhost:8000/verify-email?token=tok-123"
        )

    def test_reset_link_points_at_the_frontend_route(self):
        assert (
            reset_link("http://localhost:8000", "tok-456")
            == "http://localhost:8000/reset-password?token=tok-456"
        )

    def test_a_trailing_slash_in_the_app_url_does_not_double_up(self):
        assert verification_link("https://datara.app/", "t") == (
            "https://datara.app/verify-email?token=t"
        )

    def test_app_url_defaults_to_localhost(self):
        assert resolve_app_url() == "http://localhost:8000"

    def test_app_url_can_be_overridden(self, monkeypatch):
        monkeypatch.setenv("DATARA_APP_URL", "https://datara.app/")

        assert resolve_app_url() == "https://datara.app"


class TestRenderedEmails:
    def test_verification_email_carries_the_link(self):
        link = verification_link("http://localhost:8000", "tok-123")

        subject, body = render_verification_email(link)

        assert subject
        assert link in body

    def test_reset_email_carries_the_link_and_states_the_duration(self):
        link = reset_link("http://localhost:8000", "tok-456")

        subject, body = render_reset_email(link)

        assert subject
        assert link in body
        assert "1" in body
