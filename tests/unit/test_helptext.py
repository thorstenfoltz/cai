import pytest
import typer
from git_cai_cli.cli.helptext import HELP_TEXT, print_help_and_exit


def test_print_help_and_exit(capsys):
    # Ensure typer.Exit is raised
    with pytest.raises(typer.Exit):
        print_help_and_exit()

    # Capture printed output
    captured = capsys.readouterr()
    assert captured.out.strip() == HELP_TEXT.strip()


def test_help_lists_read_only_modes():
    """Help is hand-written, so new flags must be added there explicitly."""
    for flag in ("--explain", "--split", "--changelog", "--release"):
        assert flag in HELP_TEXT
