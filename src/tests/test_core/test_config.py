# rc/tests/test_core/test_config.py
import os
import stat
import yaml
import pytest
from unittest.mock import patch
from git_cai_cli.core.config import load_config, DEFAULT_CONFIG, load_token, TOKEN_TEMPLATE

# ------------------------------
# LOAD CONFIG UNIT TESTS
# ------------------------------
def test_load_config_returns_default(tmp_path):
    fallback_file = tmp_path / "cai_config.yml"
    config = load_config(fallback_config_file=fallback_file)
    assert config == DEFAULT_CONFIG
    assert fallback_file.exists()

def test_load_config_reads_existing_file(tmp_path):
    fallback_file = tmp_path / "cai_config.yml"
    sample_config = {"openai": {"model": "gpt-3.5", "temperature": 0.7}}
    fallback_file.write_text(yaml.safe_dump(sample_config))
    config = load_config(fallback_config_file=fallback_file)
    assert config == sample_config

def test_load_config_prefers_repo_config(tmp_path):
    repo_file = tmp_path / "cai_config.yml"
    repo_config = {"openai": {"model": "repo-model", "temperature": 1.0}}
    repo_file.write_text(yaml.safe_dump(repo_config))
    fallback_file = tmp_path / "fallback.yml"
    fallback_file.write_text(yaml.safe_dump(DEFAULT_CONFIG))
    with patch("git_cai_cli.core.config.find_git_root", return_value=tmp_path):
        config = load_config(fallback_config_file=fallback_file)
        assert config == repo_config

# ------------------------------
# LOAD TOKEN UNIT TESTS
# ------------------------------
def test_load_token_creates_template(tmp_path):
    token_file = tmp_path / "tokens.yml"
    result = load_token("openai", tokens_file=token_file)
    assert result is None
    assert token_file.exists()
    # Check file permissions
    assert stat.S_IMODE(token_file.stat().st_mode) == (stat.S_IRUSR | stat.S_IWUSR)
    loaded = yaml.safe_load(token_file.read_text())
    assert loaded == TOKEN_TEMPLATE

def test_load_token_reads_existing(tmp_path):
    token_file = tmp_path / "tokens.yml"
    sample_tokens = {"openai": "abc123"}
    token_file.write_text(yaml.safe_dump(sample_tokens))
    result = load_token("openai", tokens_file=token_file)
    assert result == "abc123"

def test_load_token_missing_key(tmp_path, caplog):
    token_file = tmp_path / "tokens.yml"
    token_file.write_text(yaml.safe_dump({"gemini": "xyz"}))
    result = load_token("openai", tokens_file=token_file)
    assert result is None
    assert "Key 'openai' not found" in caplog.text
