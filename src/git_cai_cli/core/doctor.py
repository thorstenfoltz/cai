"""Configuration diagnostics for `git cai --check`.

Offline by default: validates config, the active provider's token, prompt
resolution, and the editor without contacting any provider. With ``live=True``
(``--ping``) it additionally performs one tiny generation against the active
provider to confirm reachability.
"""

import logging
import shlex
import shutil
import stat
import time

import typer

from git_cai_cli.core.config import (
    DEFAULT_CONFIG,
    FALLBACK_CONFIG_FILE,
    TOKENLESS_PROVIDERS,
    TOKENS_FILE,
    _find_repo_config,
    load_config,
    load_token,
)
from git_cai_cli.core.gitutils import get_git_editor
from git_cai_cli.core.validate import _validate_config_keys, _validate_style

log = logging.getLogger(__name__)

_OK = "✓"
_WARN = "⚠"
_FAIL = "✗"


def _line(marker: str, text: str) -> None:
    typer.echo(f"  {marker} {text}")


def run_check(*, live: bool = False) -> int:
    """Run the offline checks (and an optional live probe). Returns an exit code.

    Quiets INFO/DEBUG package logging for the duration so the ✓/✗ report stays
    readable, unless the user explicitly enabled debug logging.
    """
    pkg_logger = logging.getLogger("git_cai_cli")
    prior_level = pkg_logger.level
    if pkg_logger.getEffectiveLevel() > logging.DEBUG:
        pkg_logger.setLevel(logging.WARNING)
    try:
        return _run_check_impl(live=live)
    finally:
        pkg_logger.setLevel(prior_level)


def _run_check_impl(*, live: bool = False) -> int:
    typer.echo("git-cai doctor\n")
    ok = True

    # 1. Which config is authoritative.
    repo_config = _find_repo_config()
    if repo_config:
        _line(_OK, f"Config source: repository ({repo_config})")
    elif FALLBACK_CONFIG_FILE.exists():
        _line(_OK, f"Config source: home ({FALLBACK_CONFIG_FILE})")
    else:
        _line(_WARN, "Config source: built-in defaults (no config file found)")

    # 2. Load + validate config keys. Without a usable config the rest is moot.
    try:
        config = load_config()
        _validate_config_keys(config, DEFAULT_CONFIG)
        _line(_OK, "Config keys valid")
    except (KeyError, ValueError, OSError) as exc:
        _line(_FAIL, f"Config invalid: {exc}")
        typer.echo("\nSome checks failed.")
        return 1

    # 3. Default provider and its block.
    provider = config.get("default")
    block = config.get(provider) if provider else None
    if not provider:
        _line(_FAIL, "No default provider set")
        ok = False
    elif not isinstance(block, dict) or not {"model", "temperature"} <= set(block):
        _line(_FAIL, f"Provider '{provider}' block missing model/temperature")
        ok = False
    else:
        _line(_OK, f"Default provider: {provider} (model {block.get('model')})")

    # 4. Token for the active provider (unless tokenless), plus file permissions.
    if provider in TOKENLESS_PROVIDERS:
        _line(_OK, f"Provider '{provider}' needs no token")
    else:
        token = load_token(config=config)
        if token and token.strip() and not str(token).startswith("PUT-YOUR-"):
            _line(_OK, f"Token present for '{provider}'")
        else:
            _line(_FAIL, f"No usable token for '{provider}' in {TOKENS_FILE}")
            ok = False
        if TOKENS_FILE.exists():
            mode = stat.S_IMODE(TOKENS_FILE.stat().st_mode)
            if mode & 0o077:
                _line(_WARN, f"tokens.yml permissions are {oct(mode)} (expected 0o600)")

    # 5. Prompt resolution (always resolves to at least the hardcoded fallback).
    from git_cai_cli.core.llm import load_prompt_file
    from git_cai_cli.core.prompts_fallback import (
        HARDCODED_COMMIT_PROMPT,
        HARDCODED_FULL_FILES_PROMPT,
        HARDCODED_PR_PROMPT,
        HARDCODED_SQUASH_PROMPT,
    )

    prompt_specs = [
        ("commit", "prompt_file", "commit_prompt.md", HARDCODED_COMMIT_PROMPT),
        ("squash", "squash_prompt_file", "squash_prompt.md", HARDCODED_SQUASH_PROMPT),
        ("full-files", "full_files_prompt_file", "full_files_prompt.md", HARDCODED_FULL_FILES_PROMPT),
        ("pr", "pr_prompt_file", "pr_prompt.md", HARDCODED_PR_PROMPT),
    ]
    for label, key, fname, fallback in prompt_specs:
        text = load_prompt_file(
            config_key=key, config=config, default_filename=fname, hardcoded_fallback=fallback
        )
        if text and text.strip():
            _line(_OK, f"Prompt '{label}' resolves ({len(text)} chars)")
        else:
            _line(_WARN, f"Prompt '{label}' resolved empty")
            ok = False

    # 6. Editor resolvable and on PATH.
    editor = get_git_editor()
    parts = shlex.split(editor) if editor else []
    if parts and shutil.which(parts[0]):
        _line(_OK, f"Editor: {editor}")
    else:
        _line(_FAIL, f"Editor not found on PATH: {editor!r}")
        ok = False

    # 7. Style valid (language always falls back, so it is not a failure case).
    try:
        _validate_style(config.get("style"))
        _line(_OK, f"Style '{config.get('style')}' valid")
    except ValueError as exc:
        _line(_FAIL, f"Style invalid: {exc}")
        ok = False

    if live:
        typer.echo("")
        ok = _live_probe(config, provider) and ok

    typer.echo("")
    if ok:
        typer.echo("All checks passed.")
        return 0
    typer.echo("Some checks failed.")
    return 1


def _live_probe(config: dict, provider: str) -> bool:
    """Send one tiny synthetic diff to the active provider and report reachability."""
    from git_cai_cli.core.llm import CommitMessageGenerator
    from git_cai_cli.core.validate import _validate_llm_call

    token = load_token(config=config)
    generator = CommitMessageGenerator(token, config, provider)
    generator.allow_secrets = True  # synthetic content; never gate the probe
    tiny_diff = (
        "diff --git a/ping.txt b/ping.txt\n"
        "--- a/ping.txt\n+++ b/ping.txt\n"
        "@@ -0,0 +1 @@\n+ping\n"
    )
    try:
        start = time.perf_counter()
        _validate_llm_call(
            generator.generate,
            tiny_diff,
            token=token,
            requires_token=provider not in TOKENLESS_PROVIDERS,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        _line(_OK, f"Provider '{provider}' reachable ({elapsed_ms:.0f} ms)")
        return True
    except ValueError as exc:
        _line(_FAIL, f"Provider '{provider}' probe failed: {exc}")
        return False
    finally:
        generator.close()
