"""mailru — agent-first CLI for Mail.ru mailboxes.

All output is structured JSON by default (``--format table`` for humans).
Errors go to stderr as JSON with a non-zero exit code.
"""

from __future__ import annotations

import imaplib
import json
import smtplib
import sys
from pathlib import Path

import click

from . import __version__, config as cfgmod, imap as imapmod, serialize, smtp as smtpmod

EXIT_ERROR = 1
EXIT_AUTH = 2

NETWORK_ERRORS = (
    imaplib.IMAP4.error,
    smtplib.SMTPException,
    OSError,
    TimeoutError,
)


def emit(ctx: click.Context, data) -> None:
    if ctx.obj.get("fmt") == "table":
        click.echo(_to_table(data))
    else:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _to_table(data) -> str:
    rows = data if isinstance(data, list) else [data]
    if not rows:
        return "(empty)"
    keys = list(rows[0].keys())

    def cell(row, key):
        value = row.get(key, "")
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        return str(value)[:60]

    widths = {k: max(len(k), *(len(cell(r, k)) for r in rows)) for k in keys}
    lines = [" | ".join(k.ljust(widths[k]) for k in keys)]
    lines.append("-+-".join("-" * widths[k] for k in keys))
    for row in rows:
        lines.append(" | ".join(cell(row, k).ljust(widths[k]) for k in keys))
    return "\n".join(lines)


def fail(message: str, code: int = EXIT_ERROR) -> None:
    click.echo(json.dumps({"error": message}, ensure_ascii=False), err=True)
    sys.exit(code)


def _credentials(cfg: dict) -> tuple[str, str, str]:
    email = cfgmod.resolve_email(cfg)
    if not email:
        fail("no email configured — run `mailru auth setup` or set MAILRU_EMAIL", EXIT_AUTH)
    password, source = cfgmod.resolve_password(email, cfg)
    if not password:
        fail(
            f"no password found for {email} — run `mailru auth setup` or set MAILRU_PASSWORD",
            EXIT_AUTH,
        )
    return email, password, source


@click.group()
@click.version_option(__version__, prog_name="mailru")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "table"]),
    default="json",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def main(ctx: click.Context, fmt: str) -> None:
    """Mail.ru mailbox from the command line: list, read, search, send."""
    ctx.obj = {"fmt": fmt}


# --------------------------------------------------------------------------- auth


@main.group()
def auth() -> None:
    """Manage credentials (Mail.ru app passwords)."""


@auth.command("setup")
@click.option("--email", "email_opt", help="Mailbox address (prompted if omitted).")
@click.option(
    "--store",
    type=click.Choice(["keyring", "config", "none"]),
    default="keyring",
    show_default=True,
    help="Where to store the password: OS credential store, config file (0600), or nowhere (env-only usage).",
)
@click.pass_context
def auth_setup(ctx: click.Context, email_opt: str | None, store: str) -> None:
    """Verify and store an app password.

    Create one at Mail.ru: Настройки → Безопасность → «Пароли для внешних
    приложений», type «Полный доступ к Почте». The regular account password
    will NOT work.
    """
    cfg = cfgmod.load_config()
    email = email_opt or cfgmod.resolve_email(cfg) or click.prompt("Mailbox address")
    import os

    password = os.environ.get("MAILRU_PASSWORD") or click.prompt(
        "App password (hidden)", hide_input=True
    )

    try:
        with imapmod.open_mailbox(cfg, email, password):
            pass
    except NETWORK_ERRORS as exc:
        fail(f"IMAP login failed for {email}: {exc}", EXIT_AUTH)

    stored_in = "none"
    if store == "keyring":
        try:
            cfgmod.store_password_keyring(email, password)
            stored_in = "keyring"
        except Exception as exc:
            click.echo(
                json.dumps(
                    {"warning": f"keyring unavailable ({exc}); falling back to config file"},
                    ensure_ascii=False,
                ),
                err=True,
            )
            store = "config"
    if store == "config":
        cfg["password"] = password
        stored_in = "config"

    cfg["email"] = email
    if stored_in != "config":
        cfg.pop("password", None)
    cfgmod.save_config(cfg)
    emit(ctx, {"ok": True, "email": email, "password_stored_in": stored_in})


