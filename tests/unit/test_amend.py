"""
Unit tests for the --amend / -A feature.
"""

from unittest.mock import MagicMock, patch

import pytest
import typer
from git_cai_cli.cli import modes
from git_cai_cli.cli.modes import Mode
from git_cai_cli.core.gitutils import (
    commit_direct,
    get_last_commit_diff,
    get_last_commit_message,
)
from git_cai_cli.core.llm import CommitMessageGenerator

# ----------------------
# resolve_mode with amend
# ----------------------


def test_resolve_mode_amend():
    """--amend flag should return AMEND mode."""
    mode = modes.resolve_mode(
        amend=True, list_flag=False, pr=False, squash=False, update=False
    )
    assert mode == Mode.AMEND


def test_resolve_mode_amend_conflicts_with_squash(capsys):
    """--amend and --squash cannot be used together."""
    with pytest.raises(typer.Exit) as exc:
        modes.resolve_mode(
            amend=True, list_flag=False, pr=False, squash=True, update=False
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used together" in captured.out
        or "cannot be used together" in captured.err
    )
    assert exc.value.exit_code == 1


def test_resolve_mode_amend_conflicts_with_list(capsys):
    """--amend and --list cannot be used together."""
    with pytest.raises(typer.Exit) as exc:
        modes.resolve_mode(
            amend=True, list_flag=True, pr=False, squash=False, update=False
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used together" in captured.out
        or "cannot be used together" in captured.err
    )
    assert exc.value.exit_code == 1


# ----------------------
# validate_options with amend
# ----------------------


def test_validate_options_stage_tracked_allowed_with_amend():
    """--all should be allowed with AMEND mode."""
    modes.validate_options(
        mode=Mode.AMEND,
        stage_tracked=True,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
    )


# ----------------------
# get_last_commit_diff
# ----------------------


def test_get_last_commit_diff_success(tmp_path):
    """get_last_commit_diff should return the diff output."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "diff --git a/file.py b/file.py\n+added line"

    result = get_last_commit_diff(tmp_path, run_cmd=lambda *a, **kw: mock_proc)
    assert "added line" in result


def test_get_last_commit_diff_no_commits(tmp_path):
    """get_last_commit_diff should return empty string when there's no previous commit."""
    mock_proc = MagicMock()
    mock_proc.returncode = 128
    mock_proc.stderr = "fatal: bad revision 'HEAD~1..HEAD'"
    mock_proc.stdout = ""

    result = get_last_commit_diff(tmp_path, run_cmd=lambda *a, **kw: mock_proc)
    assert result == ""


# ----------------------
# commit_direct with amend
# ----------------------


def test_commit_direct_amend_passes_flag():
    """commit_direct with amend=True should include --amend in git command."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        commit_direct("test message", amend=True)
        cmd = mock_run.call_args[0][0]
        assert "--amend" in cmd
        assert "-m" in cmd
        assert "test message" in cmd


def test_commit_direct_no_amend_by_default():
    """commit_direct without amend should not include --amend."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        commit_direct("test message")
        cmd = mock_run.call_args[0][0]
        assert "--amend" not in cmd


# ----------------------
# get_last_commit_message + amend refines existing message (#15)
# ----------------------


def _amend_gen():
    config = {
        "openai": {"model": "x", "temperature": 0},
        "default": "openai",
        "language": "none",
        "style": "none",
        "emoji": None,
    }
    return CommitMessageGenerator(token="fake", config=config, default_model="openai")


def test_get_last_commit_message_success(tmp_path):
    """get_last_commit_message returns the full stripped commit body."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "Old subject\n\nOld body line\n"

    result = get_last_commit_message(tmp_path, run_cmd=lambda *a, **kw: mock_proc)
    assert result == "Old subject\n\nOld body line"


def test_get_last_commit_message_no_commit(tmp_path):
    """get_last_commit_message returns '' when there is no commit."""
    mock_proc = MagicMock()
    mock_proc.returncode = 128
    mock_proc.stdout = ""
    mock_proc.stderr = "fatal: your current branch does not have any commits yet"

    result = get_last_commit_message(tmp_path, run_cmd=lambda *a, **kw: mock_proc)
    assert result == ""


def test_amend_prompt_includes_previous_message():
    """In amend mode the previous message and a refine instruction are appended."""
    gen = _amend_gen()
    gen.kind = "amend"
    out = gen._build_commit_prompt(previous_message="Fix login bug")
    assert "Existing commit message" in out
    assert "Fix login bug" in out
    assert "do not discard information" in out.lower()


def test_commit_prompt_excludes_previous_message():
    """A normal commit never embeds the previous message, even if one is passed."""
    gen = _amend_gen()
    gen.kind = "commit"
    out = gen._build_commit_prompt(previous_message="Fix login bug")
    assert "Fix login bug" not in out
