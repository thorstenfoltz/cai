"""
CLI entry point for git-cai-cli.
"""

import typer
from git_cai_cli.cli.helptext import print_help_and_exit
from git_cai_cli.cli.modes import resolve_mode, validate_options
from git_cai_cli.main import run

app = typer.Typer(add_completion=True, help=None, no_args_is_help=False)


@app.callback(invoke_without_command=True)
def callback(
    version: bool = typer.Option(
        False, "-v", "--version", help="Show version", is_eager=True
    ),
    help_flag: bool = typer.Option(
        False, "-h", "--help", help="Show help", is_eager=True
    ),
    enable_debug: bool = typer.Option(
        False, "--debug", "-d", help="Enable debug logging"
    ),
    list_flag: bool = typer.Option(
        False, "--list", "-l", help="List information", is_flag=True
    ),
    list_arg: str = typer.Argument(
        None, help="Optional argument for --list: 'language' or 'style'"
    ),
    stage_tracked: bool = typer.Option(
        False, "--all", "-a", help="Stage all tracked files"
    ),
    squash: bool = typer.Option(
        False, "--squash", "-s", help="Squash commits on this branch"
    ),
    update: bool = typer.Option(False, "--update", "-u", help="Check for updates"),
):
    """
    CLI entry point for git-cai-cli.
    """
    if help_flag:
        print_help_and_exit()

    if version:
        from git_cai_cli._version import __version__

        typer.echo(f"git-cai-cli version: {__version__}")
        raise typer.Exit()

    mode = resolve_mode(list_flag=list_flag, squash=squash, update=update)

    validate_options(
        mode=mode,
        stage_tracked=stage_tracked,
        enable_debug=enable_debug,
        help_flag=help_flag,
        version_flag=version,
    )

    run(
        mode=mode,
        enable_debug=enable_debug,
        list_arg=list_arg,
        stage_tracked=stage_tracked,
    )


if __name__ == "__main__":
    app()
