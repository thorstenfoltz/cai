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
  -E, --temperature FLOAT  Override the active provider's sampling temperature for this invocation
  -e, --emoji              Toggle emoji prefixes (use --no-emoji to disable)
  -F, --full-files         Send the full contents of affected files alongside the diff
  -f, --files PATH         Limit the diff (and full files) to PATH; repeat the flag for multiple files
  -g, --generate-config    Generate default cai_config.yml in the current directory
  -H, --set-home KEY=VALUE Set a config value in home config (~/.config/cai/)
  -h, --help               Show this help message or opens manual
  -I, --init               Interactive setup wizard (writes home config and tokens.yml)
  -i, --install-completion Install shell completion for git-cai
  -L, --language CODE      Override the commit message language (e.g. de, fr, none)
  -l, --list [TYPE]        List information. TYPE: config, editor, language,
                           model, path, provider, style
  -m, --model NAME         Override model for this invocation (requires --provider)
  -o, --signoff            Append a `Signed-off-by:` trailer (git user.name / user.email)
  -P, --provider NAME      Override LLM provider for this invocation
  -p, --generate-prompts   Generate default commit/squash/full_files/pr prompt files
      --print              Print the generated commit message to stdout and exit (no commit)
  -q, --sql true|false     Override stats writing for this run (wins over config)
  -r, --PR                 Generate a Pull Request description from the commits on this branch
      --base BRANCH        Base branch for --PR (overrides auto-detection)
  -S, --set KEY=VALUE      Set a config value in repo config (requires existing repo config)
  -s, --squash [N|HASH]    Squash commits on this branch and summarize them
                           No argument: squash all commits since branch checkout
                           Number: squash the last N commits
                           Hash: squash up to and including that commit
  -T, --timeout SECONDS    HTTP timeout in seconds (overrides config; default 30)
  -t, --time               Measure and log commit message generation time
  -u, --update             Check for updates
  -v, --version            Show installed version
  -x, --context TEXT       Provide extra context for the LLM (e.g. ticket number, reason)
  -y, --style NAME         Override the commit message style (e.g. funny, neutral, none)
  -z, --stats              Show local-only usage analytics (commits, tokens, latency)
      --since YYYY-MM-DD   Filter --stats to events on or after this date
      --json               Render --stats output as JSON instead of text
      --reset-stats        Delete all rows from the local stats DB

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
