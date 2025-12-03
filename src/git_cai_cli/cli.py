"""
Main function
"""

import logging
import sys
from pathlib import Path

import typer
from git_cai_cli.core.config import get_default_config, load_config, load_token
from git_cai_cli.core.gitutils import (
    commit_with_edit_template,
    find_git_root,
    git_diff_excluding,
)
from git_cai_cli.core.llm import CommitMessageGenerator
from git_cai_cli.core.options import CliManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

app = typer.Typer(add_completion=True, help=None, no_args_is_help=False)

manager = CliManager(package_name="git-cai-cli")


def main() -> None:
    """
    Check for git repo, load access tokens and run git cai
    """
    # Ensure invoked as 'git cai'
    # Only enforce this if we're not just asking for version/help
    if not any(flag in sys.argv for flag in ("--version", "-v", "--help", "-h")):
        invoked_as = Path(sys.argv[0]).name
        if not invoked_as.startswith("git-"):
            print("This command must be run as 'git cai'", file=sys.stderr)
            sys.exit(1)

    # Find the git repo root
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        sys.exit(1)

    # Load configuration and token
    config = load_config()
    default_model = get_default_config()
    log.debug("Default model from config: %s", default_model)
    token = load_token(default_model)
    if not token:
        log.error("Missing %s token in ~/.config/cai/tokens.yml", default_model)
        sys.exit(1)

    # Get git diff
    diff = git_diff_excluding(repo_root)
    if not diff.strip():
        log.info("No changes to commit. Did you run 'git add'? Files must be staged.")
        sys.exit(0)

    # Generate commit message
    generator = CommitMessageGenerator(token, config, default_model)
    commit_message = generator.generate(diff)

    # Open git commit editor with the generated message
    commit_with_edit_template(commit_message)


@app.command()
def run(
    help_flag: bool = typer.Option(False, "-h", help="Show help", is_eager=True),
    enable_debug: bool = typer.Option(
        False, "--debug", "-d", help="Enable debug logging", is_eager=True
    ),
    language: bool = typer.Option(
        False, "--languages", "-l", help="List supported languages", is_eager=True
    ),
    squash: bool = typer.Option(
        False,
        "--squash",
        "-s",
        help="Squash commits on this branch and summarize them",
        is_eager=True,
    ),
    style: bool = typer.Option(
        False, "--style", help="Show available commit message styles", is_eager=True
    ),
    update: bool = typer.Option(
        False, "--update", "-u", help="Check for updates", is_eager=True
    ),
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version", is_eager=True
    ),
):
    """
    Main entry point for the CLI
    """
    if help_flag:
        typer.echo(manager.get_help())
        raise typer.Exit()

    if enable_debug:
        manager.enable_debug()

    if language:
        typer.echo(manager.print_available_languages())
        raise typer.Exit()

    if squash:
        manager.squash_branch()
        raise typer.Exit()

    if style:
        styles = manager.styles()
        for style_name, details in styles.items():
            typer.echo(f"{style_name.capitalize()}: {details['description']}")
            typer.echo(f"  Example: {details['example']}\n")
        raise typer.Exit()

    if update:
        manager.check_and_update()
        raise typer.Exit()

    if version:
        typer.echo(manager.get_version())
        raise typer.Exit()

    main()


if __name__ == "__main__":
    app()
