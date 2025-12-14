"""
Main CLI entry point for git-cai-cli
"""

import sys
from pathlib import Path

import typer

app = typer.Typer(add_completion=True, help=None, no_args_is_help=False)

HOME = Path.home()
HELP_TEXT = f"""
Git CAI - AI-powered commit message generator

Usage:
  git cai        Generate commit message from staged changes

Flags:
  -h,                Show this help message
  -a, --all          Stage all modified and deleted files that are already tracked by Git
  -d, --debug        Enable debug logging
  -l, --list         List information about languages and styles available
  -u, --update       Check for updates
  -s, --squash       Squash commits on this branch and summarize them
  -v, --version      Show installed version

Configuration:
  Tokens are loaded from {HOME}/.config/cai/tokens.yml
"""


@app.callback(invoke_without_command=True)
def callback(
    # fast flags
    version: bool = typer.Option(
        False, "-v", "--version", help="Show version", is_eager=True
    ),
    help_flag: bool = typer.Option(
        False, "-h", "--help", help="Show help", is_eager=True
    ),
    # normal flags
    enable_debug: bool = typer.Option(
        False, "--debug", "-d", help="Enable debug logging"
    ),
    list_flag: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List information (languages or styles)",
        is_flag=True,
    ),
    list_arg: str = typer.Argument(
        None,
        help="Optional argument for --list: 'language' or 'style'",
    ),
    stage_tracked: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Stage all modified and deleted files that are already tracked by Git",
    ),
    squash: bool = typer.Option(
        False,
        "--squash",
        "-s",
        help="Squash commits on this branch and summarize them",
    ),
    update: bool = typer.Option(False, "--update", "-u", help="Check for updates"),
):
    """
    CLI bootstrap and argument routing layer.

    This function is invoked by Typer before any command logic executes.
    It is intentionally lightweight and exists to:

    - Handle bootstrap flags (--help, --version) with immediate exit and
      zero-cost execution.
    - Validate flag combinations and enforce CLI semantics
      (mutual exclusivity, debug compatibility).
    - Determine the active execution mode and dispatch control to `main`.

    No heavy imports should live here.
    """
    # fast exit
    if help_flag:
        if enable_debug:
            typer.echo("Error: --debug cannot be used with --help.", err=True)
            raise typer.Exit(code=1)

        typer.echo(HELP_TEXT)
        raise typer.Exit()

    if version:
        if enable_debug:
            typer.echo("Error: --debug cannot be used with --version.", err=True)
            raise typer.Exit(code=1)

        from git_cai_cli._version import __version__

        typer.echo(f"git-cai-cli version: {__version__}")
        raise typer.Exit()

    modes = {
        "list": list_flag,
        "squash": squash,
        "update": update,
    }

    active_modes = [name for name, active in modes.items() if active]

    if stage_tracked and active_modes:
        typer.echo(
            "Error: --all cannot be used with --list, --update, or --squash.",
            err=True,
        )
        raise typer.Exit(code=1)

    if len(active_modes) > 1:
        typer.echo(
            f"Error: options {', '.join('--' + m for m in active_modes)} "
            "cannot be used together.",
            err=True,
        )
        raise typer.Exit(code=1)

    # default behaviour
    main(
        enable_debug=enable_debug,
        list_flag=list_flag,
        list_arg=list_arg,
        stage_tracked=stage_tracked,
        squash=squash,
        update=update,
    )


def main(
    *,
    enable_debug: bool,
    list_flag: bool,
    list_arg: str | None,
    stage_tracked: bool,
    squash: bool,
    update: bool,
):
    """
    Core execution engine for git-cai cli.

    This function contains all operational logic after CLI validation has
    completed. It is responsible for:

    - Enabling logging and debug output.
    - Executing lightweight actions (list, squash, update).
    - Performing the default workflow:
        * locating the Git repository
        * loading configuration and authentication tokens
        * computing the staged diff
        * generating a commit message via the LLM
        * invoking the Git commit editor

    All expensive imports and side effects are intentionally placed here so
    they are executed only when required.
    """

    # Lazy imports
    import logging

    from git_cai_cli.core.config import (
        get_default_config,
        load_config,
        load_token,
    )
    from git_cai_cli.core.gitutils import (
        commit_with_edit_template,
        find_git_root,
        git_diff_excluding,
    )
    from git_cai_cli.core.llm import CommitMessageGenerator
    from git_cai_cli.core.options import CliManager

    logging.basicConfig(
        level=logging.DEBUG if enable_debug else logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger(__name__)

    manager = CliManager(package_name="git-cai-cli")

    # Ensure invoked as 'git cai'
    invoked_as = Path(sys.argv[0]).name
    if not invoked_as.startswith("git-"):
        typer.echo("This command must be run as 'git cai'", err=True)
        raise typer.Exit(code=1)

    # -------------------------
    # Lightweight actions
    # -------------------------
    if list_flag:
        if list_arg is None:
            typer.echo(manager.list())
            raise typer.Exit()

        option = list_arg.lower()

        if option == "language":
            typer.echo(manager.print_available_languages())
            raise typer.Exit()

        if option == "style":
            styles = manager.styles()
            for name, details in styles.items():
                typer.echo(f"{name.capitalize()}: {details['description']}")
                typer.echo(f"  Example: {details['example']}\n")
            raise typer.Exit()

        typer.echo(
            f"Error: unknown list option '{list_arg}'. "
            "Valid values are 'language' or 'style'.",
            err=True,
        )
        raise typer.Exit(code=1)

    if stage_tracked:
        manager.stage_tracked_files()

    if squash:
        manager.squash_branch()
        raise typer.Exit()

    if update:
        manager.check_and_update()
        raise typer.Exit()

    # -------------------------
    # Main workflow
    # -------------------------
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        raise typer.Exit(code=1)

    config = load_config()
    default_model = get_default_config()
    token = load_token(default_model)

    if not token:
        log.error("Missing %s token in ~/.config/cai/tokens.yml", default_model)
        raise typer.Exit(code=1)

    diff = git_diff_excluding(repo_root)
    if not diff.strip():
        log.info("No changes to commit. Did you run 'git add'? Files must be staged.")
        raise typer.Exit()

    generator = CommitMessageGenerator(token, config, default_model)
    commit_message = generator.generate(diff)

    commit_with_edit_template(commit_message)


if __name__ == "__main__":
    app()
