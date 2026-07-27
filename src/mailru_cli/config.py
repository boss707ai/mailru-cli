"""Configuration and credential resolution.

Credential lookup order (first hit wins):

1. ``MAILRU_EMAIL`` / ``MAILRU_PASSWORD`` environment variables — for CI,
   containers, and non-interactive agents.
2. OS credential store via ``keyring`` — macOS Keychain, Windows Credential
   Manager, Linux Secret Service.
3. ``password`` field in the config file (written with 0600 permissions) —
   fallback for systems without a working credential store.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from platformdirs import user_config_dir

APP_NAME = "mailru-cli"
KEYRING_SERVICE = "mailru-cli"

DEFAULTS: dict = {
    "imap_host": "imap.mail.ru",
    "imap_port": 993,
    "smtp_host": "smtp.mail.ru",
    "smtp_port": 465,
    "timeout": 30,
}


def config_path() -> Path:
    override = os.environ.get("MAILRU_CONFIG_DIR")
    base = Path(override) if override else Path(user_config_dir(APP_NAME))
    return base / "config.json"


def load_config() -> dict:
    path = config_path()
    data = {}
    if path.is_file():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    return {**DEFAULTS, **data}


def save_config(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = {k: v for k, v in cfg.items() if DEFAULTS.get(k) != v}
    # Atomic replace; the temp file is 0600 from the moment it exists, so a
    # password is never readable by other users even mid-write.
    tmp = path.with_suffix(".json.tmp")
    tmp.unlink(missing_ok=True)  # stale leftover from a crashed run
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(stored, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def resolve_email(cfg: dict) -> str | None:
    return os.environ.get("MAILRU_EMAIL") or cfg.get("email")


def resolve_password(email: str, cfg: dict) -> tuple[str | None, str]:
    """Return ``(password, source)``; source is env|keyring|config|none."""
    env = os.environ.get("MAILRU_PASSWORD")
    if env:
        return env, "env"
    try:
        import keyring

        stored = keyring.get_password(KEYRING_SERVICE, email)
    except Exception:
        stored = None
    if stored:
        return stored, "keyring"
    if cfg.get("password"):
        return str(cfg["password"]), "config"
    return None, "none"


def store_password_keyring(email: str, password: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, email, password)


def delete_password_keyring(email: str) -> bool:
    try:
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(KEYRING_SERVICE, email)
            return True
        except PasswordDeleteError:
            return False
    except Exception:
        return False
