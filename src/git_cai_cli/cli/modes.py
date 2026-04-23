"""
Module for handling operational modes and validating command-line options.
"""

from enum import Enum, auto

import typer


class Mode(Enum):
    """
    Enum representing the different operational modes of the CLI.
    """

    AMEND = auto()
    COMMIT = auto()
    LIST = auto()
    SQUASH = auto()
    UPDATE = auto()


def resolve_mode(*, amend: bool, list_flag: bool, squash: bool, update: bool) -> Mode:
    """
    Resolves the operational mode based on the provided flags.
    """
    flags = [amend, list_flag, squash, update]
    if sum(flags) > 1:
        typer.echo(
            "Error: --amend, --list, --squash, and --update cannot be used together.",
            err=True,
        )
        raise typer.Exit(code=1)

    if amend:
        return Mode.AMEND
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
    provider_override: str | None = None,
    model_override: str | None = None,
    time_flag: bool = False,
    context: str | None = None,
    files: list[str] | None = None,
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

    if stage_tracked and mode not in (Mode.COMMIT, Mode.AMEND):
        typer.echo(
            "Error: --all cannot be used with --list, --update, or --squash.",
            err=True,
        )
        raise typer.Exit(code=1)

    if (provider_override or model_override) and mode in (Mode.LIST, Mode.UPDATE):
        typer.echo(
            "Error: --provider/--model cannot be used with --list or --update.",
            err=True,
        )
        raise typer.Exit(code=1)

    if time_flag and mode in (Mode.LIST, Mode.UPDATE):
        typer.echo(
            "Error: --time cannot be used with --list or --update.",
            err=True,
        )
        raise typer.Exit(code=1)

    if context and mode not in (Mode.COMMIT, Mode.AMEND, Mode.SQUASH):
        typer.echo(
            "Error: --context cannot be used with --list or --update.",
            err=True,
        )
        raise typer.Exit(code=1)

    if files and mode not in (Mode.COMMIT, Mode.AMEND):
        typer.echo(
            "Error: --files cannot be used with --list, --update, or --squash.",
            err=True,
        )
        raise typer.Exit(code=1)
