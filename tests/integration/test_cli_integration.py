import os
import subprocess
from pathlib import Path

import pytest
from git_cai_cli.cli import cli
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def temp_git_repo():
    """
    Create a temporary Git repository with a staged file.
    The repo is fully isolated and safe.
    """
    with runner.isolated_filesystem() as temp_dir:
        temp_path = Path(temp_dir)

        # Initialize a git repository
        subprocess.run(["git", "init"], cwd=temp_path, check=True)

        # Create a dummy file
        file_path = temp_path / "file.txt"
        file_path.write_text("Hello world\n")

        # Stage the file (do NOT commit)
        subprocess.run(["git", "add", "file.txt"], cwd=temp_path, check=True)

        yield temp_path  # provide the path to the test


def test_cli_integration(temp_git_repo, monkeypatch):
    """
    Full integration test for git-cai-cli CLI.
    CLI sees a staged file but does NOT commit anything.
    """
    # Patch functions that perform real work
    monkeypatch.setattr(cli, "run", lambda **kwargs: None)
    monkeypatch.setattr(cli, "resolve_mode", lambda **kwargs: "dummy_mode")
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    # Change working directory to the temp repo
    old_cwd = os.getcwd()
    os.chdir(temp_git_repo)
    try:
        # Run the CLI with no arguments
        result = runner.invoke(cli.app, [])
        assert result.exit_code == 0

        # Run the CLI --help
        help_result = runner.invoke(cli.app, ["--help"])
        assert help_result.exit_code == 0
        assert "Git CAI - AI-powered commit message generator" in help_result.output

        # Run CLI with multiple flags
        args = ["--list", "--all", "--squash", "--update", "--debug"]
        result_flags = runner.invoke(cli.app, args)
        assert result_flags.exit_code == 0

        # Verify that no commits exist in this temporary repo
        git_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        )
        assert git_head.returncode != 0  # no commits exist
    finally:
        os.chdir(old_cwd)
