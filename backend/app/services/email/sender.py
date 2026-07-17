"""Email transport (C2) — pluggable sender with an aiosmtplib SMTP impl."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailNotConfigured(RuntimeError):
    """Raised when a send is attempted without SMTP credentials."""


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str  # e.g. "application/pdf"


class EmailSender(Protocol):
    async def send(
        self,
        *,
        to: list[str],
        subject: str,
        html_body: str,
        attachments: list[EmailAttachment] | None = None,
    ) -> None: ...


def build_message(
    *,
    sender: str,
    to: list[str],
    subject: str,
    html_body: str,
    attachments: list[EmailAttachment] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content("This report requires an HTML-capable email client.")
    msg.add_alternative(html_body, subtype="html")
    for att in attachments or []:
        maintype, _, subtype = att.mime_type.partition("/")
        msg.add_attachment(
            att.content,
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=att.filename,
        )
    return msg


class SmtpEmailSender:
    """Sends via aiosmtplib over STARTTLS using the configured SMTP server."""

    @property
    def is_configured(self) -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)

    async def send(
        self,
        *,
        to: list[str],
        subject: str,
        html_body: str,
        attachments: list[EmailAttachment] | None = None,
    ) -> None:
        if not self.is_configured:
            raise EmailNotConfigured("SMTP is not configured")
        message = build_message(
            sender=settings.SMTP_USER,
            to=to,
            subject=subject,
            html_body=html_body,
            attachments=attachments,
        )
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info("report_email_sent", recipients=len(to), subject=subject)


def get_email_sender() -> EmailSender | None:
    sender = SmtpEmailSender()
    return sender if sender.is_configured else None
