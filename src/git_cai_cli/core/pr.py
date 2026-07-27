"""
Generate a Pull Request description from the commits between the current
branch and its base branch.

This mode never modifies git state: it only reads commit history and
either prints the generated Markdown to stdout or writes it to a file in
the repository root, depending on `pr_to_file` in config.
"""

import logging
import subprocess
import sys
import time
from pathlib import Path

import typer
from git_cai_cli.core.config import (
    TOKENLESS_PROVIDERS,
    apply_provider_overrides,
    load_config,
    load_token,
)
from git_cai_cli.core.gitutils import (
    apply_diff_limit,
    changed_files_range,
    commit_log_range,
    detect_base_branch,
    find_git_root,
    merge_base,
    repo_name_from_root,
)
from git_cai_cli.core.llm import CommitMessageGenerator
from git_cai_cli.core.secrets import SecretLeakError, format_findings
from git_cai_cli.core.spinner import Spinner
from git_cai_cli.core.validate import _validate_llm_call

log = logging.getLogger(__name__)


def run_pr(
    provider_override: str | None = None,
    model_override: str | None = None,
    temperature_override: float | None = None,
    time_flag: bool = False,
    base_override: str | None = None,
    context: str | None = None,
    sql_override: bool | None = None,
    allow_secrets: bool = False,
) -> None:
    """
    Generate a PR description for the current branch.

    Args:
        provider_override: Optional. Provider override for this invocation.
        model_override: Optional. Model override for this invocation.
        time_flag: Whether to log generation time.
        base_override: Optional. Explicit base branch (e.g. "develop").
        context: Optional. Extra context for the LLM.
    """
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        raise typer.Exit(code=1)

    config = load_config()
    apply_provider_overrides(
        config, provider_override, model_override, temperature_override
    )

    from git_cai_cli.core import stats as stats_module
    from git_cai_cli.core.config import apply_cli_overrides

    apply_cli_overrides(config, sql_override=sql_override)
    stats_module.log_state(config)

    provider = config["default"]
    token = load_token(config=config)

    if provider not in TOKENLESS_PROVIDERS and not token:
        log.error(
            "Missing %s token in %s/.config/cai/tokens.yml",  # nosemgrep
            provider,
            Path.home(),
        )
        sys.exit(1)

    try:
        base_branch = base_override or detect_base_branch()
    except ValueError as e:
        log.error("%s", e)
        raise typer.Exit(code=1)

    log.info("Using base branch: %s", base_branch)

    try:
        merge_base_sha = merge_base(base_branch)
    except subprocess.CalledProcessError as e:
        log.error(
            "Failed to compute merge-base between '%s' and HEAD: %s",
            base_branch,
            e,
        )
        raise typer.Exit(code=1)

    commit_log = commit_log_range(f"{merge_base_sha}..HEAD")
    if not commit_log:
        log.info("No commits between %s and HEAD — nothing to describe.", base_branch)
        return

    commit_log = apply_diff_limit(commit_log, config, label="Commit log")

    changed_files = changed_files_range(f"{merge_base_sha}..HEAD")

    measure = time_flag or config.get("measure_time", False)
    start = time.perf_counter() if measure else None

    generator = CommitMessageGenerator(token, config, provider)
    generator.kind = "pr"
    generator.repo = repo_name_from_root(repo_root)
    generator.allow_secrets = allow_secrets
    content, system_prompt = generator.build_pr_request(
        commit_log, changed_files, context=context
    )
    try:
        try:
            with Spinner("Generating PR description"):
                description = _validate_llm_call(
                    generator.send,
                    content,
                    system_prompt,
                    token=token,
                    requires_token=provider not in TOKENLESS_PROVIDERS,
                )
        except SecretLeakError as leak:
            log.error("%s", format_findings(leak.findings))
            log.error(
                "Aborting PR generation. Re-run with --allow-secrets to override."
            )
            sys.exit(1)
        except ValueError as e:
            log.error("%s", e)
            sys.exit(1)
    finally:
        generator.close()

    if start is not None:
        elapsed = time.perf_counter() - start
        log.info("PR description generated in %.2fs", elapsed)
        generator.record_elapsed(int(elapsed * 1000))

    if config.get("pr_to_file", False):
        filename = config.get("pr_file_name") or "PR_DESCRIPTION.md"
        out_path = repo_root / filename
        out_path.write_text(description.strip() + "\n", encoding="utf-8")
        log.info("PR description written to %s", out_path)
    else:
        typer.echo(description)
