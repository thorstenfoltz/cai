"""
Unit tests for the git-cai CLI routing and flag semantics.

These tests validate only CLI-owned behavior:
- flag validation
- dispatch logic
- guardrails
"""

import sys
from pathlib import Path

import pytest
from git_cai_cli.cli import app
from typer.testing import CliRunner

pytestmark = pytest.mark.filterwarnings(
    "ignore:The 'is_flag' and 'flag_value' parameters are not supported by Typer:DeprecationWarning"
)

runner = CliRunner()


@pytest.fixture
def git_cai_invocation(monkeypatch) -> None:
    """
    Ensure the CLI appears to be invoked as `git cai`.
    """
    monkeypatch.setattr(sys, "argv", ["git-cai"])


def test_help_exits_cleanly(git_cai_invocation) -> None:
    """
    --help exits successfully and prints help text.
    """
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Git CAI" in result.stdout


def test_help_with_debug_fails(git_cai_invocation) -> None:
    """
    --help cannot be combined with --debug.
    """
    result = runner.invoke(app, ["--help", "--debug"])
    assert result.exit_code == 1


def test_version_exits_cleanly(git_cai_invocation, monkeypatch) -> None:
    """
    --version exits successfully and prints the version.
    """
    monkeypatch.setattr("git_cai_cli._version.__version__", "9.9.9", raising=False)

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "9.9.9" in result.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["--list", "--update"],
        ["--list", "--squash"],
        ["--update", "--squash"],
    ],
)
def test_mutually_exclusive_modes_fail(git_cai_invocation, args) -> None:
    """
    Only one execution mode may be selected.
    """
    result = runner.invoke(app, args)
    assert result.exit_code == 1


def test_all_with_other_modes_fails(git_cai_invocation) -> None:
    """
    --all cannot be combined with other execution modes.
    """
    result = runner.invoke(app, ["--all", "--list"])
    assert result.exit_code == 1


def test_must_be_invoked_as_git_cai(monkeypatch) -> None:
    """
    The command must be invoked via `git cai`.
    """
    monkeypatch.setattr(sys, "argv", ["cai"])

    result = runner.invoke(app, [])
    assert result.exit_code == 1


def test_list_dispatches(git_cai_invocation, monkeypatch) -> None:
    """
    --list dispatches to CliManager.list().
    """
    monkeypatch.setattr(
        "git_cai_cli.core.options.CliManager.list",
        lambda self: "LIST OUTPUT",
    )

    result = runner.invoke(app, ["--list"])
    assert result.exit_code == 0
    assert "LIST OUTPUT" in result.stdout


def test_squash_dispatches(git_cai_invocation, monkeypatch) -> None:
    """
    --squash dispatches to CliManager.squash_branch().
    """
    called = {"ok": False}

    def fake_squash(self) -> None:
        called["ok"] = True

    monkeypatch.setattr(
        "git_cai_cli.core.options.CliManager.squash_branch",
        fake_squash,
    )

    result = runner.invoke(app, ["--squash"])
    assert result.exit_code == 0
    assert called["ok"] is True


def test_update_dispatches(git_cai_invocation, monkeypatch) -> None:
    """
    --update dispatches to CliManager.check_and_update().
    """
    called = {"ok": False}

    def fake_update(self) -> None:
        called["ok"] = True

    monkeypatch.setattr(
        "git_cai_cli.core.options.CliManager.check_and_update",
        fake_update,
    )

    result = runner.invoke(app, ["--update"])
    assert result.exit_code == 0
    assert called["ok"] is True


def test_exits_when_not_in_git_repo(git_cai_invocation, monkeypatch, caplog) -> None:
    """
    Execution fails when not inside a Git repository.
    """
    monkeypatch.setattr(
        "git_cai_cli.core.gitutils.find_git_root",
        lambda: None,
    )

    result = runner.invoke(app, [])
    assert result.exit_code == 1
    assert "Not inside a Git repository" in caplog.text


def test_exits_when_no_staged_diff(git_cai_invocation, monkeypatch, caplog) -> None:
    """
    Execution exits cleanly when no staged changes exist.
    """
    monkeypatch.setattr(
        "git_cai_cli.core.gitutils.find_git_root",
        lambda: Path("/repo"),
    )
    monkeypatch.setattr(
        "git_cai_cli.core.gitutils.git_diff_excluding",
        lambda _: "",
    )
    monkeypatch.setattr(
        "git_cai_cli.core.config.load_config",
        lambda: {"default": "openai"},
    )
    monkeypatch.setattr(
        "git_cai_cli.core.config.load_token",
        lambda config: "TOKEN",
    )

    with caplog.at_level("INFO"):
        result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "No changes to commit" in caplog.text
