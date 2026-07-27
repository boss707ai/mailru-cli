import ssl

import pytest

from mailru_cli import imap as imapmod, smtp as smtpmod
from mailru_cli.serialize import write_unique


def test_imap_ssl_context_verifies():
    assert imapmod.SSL_CONTEXT.verify_mode == ssl.CERT_REQUIRED
    assert imapmod.SSL_CONTEXT.check_hostname is True


def test_smtp_ssl_context_verifies():
    assert smtpmod.SSL_CONTEXT.verify_mode == ssl.CERT_REQUIRED
    assert smtpmod.SSL_CONTEXT.check_hostname is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"subject": 'x"\r\nA1 DELETE INBOX'},
        {"from_addr": "a\nb"},
        {"to_addr": "a\rb"},
        {"text": "a\x00b"},
        {"uid": "1\r\n"},
    ],
)
def test_build_criteria_rejects_control_chars(kwargs):
    with pytest.raises(ValueError, match="control characters"):
        imapmod.build_criteria(**kwargs)


def test_check_clean_allows_normal_values():
    assert imapmod.check_clean("Отправленные", "folder") == "Отправленные"
    assert imapmod.check_clean(None, "folder") is None


def test_write_unique_never_overwrites(tmp_path):
    first = write_unique(tmp_path, "a.txt", b"one")
    second = write_unique(tmp_path, "a.txt", b"two")
    assert first.name == "a.txt"
    assert second.name == "a-1.txt"
    assert first.read_bytes() == b"one"
    assert second.read_bytes() == b"two"


def test_write_unique_refuses_symlink(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"precious")
    (tmp_path / "evil.txt").symlink_to(victim)
    result = write_unique(tmp_path, "evil.txt", b"payload")
    assert result.name == "evil-1.txt"  # exclusive open refuses the symlink path
    assert victim.read_bytes() == b"precious"


def test_table_output_strips_ansi_escapes():
    from mailru_cli.cli import _to_table

    rows = [{"subject": "evil\x1b[2Jclear\x07bell"}]
    out = _to_table(rows)
    assert "\x1b" not in out
    assert "\x07" not in out
    assert "evil" in out
