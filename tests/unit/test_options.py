"""
Unit tests for git_cai_cli.core.options.CliManager
"""

import logging
import subprocess
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

import pytest
import requests
from git_cai_cli.core.options import CliManager


@pytest.mark.parametrize(
    "input_version, expected",
    [
        ("0.1.2", (0, 1, 2)),
        ("0.1.2.dev8", (0, 1, 2)),
        ("1.4", (1, 4, 0)),
        ("2", (0, 0, 0)),
        ("invalid", (0, 0, 0)),
    ],
)
def test_extract_numeric_version(input_version, expected) -> None:
    """
    Test extraction of numeric version from version string.
    """
    manager = CliManager()
    assert manager._extract_numeric_version(input_version) == expected


def test_check_and_update_package_not_installed(caplog):
    manager = CliManager()

    with patch(
        "git_cai_cli.core.options.version",
        side_effect=PackageNotFoundError,
    ):
        with caplog.at_level(logging.ERROR):
            manager.check_and_update()

    assert "Package" in caplog.text


def test_check_and_update_request_failure(caplog) -> None:
    """
    Test handling of request failure during update check.
    """
    manager = CliManager()

    with (
        patch("git_cai_cli.core.options.version", return_value="0.1.0"),
        patch(
            "git_cai_cli.core.options.requests.get",
            side_effect=requests.RequestException("boom"),
        ),
        caplog.at_level(logging.ERROR),
    ):
        manager.check_and_update()

    assert "Could not fetch version info" in caplog.text


def test_check_and_update_already_up_to_date(capsys) -> None:
    """
    Test behavior when the package is already up to date.
    """
    manager = CliManager()

    response = MagicMock()
    response.json.return_value = {"info": {"version": "1.0.0"}}

    with (
        patch("git_cai_cli.core.options.version", return_value="1.0.0"),
        patch("git_cai_cli.core.options.requests.get", return_value=response),
    ):
        manager.check_and_update()

    out = capsys.readouterr().out
    assert "Already up to date" in out


def test_check_and_update_user_declines(capsys) -> None:
    """
    Test behavior when the user declines the update.
    """
    manager = CliManager()

    response = MagicMock()
    response.json.return_value = {"info": {"version": "2.0.0"}}

    with (
        patch("git_cai_cli.core.options.version", return_value="1.0.0"),
        patch("git_cai_cli.core.options.requests.get", return_value=response),
        patch("builtins.input", return_value="no"),
    ):
        manager.check_and_update()

    out = capsys.readouterr().out
    assert "Update cancelled" in out


def test_check_and_update_auto_confirm_success(capsys) -> None:
    """
    Test successful update with auto_confirm=True.
    """
    manager = CliManager()

    response = MagicMock()
    response.json.return_value = {"info": {"version": "2.0.0"}}

    completed = subprocess.CompletedProcess(
        args=["pipx"], returncode=0, stdout="", stderr=""
    )

    with (
        patch("git_cai_cli.core.options.version", return_value="1.0.0"),
        patch("git_cai_cli.core.options.requests.get", return_value=response),
        patch("subprocess.run", return_value=completed),
    ):
        manager.check_and_update(auto_confirm=True)

    out = capsys.readouterr().out
    assert "Successfully updated" in out


def test_check_and_update_upgrade_failure(capsys) -> None:
    """
    Test behavior when the update upgrade fails.
    """
    manager = CliManager()

    response = MagicMock()
    response.json.return_value = {"info": {"version": "2.0.0"}}

    completed = subprocess.CompletedProcess(
        args=["pipx"], returncode=1, stdout="", stderr="fail"
    )

    with (
        patch("git_cai_cli.core.options.version", return_value="1.0.0"),
        patch("git_cai_cli.core.options.requests.get", return_value=response),
        patch("subprocess.run", return_value=completed),
    ):
        manager.check_and_update(auto_confirm=True)

    out = capsys.readouterr().out
    assert "Update failed" in out


