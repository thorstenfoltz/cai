"""
Unit tests for provider override logic in git_cai_cli.core.config.
"""

import pytest
import typer
from git_cai_cli.core.config import KNOWN_PROVIDERS, apply_provider_overrides

# ------------------------------------------
# Tests for apply_provider_overrides
# ------------------------------------------


def test_provider_override_changes_default():
    """Verify provider override updates config['default']."""
    config = {
        "default": "groq",
        "groq": {"model": "llama-3.3-70b", "temperature": 0},
        "openai": {"model": "gpt-5.1", "temperature": 0},
    }
    apply_provider_overrides(config, provider_override="openai", model_override=None)
    assert config["default"] == "openai"


def test_model_override_changes_provider_model():
    """Verify model override updates the provider's model in config."""
    config = {
        "default": "groq",
        "groq": {"model": "llama-3.3-70b", "temperature": 0},
        "openai": {"model": "gpt-5.1", "temperature": 0},
    }
    apply_provider_overrides(
        config, provider_override="openai", model_override="gpt-4o"
    )
    assert config["default"] == "openai"
    assert config["openai"]["model"] == "gpt-4o"


def test_provider_override_uses_config_model():
    """Verify that when only provider is overridden, model comes from config."""
    config = {
        "default": "groq",
        "groq": {"model": "llama-3.3-70b", "temperature": 0},
        "openai": {"model": "gpt-5.1", "temperature": 0},
    }
    apply_provider_overrides(config, provider_override="openai", model_override=None)
    assert config["default"] == "openai"
    assert config["openai"]["model"] == "gpt-5.1"  # unchanged


def test_model_without_provider_fails():
    """Verify that --model without --provider exits with error."""
    config = {"default": "groq"}
    with pytest.raises(typer.Exit) as exc:
        apply_provider_overrides(
            config, provider_override=None, model_override="gpt-4o"
        )
    assert exc.value.exit_code == 1


def test_unknown_provider_fails_with_message(capsys):
    """Verify that an unknown provider exits with error listing available providers."""
    config = {"default": "groq"}
    with pytest.raises(typer.Exit) as exc:
        apply_provider_overrides(
            config, provider_override="foobar", model_override=None
        )
    captured = capsys.readouterr()
    assert "Unknown provider 'foobar'" in captured.err
    assert "anthropic" in captured.err
    assert "openai" in captured.err
    assert exc.value.exit_code == 1


def test_no_overrides_leaves_config_unchanged():
    """Verify that no overrides leaves config untouched."""
    config = {
        "default": "groq",
        "groq": {"model": "llama-3.3-70b", "temperature": 0},
    }
    original = config.copy()
    apply_provider_overrides(config, provider_override=None, model_override=None)
    assert config == original


def test_provider_override_creates_block_for_missing_provider():
    """Verify override creates a provider block if it doesn't exist in config."""
    config = {
        "default": "groq",
        "groq": {"model": "llama-3.3-70b", "temperature": 0},
        # No "openai" block
    }
    apply_provider_overrides(
        config, provider_override="openai", model_override="gpt-4o"
    )
    assert config["default"] == "openai"
    assert config["openai"]["model"] == "gpt-4o"
    assert config["openai"]["temperature"] == 0


def test_known_providers_set_is_complete():
    """Verify KNOWN_PROVIDERS contains all expected providers."""
    expected = {
        "openai",
        "gemini",
        "anthropic",
        "groq",
        "xai",
        "mistral",
        "deepseek",
        "ollama",
    }
    assert KNOWN_PROVIDERS == expected
