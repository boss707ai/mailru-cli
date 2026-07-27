"""Convert imap-tools MailMessage objects into JSON-safe dicts."""

from __future__ import annotations

from pathlib import Path


def _is_unread(flags) -> bool:
    return not any(f.upper() == "\\SEEN" for f in flags)


def envelope(msg) -> dict:
    return {
        "uid": msg.uid,
        "date": msg.date.isoformat() if msg.date else None,
        "from": msg.from_,
        "to": list(msg.to),
        "cc": list(msg.cc),
        "subject": msg.subject,
        "flags": list(msg.flags),
        "unread": _is_unread(msg.flags),
    }


def full(msg, include_html: bool = False) -> dict:
    data = envelope(msg)
    data["text"] = msg.text
    if include_html:
        data["html"] = msg.html
    data["attachments"] = [
        {
            "filename": att.filename,
            "content_type": att.content_type,
            "size": len(att.payload),
        }
        for att in msg.attachments
    ]
    return data


def safe_filename(name: str, fallback: str) -> str:
    """Strip any path components so a hostile attachment name can't escape
    the target directory."""
    cleaned = Path(name.replace("\\", "/")).name.strip()
    if cleaned in ("", ".", ".."):
        return fallback
    return cleaned
