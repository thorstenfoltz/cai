"""
Explain a change in plain prose (`--explain`).

Describes the staged diff, or the diff of a given commit-ish, and prints the
result to stdout. Read-only: nothing is committed and git state is untouched.
"""

import logging
import subprocess

import typer
from git_cai_cli.core.generation import prepare, run_generation
from git_cai_cli.core.gitutils import (
    apply_diff_limit,
    get_commit_diff,
    git_diff_excluding,
    repo_name_from_root,
)
from git_cai_cli.core.llm import CommitMessageGenerator

log = logging.getLogger(__name__)


def run_explain(
    *,
    rev: str | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
    temperature_override: float | None = None,
    time_flag: bool = False,
    context: str | None = None,
    sql_override: bool | None = None,
    allow_secrets: bool = False,
) -> None:
    """
    Explain the staged diff, or the diff of ``rev`` when given.

    Args:
        rev: Optional. Commit-ish to explain instead of the staged changes.
        provider_override: Optional. Provider override for this invocation.
        model_override: Optional. Model override for this invocation.
        temperature_override: Optional. Temperature override.
        time_flag: Whether to log generation time.
        context: Optional. Extra context for the LLM.
        allow_secrets: Bypass the local secret scan.
    """
    repo_root, config, provider, token = prepare(
        provider_override, model_override, temperature_override, sql_override
    )

    if rev:
        try:
            diff = get_commit_diff(repo_root, rev)
        except subprocess.CalledProcessError as exc:
            log.error("Not a valid commit: '%s'", rev)
            raise typer.Exit(code=1) from exc
    else:
        diff = git_diff_excluding(repo_root)

    if not diff.strip():
        log.info("Nothing to explain (no staged changes / empty commit).")
        return

    diff = apply_diff_limit(diff, config, label="Diff")

    generator = CommitMessageGenerator(token, config, provider)
    generator.kind = "explain"
    generator.repo = repo_name_from_root(repo_root)
    generator.allow_secrets = allow_secrets

    explanation = run_generation(
        provider=provider,
        token=token,
        generator=generator,
        build=lambda: generator.build_explain_request(diff, context=context),
        spinner_text="Explaining changes",
        measure=time_flag or config.get("measure_time", False),
    )

    typer.echo(explanation)
