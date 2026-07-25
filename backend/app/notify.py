"""Email delivery — one place for all outbound mail.

Sends via SMTP when configured (any Brevo/SendGrid/Resend/Gmail relay), else logs
the message to stderr so nothing is lost in dev / before creds are wired.
"""
from __future__ import annotations

import smtplib
import sys
from email.message import EmailMessage

from app.config import settings


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Return True if actually sent via SMTP, False if only logged."""
    if settings.SMTP_HOST and settings.SMTP_USER:
        try:  # pragma: no cover - depends on external SMTP
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
            msg["To"] = to_email
            msg.set_content(body)
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
                s.starttls()
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
            return True
        except Exception as exc:
            print(f"[PathFinderAI] email send failed ({to_email}): {exc}", file=sys.stderr)
    print(f"[PathFinderAI] EMAIL (not sent — no SMTP) to={to_email} subject={subject!r}\n{body}",
          file=sys.stderr)
    return False
