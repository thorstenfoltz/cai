"""
Integration tests for git_cai_cli.core.pr.run_pr.

Scope:
- Real filesystem (a temporary git repo is set up).
- Real Git operations for branching, commits, and base detection.
- LLM call is mocked.
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from git_cai_cli.core.pr import run_pr


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=cwd, check=True)


@pytest.fixture
def feature_branch_repo(tmp_path, monkeypatch) -> Path:
    """Initialize a git repo with `main` and a `feature/x` branch with one commit."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")

    _git(["init", "-b", "main"], cwd=tmp_path)
    # Disable signing for the test repo so this works on developer machines
    # that have commit signing globally enabled.
    _git(["config", "--local", "commit.gpgsign", "false"], cwd=tmp_path)
    _git(["config", "--local", "tag.gpgsign", "false"], cwd=tmp_path)

    (tmp_path / "README.md").write_text("# repo\n", encoding="utf-8")
    _git(["add", "README.md"], cwd=tmp_path)
    _git(["commit", "-m", "Initial commit"], cwd=tmp_path)

    _git(["checkout", "-b", "feature/x"], cwd=tmp_path)
    (tmp_path / "src.py").write_text("print('hi')\n", encoding="utf-8")
    _git(["add", "src.py"], cwd=tmp_path)
    _git(["commit", "-m", "Add src.py"], cwd=tmp_path)

    monkeypatch.chdir(tmp_path)
    return tmp_path


def _config_for(tmp_path: Path, **overrides) -> dict:
    cfg = {
        "default": "openai",
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "style": "professional",
        "emoji": True,
        "prompt_file": "",
        "squash_prompt_file": "",
        "pr_prompt_file": "",
        "pr_to_file": False,
        "pr_file_name": "PR_DESCRIPTION.md",
        "load_tokens_from": str(tmp_path / "tokens.yml"),
    }
    cfg.update(overrides)
    return cfg


def test_pr_writes_to_stdout_by_default(feature_branch_repo, capsys):
    cfg = _config_for(feature_branch_repo)

    with (
        patch("git_cai_cli.core.pr.load_config", return_value=cfg),
        patch("git_cai_cli.core.pr.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.llm.CommitMessageGenerator.generate_pr_description",
            return_value="## Summary\n- added src\n\n## Test plan\n- [ ] run",
        ),
    ):
        run_pr(base_override="main")

    captured = capsys.readouterr()
    assert "## Summary" in captured.out
    assert "## Test plan" in captured.out
    assert not (feature_branch_repo / "PR_DESCRIPTION.md").exists()


def test_pr_writes_to_file_when_pr_to_file_true(feature_branch_repo):
    cfg = _config_for(feature_branch_repo, pr_to_file=True)

    with (
        patch("git_cai_cli.core.pr.load_config", return_value=cfg),
        patch("git_cai_cli.core.pr.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.llm.CommitMessageGenerator.generate_pr_description",
            return_value="## Summary\n- added src",
        ),
    ):
        run_pr(base_override="main")

    out_file = feature_branch_repo / "PR_DESCRIPTION.md"
    assert out_file.exists()
    assert "## Summary" in out_file.read_text(encoding="utf-8")


def test_pr_respects_custom_pr_file_name(feature_branch_repo):
    cfg = _config_for(feature_branch_repo, pr_to_file=True, pr_file_name="CUSTOM_PR.md")

    with (
        patch("git_cai_cli.core.pr.load_config", return_value=cfg),
        patch("git_cai_cli.core.pr.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.llm.CommitMessageGenerator.generate_pr_description",
            return_value="BODY",
        ),
    ):
        run_pr(base_override="main")

    assert (feature_branch_repo / "CUSTOM_PR.md").exists()
    assert not (feature_branch_repo / "PR_DESCRIPTION.md").exists()


def test_pr_no_commits_does_nothing(feature_branch_repo, capsys, caplog):
    """If HEAD has not diverged from base, run_pr should log and exit cleanly."""
    cfg = _config_for(feature_branch_repo)

    # Move HEAD to main so there is nothing between main and HEAD.
    _git(["checkout", "main"], cwd=feature_branch_repo)

    with (
        patch("git_cai_cli.core.pr.load_config", return_value=cfg),
        patch("git_cai_cli.core.pr.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.llm.CommitMessageGenerator.generate_pr_description",
            side_effect=AssertionError("should not be called"),
        ),
    ):
        with caplog.at_level("INFO"):
            run_pr(base_override="main")

    assert "nothing to describe" in caplog.text
