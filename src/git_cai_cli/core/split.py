"""
Suggest how to break one staged change into several commits (`--split`).

Groups the staged files into logically coherent commits at file granularity.
Advisory only: the plan is printed, nothing is staged, reset, or committed.
"""

import logging

import typer
from git_cai_cli.core.generation import prepare, run_generation
from git_cai_cli.core.gitutils import (
    apply_diff_limit,
    git_diff_excluding,
    repo_name_from_root,
    staged_file_names,
)
from git_cai_cli.core.llm import CommitMessageGenerator

log = logging.getLogger(__name__)


def run_split(
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
    Print a suggested split of the staged change into several commits.

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

    diff = git_diff_excluding(repo_root)
    if not diff.strip():
        log.info("No staged changes to split. Did you run 'git add'?")
        return

    file_list = staged_file_names(repo_root)

    diff = apply_diff_limit(diff, config, label="Diff")

    generator = CommitMessageGenerator(token, config, provider)
    generator.kind = "split"
    generator.repo = repo_name_from_root(repo_root)
    generator.allow_secrets = allow_secrets

    plan = run_generation(
        provider=provider,
        token=token,
        generator=generator,
        build=lambda: generator.build_split_request(diff, file_list, context=context),
        spinner_text="Planning commit split",
        measure=time_flag or config.get("measure_time", False),
    )

    typer.echo(plan)
    typer.echo(
        "\nTo apply a group: 'git reset', then 'git add <files>' and "
        "'git cai' for each group above."
    )
