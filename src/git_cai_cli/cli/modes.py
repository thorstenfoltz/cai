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
    CHANGELOG = auto()
    CHECK = auto()
    COMMIT = auto()
    EXPLAIN = auto()
    INIT = auto()
    LIST = auto()
    PR = auto()
    RELEASE = auto()
    SPLIT = auto()
    SQUASH = auto()
    STATS = auto()
    UPDATE = auto()


# Read-only modes that generate advisory output and never touch git state.
READ_ONLY_MODES = (Mode.EXPLAIN, Mode.SPLIT, Mode.CHANGELOG, Mode.RELEASE)


def resolve_mode(
    *,
    amend: bool,
    changelog: bool = False,
    check: bool = False,
    explain: bool = False,
    init: bool = False,
    list_flag: bool,
    pr: bool,
    release: bool = False,
    split: bool = False,
    squash: bool,
    stats: bool = False,
    update: bool,
) -> Mode:
    """
    Resolves the operational mode based on the provided flags.
    """
    flags = [
        amend,
        changelog,
        check,
        explain,
        init,
        list_flag,
        pr,
        release,
        split,
        squash,
        stats,
        update,
    ]
    if sum(flags) > 1:
        typer.echo(
            "Error: mode flags (--amend, --changelog, --check, --explain, --init, "
            "--list, --PR, --release, --split, --squash, --stats, --update) "
            "cannot be used together.",
            err=True,
        )
        raise typer.Exit(code=1)

    if amend:
        return Mode.AMEND
    if changelog:
        return Mode.CHANGELOG
    if check:
        return Mode.CHECK
    if explain:
        return Mode.EXPLAIN
    if init:
        return Mode.INIT
    if list_flag:
        return Mode.LIST
    if pr:
        return Mode.PR
    if release:
        return Mode.RELEASE
    if split:
        return Mode.SPLIT
    if squash:
        return Mode.SQUASH
    if stats:
        return Mode.STATS
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
    print_only: bool = False,
    crazy: bool = False,
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
            "Error: --all can only be used in COMMIT or AMEND mode.",
            err=True,
        )
        raise typer.Exit(code=1)

    if (provider_override or model_override) and mode in (
        Mode.INIT,
        Mode.LIST,
        Mode.UPDATE,
    ):
        typer.echo(
            "Error: --provider/--model cannot be used with --init, --list, or --update.",
            err=True,
        )
        raise typer.Exit(code=1)

    if time_flag and mode in (Mode.INIT, Mode.LIST, Mode.UPDATE):
        typer.echo(
            "Error: --time cannot be used with --init, --list, or --update.",
            err=True,
        )
        raise typer.Exit(code=1)

    if context and mode not in (
        Mode.COMMIT,
        Mode.AMEND,
        Mode.SQUASH,
        Mode.PR,
        *READ_ONLY_MODES,
    ):
        typer.echo(
            "Error: --context cannot be used with this mode.",
            err=True,
        )
        raise typer.Exit(code=1)

    if files and mode not in (Mode.COMMIT, Mode.AMEND):
        typer.echo(
            "Error: --files can only be used in COMMIT or AMEND mode.",
            err=True,
        )
        raise typer.Exit(code=1)

    if print_only:
        if mode not in (Mode.COMMIT, Mode.AMEND):
            typer.echo(
                "Error: --print can only be used in COMMIT or AMEND mode.",
                err=True,
            )
            raise typer.Exit(code=1)
        if crazy:
            typer.echo(
                "Error: --print and --crazy are mutually exclusive.",
                err=True,
            )
            raise typer.Exit(code=1)
