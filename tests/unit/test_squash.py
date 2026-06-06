"""
Unit tests for git_cai_cli.core.squash.squash_branch function.
"""

import builtins
import subprocess
import typing
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from git_cai_cli.core.squash import (
    _count_commits_on_branch,
    _count_total_commits,
    _resolve_squash_target,
    squash_branch,
)


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
        if cmd[:3] == ["git", "rev-parse", "--is-shallow-repository"]:
            return "false"
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
                "false",  # is-shallow-repository
                "",  # staged
                "file.py",  # unstaged
            ],
        ),
        patch(
            "git_cai_cli.core.squash.load_config", return_value={"default": "openai"}
        ),
        patch("git_cai_cli.core.squash.load_token", return_value="token"),
    ):
        squash_branch()


def test_squash_classifies_auth_error(mock_repo_root, clean_git_state, caplog) -> None:
    """A 401 from the provider during history summarization must surface as a
    friendly message + clean exit, not an uncaught requests.HTTPError."""
    import requests

    resp = MagicMock()
    resp.status_code = 401
    resp.json.return_value = {"error": {"message": "bad key"}}

    gen = MagicMock()
    gen.summarize_commit_history.side_effect = requests.HTTPError(response=resp)

    with (
        patch("git_cai_cli.core.squash.find_git_root", return_value=mock_repo_root),
        patch("subprocess.check_output", side_effect=clean_git_state),
        patch(
            "git_cai_cli.core.squash.load_config", return_value={"default": "openai"}
        ),
        patch("git_cai_cli.core.squash.load_token", return_value="token"),
        patch("git_cai_cli.core.squash.CommitMessageGenerator", return_value=gen),
        pytest.raises(SystemExit),
    ):
        squash_branch()

    assert "invalid or not authorized" in caplog.text


def test_commits_staged_changes_first(mock_repo_root, mock_generator) -> None:
    """
    Test that squash_branch commits staged changes before squashing.
    """

    def git_side_effect(cmd, text=True, **kwargs) -> str:
        """
        Simulates subprocess.check_output side effects for staged changes.
        """
        if cmd[:3] == ["git", "rev-parse", "--is-shallow-repository"]:
            return "false"
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


# --- Tests for new squash argument helpers ---


def test_count_commits_on_branch() -> None:
    with patch("subprocess.check_output", return_value="5\n"):
        assert _count_commits_on_branch("BASE") == 5


def test_count_total_commits() -> None:
    with patch("subprocess.check_output", return_value="42\n"):
        assert _count_total_commits() == 42


def test_resolve_squash_target_with_number() -> None:
    """Squash last N commits resolves to HEAD~N."""
    with (
        patch("git_cai_cli.core.squash._count_total_commits", return_value=10),
        patch("git_cai_cli.core.squash._get_branch_base", return_value="BASE"),
        patch("git_cai_cli.core.squash._count_commits_on_branch", return_value=8),
        patch("subprocess.check_output", return_value="abc123\n"),
    ):
        result = _resolve_squash_target("3")
    assert result == "abc123"


def test_resolve_squash_target_number_exceeds_total(caplog) -> None:
    """Error when count exceeds total commits in repo."""
    with (
        patch("git_cai_cli.core.squash._count_total_commits", return_value=5),
        pytest.raises(SystemExit),
    ):
        _resolve_squash_target("10")


def test_resolve_squash_target_number_exceeds_branch_warns() -> None:
    """Warning when count exceeds branch commits, user declines."""
    with (
        patch("git_cai_cli.core.squash._count_total_commits", return_value=20),
        patch("git_cai_cli.core.squash._get_branch_base", return_value="BASE"),
        patch("git_cai_cli.core.squash._count_commits_on_branch", return_value=3),
        patch.object(builtins, "input", return_value="no"),
        pytest.raises(SystemExit),
    ):
        _resolve_squash_target("5")


def test_resolve_squash_target_number_exceeds_branch_continues() -> None:
    """Warning when count exceeds branch commits, user confirms."""
    with (
        patch("git_cai_cli.core.squash._count_total_commits", return_value=20),
        patch("git_cai_cli.core.squash._get_branch_base", return_value="BASE"),
        patch("git_cai_cli.core.squash._count_commits_on_branch", return_value=3),
        patch.object(builtins, "input", return_value="yes"),
        patch("subprocess.check_output", return_value="def456\n"),
    ):
        result = _resolve_squash_target("5")
    assert result == "def456"


