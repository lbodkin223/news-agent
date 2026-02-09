"""Deliver briefings — save to file and / or send via email."""

import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests

from data_collector.config import (
    EMAIL_BACKEND,
    EMAIL_FROM,
    EMAIL_TO,
    OUTPUT_DIR,
    SENDGRID_API_KEY,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


# ── file delivery ────────────────────────────────────────────────────────────


def save_to_file(
    briefing_text: str,
    mode: str = "daily",
    output_dir: Optional[str] = None,
) -> str:
    """Write the briefing markdown to a dated file in *output_dir*.

    Returns the absolute path of the written file.
    """
    dest = output_dir or OUTPUT_DIR
    os.makedirs(dest, exist_ok=True)

    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    filename = f"briefing_{mode}_{ts}.md"
    path = os.path.join(dest, filename)

    with open(path, "w") as fh:
        fh.write(briefing_text)

    abs_path = os.path.abspath(path)
    logger.info("Briefing saved to %s", abs_path)
    return abs_path


# ── email helpers ────────────────────────────────────────────────────────────


def _subject_line(mode: str) -> str:
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return f"[News Agent] {mode.capitalize()} Intelligence Briefing — {date_str}"


def _recipient_list(email_to: Optional[str] = None) -> list[str]:
    raw = email_to or EMAIL_TO
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


# ── SMTP delivery ────────────────────────────────────────────────────────────


def send_via_smtp(
    briefing_text: str,
    mode: str = "daily",
    email_to: Optional[str] = None,
) -> bool:
    """Send the briefing as a plain-text + HTML email over SMTP.

    Returns True on success.
    """
    recipients = _recipient_list(email_to)
    if not recipients:
        logger.warning("No EMAIL_TO configured — skipping SMTP delivery.")
        return False
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not set — skipping SMTP delivery.")
        return False

    subject = _subject_line(mode)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM or SMTP_USER
    msg["To"] = ", ".join(recipients)

    # Plain-text part (the raw markdown is perfectly readable).
    msg.attach(MIMEText(briefing_text, "plain", "utf-8"))

    # Simple HTML wrapper so links are clickable in email clients.
    html_body = (
        "<html><body><pre style='font-family: sans-serif; white-space: pre-wrap;'>"
        + briefing_text
        + "</pre></body></html>"
    )
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(msg["From"], recipients, msg.as_string())
        logger.info("Email sent via SMTP to %s", recipients)
        return True
    except Exception:
        logger.exception("SMTP delivery failed")
        return False


# ── SendGrid delivery ────────────────────────────────────────────────────────


def send_via_sendgrid(
    briefing_text: str,
    mode: str = "daily",
    email_to: Optional[str] = None,
) -> bool:
    """Send the briefing via the SendGrid v3 Mail Send API.

    Uses ``requests`` directly so we don't add the sendgrid SDK as a
    hard dependency.

    Returns True on success.
    """
    recipients = _recipient_list(email_to)
    if not recipients:
        logger.warning("No EMAIL_TO configured — skipping SendGrid delivery.")
        return False
    if not SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY not set — skipping SendGrid delivery.")
        return False

    subject = _subject_line(mode)
    sender = EMAIL_FROM
    if not sender:
        logger.warning("EMAIL_FROM not set — skipping SendGrid delivery.")
        return False

    payload = {
        "personalizations": [
            {"to": [{"email": addr} for addr in recipients]},
        ],
        "from": {"email": sender},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": briefing_text},
        ],
    }

    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if resp.status_code in (200, 201, 202):
            logger.info("Email sent via SendGrid to %s", recipients)
            return True
        else:
            logger.error(
                "SendGrid returned %d: %s", resp.status_code, resp.text
            )
            return False
    except Exception:
        logger.exception("SendGrid delivery failed")
        return False


# ── unified delivery entry point ─────────────────────────────────────────────


def deliver(
    briefing_text: str,
    mode: str = "daily",
    output_dir: Optional[str] = None,
    email_to: Optional[str] = None,
    skip_file: bool = False,
    skip_email: bool = False,
) -> dict:
    """Deliver a briefing via all configured channels.

    Always saves to file unless *skip_file* is True.
    Sends email when ``EMAIL_BACKEND`` is set (``"smtp"`` or ``"sendgrid"``),
    unless *skip_email* is True.

    Returns ``{"file": path_or_None, "email": True/False}``.
    """
    result: dict = {"file": None, "email": False}

    if not skip_file:
        result["file"] = save_to_file(briefing_text, mode=mode, output_dir=output_dir)

    if skip_email or not EMAIL_BACKEND:
        if not skip_email and not EMAIL_BACKEND:
            logger.debug(
                "EMAIL_BACKEND not configured — email delivery skipped."
            )
        return result

    backend = EMAIL_BACKEND.lower().strip()
    if backend == "smtp":
        result["email"] = send_via_smtp(briefing_text, mode=mode, email_to=email_to)
    elif backend == "sendgrid":
        result["email"] = send_via_sendgrid(briefing_text, mode=mode, email_to=email_to)
    else:
        logger.warning("Unknown EMAIL_BACKEND %r — skipping email.", backend)

    return result
