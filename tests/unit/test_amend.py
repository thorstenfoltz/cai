"""
Unit tests for the --amend / -A feature.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from git_cai_cli.cli import modes
from git_cai_cli.cli.modes import Mode
from git_cai_cli.core.gitutils import commit_direct, get_last_commit_diff


# ----------------------
# resolve_mode with amend
# ----------------------


def test_resolve_mode_amend():
    """--amend flag should return AMEND mode."""
    mode = modes.resolve_mode(amend=True, list_flag=False, squash=False, update=False)
    assert mode == Mode.AMEND


def test_resolve_mode_amend_conflicts_with_squash(capsys):
    """--amend and --squash cannot be used together."""
    with pytest.raises(typer.Exit) as exc:
        modes.resolve_mode(amend=True, list_flag=False, squash=True, update=False)
    captured = capsys.readouterr()
    assert (
        "cannot be used together" in captured.out
        or "cannot be used together" in captured.err
    )
    assert exc.value.exit_code == 1


def test_resolve_mode_amend_conflicts_with_list(capsys):
    """--amend and --list cannot be used together."""
    with pytest.raises(typer.Exit) as exc:
        modes.resolve_mode(amend=True, list_flag=True, squash=False, update=False)
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
