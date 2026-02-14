"""
Help text for git-cai-cli.
"""

from pathlib import Path

import typer

HOME = Path.home()

HELP_TEXT = f"""
Git CAI - AI-powered commit message generator

Usage:
  git cai        Generate commit message from staged changes

Flags:
  -h, --help              Show this help message or opens manual
  -a, --all               Stage all modified and deleted files that are already tracked by Git
  -c, --crazy             Commit immediately without opening editor (trust LLM output)
  -d, --debug             Enable debug logging
  -g, --generate-config   Generate default cai_config.yml in the current directory
  -p, --generate-prompts  Generate default commit_prompt.md and squash_prompt.md in the current directory
  -l, --list              List information about available languages and styles
  -s, --squash            Squash commits on this branch and summarize them
  -u, --update            Check for updates
  -v, --version           Show installed version

Configuration:
  Tokens are loaded from {HOME}/.config/cai/tokens.yml
  Reset to default config by deleting {HOME}/.config/cai/cai_config.yml
  and executing 'git cai' again.
"""


def print_help_and_exit() -> None:
    """
    Print help text and exit.
    """
    typer.echo(HELP_TEXT)
    raise typer.Exit()