@auth.command("status")
@click.pass_context
def auth_status(ctx: click.Context) -> None:
    """Check credentials and connectivity to IMAP and SMTP."""
    cfg = cfgmod.load_config()
    email, password, source = _credentials(cfg)

    imap_ok, imap_error = True, None
    try:
        with imapmod.open_mailbox(cfg, email, password):
            pass
    except NETWORK_ERRORS as exc:
        imap_ok, imap_error = False, str(exc)

    smtp_ok, smtp_error = True, None
    try:
        with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=cfg["timeout"]) as s:
            s.login(email, password)
    except NETWORK_ERRORS as exc:
        smtp_ok, smtp_error = False, str(exc)

    emit(
        ctx,
        {
            "email": email,
            "password_source": source,
            "imap": {"ok": imap_ok, "error": imap_error, "host": cfg["imap_host"]},
            "smtp": {"ok": smtp_ok, "error": smtp_error, "host": cfg["smtp_host"]},
        },
    )
    if not (imap_ok and smtp_ok):
        sys.exit(EXIT_AUTH)


@auth.command("remove")
@click.pass_context
def auth_remove(ctx: click.Context) -> None:
    """Remove stored credentials (keyring entry and config password)."""
    cfg = cfgmod.load_config()
    email = cfgmod.resolve_email(cfg)
    removed_keyring = cfgmod.delete_password_keyring(email) if email else False
    removed_config = cfg.pop("password", None) is not None
    cfgmod.save_config(cfg)
    emit(ctx, {"ok": True, "removed_keyring": removed_keyring, "removed_config": removed_config})


# --------------------------------------------------------------------------- mail


@main.group()
def mail() -> None:
    """Read, search, and send mail."""


@mail.command("list")
@click.option("--folder", default="INBOX", show_default=True)
@click.option("--limit", default=10, show_default=True)
@click.option("--unread", is_flag=True, help="Only unread messages.")
@click.pass_context
def mail_list(ctx: click.Context, folder: str, limit: int, unread: bool) -> None:
    """List newest messages (headers only, never marks as read)."""
    cfg = cfgmod.load_config()
    email, password, _ = _credentials(cfg)
    criteria = imapmod.build_criteria(unread=unread)
    try:
        with imapmod.open_mailbox(cfg, email, password, folder) as mb:
            messages = [
                serialize.envelope(m)
                for m in imapmod.fetch(mb, criteria, limit=limit, headers_only=True)
            ]
    except NETWORK_ERRORS as exc:
        fail(str(exc))
    emit(ctx, messages)


@mail.command("read")
@click.argument("uid")
@click.option("--folder", default="INBOX", show_default=True)
@click.option("--keep-unread", is_flag=True, help="Do not mark the message as read.")
@click.option("--html", "include_html", is_flag=True, help="Include the HTML body.")
@click.option(
    "--save-attachments",
    type=click.Path(file_okay=False),
    help="Directory to save attachments into.",
)
@click.pass_context
def mail_read(
    ctx: click.Context,
    uid: str,
    folder: str,
    keep_unread: bool,
    include_html: bool,
    save_attachments: str | None,
) -> None:
    """Read one message by IMAP UID."""
    cfg = cfgmod.load_config()
    email, password, _ = _credentials(cfg)
    criteria = imapmod.build_criteria(uid=uid)
    try:
        with imapmod.open_mailbox(cfg, email, password, folder) as mb:
            found = list(
                imapmod.fetch(
                    mb, criteria, limit=1, headers_only=False, mark_seen=not keep_unread
                )
            )
            if not found:
                fail(f"uid {uid} not found in folder {folder}")
            msg = found[0]
            data = serialize.full(msg, include_html=include_html)
            if save_attachments:
                target = Path(save_attachments)
                target.mkdir(parents=True, exist_ok=True)
                saved = []
                for i, att in enumerate(msg.attachments):
                    name = serialize.safe_filename(att.filename, f"attachment-{i}")
                    path = target / name
                    path.write_bytes(att.payload)
                    saved.append(str(path))
                data["saved_attachments"] = saved
    except NETWORK_ERRORS as exc:
        fail(str(exc))
    emit(ctx, data)


