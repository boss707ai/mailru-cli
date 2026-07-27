from mailru_cli.smtp import build_message, describe, extract_addrs, parse_addrs


def test_parse_addrs_flattens_commas_and_repeats():
    assert parse_addrs(("a@b.ru, c@d.ru", "e@f.ru")) == ["a@b.ru", "c@d.ru", "e@f.ru"]


def test_parse_addrs_quotes_display_name_with_comma():
    result = parse_addrs(('"Doe, John" <j@d.ru>',))
    assert result == ['"Doe, John" <j@d.ru>']


def test_roundtrip_display_name_with_comma_stays_one_recipient():
    to = parse_addrs(('"Doe, John" <j@d.ru>',))
    msg = build_message(sender="me@mail.ru", to=to, subject="s", text="x")
    assert extract_addrs(msg["To"]) == ["j@d.ru"]


def test_extract_addrs_strips_display_names():
    assert extract_addrs("Ann <a@b.ru>, c@d.ru", None, "Bob <e@f.ru>") == [
        "a@b.ru",
        "c@d.ru",
        "e@f.ru",
    ]


def _msg(**kwargs):
    defaults = dict(sender="me@mail.ru", to=["you@mail.ru"], subject="Test")
    return build_message(**{**defaults, **kwargs})


def test_build_message_basic_headers():
    msg = _msg(text="hello", cc=["cc@mail.ru"])
    assert msg["From"] == "me@mail.ru"
    assert msg["To"] == "you@mail.ru"
    assert msg["Cc"] == "cc@mail.ru"
    assert msg["Subject"] == "Test"
    assert msg["Message-ID"]
    assert msg.get_body(("plain",)).get_content().strip() == "hello"


def test_build_message_never_has_bcc_header():
    msg = _msg(text="x")
    assert msg["Bcc"] is None


def test_build_message_html_alternative():
    msg = _msg(text="plain", html="<b>rich</b>")
    assert msg.get_body(("html",)) is not None
    assert msg.get_body(("plain",)) is not None


def test_build_message_attachment(tmp_path):
    f = tmp_path / "прайс.pdf"
    f.write_bytes(b"%PDF-fake")
    msg = _msg(text="see attached", attachments=[str(f)])
    atts = list(msg.iter_attachments())
    assert len(atts) == 1
    assert atts[0].get_filename() == "прайс.pdf"
    assert atts[0].get_content_type() == "application/pdf"


def test_describe_includes_bcc_and_size():
    msg = _msg(text="hello")
    info = describe(msg, bcc=["hidden@mail.ru"])
    assert info["bcc"] == ["hidden@mail.ru"]
    assert info["size_bytes"] > 0
    assert info["attachments"] == []
