"""Sends the backup email over SMTP (standard library only).

Mail always travels encrypted: port 465 uses TLS from the start, any other port must
offer STARTTLS, which is switched on before logging in. If the server does not offer it,
nothing is sent. The host name used in EHLO and the Message-ID are given explicitly, so
sending never waits on a local DNS lookup. Errors come out as MailError with a plain
message that never contains the password or the recipient address.
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Callable, Iterable

from ..domain import validation
from . import aeszip

SSL_PORT = 465
TIMEOUT_SECONDS = 20.0


class MailError(Exception):
    def __init__(self, public_message: str):
        super().__init__(public_message)
        self.public_message = public_message


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    sender: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    timeout: float = TIMEOUT_SECONDS

    @property
    def domain(self) -> str:
        return self.sender.rsplit("@", 1)[-1]


class BackupMailer:
    """What the services use: `encrypt_zip(...)` and `await send(...)`."""

    def __init__(self, config: SmtpConfig, zip_password: str, *,
                 smtp_class: Callable[..., Any] = smtplib.SMTP, smtp_ssl_class: Callable[..., Any] = smtplib.SMTP_SSL):
        self.config = config
        self._zip_password = zip_password
        self._smtp_class = smtp_class
        self._smtp_ssl_class = smtp_ssl_class

    def __repr__(self) -> str:
        return f"BackupMailer(host={self.config.host!r}, port={self.config.port})"

    def encrypt_zip(self, entries: Iterable[tuple[str, bytes]], *, modified) -> bytes:
        return aeszip.encrypt_zip(entries, self._zip_password, modified=modified)

    def build_message(self, *, to: str, subject: str, text: str, attachment: tuple[str, bytes] | None) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self.config.sender
        message["To"] = to
        message["Subject"] = subject
        message["Date"] = formatdate(usegmt=True)
        message["Message-ID"] = make_msgid(domain=self.config.domain)
        message.set_content(text)
        if attachment is not None:
            name, data = attachment
            message.add_attachment(data, maintype="application", subtype="zip", filename=name)
        return message

    async def send(self, *, to: str, subject: str, text: str, attachment: tuple[str, bytes] | None = None) -> None:
        await asyncio.to_thread(self.send_now, to=to, subject=subject, text=text, attachment=attachment)

    def send_now(self, *, to: str, subject: str, text: str, attachment: tuple[str, bytes] | None = None) -> None:
        try:
            to = validation.email_recipient(to)
        except validation.ValidationError:
            raise MailError("The saved backup email address is not valid.") from None
        message = self.build_message(to=to, subject=subject, text=text, attachment=attachment)
        config = self.config
        context = ssl.create_default_context()
        try:
            if config.port == SSL_PORT:
                server = self._smtp_ssl_class(config.host, config.port, local_hostname=config.domain,
                                              timeout=config.timeout, context=context)
            else:
                server = self._smtp_class(config.host, config.port, local_hostname=config.domain,
                                          timeout=config.timeout)
            with server:
                if config.port != SSL_PORT:
                    server.ehlo()
                    if not server.has_extn("starttls"):
                        raise MailError("The mail server does not offer an encrypted connection (STARTTLS), "
                                        "so nothing was sent.")
                    server.starttls(context=context)
                    server.ehlo()
                if config.username:
                    server.login(config.username, config.password or "")
                refused = server.send_message(message, from_addr=config.sender, to_addrs=[to])
                if refused:
                    raise MailError("The mail server refused the backup email address.")
        except MailError:
            raise
        except smtplib.SMTPAuthenticationError:
            raise MailError("The mail server did not accept SMTP_USERNAME and SMTP_PASSWORD.") from None
        except smtplib.SMTPRecipientsRefused:
            raise MailError("The mail server refused the backup email address.") from None
        except ssl.SSLError:
            raise MailError("The encrypted connection to the mail server failed, so nothing was sent.") from None
        except (smtplib.SMTPException, OSError) as exc:
            raise MailError(f"The email could not be sent ({type(exc).__name__}).") from None


def from_settings(settings, **kwargs) -> tuple[BackupMailer | None, tuple[str, ...]]:
    """The mailer, or None plus the plain names of what is missing."""
    missing = list(settings.mail_missing())
    if not aeszip.available():
        missing.append("pyzipper is not installed")
    if missing:
        return None, tuple(missing)
    config = SmtpConfig(host=settings.smtp_host, port=settings.smtp_port, sender=settings.smtp_from,
                        username=settings.smtp_username, password=settings.smtp_password)
    return BackupMailer(config, settings.backup_zip_password, **kwargs), ()
