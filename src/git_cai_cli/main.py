"""
Main entry point for the Git CAI CLI tool.
Handles command-line arguments, logging configuration, and mode dispatching.
"""

import logging
import sys
from pathlib import Path

import typer
from git_cai_cli.cli.modes import Mode


def configure_logging(debug: bool) -> None:
    """
    Configures the logging settings based on the debug flag.
    """
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def ensure_git_alias() -> None:
    """
    Ensures that the script is invoked as a Git alias (i.e., 'git cai')
    """
    invoked_as = Path(sys.argv[0]).name
    if not invoked_as.startswith("git-"):
        typer.echo("This command must be run as 'git cai'", err=True)
        raise typer.Exit(code=1)


def run(
    *,
    mode: Mode,
    enable_debug: bool,
    list_arg: str | None,
    stage_tracked: bool,
    crazy: bool,
) -> None:
    """
    Main function to run the Git CAI CLI tool.
    Handles different modes of operation based on command-line arguments.
    """
    configure_logging(enable_debug)
    ensure_git_alias()

    # Lazy imports
    from git_cai_cli.core.config import TOKENLESS_PROVIDERS, load_config, load_token
    from git_cai_cli.core.gitutils import (
        commit_with_edit_template,
        find_git_root,
        git_diff_excluding,
    )
    from git_cai_cli.core.llm import CommitMessageGenerator
    from git_cai_cli.core.options import CliManager
    from git_cai_cli.core.validate import _validate_llm_call

    log = logging.getLogger(__name__)
    manager = CliManager(package_name="git-cai-cli")

    if stage_tracked:
        manager.stage_tracked_files()

    if mode is Mode.LIST:
        if list_arg is None:
            typer.echo(manager.list())
            return

        option = list_arg.lower()
        if option == "editor":
            for editor in manager.editor_list():
                typer.echo(editor)
            return
        if option == "language":
            typer.echo(manager.print_available_languages())
            return
        if option == "style":
            for name, details in manager.styles().items():
                typer.echo(f"{name.capitalize()}: {details['description']}")
                typer.echo(f"  Example: {details['example']}\n")
            return

        typer.echo(
            f"Error: unknown list option '{list_arg}'. "
            "Valid values are 'language' or 'style'.",
            err=True,
        )
        raise typer.Exit(code=1)

    if mode is Mode.SQUASH:
        manager.squash_branch()
        return

    if mode is Mode.UPDATE:
        manager.check_and_update()
        return

    # Default mode: generate commit message
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        raise typer.Exit(code=1)

    config = load_config()
    provider = config["default"]
    token = load_token(config=config)

    diff = git_diff_excluding(repo_root)
    if not diff.strip():
        log.info("No changes to commit. Did you run 'git add'?")
        raise typer.Exit()

    generator = CommitMessageGenerator(token, config, provider)
    try:
        try:
            commit_message = _validate_llm_call(
                generator.generate,
                diff,
                token=token,
                requires_token=provider not in TOKENLESS_PROVIDERS,
            )
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
    finally:
        generator.close()

    if crazy:
        rc = manager.commit_crazy(commit_message)
        raise typer.Exit(code=rc)

    commit_with_edit_template(commit_message)