def test_resolve_squash_target_with_valid_hash() -> None:
    """Commit hash resolves to its parent."""
    with (
        patch(
            "subprocess.check_output",
            side_effect=["full_hash\n", "parent_hash\n"],
        ),
        patch(
            "subprocess.run",
            return_value=MagicMock(returncode=0),
        ),
    ):
        result = _resolve_squash_target("abc123")
    assert result == "parent_hash"


def test_resolve_squash_target_with_invalid_hash() -> None:
    """Error on invalid commit reference."""
    with (
        patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ),
        pytest.raises(SystemExit),
    ):
        _resolve_squash_target("nonexistent")


def test_resolve_squash_target_hash_not_in_branch() -> None:
    """Error when commit exists but is not in current branch."""
    with (
        patch("subprocess.check_output", return_value="full_hash\n"),
        patch(
            "subprocess.run",
            return_value=MagicMock(returncode=1),
        ),
        pytest.raises(SystemExit),
    ):
        _resolve_squash_target("abc123")


def test_resolve_squash_target_zero_count() -> None:
    """Error on zero as commit count."""
    with pytest.raises(SystemExit):
        _resolve_squash_target("0")


def test_resolve_squash_target_negative_count() -> None:
    """Error on negative commit count."""
    with pytest.raises(SystemExit):
        _resolve_squash_target("-3")


def test_squash_branch_with_squash_arg(mock_repo_root, mock_generator) -> None:
    """Test that squash_branch uses _resolve_squash_target when squash_arg is provided."""
    run_mock = MagicMock(return_value=MagicMock(returncode=0))

    def git_side_effect(cmd, text=True, **kwargs) -> str:
        if cmd[:3] == ["git", "rev-parse", "--is-shallow-repository"]:
            return "false"
        if cmd[:3] == ["git", "diff", "--cached"]:
            return ""
        if cmd[:2] == ["git", "diff"]:
            return ""
        if cmd[:2] == ["git", "--no-pager"] and "log" in cmd:
            return "commit 1\ncommit 2"
        raise AssertionError(f"Unexpected git command: {cmd}")

    with (
        patch("git_cai_cli.core.squash.find_git_root", return_value=mock_repo_root),
        patch("subprocess.check_output", side_effect=git_side_effect),
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
        patch("git_cai_cli.core.squash._has_commits", return_value=True),
        patch(
            "git_cai_cli.core.squash._resolve_squash_target",
            return_value="TARGET_HASH",
        ) as resolve_mock,
    ):
        squash_branch(squash_arg="3")

    resolve_mock.assert_called_once_with("3")
    run_mock.assert_has_calls(
        [
            call(["git", "reset", "--soft", "TARGET_HASH"], check=True),
            call(["git", "commit", "-m", "squash summary"], check=True),
        ],
        any_order=False,
    )


def test_squash_branch_passes_context_to_generator(
    mock_generator, mock_repo_root, clean_git_state
):
    """squash_branch() with context passes it to summarize_commit_history()."""

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
        patch("subprocess.run", return_value=MagicMock(returncode=0)),
        patch("git_cai_cli.core.squash._has_upstream", return_value=False),
        patch("git_cai_cli.core.squash._has_commits", return_value=True),
    ):
        squash_branch(context="Closes #42")

    call_args = mock_generator.summarize_commit_history.call_args
    assert call_args[1].get("context") == "Closes #42"


# ---------------------------------------------------------------------------
# Editor launch must use argv form (no shell=True) — F0.2 security fix
# ---------------------------------------------------------------------------


