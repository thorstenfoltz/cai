"""
Unit and integration tests for git_cai_cli.core.gitutils.

These tests verify:
- Git root detection
- git diff exclusion logic
- editor resolution
- hash computation
- commit template workflow

All subprocess and filesystem interactions are mocked so no real Git repo
or external tools are required.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from git_cai_cli.core.gitutils import (
    commit_with_edit_template,
    find_git_root,
    get_git_editor,
    git_diff_excluding,
    sha256_of_file,
)

# ------------------------------------------------------------------------------
# find_git_root
# ------------------------------------------------------------------------------


def test_find_git_root_success():
    """
    Find_git_root() should return the path returned by git.
    """
    mock_proc = MagicMock()
    mock_proc.stdout = "/fake/repo\n"

    def fake_run(*args, **kwargs):
        return mock_proc

    path = find_git_root(run_cmd=fake_run)
    assert path == Path("/fake/repo")


def test_find_git_root_failure_returns_none():
    """
    Find_git_root() should return None when git rev-parse fails.
    """

    def fake_run(*_, **__):
        raise subprocess.CalledProcessError(1, "cmd")

    assert find_git_root(run_cmd=fake_run) is None


# ------------------------------------------------------------------------------
# git_diff_excluding
# ------------------------------------------------------------------------------


def test_git_diff_excluding_reads_ignore_file_and_excludes_patterns(tmp_path):
    """
    git_diff_excluding() should append :!pattern for each line in .caiignore.
    """
    repo_root = tmp_path
    ignore_file = repo_root / ".caiignore"
    ignore_file.write_text("*.pyc\n# comment\nbuild/\n")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "diff output"

    def fake_run(cmd, capture_output, text, check):
        # Ensure ignore patterns were added
        assert ":!*.pyc" in cmd
        assert ":!build/" in cmd
        return mock_proc

    output = git_diff_excluding(repo_root, run_cmd=fake_run)
    assert output == "diff output"


def test_git_diff_excluding_exits_on_failure(tmp_path):
    """
    git_diff_excluding() should call exit_func(1) when diff returns error.
    """
    repo_root = tmp_path
    (repo_root / ".caiignore").write_text("node_modules/\n")

    mock_proc = MagicMock()
    mock_proc.returncode = 123  # triggers exit

    def fake_run(*args, **kwargs):
        return mock_proc

    exit_called = False

    def fake_exit(code):
        nonlocal exit_called
        exit_called = True
        assert code == 1

    git_diff_excluding(repo_root, run_cmd=fake_run, exit_func=fake_exit)
    assert exit_called is True


# ------------------------------------------------------------------------------
# get_git_editor
# ------------------------------------------------------------------------------


def test_get_git_editor_prefers_git_var():
    """
    get_git_editor() should return output of git var GIT_EDITOR when available.
    """
    mock_proc = MagicMock()
    mock_proc.stdout = "vim\n"

    with patch("subprocess.run", return_value=mock_proc):
        assert get_git_editor() == "vim"


def test_get_git_editor_falls_back_to_env():
    """
    get_git_editor() should fall back to environment variables if git var fails.
    """
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")):
        with patch.dict(os.environ, {"EDITOR": "nano"}):
            assert get_git_editor() == "nano"


def test_get_git_editor_fallback_system_editor():
    """
    get_git_editor() should fall back to vi/nano when no env vars are set.
    """
    with (
        patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")),
        patch.dict(os.environ, {}, clear=True),
        patch("shutil.which", return_value="vi"),
    ):
        assert get_git_editor() == "vi"


# ------------------------------------------------------------------------------
# sha256_of_file
# ------------------------------------------------------------------------------


def test_sha256_of_file(tmp_path):
    """
    sha256_of_file() should compute correct SHA256.
    """
    file = tmp_path / "data.txt"
    file.write_text("hash test")

    h = sha256_of_file(file)
    import hashlib

    assert h == hashlib.sha256(b"hash test").hexdigest()


# ------------------------------------------------------------------------------
# commit_with_edit_template
# ------------------------------------------------------------------------------


def test_commit_with_edit_template_abort_on_unchanged(tmp_path):
    """
    commit_with_edit_template() should abort if editor does not modify the file.
    """

    # Editor does nothing but return success
    def fake_editor_run(cmd, check):
        return MagicMock(returncode=0)

    # Git commit should not be called because file unchanged
    with (
        patch("git_cai_cli.core.gitutils.get_git_editor", return_value="true"),
        patch("subprocess.run", side_effect=fake_editor_run),
    ):
        rc = commit_with_edit_template("initial\n")
        assert rc == 1


def test_commit_with_edit_template_runs_git_commit(tmp_path):
    """
    commit_with_edit_template() should perform git commit when file is modified.
    """

    # Fake editor modifies file by rewriting its content
    def fake_editor_run(cmd, check):
        path = cmd[-1]
        Path(path).write_text("edited message")
        return MagicMock(returncode=0)

    # Fake git commit success
    def fake_git_commit(cmd, check):
        return MagicMock()

    with (
        patch("git_cai_cli.core.gitutils.get_git_editor", return_value="true"),
        patch(
            "subprocess.run",
            side_effect=lambda cmd, **kw: (
                fake_editor_run(cmd, kw) if "true" in cmd else fake_git_commit(cmd, kw)
            ),
        ),
    ):

        rc = commit_with_edit_template("initial\n")
        assert rc == 0
