"""
Unit tests for `--split` (core.split).

Advisory mode: it must print a plan and never touch git state.
Git and LLM boundaries are mocked.
"""

from pathlib import Path
from unittest.mock import patch

import git_cai_cli.core.split as sp


def _cfg():
    return {
        "default": "openai",
        "openai": {"model": "gpt", "temperature": 0},
        "max_diff_bytes": 0,
        "split_prompt_file": "",
    }


def test_run_split_prints_plan(capsys):
    with (
        patch.object(
            sp, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(sp, "git_diff_excluding", return_value="DIFF"),
        patch.object(sp, "staged_file_names", return_value=["a.py", "b.py"]),
        patch.object(sp, "repo_name_from_root", return_value="repo"),
        patch.object(sp, "run_generation", return_value="1. msg\n- a.py") as rg,
    ):
        sp.run_split()

    assert "1. msg" in capsys.readouterr().out
    assert rg.call_args.kwargs["generator"].kind == "split"


def test_run_split_empty_returns():
    with (
        patch.object(
            sp, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(sp, "git_diff_excluding", return_value=""),
        patch.object(sp, "run_generation") as rg,
    ):
        sp.run_split()

    rg.assert_not_called()


def test_run_split_sends_file_list_to_the_llm():
    with (
        patch.object(
            sp, "prepare", return_value=(Path("/repo"), _cfg(), "openai", "tok")
        ),
        patch.object(sp, "git_diff_excluding", return_value="DIFF"),
        patch.object(sp, "staged_file_names", return_value=["a.py", "b.py"]),
        patch.object(sp, "repo_name_from_root", return_value="repo"),
        patch.object(sp, "run_generation", return_value="plan") as rg,
    ):
        sp.run_split()

    content, _ = rg.call_args.kwargs["build"]()
    assert "a.py" in content and "b.py" in content
