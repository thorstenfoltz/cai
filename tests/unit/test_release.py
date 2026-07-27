"""
Unit tests for `--release` (core.release).

Git and LLM boundaries are mocked — no repo, no network.
"""

from pathlib import Path
from unittest.mock import patch

import git_cai_cli.core.release as rel


def _cfg():
    return {
        "default": "openai",
        "openai": {"model": "gpt", "temperature": 0},
        "max_diff_bytes": 0,
        "release_prompt_file": "",
    }


_NOTES = "Release title\n\nBug fixes\n- fixed the thing"


def test_run_release_prints_only_the_notes(capsys):
    """No version line and no git command — just the release notes."""
    with (
        patch.object(
            rel, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(rel, "last_git_tag", return_value="v1.0.0"),
        patch.object(rel, "commit_log_range", return_value="feat: x"),
        patch.object(rel, "repo_name_from_root", return_value="repo"),
        patch.object(rel, "run_generation", return_value=_NOTES) as rg,
    ):
        rel.run_release()

    out = capsys.readouterr().out
    assert out.strip() == _NOTES
    assert "git tag" not in out
    assert "Suggested version" not in out
    assert rg.call_args.kwargs["generator"].kind == "release"


def test_run_release_prints_the_notes_exactly_once(capsys):
    """Regression: the notes used to appear twice — once as a block and
    again embedded in a `git tag -a -m` command."""
    with (
        patch.object(
            rel, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(rel, "last_git_tag", return_value="v1.0.0"),
        patch.object(rel, "commit_log_range", return_value="feat: x"),
        patch.object(rel, "repo_name_from_root", return_value="repo"),
        patch.object(rel, "run_generation", return_value=_NOTES),
    ):
        rel.run_release()

    out = capsys.readouterr().out
    assert out.count("Release title") == 1
    assert out.count("- fixed the thing") == 1


def test_run_release_passes_notes_through_verbatim(capsys):
    """Quotes reach the terminal unmangled — nothing is escaped any more."""
    with (
        patch.object(
            rel, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(rel, "last_git_tag", return_value="v1.0.0"),
        patch.object(rel, "commit_log_range", return_value="fix: x"),
        patch.object(rel, "repo_name_from_root", return_value="repo"),
        patch.object(rel, "run_generation", return_value='Fix the "quoted" thing'),
    ):
        rel.run_release()

    out = capsys.readouterr().out
    assert 'Fix the "quoted" thing' in out
    assert "\\" not in out


def test_run_release_no_commits_returns():
    with (
        patch.object(
            rel, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(rel, "last_git_tag", return_value="v1.0.0"),
        patch.object(rel, "commit_log_range", return_value=""),
        patch.object(rel, "run_generation") as rg,
    ):
        rel.run_release()

    rg.assert_not_called()


def test_run_release_uses_full_history_without_tags():
    with (
        patch.object(
            rel, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(rel, "last_git_tag", return_value=None),
        patch.object(rel, "commit_log_range", return_value="feat: x") as clr,
        patch.object(rel, "repo_name_from_root", return_value="repo"),
        patch.object(rel, "run_generation", return_value="notes"),
    ):
        rel.run_release()

    assert clr.call_args[0][0] == "HEAD"
