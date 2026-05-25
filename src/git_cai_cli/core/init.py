"""
Interactive setup wizard for git-cai.

Bootstraps the home-scope configuration (``~/.config/cai/cai_config.yml``)
and, for providers that require one, the API token store
(``~/.config/cai/tokens.yml``).
"""

import getpass
import logging
import os
import stat
from pathlib import Path
from typing import Any, cast

import typer
import yaml
from git_cai_cli.core.config import (
    CONFIG_DIR,
    DEFAULT_CONFIG,
    FALLBACK_CONFIG_FILE,
    KNOWN_PROVIDERS,
    TOKENLESS_PROVIDERS,
    TOKENS_FILE,
)
from git_cai_cli.core.languages import LANGUAGE_MAP

log = logging.getLogger(__name__)

_STYLES = (
    "professional",
    "neutral",
    "friendly",
    "funny",
    "excited",
    "sarcastic",
    "apologetic",
    "academic",
    "none",
)


def _pick_provider() -> str:
    providers = sorted(KNOWN_PROVIDERS)
    typer.echo("\nAvailable providers:")
    for idx, name in enumerate(providers, start=1):
        block = DEFAULT_CONFIG.get(name, {})
        model = block.get("model", "n/a") if isinstance(block, dict) else "n/a"
        token_info = (
            "no token required"
            if name in TOKENLESS_PROVIDERS
            else "token required"
        )
        typer.echo(f"  {idx}. {name:<10} default model: {model}  ({token_info})")

    while True:
        raw = typer.prompt(
            "\nPick a provider (number or name)", default=providers[0]
        ).strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(providers):
                return providers[idx - 1]
            typer.echo(f"Please enter a number between 1 and {len(providers)}.")
            continue
        normalized = raw.lower()
        if normalized in KNOWN_PROVIDERS:
            return normalized
        typer.echo(f"Unknown provider '{raw}'. Try again.")


def _pick_language() -> str:
    default = "en"
    while True:
        raw = typer.prompt(
            "Language code (e.g. en, de, fr; 'none' to disable)", default=default
        ).strip().lower()
        if raw == "none" or raw in LANGUAGE_MAP:
            return raw
        typer.echo(
            "Unknown language. Run 'git cai -l language' after setup to see all options."
        )


def _pick_style() -> str:
    default = "professional"
    typer.echo("\nAvailable styles: " + ", ".join(_STYLES))
    while True:
        raw = typer.prompt("Style", default=default).strip().lower()
        if raw in _STYLES:
            return raw
        typer.echo("Unknown style. Pick one from the list above.")


def _read_token(provider: str) -> str:
    typer.echo(
        f"\nEnter your {provider} API key. "
        "Input will be hidden while you type."
    )
    while True:
        token = getpass.getpass(prompt=f"{provider} API key: ").strip()
        if token:
            return token
        typer.echo("Empty key — please paste your token (or Ctrl-C to abort).")


def _write_tokens_file(provider: str, token: str, tokens_path: Path) -> None:
    tokens: dict[str, Any] = {}
    if tokens_path.exists() and tokens_path.stat().st_size > 0:
        try:
            with tokens_path.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                tokens = cast(dict[str, Any], loaded)
        except yaml.YAMLError as exc:
            log.warning("Existing tokens.yml could not be parsed (%s) — overwriting.", exc)

        if provider in tokens and not typer.confirm(
            f"A {provider} token already exists in {tokens_path}. Overwrite?",
            default=False,
        ):
            typer.echo("Keeping existing token.")
            return

    tokens[provider] = token

    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    old_umask = os.umask(0o077)
    try:
        with tokens_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(tokens, f, sort_keys=False)
    finally:
        os.umask(old_umask)
    os.chmod(tokens_path, stat.S_IRUSR | stat.S_IWUSR)


def _write_config_file(
    config_path: Path,
    provider: str,
    language: str,
    style: str,
    emoji: bool,
) -> None:
    block = DEFAULT_CONFIG.get(provider, {})
    provider_block = (
        {k: v for k, v in block.items()} if isinstance(block, dict) else {}
    )

    config: dict[str, Any] = {
        "default": provider,
        "language": language,
        "style": style,
        "emoji": emoji,
        "load_tokens_from": str(TOKENS_FILE),
        provider: provider_block,
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)


def run_init_wizard(
    config_path: Path = FALLBACK_CONFIG_FILE,
    tokens_path: Path = TOKENS_FILE,
) -> int:
    """Run the interactive setup wizard. Returns a process exit code."""
    typer.echo("git-cai setup wizard — writes to home scope only.")
    typer.echo(f"  Config dir:  {CONFIG_DIR}")

    try:
        if config_path.exists() and config_path.stat().st_size > 0:
            if not typer.confirm(
                f"\n{config_path} already exists. Overwrite?", default=False
            ):
                typer.echo("Aborted. Existing configuration left untouched.")
                return 0

        provider = _pick_provider()
        language = _pick_language()
        style = _pick_style()
        emoji = typer.confirm("Use emoji in commit messages?", default=True)

        if provider not in TOKENLESS_PROVIDERS:
            token = _read_token(provider)
            _write_tokens_file(provider, token, tokens_path)
            typer.echo(f"  Wrote token to {tokens_path} (mode 0600).")
        else:
            typer.echo(
                f"  Provider '{provider}' does not need a token — skipping token entry."
            )

        _write_config_file(config_path, provider, language, style, emoji)
        typer.echo(f"  Wrote config to {config_path}.")

        typer.echo(
            "\nSetup complete. Next: cd into a git repo, stage some changes, "
            "and run 'git cai'."
        )
        return 0
    except KeyboardInterrupt:
        typer.echo("\nAborted.", err=True)
        return 130
