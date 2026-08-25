"""Send a generated PDF as an email attachment via user-supplied SMTP settings."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True


def send_email_with_attachment(
    smtp: SmtpConfig,
    to_email: str,
    subject: str,
    body: str,
    attachment_bytes: bytes,
    attachment_name: str,
) -> None:
    """Send `body` to `to_email` with the PDF attached. Raises on failure."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp.username
    msg["To"] = to_email
    msg.set_content(body)
    msg.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_name,
    )

    if smtp.port == 465:
        with smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=20) as server:
            server.login(smtp.username, smtp.password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp.host, smtp.port, timeout=20) as server:
            if smtp.use_tls:
                server.starttls()
            server.login(smtp.username, smtp.password)
            server.send_message(msg)
