"""
Integration tests for git_cai_cli.core.options.CliManager
"""
import subprocess
from pathlib import Path
import pytest
from git_cai_cli.core.options import CliManager

@pytest.fixture()
def git_repo(tmp_path) -> Path:
    """
    Create a real temporary Git repository for integration tests.
    """
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    return tmp_path

def test_stage_tracked_files_in_real_git_repo(git_repo, monkeypatch) -> None:
    """
    Integration: stage_tracked_files executes successfully in a real Git repo.
    No commits are created.
    """
    monkeypatch.chdir(git_repo)

    # create and stage file once so it becomes tracked
    file = git_repo / "tracked.txt"
    file.write_text("hello")
    subprocess.run(["git", "add", "tracked.txt"], cwd=git_repo, check=True)

    # modify tracked file
    file.write_text("modified")

    manager = CliManager()
    manager.stage_tracked_files()

    # verify file is staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "tracked.txt" in result.stdout


def test_print_available_languages_real_data() -> None:
    """
    Integration: uses real LANGUAGE_MAP.
    """
    manager = CliManager()
    output = manager.print_available_languages()

    assert "→" in output
    assert "Available languages" in output
