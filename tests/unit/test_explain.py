"""
Unit tests for `--explain` (core.explain).

Everything past the git boundary is mocked — no repo and no network needed.
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import git_cai_cli.core.explain as ex
import pytest
import typer


def _cfg():
    return {
        "default": "openai",
        "openai": {"model": "gpt", "temperature": 0},
        "max_diff_bytes": 0,
        "explain_prompt_file": "",
    }


def test_run_explain_uses_staged_diff_and_echoes(capsys):
    with (
        patch.object(
            ex, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(ex, "git_diff_excluding", return_value="STAGED DIFF"),
        patch.object(ex, "repo_name_from_root", return_value="repo"),
        patch.object(ex, "run_generation", return_value="EXPLANATION") as rg,
    ):
        ex.run_explain()

    assert "EXPLANATION" in capsys.readouterr().out
    assert rg.call_args.kwargs["generator"].kind == "explain"


def test_run_explain_uses_commit_diff_when_rev_given():
    with (
        patch.object(
            ex, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(ex, "get_commit_diff", return_value="COMMIT DIFF") as gcd,
        patch.object(ex, "git_diff_excluding") as staged,
        patch.object(ex, "repo_name_from_root", return_value="repo"),
        patch.object(ex, "run_generation", return_value="X"),
    ):
        ex.run_explain(rev="abc123")

    gcd.assert_called_once_with(Path("/repo"), "abc123")
    staged.assert_not_called()


def test_run_explain_empty_diff_returns():
    with (
        patch.object(
            ex, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(ex, "git_diff_excluding", return_value="   "),
        patch.object(ex, "run_generation") as rg,
    ):
        ex.run_explain()

    rg.assert_not_called()


def test_run_explain_passes_context_and_allow_secrets():
    with (
        patch.object(
            ex, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(ex, "git_diff_excluding", return_value="DIFF"),
        patch.object(ex, "repo_name_from_root", return_value="repo"),
        patch.object(ex, "run_generation", return_value="X") as rg,
    ):
        ex.run_explain(context="ticket-7", allow_secrets=True)

    generator = rg.call_args.kwargs["generator"]
    assert generator.allow_secrets is True
    # The build callable must forward the author's context to the LLM request.
    content, _ = rg.call_args.kwargs["build"]()
    assert "ticket-7" in content


def test_run_explain_rejects_unknown_rev(capsys):
    """A bad commit-ish must exit cleanly, not raise CalledProcessError."""
    with (
        patch.object(
            ex, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(
            ex,
            "get_commit_diff",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ),
        patch.object(ex, "run_generation") as rg,
    ):
        with pytest.raises(typer.Exit):
            ex.run_explain(rev="nope")

    rg.assert_not_called()
