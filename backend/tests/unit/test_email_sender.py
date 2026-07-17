"""C2: email transport — MIME assembly + configured-gate + mocked SMTP send."""

import pytest

from app.services.email import sender as S
from app.services.email.sender import EmailAttachment, EmailNotConfigured, SmtpEmailSender


def test_build_message_has_html_and_attachment():
    msg = S.build_message(
        sender="it@aditi.com",
        to=["lead@aditi.com", "admin@aditi.com"],
        subject="Monthly Report",
        html_body="<p>hi</p>",
        attachments=[EmailAttachment("report.pdf", b"%PDF-1.4 data", "application/pdf")],
    )
    assert msg["To"] == "lead@aditi.com, admin@aditi.com"
    assert msg["Subject"] == "Monthly Report"
    payloads = list(msg.iter_attachments())
    assert len(payloads) == 1
    assert payloads[0].get_filename() == "report.pdf"


def test_is_configured_false_without_creds(monkeypatch):
    monkeypatch.setattr(S.settings, "SMTP_HOST", "smtp.office365.com", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_USER", "", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_PASSWORD", "", raising=False)
    assert SmtpEmailSender().is_configured is False


@pytest.mark.asyncio
async def test_send_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(S.settings, "SMTP_USER", "", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_PASSWORD", "", raising=False)
    with pytest.raises(EmailNotConfigured):
        await SmtpEmailSender().send(to=["x@aditi.com"], subject="s", html_body="<p>b</p>")


@pytest.mark.asyncio
async def test_send_invokes_aiosmtplib(monkeypatch):
    monkeypatch.setattr(S.settings, "SMTP_HOST", "smtp.office365.com", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_PORT", 587, raising=False)
    monkeypatch.setattr(S.settings, "SMTP_USER", "it@aditi.com", raising=False)
    monkeypatch.setattr(S.settings, "SMTP_PASSWORD", "secret", raising=False)
    calls = {}

    async def _fake_send(message, **kwargs):
        calls["kwargs"] = kwargs
        calls["to"] = message["To"]

    monkeypatch.setattr(S.aiosmtplib, "send", _fake_send)
    await SmtpEmailSender().send(to=["lead@aditi.com"], subject="s", html_body="<p>b</p>")
    assert calls["to"] == "lead@aditi.com"
    assert calls["kwargs"]["hostname"] == "smtp.office365.com"
    assert calls["kwargs"]["start_tls"] is True
    assert calls["kwargs"]["username"] == "it@aditi.com"
