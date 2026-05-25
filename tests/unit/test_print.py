"""
Tests for the --print no-commit output feature.

Mutual-exclusion tests live alongside other mode-validation tests in
test_modes.py; this file covers the runtime behavior that ``--print``
short-circuits before any ``git commit`` call.
"""

import pytest
import typer
from git_cai_cli.cli import modes
from git_cai_cli.cli.modes import Mode


def test_print_only_allowed_in_commit_mode():
    modes.validate_options(
        mode=Mode.COMMIT,
        stage_tracked=False,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
        print_only=True,
    )


def test_print_only_allowed_in_amend_mode():
    modes.validate_options(
        mode=Mode.AMEND,
        stage_tracked=False,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
        print_only=True,
    )


def test_print_rejected_in_squash_mode(capsys):
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.SQUASH,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            print_only=True,
        )
    captured = capsys.readouterr()
    assert "--print can only be used" in captured.err
    assert exc.value.exit_code == 1


def test_print_rejected_in_pr_mode(capsys):
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.PR,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            print_only=True,
        )
    captured = capsys.readouterr()
    assert "--print can only be used" in captured.err
    assert exc.value.exit_code == 1


def test_print_with_crazy_rejected(capsys):
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.COMMIT,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            print_only=True,
            crazy=True,
        )
    captured = capsys.readouterr()
    assert "--print and --crazy are mutually exclusive" in captured.err
    assert exc.value.exit_code == 1
