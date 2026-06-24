"""
Unit tests for the --set / --set-home config CLI feature.
"""

import pytest
import yaml
from git_cai_cli.core.config import (
    _parse_config_value,
    add_to_secret_scan_exclude,
    set_config_value,
)

# ----------------------
# _parse_config_value
# ----------------------


def test_parse_bool_true():
    assert _parse_config_value("true") is True
    assert _parse_config_value("True") is True
    assert _parse_config_value("yes") is True


def test_parse_bool_false():
    assert _parse_config_value("false") is False
    assert _parse_config_value("False") is False
    assert _parse_config_value("no") is False


def test_parse_int():
    assert _parse_config_value("42") == 42
    assert _parse_config_value("0") == 0


def test_parse_float():
    assert _parse_config_value("0.7") == 0.7
    assert _parse_config_value("1.5") == 1.5


def test_parse_string():
    assert _parse_config_value("anthropic") == "anthropic"
    assert _parse_config_value("hello world") == "hello world"


def test_parse_empty_string():
    assert _parse_config_value("") == ""


# ----------------------
# set_config_value
# ----------------------


def test_set_top_level_key(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(yaml.safe_dump({"default": "groq", "language": "en"}))

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    result = set_config_value("default", "anthropic")

    data = yaml.safe_load(repo_config.read_text())
    assert data["default"] == "anthropic"
    assert data["language"] == "en"
    assert result == repo_config


def test_set_nested_key(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(
        yaml.safe_dump({"groq": {"model": "old-model", "temperature": 0}})
    )

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    set_config_value("groq.model", "llama-3.3-70b-versatile")

    data = yaml.safe_load(repo_config.read_text())
    assert data["groq"]["model"] == "llama-3.3-70b-versatile"
    assert data["groq"]["temperature"] == 0


def test_set_boolean_value(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(yaml.safe_dump({"emoji": True}))

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    set_config_value("emoji", "false")

    data = yaml.safe_load(repo_config.read_text())
    assert data["emoji"] is False


def test_set_float_value(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(
        yaml.safe_dump({"openai": {"model": "gpt-5.1", "temperature": 0}})
    )

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    set_config_value("openai.temperature", "0.7")

    data = yaml.safe_load(repo_config.read_text())
    assert data["openai"]["temperature"] == 0.7


def test_set_targets_repo_config_when_exists(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(yaml.safe_dump({"default": "groq"}))

    home_config = tmp_path / "home_config.yml"
    home_config.write_text(yaml.safe_dump({"default": "openai"}))

    monkeypatch.setattr(config_module, "FALLBACK_CONFIG_FILE", home_config)
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    result = set_config_value("default", "anthropic")

    assert result == repo_config
    assert yaml.safe_load(repo_config.read_text())["default"] == "anthropic"
    assert yaml.safe_load(home_config.read_text())["default"] == "openai"


def test_set_force_home(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(yaml.safe_dump({"default": "groq"}))

    home_config = tmp_path / "home_config.yml"
    home_config.write_text(yaml.safe_dump({"default": "openai"}))

    monkeypatch.setattr(config_module, "FALLBACK_CONFIG_FILE", home_config)
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    result = set_config_value("default", "anthropic", force_home=True)

    assert result == home_config
    assert yaml.safe_load(home_config.read_text())["default"] == "anthropic"
    assert yaml.safe_load(repo_config.read_text())["default"] == "groq"


def test_set_creates_nested_section_if_missing(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(yaml.safe_dump({"default": "groq"}))

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    set_config_value("mistral.model", "codestral-2508")

    data = yaml.safe_load(repo_config.read_text())
    assert data["mistral"]["model"] == "codestral-2508"


def test_set_empty_key_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        set_config_value("", "value")


def test_set_raises_when_no_repo_config(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    with pytest.raises(ValueError, match="No repository config found"):
        set_config_value("default", "anthropic")


# ----------------------
# add_to_secret_scan_exclude
# ----------------------


def test_exclude_targets_repo_config_when_exists(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(yaml.safe_dump({"default": "groq"}))
    home_config = tmp_path / "home_config.yml"
    home_config.write_text(yaml.safe_dump({"default": "openai"}))

    monkeypatch.setattr(config_module, "FALLBACK_CONFIG_FILE", home_config)
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    result = add_to_secret_scan_exclude("tests/f.py")

    assert result == repo_config
    assert yaml.safe_load(repo_config.read_text())["secret_scan_exclude"] == [
        "tests/f.py"
    ]
    assert "secret_scan_exclude" not in yaml.safe_load(home_config.read_text())


def test_exclude_falls_back_to_home_when_no_repo(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    home_config = tmp_path / "home_config.yml"
    home_config.write_text(yaml.safe_dump({"default": "openai"}))

    monkeypatch.setattr(config_module, "FALLBACK_CONFIG_FILE", home_config)
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    result = add_to_secret_scan_exclude("tests/f.py")

    assert result == home_config
    assert yaml.safe_load(home_config.read_text())["secret_scan_exclude"] == [
        "tests/f.py"
    ]


def test_exclude_dedups(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(
        yaml.safe_dump({"default": "groq", "secret_scan_exclude": ["a.py"]})
    )
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    add_to_secret_scan_exclude("a.py")

    assert yaml.safe_load(repo_config.read_text())["secret_scan_exclude"] == ["a.py"]


def test_exclude_appends_to_existing_list(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text(
        yaml.safe_dump({"default": "groq", "secret_scan_exclude": ["a.py"]})
    )
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    add_to_secret_scan_exclude("b.py")

    assert yaml.safe_load(repo_config.read_text())["secret_scan_exclude"] == [
        "a.py",
        "b.py",
    ]
