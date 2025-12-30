"""
Unit tests for git_cai_cli.core.squash.squash_branch function.
"""

import builtins
import typing
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from git_cai_cli.core.squash import squash_branch


@pytest.fixture
def mock_repo_root() -> Path:
    """
    Fixture that simulates a Git repository root path.
    """
    return Path("/fake/repo")


@pytest.fixture
def mock_generator() -> MagicMock:
    """
    Fixture that simulates a commit message generator.
    """
    gen = MagicMock()
    gen.generate.return_value = "commit message"
    gen.summarize_commit_history.return_value = "squash summary"
    return gen


@pytest.fixture
def clean_git_state() -> typing.Callable:
    """
    Simulates a clean working tree and a multi-commit branch.
    """

    def _side_effect(cmd, text=True) -> str:
        """
        Simulates subprocess.check_output side effects for a clean Git state.
        """
        if cmd[:3] == ["git", "diff", "--cached"]:
            return ""
        if cmd[:2] == ["git", "diff"]:
            return ""
        if cmd[:2] == ["git", "--no-pager"] and "log" in cmd:
            return "commit 1\ncommit 2"
        if "merge-base" in cmd:
            return "BASE"
        if "symbolic-ref" in cmd:
            return "refs/remotes/origin/main"
        raise AssertionError(f"Unexpected git command: {cmd}")

    return _side_effect


def test_aborts_if_not_in_git_repo(caplog) -> None:
    """
    Test that squash_branch logs an error if not in a Git repository.
    """
    with patch("git_cai_cli.core.squash.find_git_root", return_value=None):
        squash_branch()

    assert "Not inside a Git repository" in caplog.text


def test_aborts_on_unstaged_changes(mock_repo_root) -> None:
    """
    Test that squash_branch aborts if there are unstaged changes.
    """
    with (
        patch("git_cai_cli.core.squash.find_git_root", return_value=mock_repo_root),
        patch(
            "subprocess.check_output",
            side_effect=[
                "",  # staged
                "file.py",  # unstaged
            ],
        ),
    ):
        squash_branch()


def test_commits_staged_changes_first(mock_repo_root, mock_generator) -> None:
    """
    Test that squash_branch commits staged changes before squashing.
    """

    def git_side_effect(cmd, text=True, **kwargs) -> str:
        """
        Simulates subprocess.check_output side effects for staged changes.
        """
        if cmd[:3] == ["git", "diff", "--cached"]:
            return "file.py"
        if cmd[:2] == ["git", "diff"]:
            return ""
        if cmd[:2] == ["git", "--no-pager"] and "log" in cmd:
            return "commit 1\ncommit 2"
        if "merge-base" in cmd:
            return "BASE"
        if "symbolic-ref" in cmd:
            return "refs/remotes/origin/main"
        raise AssertionError(f"Unexpected git command: {cmd}")

    with (
        patch("git_cai_cli.core.squash.find_git_root", return_value=mock_repo_root),
        patch("git_cai_cli.core.squash.git_diff_excluding", return_value="diff"),
        patch("subprocess.check_output", side_effect=git_side_effect),
        patch(
            "git_cai_cli.core.squash.commit_with_edit_template", return_value=0
        ) as commit,
        patch(
            "git_cai_cli.core.squash.load_config", return_value={"default": "openai"}
        ),
        patch("git_cai_cli.core.squash.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.squash.CommitMessageGenerator",
            return_value=mock_generator,
        ),
        patch("git_cai_cli.core.squash.get_git_editor", return_value="true"),
        patch("git_cai_cli.core.squash.sha256_of_file", side_effect=["a", "b"]),
        patch("git_cai_cli.core.squash._has_upstream", return_value=False),
        patch("subprocess.run", return_value=MagicMock(returncode=0)),
    ):
        squash_branch()

    commit.assert_called_once()


def test_cancels_if_editor_exits_nonzero(
    mock_repo_root, clean_git_state, mock_generator
) -> None:
    """
    Test that squash_branch cancels if the git editor exits with non-zero.
    """
    with (
        patch("git_cai_cli.core.squash.find_git_root", return_value=mock_repo_root),
        patch("subprocess.check_output", side_effect=clean_git_state),
        patch(
            "git_cai_cli.core.squash.load_config", return_value={"default": "openai"}
        ),
        patch("git_cai_cli.core.squash.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.squash.CommitMessageGenerator",
            return_value=mock_generator,
        ),
        patch("git_cai_cli.core.squash.get_git_editor", return_value="false"),
        patch("git_cai_cli.core.squash.sha256_of_file", return_value="hash"),
        patch("subprocess.run", return_value=MagicMock(returncode=1)),
    ):
        squash_branch()


def test_performs_soft_reset_and_commit(
    mock_repo_root, clean_git_state, mock_generator
) -> None:
    """
    Test that squash_branch performs a soft reset and creates the squash commit.
    """
    run_mock = MagicMock(return_value=MagicMock(returncode=0))

    with (
        patch("git_cai_cli.core.squash.find_git_root", return_value=mock_repo_root),
        patch("subprocess.check_output", side_effect=clean_git_state),
        patch(
            "git_cai_cli.core.squash.load_config", return_value={"default": "openai"}
        ),
        patch("git_cai_cli.core.squash.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.squash.CommitMessageGenerator",
            return_value=mock_generator,
        ),
        patch("git_cai_cli.core.squash.get_git_editor", return_value="true"),
        patch("git_cai_cli.core.squash.sha256_of_file", side_effect=["a", "b"]),
        patch("subprocess.run", run_mock),
        patch("git_cai_cli.core.squash._has_upstream", return_value=False),
    ):
        squash_branch()

    run_mock.assert_has_calls(
        [
            call(["git", "reset", "--soft", "BASE"], check=True),
            call(["git", "commit", "-m", "squash summary"], check=True),
        ],
        any_order=False,
    )


def test_force_push_prompt_and_execution(
    mock_repo_root, clean_git_state, mock_generator
) -> None:
    """
    Test that squash_branch prompts for and performs force push when upstream exists.
    """
    run_mock = MagicMock(return_value=MagicMock(returncode=0))

    with (
        patch("git_cai_cli.core.squash.find_git_root", return_value=mock_repo_root),
        patch("subprocess.check_output", side_effect=clean_git_state),
        patch(
            "git_cai_cli.core.squash.load_config", return_value={"default": "openai"}
        ),
        patch("git_cai_cli.core.squash.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.squash.CommitMessageGenerator",
            return_value=mock_generator,
        ),
        patch("git_cai_cli.core.squash.get_git_editor", return_value="true"),
        patch("git_cai_cli.core.squash.sha256_of_file", side_effect=["a", "b"]),
        patch("subprocess.run", run_mock),
        patch("git_cai_cli.core.squash._has_upstream", return_value=True),
        patch.object(builtins, "input", return_value="yes"),
    ):
        squash_branch()

    run_mock.assert_any_call(["git", "push", "--force-with-lease"], check=True)
