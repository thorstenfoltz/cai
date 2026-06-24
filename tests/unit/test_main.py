"""
Unit tests for provider override logic in git_cai_cli.core.config.
"""

from unittest.mock import patch

import pytest
import typer
from git_cai_cli.core.config import KNOWN_PROVIDERS, apply_provider_overrides
from git_cai_cli.core.secrets import Finding
from git_cai_cli.main import _relpaths_from_repo, _route_false_alarm

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


def test_relpaths_from_repo_strips_absolute_prefix(tmp_path):
    """Absolute paths inside the repo are rewritten to repo-relative form."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("x", encoding="utf-8")

    rels = _relpaths_from_repo(tmp_path, [str(tmp_path / "src" / "foo.py")])
    assert rels == ["src/foo.py"]


def test_relpaths_from_repo_leaves_relative_paths_untouched(tmp_path):
    rels = _relpaths_from_repo(tmp_path, ["src/foo.py", "bar.txt"])
    assert rels == ["src/foo.py", "bar.txt"]


def test_relpaths_from_repo_keeps_paths_outside_repo(tmp_path):
    """Absolute paths outside the repo are left as-is rather than erroring."""
    outside = tmp_path.parent / "other" / "thing.py"
    rels = _relpaths_from_repo(tmp_path, [str(outside)])
    assert rels == [str(outside)]


# ------------------------------------------
# Tests for _route_false_alarm
# ------------------------------------------


def _finding(path):
    return Finding("AWS access key", path, 1, "AK…VD")


def test_route_false_alarm_config_choice(tmp_path):
    with (
        patch("typer.prompt", return_value="2"),
        patch("git_cai_cli.core.config.add_to_secret_scan_exclude") as add_cfg,
        patch("git_cai_cli.core.gitutils.append_to_caiignore") as add_ign,
    ):
        _route_false_alarm([_finding("tests/f.py")], tmp_path)

    add_cfg.assert_called_once_with("tests/f.py")
    add_ign.assert_not_called()


def test_route_false_alarm_caiignore_choice(tmp_path):
    with (
        patch("typer.prompt", return_value="1"),
        patch("git_cai_cli.core.config.add_to_secret_scan_exclude") as add_cfg,
        patch("git_cai_cli.core.gitutils.append_to_caiignore") as add_ign,
    ):
        _route_false_alarm([_finding("tests/f.py")], tmp_path)

    add_ign.assert_called_once_with(tmp_path, "tests/f.py")
    add_cfg.assert_not_called()


def test_route_false_alarm_skip_choice_records_nothing(tmp_path):
    with (
        patch("typer.prompt", return_value="3"),
        patch("git_cai_cli.core.config.add_to_secret_scan_exclude") as add_cfg,
        patch("git_cai_cli.core.gitutils.append_to_caiignore") as add_ign,
    ):
        _route_false_alarm([_finding("tests/f.py")], tmp_path)

    add_cfg.assert_not_called()
    add_ign.assert_not_called()


def test_route_false_alarm_skips_pathless_findings(tmp_path):
    with (
        patch("typer.prompt") as prompt,
        patch("git_cai_cli.core.config.add_to_secret_scan_exclude") as add_cfg,
        patch("git_cai_cli.core.gitutils.append_to_caiignore") as add_ign,
    ):
        _route_false_alarm([_finding(None)], tmp_path)

    prompt.assert_not_called()
    add_cfg.assert_not_called()
    add_ign.assert_not_called()


def test_route_false_alarm_prompts_once_per_distinct_path(tmp_path):
    findings = [_finding("tests/f.py"), _finding("tests/f.py")]
    with (
        patch("typer.prompt", return_value="2") as prompt,
        patch("git_cai_cli.core.config.add_to_secret_scan_exclude") as add_cfg,
        patch("git_cai_cli.core.gitutils.append_to_caiignore"),
    ):
        _route_false_alarm(findings, tmp_path)

    assert prompt.call_count == 1
    add_cfg.assert_called_once_with("tests/f.py")


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
