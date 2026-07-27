# mailru-cli

Agent-first command-line client for [Mail.ru](https://mail.ru) mailboxes over IMAP/SMTP.
Structured JSON output by default — built for AI agents, scripts, and humans who pipe.

Works on macOS, Linux, and Windows. No cloud, no telemetry: the only network
connections are to `imap.mail.ru` and `smtp.mail.ru`.

## Install

Any standard Python installer works (Python 3.10+):

```bash
pipx install mailru-cli      # or:
uv tool install mailru-cli   # or:
pip install mailru-cli
```

## Setup

Mail.ru does not accept your regular account password in external apps.
Create an **app password**: Mail.ru → Настройки → Все настройки → Безопасность →
«Пароли для внешних приложений» → Создать, type **«Полный доступ к Почте»**
(a linked phone number is required).

```bash
mailru auth setup            # prompts for address + app password, verifies, stores
mailru auth status           # checks IMAP + SMTP connectivity
```

Credential lookup order:

1. `MAILRU_EMAIL` / `MAILRU_PASSWORD` environment variables (CI, containers, agents)
2. OS credential store via [keyring](https://pypi.org/project/keyring/) —
   macOS Keychain, Windows Credential Manager, Linux Secret Service
3. `password` field in the config file (created `0600`) — fallback for headless
   systems without a credential store (`mailru auth setup --store config`)

Config file lives in the platform config dir (`~/Library/Application Support/mailru-cli/`,
`%APPDATA%\mailru-cli\`, `~/.config/mailru-cli/`); override with `MAILRU_CONFIG_DIR`.

## Usage

```bash
mailru mail list --limit 10 --unread          # newest first, never marks as read
mailru mail read 4211 --keep-unread           # one message by IMAP UID
mailru mail read 4211 --save-attachments ./attachments
mailru mail search --from billing@ --since 2026-07-01
mailru mail search --subject "счёт" --folder INBOX
mailru folders list --counts                  # Cyrillic folder names decoded

mailru mail send --to a@b.ru --subject "Hi" --text "Body" --dry-run   # preview
mailru mail send --to a@b.ru --cc c@d.ru --subject "Hi" --attach report.pdf --text "См. вложение"
echo "Body from stdin" | mailru mail send --to a@b.ru --subject "Hi"

mailru --format table mail list               # human-readable tables
```

Exit codes: `0` success, `1` error, `2` auth/credentials problem.
Errors are JSON on stderr: `{"error": "..."}`.

## Security notes

- Use a **scoped** app password («Полный доступ к Почте»), never your account password.
- `--dry-run` on `mail send` builds the full message and shows recipients,
  subject, and size without connecting to SMTP.
- Attachment filenames are sanitized on save (no path traversal).
- Bcc recipients are passed in the SMTP envelope only — never written into headers.
- If you drive this tool with an LLM agent: email bodies are untrusted input
  (prompt injection); keep `mail send` behind explicit human confirmation.

## Development

```bash
git clone https://github.com/smart-boss/mailru-cli && cd mailru-cli
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## License

MIT
