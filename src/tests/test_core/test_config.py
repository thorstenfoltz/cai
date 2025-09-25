import builtins
import logging
from pathlib import Path
from unittest import mock

import pytest
import yaml

from git_cai_cli.core import config  # adjust import path as needed


@pytest.fixture
def mock_logger():
    return mock.MagicMock(spec=logging.Logger)


@pytest.fixture
def temp_config_file(tmp_path):
    return tmp_path / "cai_config.yml"


@pytest.fixture
def temp_tokens_file(tmp_path):
    return tmp_path / "tokens.yml"


#def test_load_config_repo_file_exists(monkeypatch, mock_logger, tmp_path):
#    repo_config_path = tmp_path / "cai_config.yml"
#    repo_config_path.write_text(yaml.safe_dump({"openai": {"model": "gpt-test"}}))
#
#    monkeypatch.setattr(config, "find_git_root", lambda: tmp_path)
#    
#    cfg = config.load_config(log=mock_logger)
#    assert cfg["openai"]["model"] == "gpt-test"
#
#
#def test_load_config_fallback_file_created(monkeypatch, mock_logger, tmp_path):
#    fallback_path = tmp_path / "cai_config.yml"
#    monkeypatch.setattr(config, "FALLBACK_CONFIG_FILE", fallback_path)
#    monkeypatch.setattr(config, "find_git_root", lambda: None)
#
#    cfg = config.load_config(log=mock_logger)
#    assert cfg == config.DEFAULT_CONFIG
#    assert fallback_path.exists()
#    mock_logger.warning.assert_called()
#
#
#def test_load_config_fallback_file_existing(monkeypatch, tmp_path, mock_logger):
#    fallback_path = tmp_path / "cai_config.yml"
#    fallback_path.write_text(yaml.safe_dump({"openai": {"model": "existing"}}))
#    monkeypatch.setattr(config, "FALLBACK_CONFIG_FILE", fallback_path)
#    monkeypatch.setattr(config, "find_git_root", lambda: None)
#
#    cfg = config.load_config(log=mock_logger)
#    assert cfg["openai"]["model"] == "existing"
#
#
def test_load_token_file_creation(monkeypatch, tmp_path, mock_logger):
    tokens_path = tmp_path / "tokens.yml"
    monkeypatch.setattr(config, "TOKENS_FILE", tokens_path)

    token = config.load_token("openai", tokens_file=tokens_path, log=mock_logger)
    assert token is None
    assert tokens_path.exists()
    mock_logger.warning.assert_called()
    mock_logger.info.assert_called()
#
#
#def test_load_token_existing_key(monkeypatch, tmp_path, mock_logger):
#    tokens_path = tmp_path / "tokens.yml"
#    tokens_path.write_text(yaml.safe_dump({"openai": "abc123"}))
#
#    monkeypatch.setattr(config, "TOKENS_FILE", tokens_path)
#
#    token = config.load_token("openai", tokens_file=tokens_path, log=mock_logger)
#    assert token == "abc123"
#
#
#def test_load_token_missing_key(monkeypatch, tmp_path, mock_logger):
#    tokens_path = tmp_path / "tokens.yml"
#    tokens_path.write_text(yaml.safe_dump({"huggingface": "xyz"}))
#
#    monkeypatch.setattr(config, "TOKENS_FILE", tokens_path)
#
#    token = config.load_token("openai", tokens_file=tokens_path, log=mock_logger)
#    assert token is None
#    mock_logger.error.assert_called()
