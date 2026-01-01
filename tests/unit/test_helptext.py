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
