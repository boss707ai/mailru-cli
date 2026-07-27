"""IMAP operations via imap-tools (handles UTF-7 folder names, e.g. Mail.ru's
Cyrillic «Отправленные»/«Черновики»)."""

from __future__ import annotations

import datetime as dt

from imap_tools import AND, MailBox


def open_mailbox(cfg: dict, email: str, password: str, folder: str = "INBOX") -> MailBox:
    mailbox = MailBox(cfg["imap_host"], cfg["imap_port"], timeout=cfg["timeout"])
    return mailbox.login(email, password, initial_folder=folder)


def build_criteria(
    unread: bool = False,
    from_addr: str | None = None,
    to_addr: str | None = None,
    subject: str | None = None,
    text: str | None = None,
    since: str | None = None,
    before: str | None = None,
    uid: str | None = None,
):
    kwargs: dict = {}
    if unread:
        kwargs["seen"] = False
    if from_addr:
        kwargs["from_"] = from_addr
    if to_addr:
        kwargs["to"] = to_addr
    if subject:
        kwargs["subject"] = subject
    if text:
        kwargs["text"] = text
    if since:
        kwargs["date_gte"] = dt.date.fromisoformat(since)
    if before:
        kwargs["date_lt"] = dt.date.fromisoformat(before)
    if uid:
        kwargs["uid"] = uid
    if not kwargs:
        return "ALL"
    return AND(**kwargs)


def needs_utf8_charset(criteria) -> bool:
    """IMAP SEARCH defaults to US-ASCII; non-ASCII terms need CHARSET UTF-8."""
    return not str(criteria).isascii()


def fetch(mailbox: MailBox, criteria, limit: int, headers_only: bool, mark_seen: bool = False):
    charset = "UTF-8" if needs_utf8_charset(criteria) else "US-ASCII"
    return mailbox.fetch(
        criteria,
        limit=limit,
        reverse=True,  # newest first
        mark_seen=mark_seen,
        headers_only=headers_only,
        bulk=True,
        charset=charset,
    )


def list_folders(mailbox: MailBox, with_counts: bool = False) -> list[dict]:
    result = []
    for f in mailbox.folder.list():
        row: dict = {"name": f.name, "flags": list(f.flags)}
        if with_counts:
            try:
                status = mailbox.folder.status(f.name)
                row["messages"] = status.get("MESSAGES")
                row["unseen"] = status.get("UNSEEN")
            except Exception:
                row["messages"] = row["unseen"] = None
        result.append(row)
    return result
