"""
CLI entry point for git-cai-cli.
"""

import logging

import typer

log = logging.getLogger(__name__)
from git_cai_cli.cli.helptext import print_help_and_exit
from git_cai_cli.cli.modes import resolve_mode, validate_options
from git_cai_cli.main import run

app = typer.Typer(add_completion=False, help=None, no_args_is_help=False)


@app.callback(invoke_without_command=True)
def callback(
    version: bool = typer.Option(
        False, "-v", "--version", help="Show version", is_eager=True
    ),
    help_flag: bool = typer.Option(
        False, "-h", "--help", help="Show help", is_eager=True
    ),
    install_completion: bool = typer.Option(
        False,
        "--install-completion",
        "-i",
        help="Install shell completion for git-cai",
        is_eager=True,
    ),
    amend: bool = typer.Option(
        False, "-A", "--amend", help="Regenerate and amend the last commit message"
    ),
    conventional: bool = typer.Option(
        False,
        "-C",
        "--conventional",
        help="Use Conventional Commits format (type(scope): description)",
    ),
    crazy: bool = typer.Option(
        False, "-c", "--crazy", help="Commit immediately without opening editor"
    ),
    enable_debug: bool = typer.Option(
        False, "--debug", "-d", help="Enable debug logging"
    ),
    generate_config: bool = typer.Option(
        False,
        "-g",
        "--generate-config",
        help="Generate default cai_config.yml in the current directory",
    ),
    generate_prompts: bool = typer.Option(
        False,
        "-p",
        "--generate-prompts",
        help="Generate default commit/squash prompt files in the current directory",
    ),
    list_flag: bool = typer.Option(
        False, "--list", "-l", help="List information", is_flag=True
    ),
    list_arg: str = typer.Argument(
        None, help="Optional argument for --list: 'language', 'style' or 'editor'"
    ),
    stage_tracked: bool = typer.Option(
        False, "--all", "-a", help="Stage all tracked files"
    ),
    squash: bool = typer.Option(
        False, "--squash", "-s", help="Squash commits on this branch"
    ),
    update: bool = typer.Option(False, "--update", "-u", help="Check for updates"),
    set_config: str = typer.Option(
        None,
        "-S",
        "--set",
        help="Set a config value in repo config (key=value). Requires existing repo config.",
    ),
    set_home: str = typer.Option(
        None,
        "-H",
        "--set-home",
        help="Set a config value in home config (key=value). Always targets ~/.config/cai/.",
    ),
    provider: str = typer.Option(
        None, "--provider", "-P", help="Override LLM provider for this invocation"
    ),
    model: str = typer.Option(
        None, "--model", "-m", help="Override model (requires --provider)"
    ),
    time_flag: bool = typer.Option(
        False, "--time", "-t", help="Measure and log generation time"
    ),
):
    """
    CLI entry point for git-cai-cli.
    """
    if help_flag:
        print_help_and_exit()

    if version:
        from git_cai_cli._version import __version__

        typer.echo(f"cai version: {__version__}")
        raise typer.Exit()

    if install_completion:
        from git_cai_cli.core.completion import install_completion as do_install

        do_install()
        raise typer.Exit()

    mode = resolve_mode(amend=amend, list_flag=list_flag, squash=squash, update=update)

    validate_options(
        mode=mode,
        stage_tracked=stage_tracked,
        enable_debug=enable_debug,
        help_flag=help_flag,
        version_flag=version,
        provider_override=provider,
        model_override=model,
        time_flag=time_flag,
    )

    if generate_config:
        from git_cai_cli.core.options import CliManager

        manager = CliManager(package_name="git-cai-cli")

        try:
            manager.generate_config_here()
            typer.echo("cai_config.yml created in current directory.")
        except RuntimeError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)

        raise typer.Exit()

    if generate_prompts:
        from git_cai_cli.core.options import CliManager

        manager = CliManager(package_name="git-cai-cli")

        try:
            manager.generate_prompts_here()
            typer.echo(
                "commit_prompt.md and squash_prompt.md created in current directory."
            )
        except RuntimeError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)

        raise typer.Exit()

    if set_config or set_home:
        from git_cai_cli.core.config import set_config_value
        from git_cai_cli.main import configure_logging

        configure_logging(enable_debug)

        raw = set_home if set_home else set_config
        force_home = set_home is not None

        if "=" not in raw:
            log.error("Invalid format: expected key=value, got '%s'", raw)
            raise typer.Exit(code=1)

        key, value = raw.split("=", 1)

        try:
            target = set_config_value(key, value, force_home=force_home)
            log.info("Configuration updated: %s = %s in %s", key, value, target)
        except ValueError as e:
            log.error("Failed to set config: %s", e)
            raise typer.Exit(code=1)

        raise typer.Exit()

    run(
        mode=mode,
        enable_debug=enable_debug,
        list_arg=list_arg,
        stage_tracked=stage_tracked,
        conventional=conventional,
        crazy=crazy,
        provider_override=provider,
        model_override=model,
        time_flag=time_flag,
    )


if __name__ == "__main__":
    app()
