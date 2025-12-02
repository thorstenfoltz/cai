"""
Integration tests for git_cai_cli.core.config.

These tests verify real interactions between:
- Filesystem
- Git repository detection
- Repo vs home config precedence
- Token loading/creation
"""

import subprocess
from pathlib import Path

import pytest
import yaml
from git_cai_cli.core.config import (
    load_config,
)


@pytest.fixture()  # pylint: disable=redefined-outer-name
def git_repo(tmp_path) -> Path:
    """
    Create a real temporary Git repository for integration tests
    and tests that repo-level config is detected over home-level config.
    """
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_load_config_repo_precedence(
    git_repo, tmp_path, monkeypatch
):  # pylint: disable=redefined-outer-name
    """
    Integration: verify repo → home → defaults config precedence.
    """

    repo_cfg = git_repo / "cai_config.yml"
    repo_cfg.write_text(
        yaml.safe_dump(
            {
                "default": "openai",
                "language": "nl",
                "style": "sarcastic",
                "emoji": "true",
            }
        )
    )

    home_cfg = tmp_path / "home_config.yml"
    home_cfg.write_text(
        yaml.safe_dump(
            {
                "default": "groq",
                "language": "en",
                "style": "friendly",
                "emoji": "false",
            }
        )
    )

    monkeypatch.setenv("HOME", str(tmp_path))

    monkeypatch.chdir(git_repo)

    config = load_config()

    assert config["default"] == "openai"
    assert config["language"] == "nl"
    assert config["style"] == "sarcastic"
    assert config["emoji"] == "true"
