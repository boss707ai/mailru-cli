import json
import sys
import types

from mailru_cli import config as cfgmod


def test_env_beats_everything(monkeypatch):
    monkeypatch.setenv("MAILRU_PASSWORD", "from-env")
    password, source = cfgmod.resolve_password("x@mail.ru", {"password": "from-config"})
    assert (password, source) == ("from-env", "env")


def test_keyring_beats_config(monkeypatch):
    monkeypatch.delenv("MAILRU_PASSWORD", raising=False)
    fake = types.ModuleType("keyring")
    fake.get_password = lambda service, user: "from-keyring"
    monkeypatch.setitem(sys.modules, "keyring", fake)
    password, source = cfgmod.resolve_password("x@mail.ru", {"password": "from-config"})
    assert (password, source) == ("from-keyring", "keyring")


def test_config_fallback_when_keyring_broken(monkeypatch):
    monkeypatch.delenv("MAILRU_PASSWORD", raising=False)
    fake = types.ModuleType("keyring")

    def boom(service, user):
        raise RuntimeError("no backend")

    fake.get_password = boom
    monkeypatch.setitem(sys.modules, "keyring", fake)
    password, source = cfgmod.resolve_password("x@mail.ru", {"password": "from-config"})
    assert (password, source) == ("from-config", "config")


def test_none_when_nothing_stored(monkeypatch):
    monkeypatch.delenv("MAILRU_PASSWORD", raising=False)
    fake = types.ModuleType("keyring")
    fake.get_password = lambda service, user: None
    monkeypatch.setitem(sys.modules, "keyring", fake)
    password, source = cfgmod.resolve_password("x@mail.ru", {})
    assert (password, source) == (None, "none")


def test_save_and_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("MAILRU_CONFIG_DIR", str(tmp_path))
    cfg = cfgmod.load_config()
    cfg["email"] = "x@mail.ru"
    cfgmod.save_config(cfg)

    stored = json.loads((tmp_path / "config.json").read_text())
    assert stored == {"email": "x@mail.ru"}  # defaults are not persisted

    loaded = cfgmod.load_config()
    assert loaded["email"] == "x@mail.ru"
    assert loaded["imap_host"] == "imap.mail.ru"


def test_config_file_is_owner_only(monkeypatch, tmp_path):
    monkeypatch.setenv("MAILRU_CONFIG_DIR", str(tmp_path))
    cfgmod.save_config({**cfgmod.DEFAULTS, "email": "x@mail.ru"})
    mode = (tmp_path / "config.json").stat().st_mode & 0o777
    assert mode == 0o600
