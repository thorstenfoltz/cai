"""
Unit tests for git_cai_cli.core.config module.

These tests cover the basic functionality of load_config and load_token,
including file creation, reading existing files, repo config precedence,
token retrieval, and handling missing keys.
"""

import stat
from unittest.mock import patch

import pytest
import yaml
from git_cai_cli.core.config import (
    DEFAULT_CONFIG,
    TOKEN_TEMPLATE,
    _validate_config_keys,
    _validate_language,
    get_default_config,
    load_config,
    load_token,
)

# ------------------------------
# LOAD CONFIG UNIT TESTS
# ------------------------------


def test_load_config_returns_default(tmp_path):
    """
    Test that load_config returns the default configuration when no fallback
    or repo-level config exists, and that it creates the fallback file.
    """
    fallback_file = tmp_path / "cai_config.yml"
    config = load_config(fallback_config_file=fallback_file)

    # Should return the default configuration
    assert config == DEFAULT_CONFIG

    # Should create the fallback file
    assert fallback_file.exists()


def test_load_config_reads_existing_file(tmp_path):
    """
    Test that load_config correctly reads an existing fallback configuration file.
    """
    fallback_file = tmp_path / "cai_config.yml"
    sample_config = {
        "openai": {"model": "gpt-3.5", "temperature": 0.7},
        "gemini": {"model": "gemini-1", "temperature": 0.3},
        "language": "es",
        "default": "openai",
        "style": "friendly",
        "emoji": "false",
    }

    # Write sample config to fallback file
    fallback_file.write_text(yaml.safe_dump(sample_config))

    # load_config should return the contents of the file
    config = load_config(fallback_config_file=fallback_file)
    assert config == sample_config


def test_load_config_prefers_repo_config(tmp_path):
    """
    Test that load_config prefers a repo-level config over the fallback config.
    """
    # Create a repo-level config file
    repo_file = tmp_path / "cai_config.yml"
    repo_config = {
        "openai": {"model": "repo-model", "temperature": 1.0},
        "gemini": {"model": "repo-gemini", "temperature": 0.5},
        "language": "fr",
        "default": "gemini",
        "style": "friendly",
        "emoji": "false",
    }
    repo_file.write_text(yaml.safe_dump(repo_config))

    # Create a fallback file
    fallback_file = tmp_path / "fallback.yml"
    fallback_file.write_text(yaml.safe_dump(DEFAULT_CONFIG))

    # Mock find_git_root to simulate a repo
    with patch("git_cai_cli.core.config.find_git_root", return_value=tmp_path):
        config = load_config(fallback_config_file=fallback_file)
        assert config == repo_config


# ------------------------------
# LOAD TOKEN UNIT TESTS
# ------------------------------


def test_load_token_creates_template(tmp_path):
    """
    Test that load_token creates a template token file if none exists,
    returns None, and sets correct file permissions.
    """
    token_file = tmp_path / "tokens.yml"

    result = load_token("openai", tokens_file=token_file)

    # Function should return None when creating a template
    assert result is None

    # Template file should exist
    assert token_file.exists()

    # File permissions should be user read/write only
    assert stat.S_IMODE(token_file.stat().st_mode) == (stat.S_IRUSR | stat.S_IWUSR)

    # File contents should match TOKEN_TEMPLATE
    loaded = yaml.safe_load(token_file.read_text())
    assert loaded == TOKEN_TEMPLATE


def test_load_token_reads_existing(tmp_path):
    """
    Test that load_token returns the correct token when the token file exists.
    """
    token_file = tmp_path / "tokens.yml"
    sample_tokens = {"openai": "abc123"}
    token_file.write_text(yaml.safe_dump(sample_tokens))

    result = load_token("openai", tokens_file=token_file)
    assert result == "abc123"


