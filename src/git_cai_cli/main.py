"""
Main entry point for the Git CAI CLI tool.
Handles command-line arguments, logging configuration, and mode dispatching.
"""

import logging
import sys
import time
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


def _relpaths_from_repo(repo_root: Path, paths: list[str]) -> list[str]:
    """Return paths expressed relative to the repository root.

    Absolute paths inside the repo are rewritten to repo-relative form; paths
    already relative (or living outside the repo) are returned unchanged.
    """
    rels: list[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_absolute():
            try:
                p = p.resolve().relative_to(repo_root.resolve())
            except ValueError:
                pass
        rels.append(str(p))
    return rels


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
    conventional: bool = False,
    branch_context: bool = False,
    crazy: bool,
    provider_override: str | None = None,
    model_override: str | None = None,
    time_flag: bool = False,
    context: str | None = None,
    timeout_override: int | None = None,
    full_files_override: bool = False,
    files_override: list[str] | None = None,
    base_override: str | None = None,
) -> None:
    """
    Main function to run the Git CAI CLI tool.
    Handles different modes of operation based on command-line arguments.
    """
    configure_logging(enable_debug)
    ensure_git_alias()

    # Lazy imports
    from git_cai_cli.core.config import (
        TOKENLESS_PROVIDERS,
        apply_cli_overrides,
        apply_provider_overrides,
        load_config,
        load_token,
    )
    from git_cai_cli.core.gitutils import (
        collect_staged_file_contents,
        commit_with_edit_template,
        find_git_root,
        get_last_commit_diff,
        git_diff_excluding,
    )
    from git_cai_cli.core.llm import CommitMessageGenerator
    from git_cai_cli.core.options import CliManager
    from git_cai_cli.core.spinner import Spinner
    from git_cai_cli.core.validate import _validate_llm_call

    log = logging.getLogger(__name__)
    manager = CliManager(package_name="git-cai-cli")

    if stage_tracked:
        manager.stage_tracked_files()

    if mode is Mode.LIST:
        manager.handle_list(list_arg)
        return

    if mode is Mode.SQUASH:
        manager.squash_branch(
            provider_override=provider_override,
            model_override=model_override,
            time_flag=time_flag,
            squash_arg=list_arg,
            context=context,
        )
        return

    if mode is Mode.PR:
        from git_cai_cli.core.pr import run_pr

        run_pr(
            provider_override=provider_override,
            model_override=model_override,
            time_flag=time_flag,
            base_override=base_override,
            context=context,
        )
        return

    if mode is Mode.UPDATE:
        manager.check_and_update()
        return

    is_amend = mode is Mode.AMEND

    # Default mode: generate commit message (COMMIT or AMEND)
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        raise typer.Exit(code=1)

    config = load_config()
    apply_provider_overrides(config, provider_override, model_override)
    apply_cli_overrides(
        config,
        conventional=conventional,
        branch_context=branch_context,
        timeout_override=timeout_override,
        full_files_override=full_files_override,
    )

    if config.get("branch_context", False):
        from git_cai_cli.core.gitutils import get_current_branch

        branch_name = get_current_branch()
        if branch_name:
            config["branch_name"] = branch_name

    provider = config["default"]
    token = load_token(config=config)

    if is_amend:
        diff = get_last_commit_diff(repo_root)
        if not diff.strip():
            log.error("No previous commit found or commit has no diff.")
            raise typer.Exit(code=1)
    else:
        if files_override:
            log.info(
                "Restricting diff to files (-f/--files): %s",
                ", ".join(_relpaths_from_repo(repo_root, files_override)),
            )
        diff = git_diff_excluding(repo_root, files=files_override)
        if not diff.strip():
            log.info("No changes to commit. Did you run 'git add'?")
            raise typer.Exit()

        if config.get("full_files", False):
            log.info(
                "Full file contents enabled (-F/--full-files) — "
                "attaching complete file bodies alongside the diff."
            )
            file_dump = collect_staged_file_contents(repo_root, files=files_override)
            if file_dump:
                diff = f"{diff}\n\n--- Full file contents ---\n{file_dump}"

    measure = time_flag or config.get("measure_time", False)
    start = time.perf_counter() if measure else None

    generator = CommitMessageGenerator(token, config, provider)
    try:
        try:
            spinner_text = (
                "Regenerating commit message"
                if is_amend
                else "Generating commit message"
            )
            with Spinner(spinner_text):
                commit_message = _validate_llm_call(
                    generator.generate,
                    diff,
                    context=context,
                    token=token,
                    requires_token=provider not in TOKENLESS_PROVIDERS,
                )
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
    finally:
        generator.close()

    if start is not None:
        elapsed = time.perf_counter() - start
        log.info("Commit message generated in %.2fs", elapsed)

    if crazy:
        rc = manager.commit_crazy(commit_message, amend=is_amend)
        raise typer.Exit(code=rc)

    commit_with_edit_template(commit_message, amend=is_amend)