@mail.command("search")
@click.option("--from", "from_addr", help="Sender contains.")
@click.option("--to", "to_addr", help="Recipient contains.")
@click.option("--subject", help="Subject contains.")
@click.option("--text", help="Body contains.")
@click.option("--since", help="Date YYYY-MM-DD (inclusive).")
@click.option("--before", help="Date YYYY-MM-DD (exclusive).")
@click.option("--unread", is_flag=True)
@click.option("--folder", default="INBOX", show_default=True)
@click.option("--limit", default=25, show_default=True)
@click.pass_context
def mail_search(
    ctx: click.Context,
    from_addr: str | None,
    to_addr: str | None,
    subject: str | None,
    text: str | None,
    since: str | None,
    before: str | None,
    unread: bool,
    folder: str,
    limit: int,
) -> None:
    """Search messages (newest first, headers only)."""
    if not any([from_addr, to_addr, subject, text, since, before, unread]):
        fail("give at least one search criterion")
    cfg = cfgmod.load_config()
    email, password, _ = _credentials(cfg)
    try:
        criteria = imapmod.build_criteria(
            unread=unread,
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            text=text,
            since=since,
            before=before,
        )
    except ValueError as exc:
        fail(f"bad date: {exc}")
    try:
        with imapmod.open_mailbox(cfg, email, password, folder) as mb:
            messages = [
                serialize.envelope(m)
                for m in imapmod.fetch(mb, criteria, limit=limit, headers_only=True)
            ]
    except NETWORK_ERRORS as exc:
        fail(str(exc))
    emit(ctx, messages)


@mail.command("send")
@click.option("--to", "to_addrs", multiple=True, required=True, help="Repeatable.")
@click.option("--cc", "cc_addrs", multiple=True, help="Repeatable.")
@click.option("--bcc", "bcc_addrs", multiple=True, help="Repeatable.")
@click.option("--subject", required=True)
@click.option("--text", "text_body", help="Plain-text body; reads stdin if omitted and no --html.")
@click.option("--html", "html_body", help="HTML body (sent as alternative).")
@click.option("--reply-to")
@click.option(
    "--attach",
    "attachments",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Repeatable.",
)
@click.option("--dry-run", is_flag=True, help="Build and show the message without sending.")
@click.pass_context
def mail_send(
    ctx: click.Context,
    to_addrs: tuple[str, ...],
    cc_addrs: tuple[str, ...],
    bcc_addrs: tuple[str, ...],
    subject: str,
    text_body: str | None,
    html_body: str | None,
    reply_to: str | None,
    attachments: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Send a message via smtp.mail.ru."""
    cfg = cfgmod.load_config()
    if dry_run:
        email = cfgmod.resolve_email(cfg) or "unconfigured@mail.ru"
        password = None
    else:
        email, password, _ = _credentials(cfg)
    if text_body is None and html_body is None:
        text_body = sys.stdin.read()

    to = smtpmod.parse_addrs(to_addrs)
    cc = smtpmod.parse_addrs(cc_addrs)
    bcc = smtpmod.parse_addrs(bcc_addrs)
    if not to:
        fail("no valid --to address")

    msg = smtpmod.build_message(
        sender=email,
        to=to,
        subject=subject,
        text=text_body,
        html=html_body,
        cc=cc,
        reply_to=reply_to,
        attachments=list(attachments),
    )
    if dry_run:
        emit(ctx, {"dry_run": True, **smtpmod.describe(msg, bcc)})
        return
    try:
        result = smtpmod.send(cfg, email, password, msg, bcc)
    except NETWORK_ERRORS as exc:
        fail(str(exc))
    emit(ctx, result)


# --------------------------------------------------------------------------- folders


@main.group()
def folders() -> None:
    """Mailbox folders."""


@folders.command("list")
@click.option("--counts", is_flag=True, help="Include message/unseen counts (slower).")
@click.pass_context
def folders_list(ctx: click.Context, counts: bool) -> None:
    """List folders (Cyrillic names decoded from IMAP UTF-7)."""
    cfg = cfgmod.load_config()
    email, password, _ = _credentials(cfg)
    try:
        with imapmod.open_mailbox(cfg, email, password) as mb:
            data = imapmod.list_folders(mb, with_counts=counts)
    except NETWORK_ERRORS as exc:
        fail(str(exc))
    emit(ctx, data)


if __name__ == "__main__":
    main()
