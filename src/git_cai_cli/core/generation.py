"""
Shared prologue and send-loop for the read-only generator modes
(--explain, --split, --changelog, --release).

Mirrors the flow in `core.pr` — resolve repo/config/provider/token, then
send one request under a spinner — without ever mutating git state.
"""

import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable

import typer
from git_cai_cli.core.config import (
    TOKENLESS_PROVIDERS,
    apply_cli_overrides,
    apply_provider_overrides,
    load_config,
    load_token,
)
from git_cai_cli.core.gitutils import find_git_root
from git_cai_cli.core.secrets import SecretLeakError, format_findings
from git_cai_cli.core.spinner import Spinner
from git_cai_cli.core.validate import _validate_llm_call

log = logging.getLogger(__name__)


def prepare(
    provider_override: str | None,
    model_override: str | None,
    temperature_override: float | None,
    sql_override: bool | None,
) -> tuple[Path, dict[str, Any], str, str | None]:
    """Resolve repo root, config, provider, and token for a read-only mode.

    Exits with a friendly message when run outside a Git repository or when
    the active provider needs a token that is not configured.
    """
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        raise typer.Exit(code=1)

    from git_cai_cli.core import stats as stats_module

    config = load_config()
    apply_provider_overrides(
        config, provider_override, model_override, temperature_override
    )
    apply_cli_overrides(config, sql_override=sql_override)
    stats_module.log_state(config)

    provider = config["default"]
    token = load_token(config=config)
    if provider not in TOKENLESS_PROVIDERS and not token:
        # Logs where to put the token, never the token itself.
        # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        log.error(
            "Missing %s token in %s/.config/cai/tokens.yml",
            provider,
            Path.home(),
        )
        sys.exit(1)

    return repo_root, config, provider, token


def run_generation(
    *,
    provider: str,
    token: str | None,
    generator: Any,
    build: Callable[[], tuple[str, str]],
    spinner_text: str,
    measure: bool,
) -> str:
    """Build the request, send it under a spinner, and return the LLM text.

    ``build`` is a zero-arg callable returning ``(content, system_prompt)``.
    It runs before the spinner starts so its config logging does not
    interleave with the live spinner frames.
    """
    start = time.perf_counter() if measure else None
    content, system_prompt = build()

    try:
        try:
            with Spinner(spinner_text):
                result = _validate_llm_call(
                    generator.send,
                    content,
                    system_prompt,
                    token=token,
                    requires_token=provider not in TOKENLESS_PROVIDERS,
                )
        except SecretLeakError as leak:
            log.error("%s", format_findings(leak.findings))
            log.error("Aborting. Re-run with --allow-secrets to override.")
            sys.exit(1)
        except ValueError as e:
            log.error("%s", e)
            sys.exit(1)
    finally:
        generator.close()

    if start is not None:
        elapsed = time.perf_counter() - start
        log.info("%s in %.2fs", spinner_text, elapsed)
        generator.record_elapsed(int(elapsed * 1000))

    return result
