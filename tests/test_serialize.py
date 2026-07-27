from imap_tools import MailMessage

from mailru_cli.serialize import envelope, full, safe_filename

RAW = b"""From: =?utf-8?B?0JjQstCw0L0=?= <ivan@mail.ru>\r
To: you@mail.ru\r
Subject: =?utf-8?B?0J/RgNC40LLQtdGC?=\r
Date: Mon, 27 Jul 2026 10:00:00 +0300\r
Content-Type: text/plain; charset=utf-8\r
Content-Transfer-Encoding: 8bit\r
\r
\xd0\xa2\xd0\xb5\xd0\xbb\xd0\xbe \xd0\xbf\xd0\xb8\xd1\x81\xd1\x8c\xd0\xbc\xd0\xb0\r
"""


def test_envelope_decodes_cyrillic():
    msg = MailMessage.from_bytes(RAW)
    data = envelope(msg)
    assert data["from"] == "ivan@mail.ru"
    assert data["subject"] == "Привет"
    assert data["to"] == ["you@mail.ru"]
    assert data["date"].startswith("2026-07-27T10:00:00")


def test_full_includes_text_body():
    msg = MailMessage.from_bytes(RAW)
    data = full(msg)
    assert "Тело письма" in data["text"]
    assert data["attachments"] == []


def test_unread_flag_case_insensitive():
    msg = MailMessage.from_bytes(RAW)
    assert envelope(msg)["unread"] is True  # no \Seen flag on a raw message


def test_safe_filename_blocks_traversal():
    assert safe_filename("../../etc/passwd", "fb") == "passwd"
    assert safe_filename("..\\..\\boot.ini", "fb") == "boot.ini"
    assert safe_filename("..", "fb") == "fb"
    assert safe_filename("", "fb") == "fb"
    assert safe_filename("отчёт.xlsx", "fb") == "отчёт.xlsx"
