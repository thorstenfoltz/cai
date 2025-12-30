"""
Unit tests for git_cai_cli.core.options.CliManager
"""
import logging
import subprocess
from unittest.mock import MagicMock, patch

import pytest
import requests
from importlib.metadata import PackageNotFoundError

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
