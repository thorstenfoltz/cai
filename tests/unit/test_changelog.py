"""
Unit tests for `--changelog` (core.changelog).

Git and LLM boundaries are mocked — no repo, no network.
"""

from pathlib import Path
from unittest.mock import patch

import git_cai_cli.core.changelog as cl


def _cfg(**overrides):
    config = {
        "default": "openai",
        "openai": {"model": "gpt", "temperature": 0},
        "max_diff_bytes": 0,
        "changelog_prompt_file": "",
        "changelog_to_file": False,
        "changelog_file_name": "CHANGELOG.md",
    }
    config.update(overrides)
    return config


def test_run_changelog_prints_by_default(capsys):
    with (
        patch.object(
            cl, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(cl, "last_git_tag", return_value="v1.0.0"),
        patch.object(cl, "commit_log_range", return_value="feat: x") as clr,
        patch.object(cl, "changed_files_range", return_value="a.py"),
        patch.object(cl, "repo_name_from_root", return_value="repo"),
        patch.object(cl, "run_generation", return_value="## Unreleased\n- x") as rg,
    ):
        cl.run_changelog()

    assert "## Unreleased" in capsys.readouterr().out
    assert clr.call_args[0][0] == "v1.0.0..HEAD"
    assert rg.call_args.kwargs["generator"].kind == "changelog"


def test_run_changelog_no_tag_uses_full_history():
    with (
        patch.object(
            cl, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(cl, "last_git_tag", return_value=None),
        patch.object(cl, "commit_log_range", return_value="feat: x") as clr,
        patch.object(cl, "repo_name_from_root", return_value="repo"),
        patch.object(cl, "run_generation", return_value="X"),
    ):
        cl.run_changelog()

    assert clr.call_args[0][0] == "HEAD"


def test_run_changelog_no_commits_returns():
    with (
        patch.object(
            cl, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(cl, "last_git_tag", return_value="v1.0.0"),
        patch.object(cl, "commit_log_range", return_value="  "),
        patch.object(cl, "run_generation") as rg,
    ):
        cl.run_changelog()

    rg.assert_not_called()


def test_run_changelog_writes_file_when_enabled(tmp_path):
    with (
        patch.object(
            cl,
            "prepare",
            return_value=(tmp_path, _cfg(changelog_to_file=True), "openai", "tok"),
        ),
        patch.object(cl, "last_git_tag", return_value="v1.0.0"),
        patch.object(cl, "commit_log_range", return_value="feat: x"),
        patch.object(cl, "changed_files_range", return_value="a.py"),
        patch.object(cl, "repo_name_from_root", return_value="repo"),
        patch.object(cl, "run_generation", return_value="## Unreleased\n- x"),
    ):
        cl.run_changelog()

    assert "## Unreleased" in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")


def test_run_changelog_prepends_to_existing_file(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## v1.0.0\n- old entry\n", encoding="utf-8")

    with (
        patch.object(
            cl,
            "prepare",
            return_value=(tmp_path, _cfg(changelog_to_file=True), "openai", "tok"),
        ),
        patch.object(cl, "last_git_tag", return_value="v1.0.0"),
        patch.object(cl, "commit_log_range", return_value="feat: x"),
        patch.object(cl, "changed_files_range", return_value="a.py"),
        patch.object(cl, "repo_name_from_root", return_value="repo"),
        patch.object(cl, "run_generation", return_value="## Unreleased\n- new"),
    ):
        cl.run_changelog()

    written = changelog.read_text(encoding="utf-8")
    assert written.index("## Unreleased") < written.index("## v1.0.0")
    assert "- old entry" in written