def test_load_token_missing_key(tmp_path, caplog):
    """
    Test that load_token returns None and logs an error when the requested
    key is not found in the token file.
    """
    token_file = tmp_path / "tokens.yml"
    token_file.write_text(yaml.safe_dump({"gemini": "xyz"}))

    result = load_token("openai", tokens_file=token_file)

    # Should return None for missing key
    assert result is None

    # Should log an error about missing key
    assert "Key 'openai' not found" in caplog.text


# ------------------------------
# LOAD DEFAULT CONFIG UNIT TESTS
# ------------------------------


def test_get_default_config_raises_if_missing(tmp_path):
    """
    Confirm that a FileNotFoundError is raised when neither a repo nor
    a home configuration file exists.
    """
    with (
        patch("git_cai_cli.core.config.find_git_root", return_value=None),
        patch("pathlib.Path.home", return_value=tmp_path),
    ):
        with pytest.raises(FileNotFoundError):
            get_default_config()


def test_get_default_config_raises_if_no_default_key(tmp_path):
    """
    Ensure that if a configuration file exists but does not contain the
    'default' key, a KeyError is raised.
    """
    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text("openai: {model: gpt-4}")

    with patch("git_cai_cli.core.config.find_git_root", return_value=tmp_path):
        with pytest.raises(KeyError):
            get_default_config()


def test_get_default_config_yaml_parse_error(tmp_path):
    """
    Validate that malformed YAML files properly trigger a ValueError,
    indicating a parsing issue that should not be silently ignored.
    """
    repo_config = tmp_path / "cai_config.yml"
    repo_config.write_text("default: [unclosed-list")

    with patch("git_cai_cli.core.config.find_git_root", return_value=tmp_path):
        with pytest.raises(ValueError):
            get_default_config()


# -------------------------------
# LOAD VALIDATE CONFIG UNIT TESTS
# -------------------------------


def test_validate_config_keys_warns_on_missing_keys(caplog):
    """
    Check that missing keys compared to the reference configuration
    are reported via a WARNING-level log entry.
    """
    caplog.set_level("WARNING")
    reference = {"a": 1, "b": 2}
    config = {"a": 1}
    _validate_config_keys(config, reference)
    assert "missing keys: b" in caplog.text


def test_validate_config_keys_raises_on_extra_keys():
    """
    Ensure that extra keys in the configuration compared to the reference
    raise a KeyError.
    """
    reference = {"a": 1}
    config = {"a": 1, "x": 99}

    with pytest.raises(KeyError) as exc:
        _validate_config_keys(config, reference)

    assert "Unknown config keys: x" in str(exc.value)


def test_validate_config_keys_no_warnings(caplog):
    """
    Validate that when config matches the expected reference set
    exactly, no log output or warnings are produced.
    """
    caplog.set_level("WARNING")
    reference = {"a": 1, "b": 2}
    config = {"a": 1, "b": 2}
    _validate_config_keys(config, reference)
    assert caplog.text == ""


# ---------------------------------
# LOAD VALIDATE LANGUAGE UNIT TESTS
# ---------------------------------


def test_validate_language_accepts_allowed(caplog):
    """
    Verify that a valid language code in the configuration is returned
    unchanged and does not produce any warnings.
    """
    config = {"language": "de"}
    result = _validate_language(config, {"en", "de", "fr"})
    assert result == "de"
    assert caplog.text == ""


def test_validate_language_falls_back_on_invalid(caplog):
    """
    Ensure that an unsupported or unknown language code triggers a
    warning and that the function falls back to 'en'.
    """
    caplog.set_level("WARNING")
    config = {"language": "xx"}
    result = _validate_language(config, {"en", "de", "fr"})
    assert result == "en"
    assert "not supported" in caplog.text


def test_validate_language_defaults_if_missing(caplog):
    """
    Confirm that when no language key is present in config, a warning
    is logged and 'en' is returned as the default language.
    """
    caplog.set_level("WARNING")
    config = {}
    result = _validate_language(config, {"en", "de", "fr"})
    assert result == "en"
    assert "not supported" in caplog.text
