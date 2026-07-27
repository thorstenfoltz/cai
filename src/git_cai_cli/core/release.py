"""
Print release notes for the commits since the last tag (`--release`).

Read-only: the notes go to stdout and git state is never touched. The notes
are grouped by change type, and headings without entries are omitted.
"""

import logging

import typer
from git_cai_cli.core.generation import prepare, run_generation
from git_cai_cli.core.gitutils import (
    apply_diff_limit,
    commit_log_range,
    last_git_tag,
    repo_name_from_root,
)
from git_cai_cli.core.llm import CommitMessageGenerator

log = logging.getLogger(__name__)


def run_release(
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
    temperature_override: float | None = None,
    time_flag: bool = False,
    context: str | None = None,
    sql_override: bool | None = None,
    allow_secrets: bool = False,
) -> None:
    """
    Print release notes for the commits since the most recent tag.

    Args:
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

    tag = last_git_tag()
    commit_log = commit_log_range(f"{tag}..HEAD" if tag else "HEAD")
    if not commit_log.strip():
        log.info(
            "No commits since %s — nothing to release.",
            tag or "the first commit",
        )
        return

    commit_log = apply_diff_limit(commit_log, config, label="Commit log")

    generator = CommitMessageGenerator(token, config, provider)
    generator.kind = "release"
    generator.repo = repo_name_from_root(repo_root)
    generator.allow_secrets = allow_secrets

    notes = run_generation(
        provider=provider,
        token=token,
        generator=generator,
        build=lambda: generator.build_release_request(commit_log, context=context),
        spinner_text="Generating release notes",
        measure=time_flag or config.get("measure_time", False),
    )

    typer.echo(notes.strip())
