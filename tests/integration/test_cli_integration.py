"""
CLI integration test without real Git operations.

This test verifies that the CLI:
- passes argument parsing
- executes the main workflow
- generates a commit message
- attempts to commit via the Git abstraction

No real Git commands are executed.
"""

from pathlib import Path

from git_cai_cli.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_happy_path_without_real_git(monkeypatch) -> None:
    """
    The CLI executes the full main workflow and attempts
    to create a commit when staged changes exist.
    """
    monkeypatch.setattr(
        "git_cai_cli.core.gitutils.find_git_root",
        lambda: Path("/fake/repo"),
    )

    monkeypatch.setattr(
        "git_cai_cli.core.gitutils.git_diff_excluding",
        lambda _: "diff --git a/file b/file\n+change",
    )

    monkeypatch.setattr(
        "git_cai_cli.core.config.load_config",
        lambda: {"default": "dummy"},
    )

    monkeypatch.setattr(
        "git_cai_cli.core.config.load_token",
        lambda config: "DUMMY_TOKEN",
    )

    monkeypatch.setattr(
        "git_cai_cli.core.llm.CommitMessageGenerator.generate",
        lambda self, diff: "Generated commit message",
    )

    commit_called = {}

    def fake_commit(message: str) -> None:
        commit_called["message"] = message

    monkeypatch.setattr(
        "git_cai_cli.core.gitutils.commit_with_edit_template",
        fake_commit,
    )

    monkeypatch.setattr(
        "sys.argv",
        ["git-cai"],
    )

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert commit_called["message"] == "Generated commit message"
