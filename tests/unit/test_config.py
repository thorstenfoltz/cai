import stat
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from git_cai_cli.core.config import (
    DEFAULT_CONFIG,
    TOKEN_TEMPLATE,
    _serialize_config,
    load_config,
    load_token,
)

def test_load_config_creates_fallback(tmp_path):
    fallback = tmp_path / "cai_config.yml"

    config = load_config(
        fallback_config_file=fallback,
        allowed_languages={"en"},
    )

    assert fallback.exists()

    # Runtime config keeps Path
    assert isinstance(config["load_tokens_from"], Path)

    # Serialized file contains string
    data = yaml.safe_load(fallback.read_text())
    assert isinstance(data["load_tokens_from"], str)

def test_load_config_reads_existing(tmp_path):
    fallback = tmp_path / "cai_config.yml"

    cfg = {
        "default": "openai",
        "language": "en",
        "style": "professional",
        "emoji": True,
        "openai": {"model": "x", "temperature": 0},
        "load_tokens_from": "/tmp/tokens.yml",
    }

    fallback.write_text(yaml.safe_dump(cfg))

    result = load_config(
        fallback_config_file=fallback,
        allowed_languages={"en"},
    )

    assert result["default"] == "openai"
    assert result["load_tokens_from"] == "/tmp/tokens.yml"

def test_repo_config_precedence(tmp_path):
    repo_cfg = tmp_path / "cai_config.yml"

    repo_data = {
        "default": "gemini",
        "language": "en",
        "style": "professional",
        "emoji": True,
        "gemini": {"model": "repo", "temperature": 0},
    }

    repo_cfg.write_text(yaml.safe_dump(repo_data))

    fallback = tmp_path / "fallback.yml"
    fallback.write_text(yaml.safe_dump(_serialize_config(DEFAULT_CONFIG)))

    with patch("git_cai_cli.core.config.find_git_root", return_value=tmp_path):
        config = load_config(fallback_config_file=fallback)

    assert config == repo_data

def test_load_token_creates_template(tmp_path):
    tokens = tmp_path / "tokens.yml"

    config = {
        "default": "openai",
        "load_tokens_from": tokens,
    }

    token = load_token(config=config)

    assert token is None
    assert tokens.exists()
    assert stat.S_IMODE(tokens.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR

    loaded = yaml.safe_load(tokens.read_text())
    assert loaded == TOKEN_TEMPLATE

def test_load_token_reads_existing(tmp_path):
    tokens = tmp_path / "tokens.yml"
    tokens.write_text(yaml.safe_dump({"openai": "abc123"}))

    config = {
        "default": "openai",
        "load_tokens_from": tokens,
    }

    token = load_token(config=config)

    assert token == "abc123"

def test_load_token_missing_key(tmp_path, caplog):
    tokens = tmp_path / "tokens.yml"
    tokens.write_text(yaml.safe_dump({"gemini": "xyz"}))

    config = {
        "default": "openai",
        "load_tokens_from": tokens,
    }

    result = load_token(config=config)

    assert result is None
    assert "Token for provider 'openai' not found" in caplog.text

def test_serialize_config_converts_path():
    cfg = {"x": Path("/tmp/test")}
    out = _serialize_config(cfg)

    assert out["x"] == "/tmp/test"
    assert isinstance(out["x"], str)
