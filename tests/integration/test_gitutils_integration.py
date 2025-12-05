"""
Integration tests for gitutils functions.
"""

import subprocess
from pathlib import Path

import pytest
from git_cai_cli.core.gitutils import find_git_root, git_diff_excluding


@pytest.fixture()
def temp_git_repo(tmp_path: Path):
    """
    Creates an isolated git repo
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "commit.gpgSign", "false"], cwd=repo, check=True)

    # Create initial committed file
    f1 = repo / "file1.txt"
    f1.write_text("hello\n")
    subprocess.run(["git", "add", "file1.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True)

    return repo


def test_find_git_root_integration(temp_git_repo):
    """
    Tests that find_git_root correctly identifies the git repo root.
    """
    root = find_git_root(
        run_cmd=lambda *args, **kwargs: subprocess.run(
            *args, cwd=temp_git_repo, **kwargs
        )
    )
    assert root == temp_git_repo


def test_git_diff_excluding_integration(temp_git_repo):
    """
    Tests that git_diff_excluding correctly excludes files in .caiignore."""
    ignore = temp_git_repo / ".caiignore"
    ignore.write_text("file2.txt\n")

    (temp_git_repo / "file1.txt").write_text("changed 1\n")
    (temp_git_repo / "file2.txt").write_text("changed 2\n")
    subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True)

    diff = git_diff_excluding(
        repo_root=temp_git_repo,
        run_cmd=lambda *args, **kwargs: subprocess.run(
            *args, cwd=temp_git_repo, **kwargs
        ),
        exit_func=lambda code: (_ for _ in ()).throw(RuntimeError(f"exit {code}")),
    )

    # extract only the git diff headers
    headers = [line for line in diff.splitlines() if line.startswith("diff --git")]

    assert any("file1.txt" in h for h in headers)
    assert not any("file2.txt" in h for h in headers)