def test_enable_debug_sets_log_levels() -> None:
    """
    Test that enable_debug sets logging level to DEBUG.
    """
    manager = CliManager()

    manager.enable_debug()

    assert logging.getLogger().level == logging.DEBUG


def test_list_output_contains_expected_text() -> None:
    """
    Test that list() method returns expected text.
    """
    manager = CliManager()
    text = manager.list()
    assert "Available list options" in text


def test_print_available_languages_sorted() -> None:
    """
    Test that print_available_languages() returns languages sorted by name.
    """
    manager = CliManager(
        allowed_languages={
            "de": "German",
            "en": "English",
        }
    )

    output = manager.print_available_languages()
    assert "English → en" in output
    assert "German → de" in output


def test_styles_returns_expected_keys() -> None:
    """
    Test that styles() method returns expected keys.
    """
    manager = CliManager()
    styles = manager.styles()

    assert "professional" in styles
    assert "description" in styles["professional"]


def test_squash_branch_delegates() -> None:
    """
    Test that squash_branch() delegates to the squash_branch function.
    """
    manager = CliManager()

    with patch("git_cai_cli.core.options.squash_branch") as mock_squash:
        manager.squash_branch()

    mock_squash.assert_called_once()


def test_stage_tracked_files_success() -> None:
    """
    Test that stage_tracked_files() succeeds when git command succeeds.
    """
    manager = CliManager()

    completed = subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout="", stderr=""
    )

    with patch("subprocess.run", return_value=completed):
        manager.stage_tracked_files()


def test_stage_tracked_files_git_failure() -> None:
    """
    Test that stage_tracked_files() raises RuntimeError when git command fails.
    """
    manager = CliManager()

    completed = subprocess.CompletedProcess(
        args=["git"], returncode=1, stdout="", stderr="error"
    )

    with patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError):
            manager.stage_tracked_files()


def test_list_output_contains_all_options() -> None:
    """
    Test that list() method includes all available list options.
    """
    manager = CliManager()
    text = manager.list()
    for option in (
        "config",
        "editor",
        "language",
        "model",
        "path",
        "provider",
        "style",
    ):
        assert option in text


def test_list_providers_contains_all_providers() -> None:
    """
    Test that list_providers() returns all known providers.
    """
    manager = CliManager()
    output = manager.list_providers()
    for provider in (
        "anthropic",
        "deepseek",
        "gemini",
        "groq",
        "mistral",
        "ollama",
        "openai",
        "xai",
    ):
        assert provider in output


def test_list_providers_shows_token_requirement() -> None:
    """
    Test that list_providers() distinguishes token/tokenless providers.
    """
    manager = CliManager()
    output = manager.list_providers()
    assert "no token required" in output  # ollama
    assert "token required" in output  # all others


def test_list_providers_shows_default_models() -> None:
    """
    Test that list_providers() includes default model names.
    """
    manager = CliManager()
    output = manager.list_providers()
    assert "llama3.1" in output  # ollama default model


def test_list_models_contains_all_providers() -> None:
    """
    Test that list_models() returns a model for each provider.
    """
    manager = CliManager()
    output = manager.list_models()
    for provider in (
        "anthropic",
        "deepseek",
        "gemini",
        "groq",
        "mistral",
        "ollama",
        "openai",
        "xai",
    ):
        assert provider in output


def test_list_models_shows_arrow_format() -> None:
    """
    Test that list_models() uses the expected arrow format.
    """
    manager = CliManager()
    output = manager.list_models()
    assert "→" in output


def test_list_config_returns_active_config() -> None:
    """
    Test that list_config() returns formatted configuration.
    """
    manager = CliManager()
    with patch(
        "git_cai_cli.core.options.load_config",
        return_value={
            "default": "groq",
            "language": "en",
            "style": "professional",
            "groq": {"model": "test-model", "temperature": 0},
        },
    ):
        output = manager.list_config()
    assert "Active configuration" in output
    assert "default: groq" in output
    assert "language: en" in output
    assert "model: test-model" in output


