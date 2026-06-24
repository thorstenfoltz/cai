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


def _log_stats_state(config: dict) -> None:
    """Backwards-compatible wrapper around ``stats.log_state``.

    The implementation moved into ``core.stats`` to break a cyclic
    import (``core.pr`` / ``core.squash`` used to import this from
    ``main``). Kept here so existing test imports continue to work.
    """
    from git_cai_cli.core import stats as stats_module

    stats_module.log_state(config)


def _route_false_alarm(findings: list, repo_root: Path | None) -> None:
    """After a confirmed false alarm, offer to remember each flagged file.

    For each distinct flagged path, prompt whether to add it to ``.caiignore``
    (drop the file from git-cai), to ``secret_scan_exclude`` in the active
    config (keep the file but skip its scan), or skip (remember nothing).
    Findings without a path are unattributable and skipped.
    """
    from git_cai_cli.core.config import add_to_secret_scan_exclude
    from git_cai_cli.core.gitutils import append_to_caiignore

    seen: set[str] = set()
    for finding in findings:
        path = finding.path
        if not path or path in seen:
            continue
        seen.add(path)

        typer.echo(f"\nFalse alarm for: {path}", err=True)
        typer.echo("How should git-cai remember this file?", err=True)
        typer.echo(
            "  1) .caiignore — drop the file from git-cai entirely "
            "(it is never sent to the LLM again)",
            err=True,
        )
        typer.echo(
            "  2) config — keep sending the file, but skip its secret scan "
            "from now on (added to secret_scan_exclude)",
            err=True,
        )
        typer.echo("  3) skip — send it this once; remember nothing", err=True)
        choice = typer.prompt("Choose", default="3").strip()

        if choice == "1":
            if repo_root is None:
                typer.echo("Not in a git repo; cannot write .caiignore.", err=True)
                continue
            target = append_to_caiignore(repo_root, path)
            typer.echo(f"Added {path} to {target}", err=True)
        elif choice == "2":
            target = add_to_secret_scan_exclude(path)
            typer.echo(f"Added {path} to secret_scan_exclude in {target}", err=True)