def test_editor_launch_uses_argv_never_shell(
    mock_repo_root, clean_git_state, mock_generator
) -> None:
    """
    The editor must always be launched via argv list. Using shell=True is a
    code-injection vector if GIT_EDITOR carries shell metacharacters.
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

    for kwargs in (c.kwargs for c in run_mock.call_args_list):
        assert (
            kwargs.get("shell", False) is False
        ), "subprocess.run was invoked with shell=True — security regression"

    editor_calls = [
        c
        for c in run_mock.call_args_list
        if c.args and isinstance(c.args[0], list) and c.args[0][0] == "true"
    ]
    assert editor_calls, "expected an argv-form call for the editor invocation"


def test_editor_with_shell_metacharacters_is_not_expanded(
    mock_repo_root, clean_git_state, mock_generator, tmp_path
) -> None:
    """
    A malicious GIT_EDITOR like 'true; rm -rf /' must be parsed by shlex
    and either rejected (executable 'true; rm -rf /' isn't on PATH) or
    passed as a single argv[0] — never expanded by a shell.
    """
    canary = tmp_path / "should-not-exist.txt"
    malicious = f"true; touch {canary}"

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
        patch("git_cai_cli.core.squash.get_git_editor", return_value=malicious),
        patch("git_cai_cli.core.squash.sha256_of_file", side_effect=["a", "b"]),
        patch("subprocess.run", run_mock),
        patch("git_cai_cli.core.squash._has_upstream", return_value=False),
    ):
        squash_branch()

    for kwargs in (c.kwargs for c in run_mock.call_args_list):
        assert kwargs.get("shell", False) is False
    assert (
        not canary.exists()
    ), "shell metacharacters in GIT_EDITOR were expanded — injection vector"


def test_editor_not_on_path_aborts_cleanly(
    mock_repo_root, clean_git_state, mock_generator, caplog
) -> None:
    """
    If the editor binary isn't on PATH, the squash flow logs a clear error
    and returns — no fallback to shell=True.
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
        patch(
            "git_cai_cli.core.squash.get_git_editor",
            return_value="/nonexistent/editor-xyz",
        ),
        patch("git_cai_cli.core.squash.sha256_of_file", return_value="hash"),
        patch("subprocess.run", run_mock),
        patch("git_cai_cli.core.squash._has_upstream", return_value=False),
    ):
        squash_branch()

    assert "not found in PATH" in caplog.text
    for kwargs in (c.kwargs for c in run_mock.call_args_list):
        assert kwargs.get("shell", False) is False


# ---------------------------------------------------------------------------
# F1.2 — shallow-clone preflight
# ---------------------------------------------------------------------------


def test_shallow_clone_aborts_with_clear_message(mock_repo_root, caplog) -> None:
    """A shallow clone must be detected and surfaced clearly so the user
    isn't left guessing why HEAD~N or merge-base failed."""
    with (
        patch("git_cai_cli.core.squash.find_git_root", return_value=mock_repo_root),
        patch("subprocess.check_output", return_value="true"),
        patch(
            "git_cai_cli.core.squash.load_config", return_value={"default": "openai"}
        ),
        patch("git_cai_cli.core.squash.load_token", return_value="token"),
    ):
        squash_branch()

    assert "shallow clone" in caplog.text.lower()
    assert "git fetch --unshallow" in caplog.text


# ---------------------------------------------------------------------------
# F1.1 — squash editor cancel surfaces rollback instructions
# ---------------------------------------------------------------------------


def test_cancel_after_staged_commit_surfaces_rollback_instructions(
    mock_repo_root, mock_generator, caplog
) -> None:
    """If the user has staged changes that get committed before the squash
    summary editor is opened, and they then cancel the editor, we must
    point them at `git reset HEAD~1 --soft` so they can recover."""

    def git_side_effect(cmd, text=True, **kwargs) -> str:
        if cmd[:3] == ["git", "rev-parse", "--is-shallow-repository"]:
            return "false"
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

    caplog.set_level("WARNING")

    with (
        patch("git_cai_cli.core.squash.find_git_root", return_value=mock_repo_root),
        patch("git_cai_cli.core.squash.git_diff_excluding", return_value="diff"),
        patch("subprocess.check_output", side_effect=git_side_effect),
        patch("git_cai_cli.core.squash.commit_with_edit_template", return_value=1),
        patch(
            "git_cai_cli.core.squash.load_config", return_value={"default": "openai"}
        ),
        patch("git_cai_cli.core.squash.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.squash.CommitMessageGenerator",
            return_value=mock_generator,
        ),
    ):
        squash_branch()

    assert "git reset HEAD~1 --soft" in caplog.text
