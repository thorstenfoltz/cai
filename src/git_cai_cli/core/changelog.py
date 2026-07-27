"""
Generate a changelog section from the commits since the last tag (`--changelog`).

Produces a single "Keep a Changelog" style *Unreleased* section. Prints it to
stdout, or prepends it to the changelog file when `changelog_to_file` is set.
Read-only with respect to git state: nothing is committed or tagged.
"""

import logging

import typer
from git_cai_cli.core.generation import prepare, run_generation
from git_cai_cli.core.gitutils import (
    apply_diff_limit,
    changed_files_range,
    commit_log_range,
    last_git_tag,
    repo_name_from_root,
)
from git_cai_cli.core.llm import CommitMessageGenerator

log = logging.getLogger(__name__)


def run_changelog(
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
    Generate an "Unreleased" changelog section for the commits since the last tag.

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
    rev_range = f"{tag}..HEAD" if tag else "HEAD"

    commit_log = commit_log_range(rev_range)
    if not commit_log.strip():
        log.info("No commits since %s — nothing to log.", tag or "the first commit")
        return

    changed_files = changed_files_range(rev_range) if tag else ""

    commit_log = apply_diff_limit(commit_log, config, label="Commit log")

    generator = CommitMessageGenerator(token, config, provider)
    generator.kind = "changelog"
    generator.repo = repo_name_from_root(repo_root)
    generator.allow_secrets = allow_secrets

    section = run_generation(
        provider=provider,
        token=token,
        generator=generator,
        build=lambda: generator.build_changelog_request(
            commit_log, changed_files, context=context
        ),
        spinner_text="Generating changelog",
        measure=time_flag or config.get("measure_time", False),
    )

    if not config.get("changelog_to_file", False):
        typer.echo(section)
        return

    filename = config.get("changelog_file_name") or "CHANGELOG.md"
    path = repo_root / filename
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    body = section.strip() + "\n"
    path.write_text(f"{body}\n{existing}" if existing else body, encoding="utf-8")
    log.info("Changelog section prepended to %s", path)
