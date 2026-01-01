"""
Module for handling operational modes and validating command-line options.
"""

from enum import Enum, auto

import typer


class Mode(Enum):
    """
    Enum representing the different operational modes of the CLI.
    """

    COMMIT = auto()
    LIST = auto()
    SQUASH = auto()
    UPDATE = auto()


def resolve_mode(*, list_flag: bool, squash: bool, update: bool) -> Mode:
    """
    Resolves the operational mode based on the provided flags.
    """
    flags = [list_flag, squash, update]
    if sum(flags) > 1:
        typer.echo(
            "Error: --list, --squash, and --update cannot be used together.",
            err=True,
        )
        raise typer.Exit(code=1)

    if list_flag:
        return Mode.LIST
    if squash:
        return Mode.SQUASH
    if update:
        return Mode.UPDATE

    return Mode.COMMIT


def validate_options(
    *,
    mode: Mode,
    stage_tracked: bool,
    enable_debug: bool,
    help_flag: bool,
    version_flag: bool,
) -> None:
    """
    Validates the combination of command-line options provided by the user.
    """
    if enable_debug and (help_flag or version_flag):
        typer.echo(
            "Error: --debug cannot be used with --help or --version.",
            err=True,
        )
        raise typer.Exit(code=1)

    if stage_tracked and mode is not Mode.COMMIT:
        typer.echo(
            "Error: --all cannot be used with --list, --update, or --squash.",
            err=True,
        )
        raise typer.Exit(code=1)
