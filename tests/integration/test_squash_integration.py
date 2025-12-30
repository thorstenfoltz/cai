"""
Integration tests for git_cai_cli.core.squash.

Scope:
- Real filesystem
- Real Git repository detection
- No commits
- No history traversal
- No mutation

These tests intentionally stop before any Git history logic.
"""

import subprocess
from pathlib import Path

import pytest
from git_cai_cli.core.squash import squash_branch


@pytest.fixture()
def git_repo(tmp_path) -> Path:
    """
    Create a real temporary Git repository for integration tests.
    """
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_squash_branch_outside_git_repo(tmp_path, monkeypatch, caplog) -> None:
    """
    Integration: squash_branch logs an error when called outside a Git repository.
    """
    monkeypatch.chdir(tmp_path)

    with caplog.at_level("ERROR"):
        squash_branch()

    assert "Not inside a Git repository" in caplog.text


def test_squash_branch_in_unborn_repo_is_safe(git_repo, monkeypatch, caplog) -> None:
    """
    Integration: squash_branch does not crash merely by being
    invoked inside a real Git repository with no commits.
    """
    monkeypatch.chdir(git_repo)

    # We only assert that Git repo detection works and no uncaught exception occurs
    try:
        squash_branch()
    except Exception as exc:  # pylint: disable=broad-except
        pytest.fail(f"squash_branch raised unexpectedly: {exc}")