def run(
    *,
    mode: Mode,
    enable_debug: bool,
    list_arg: str | None,
    stage_tracked: bool,
    conventional: bool | None = None,
    branch_context: bool | None = None,
    crazy: bool,
    provider_override: str | None = None,
    model_override: str | None = None,
    time_flag: bool = False,
    context: str | None = None,
    timeout_override: int | None = None,
    full_files_override: bool | None = None,
    files_override: list[str] | None = None,
    base_override: str | None = None,
    sql_override: bool | None = None,
    stats_since: str | None = None,
    stats_json: bool = False,
    stats_reset: bool = False,
    signoff: bool | None = None,
    print_only: bool = False,
    temperature_override: float | None = None,
    style_override: str | None = None,
    language_override: str | None = None,
    emoji_override: bool | None = None,
    live_check: bool = False,
    allow_secrets: bool = False,
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
        get_last_commit_message,
        git_diff_excluding,
        repo_name_from_root,
        truncate_diff,
    )
    from git_cai_cli.core.llm import CommitMessageGenerator
    from git_cai_cli.core.options import CliManager
    from git_cai_cli.core.spinner import Spinner
    from git_cai_cli.core.validate import _validate_llm_call

    log = logging.getLogger(__name__)
    manager = CliManager(package_name="git-cai-cli")

    if stage_tracked:
        manager.stage_tracked_files()

    if mode is Mode.INIT:
        from git_cai_cli.core.init import run_init_wizard

        rc = run_init_wizard()
        raise typer.Exit(code=rc)

    if mode is Mode.LIST:
        manager.handle_list(list_arg)
        return

    if mode is Mode.CHECK:
        from git_cai_cli.core.doctor import run_check

        raise typer.Exit(code=run_check(live=live_check))

    if mode is Mode.STATS:
        from git_cai_cli.core import stats

        config = load_config()
        if stats_reset:
            removed = stats.reset(config)
            typer.echo(f"Cleared {removed} stats event(s).")
            return
        typer.echo(stats.show(config, since=stats_since, as_json=stats_json))
        return

    if mode is Mode.SQUASH:
        manager.squash_branch(
            provider_override=provider_override,
            model_override=model_override,
            temperature_override=temperature_override,
            time_flag=time_flag,
            squash_arg=list_arg,
            context=context,
            sql_override=sql_override,
            signoff=signoff,
            allow_secrets=allow_secrets,
        )
        return

    if mode is Mode.PR:
        from git_cai_cli.core.pr import run_pr

        run_pr(
            provider_override=provider_override,
            model_override=model_override,
            temperature_override=temperature_override,
            time_flag=time_flag,
            base_override=base_override,
            context=context,
            sql_override=sql_override,
            allow_secrets=allow_secrets,
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
    apply_provider_overrides(
        config, provider_override, model_override, temperature_override
    )
    apply_cli_overrides(
        config,
        conventional=conventional,
        branch_context=branch_context,
        timeout_override=timeout_override,
        full_files_override=full_files_override,
        sql_override=sql_override,
        style_override=style_override,
        language_override=language_override,
        emoji_override=emoji_override,
    )

    _log_stats_state(config)

    branch_name: str | None = None
    if config.get("branch_context", False):
        from git_cai_cli.core.gitutils import get_current_branch

        branch_name = get_current_branch()

    provider = config["default"]
    token = load_token(config=config)

    previous_message: str | None = None
    if is_amend:
        diff = get_last_commit_diff(repo_root)
        if not diff.strip():
            log.error("No previous commit found or commit has no diff.")
            raise typer.Exit(code=1)
        previous_message = get_last_commit_message(repo_root) or None
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

    max_diff_bytes = int(config.get("max_diff_bytes", 0) or 0)
    diff, was_truncated = truncate_diff(diff, max_diff_bytes)
    if was_truncated:
        log.warning(
            "Diff exceeded max_diff_bytes=%d and was truncated before sending "
            "to the LLM. Raise max_diff_bytes or use -f/--files to scope the "
            "diff if you need the full context.",
            max_diff_bytes,
        )

    measure = time_flag or config.get("measure_time", False)
    start = time.perf_counter() if measure else None

    from git_cai_cli.core.secrets import SecretLeakError, format_findings

    generator = CommitMessageGenerator(token, config, provider, branch_name=branch_name)
    generator.kind = "amend" if is_amend else "commit"
    generator.repo = repo_name_from_root(repo_root)
    generator.allow_secrets = allow_secrets
    spinner_text = (
        "Regenerating commit message" if is_amend else "Generating commit message"
    )
    # Build the prompt (and emit its config logging) before the spinner starts,
    # so that routine info does not interleave with the live spinner frames.
    content, system_prompt = generator.build_commit_request(
        diff, context=context, previous_message=previous_message
    )
    try:
        while True:
            try:
                with Spinner(spinner_text):
                    commit_message = _validate_llm_call(
                        generator.send,
                        content,
                        system_prompt,
                        token=token,
                        requires_token=provider not in TOKENLESS_PROVIDERS,
                    )
                break
            except SecretLeakError as leak:
                typer.echo(format_findings(leak.findings), err=True)
                if crazy or not sys.stdin.isatty():
                    typer.echo(
                        "Aborting: potential secret(s) in the diff. "
                        "Re-run with --allow-secrets to override.",
                        err=True,
                    )
                    raise typer.Exit(code=1)
                if not typer.confirm(
                    "Send this content to the provider anyway?", default=False
                ):
                    typer.echo("Aborted. Nothing was sent.", err=True)
                    raise typer.Exit(code=1)
                _route_false_alarm(leak.findings, repo_root)
                generator.allow_secrets = True
            except ValueError as e:
                typer.echo(f"Error: {e}", err=True)
                raise typer.Exit(code=1)
    finally:
        generator.close()

    if start is not None:
        elapsed = time.perf_counter() - start
        log.info("Commit message generated in %.2fs", elapsed)
        generator.record_elapsed(int(elapsed * 1000))

    apply_signoff = signoff if signoff is not None else config.get("signoff", False)
    if apply_signoff:
        from git_cai_cli.core.gitutils import append_signoff

        try:
            commit_message = append_signoff(commit_message)
        except RuntimeError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)

    if print_only:
        typer.echo(commit_message)
        return

    if crazy:
        rc = manager.commit_crazy(commit_message, amend=is_amend)
        raise typer.Exit(code=rc)

    commit_with_edit_template(commit_message, amend=is_amend)