def test_list_config_handles_error() -> None:
    """
    Test that list_config() handles config loading errors gracefully.
    """
    manager = CliManager()
    with patch(
        "git_cai_cli.core.options.load_config", side_effect=ValueError("bad config")
    ):
        output = manager.list_config()
    assert "Error loading configuration" in output


def test_list_paths_without_repo_config() -> None:
    """
    Test that list_paths() shows paths when no repo config exists.
    """
    manager = CliManager()
    with patch("git_cai_cli.core.options._find_repo_config", return_value=None):
        output = manager.list_paths()
    assert "Configuration file paths" in output
    assert "Home config:" in output
    assert "Tokens file:" in output
    assert "not found" in output
    assert "Active config source:" in output
    assert "home" in output


def test_list_paths_with_repo_config(tmp_path) -> None:
    """
    Test that list_paths() shows repo config when it exists.
    """
    manager = CliManager()
    fake_repo_config = tmp_path / "cai_config.yml"
    with patch(
        "git_cai_cli.core.options._find_repo_config", return_value=fake_repo_config
    ):
        output = manager.list_paths()
    assert str(fake_repo_config) in output
    assert "(active)" in output
    assert "repository" in output


def test_generate_prompts_here_creates_files(tmp_path, monkeypatch):
    manager = CliManager()
    monkeypatch.chdir(tmp_path)

    manager.generate_prompts_here()

    assert (tmp_path / "commit_prompt.md").is_file()
    assert (tmp_path / "squash_prompt.md").is_file()
    assert (tmp_path / "full_files_prompt.md").is_file()


# ---------------------------------------------------------------------------
# handle_list dispatcher
# ---------------------------------------------------------------------------


def test_handle_list_none_prints_overview(capsys):
    manager = CliManager()
    manager.handle_list(None)
    out = capsys.readouterr().out
    assert "Available list options:" in out


def test_handle_list_editor(capsys):
    manager = CliManager()
    manager.handle_list("editor")
    out = capsys.readouterr().out
    assert "Vim" in out


def test_handle_list_language(capsys):
    manager = CliManager()
    manager.handle_list("language")
    out = capsys.readouterr().out
    assert "Available languages:" in out


def test_handle_list_model(capsys):
    manager = CliManager()
    manager.handle_list("model")
    out = capsys.readouterr().out
    assert "Default models:" in out


def test_handle_list_provider(capsys):
    manager = CliManager()
    manager.handle_list("provider")
    out = capsys.readouterr().out
    assert "Supported providers:" in out


def test_handle_list_style(capsys):
    manager = CliManager()
    manager.handle_list("style")
    out = capsys.readouterr().out
    assert "Professional" in out
    assert "Example:" in out


def test_handle_list_path(capsys, monkeypatch):
    monkeypatch.setattr("git_cai_cli.core.options._find_repo_config", lambda: None)
    manager = CliManager()
    manager.handle_list("path")
    out = capsys.readouterr().out
    assert "Configuration file paths:" in out


def test_handle_list_config(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "git_cai_cli.core.options.load_config",
        lambda: {"default": "openai", "language": "en"},
    )
    manager = CliManager()
    manager.handle_list("config")
    out = capsys.readouterr().out
    assert "Active configuration:" in out
    assert "default: openai" in out


def test_handle_list_uppercase_is_accepted(capsys):
    manager = CliManager()
    manager.handle_list("EDITOR")
    out = capsys.readouterr().out
    assert "Vim" in out


def test_handle_list_unknown_raises_and_writes_stderr(capsys):
    import typer as typer_module

    manager = CliManager()
    with pytest.raises(typer_module.Exit) as exc:
        manager.handle_list("nonsense")
    assert exc.value.exit_code == 1
    err = capsys.readouterr().err
    assert "unknown list option 'nonsense'" in err
