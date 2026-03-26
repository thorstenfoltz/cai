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
  -A, --amend              Regenerate and amend the last commit message
  -a, --all                Stage all modified and deleted files that are already tracked by Git
  -b, --branch             Include current branch name as context for the LLM
  -C, --conventional       Use Conventional Commits format (type(scope): description)
  -c, --crazy              Commit immediately without opening editor (trust LLM output)
  -d, --debug              Enable debug logging
  -g, --generate-config    Generate default cai_config.yml in the current directory
  -H, --set-home KEY=VALUE Set a config value in home config (~/.config/cai/)
  -h, --help               Show this help message or opens manual
  -i, --install-completion Install shell completion for git-cai
  -l, --list               List information about available languages, styles, and editors
  -m, --model NAME         Override model for this invocation (requires --provider)
  -P, --provider NAME      Override LLM provider for this invocation
  -p, --generate-prompts   Generate default commit_prompt.md and squash_prompt.md
  -S, --set KEY=VALUE      Set a config value in repo config (requires existing repo config)
  -s, --squash             Squash commits on this branch and summarize them
  -t, --time               Measure and log commit message generation time
  -u, --update             Check for updates
  -v, --version            Show installed version

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
