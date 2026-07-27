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


def write_unique(directory: Path, name: str, payload: bytes) -> Path:
    """Write exclusively (never overwrite, never follow a planted symlink);
    on collision append -1, -2, … before the extension."""
    stem, dot, ext = name.partition(".")
    for attempt in range(1000):
        candidate = name if attempt == 0 else f"{stem}-{attempt}{dot}{ext}"
        path = directory / candidate
        try:
            with open(path, "xb") as f:
                f.write(payload)
            return path
        except FileExistsError:
            continue
    raise ValueError(f"cannot find a free filename for {name!r} in {directory}")
