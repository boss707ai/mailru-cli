"""Build and send messages via Mail.ru SMTP (smtp.mail.ru:465, SSL)."""

from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate, getaddresses, make_msgid
from pathlib import Path


def parse_addrs(values: tuple[str, ...]) -> list[str]:
    """Flatten repeated flags into RFC-safe address strings; display names
    with specials come back properly quoted ('"Doe, John" <j@d.ru>')."""
    parsed = getaddresses(list(values))
    result = []
    for name, addr in parsed:
        if not addr:
            continue
        result.append(formataddr((name, addr)) if name else addr)
    return result


def extract_addrs(*header_values: str | None) -> list[str]:
    """Bare addresses for the SMTP envelope (display names stripped)."""
    present = [v for v in header_values if v]
    return [addr for _, addr in getaddresses(present) if addr]


def build_message(
    sender: str,
    to: list[str],
    subject: str,
    text: str | None = None,
    html: str | None = None,
    cc: list[str] | None = None,
    reply_to: str | None = None,
    attachments: list[str] | None = None,
) -> EmailMessage:
    # Bcc is intentionally never written into headers — recipients are passed
    # separately to the SMTP envelope so they stay invisible.
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text or "")
    if html:
        msg.add_alternative(html, subtype="html")
    for path in attachments or []:
        p = Path(path)
        ctype, _ = mimetypes.guess_type(p.name)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        msg.add_attachment(
            p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name
        )
    return msg


def describe(msg: EmailMessage, bcc: list[str]) -> dict:
    """Dry-run summary: what would be sent, without connecting anywhere."""
    return {
        "from": msg["From"],
        "to": msg["To"],
        "cc": msg["Cc"],
        "bcc": bcc,
        "subject": msg["Subject"],
        "attachments": [
            part.get_filename() for part in msg.iter_attachments()
        ],
        "size_bytes": len(bytes(msg)),
    }


def send(cfg: dict, email: str, password: str, msg: EmailMessage, bcc: list[str]) -> dict:
    recipients = extract_addrs(msg["To"], msg["Cc"], *bcc)
    with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=cfg["timeout"]) as smtp:
        smtp.login(email, password)
        refused = smtp.send_message(msg, from_addr=email, to_addrs=recipients)
    return {
        "sent": True,
        "message_id": msg["Message-ID"],
        "recipients": recipients,
        "refused": {k: str(v) for k, v in refused.items()},
    }
