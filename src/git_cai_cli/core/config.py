"""
Configuration handling for git-cai-cli.

This module is responsible for:
- Locating and loading configuration files
- Enforcing configuration precedence (repository → home → defaults)
- Validating configuration structure and semantics
- Providing access to authentication tokens

Repository configuration, when present, is authoritative and is not merged
with any home or default configuration.
"""

import logging
import os
import stat
from pathlib import Path
from typing import Any, Optional, cast

import yaml
from git_cai_cli.core.gitutils import find_git_root
from git_cai_cli.core.languages import ALLOWED_LANGUAGES
from git_cai_cli.core.validate import (
    _validate_config_keys,
    _validate_language,
    _validate_style,
)

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "cai"
FALLBACK_CONFIG_FILE = CONFIG_DIR / "cai_config.yml"
TOKENS_FILE = CONFIG_DIR / "tokens.yml"

DEFAULT_CONFIG: dict[str, Any] = {
    "anthropic": {"model": "claude-haiku-4-5", "temperature": 0},
    "openai": {"model": "gpt-5.1", "temperature": 0},
    "deepseek": {"model": "deepseek-chat", "temperature": 0},
    "gemini": {"model": "gemini-2.5-flash", "temperature": 0},
    "groq": {"model": "moonshotai/kimi-k2-instruct", "temperature": 0},
    "xai": {"model": "grok-4-1-fast-reasoning", "temperature": 0},
    "mistral": {"model": "codestral-2508", "temperature": 0},
    "language": "en",
    "default": "groq",
    "style": "professional",
    "emoji": True,
    "load_tokens_from": TOKENS_FILE,
}

TOKEN_TEMPLATE = {
    "anthropic": "PUT-YOUR-ANTHROPIC-TOKEN-HERE",
    "gemini": "PUT-YOUR-GEMINI-TOKEN-HERE",
    "groq": "PUT-YOUR-GROQ-TOKEN-HERE",
    "openai": "PUT-YOUR-OPENAI-TOKEN-HERE",
    "mistral": "PUT-YOUR-MISTRAL-TOKEN-HERE",
    "xai": "PUT-YOUR-XAI-TOKEN-HERE",
}


def _find_repo_config() -> Path | None:
    """
    Locate a repository-local configuration file.

    Searches the Git repository root for `cai_config.yml` or
    `cai_config.yaml`.

    Returns:
        Path to the repository configuration file if found,
        otherwise None.
    """
    log.debug("Searching for repository configuration file")

    repo_root = find_git_root()
    if not repo_root:
        log.debug("Not inside a Git repository")
        return None

    for name in ("cai_config.yml", "cai_config.yaml"):
        candidate = repo_root / name
        log.debug("Checking config candidate: %s", candidate)
        if candidate.is_file():
            log.info("Repository config found: %s", candidate)
            return candidate

    log.debug("No repository config found")
    return None


def load_config(
    fallback_config_file: Path = FALLBACK_CONFIG_FILE,
    default_config: Optional[dict[str, Any]] = None,
    allowed_languages: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    Load and validate the active configuration.

    Precedence:
    1. Repository configuration (authoritative)
    2. Home configuration
    3. Generated default configuration

    Args:
        fallback_config_file: Path to the home configuration file.
        default_config: Optional default configuration.
        allowed_languages: Optional set of allowed languages.

    Returns:
        A validated configuration dictionary.

    Raises:
        ValueError: If a repository configuration exists but is invalid.
    """
    log.debug("Loading configuration")

    if default_config is None:
        log.debug("Using built-in default configuration")
        default_config = DEFAULT_CONFIG.copy()

    languages = (
        ALLOWED_LANGUAGES.copy() if allowed_languages is None else allowed_languages
    )

    repo_config_file = _find_repo_config()
    if repo_config_file:
        log.info("Using repository configuration")

        try:
            with repo_config_file.open("r", encoding="utf-8") as f:
                config = cast(dict[str, Any], yaml.safe_load(f) or {})
            log.debug("Repository config loaded successfully")
        except yaml.YAMLError as e:
            log.error("Failed to parse repository config %s", repo_config_file)
            raise ValueError(
                f"Failed to parse repository config {repo_config_file}: {e}"
            ) from e

        _validate_config_keys(config, DEFAULT_CONFIG)
        config["language"] = _validate_language(config, languages)
        config["style"] = _validate_style(config.get("style"))

        log.info("Repository configuration validated successfully")
        return config

    log.info("No repository config found, using home configuration")

    if not fallback_config_file.exists() or fallback_config_file.stat().st_size == 0:
        log.warning(
            "Home config missing or empty, creating default at %s",
            fallback_config_file,
        )

        fallback_config_file.parent.mkdir(parents=True, exist_ok=True)

        priority_keys = ["default", "language", "style", "emoji", "load_tokens_from"]
        ordered: dict[str, Any] = {}

        for key in priority_keys:
            ordered[key] = default_config[key]

        for key in sorted(k for k in default_config if k not in priority_keys):
            ordered[key] = default_config[key]

        with fallback_config_file.open("w", encoding="utf-8") as f:
            yaml.safe_dump(_serialize_config(ordered), f, sort_keys=False)

        log.info("Default home configuration written")

        default_config["language"] = _validate_language(default_config, languages)
        default_config["style"] = _validate_style(
            cast(str | None, default_config.get("style"))
        )

        return default_config

    try:
        with fallback_config_file.open("r", encoding="utf-8") as f:
            config = cast(dict[str, Any], yaml.safe_load(f) or default_config)
        log.debug("Home config loaded successfully")
    except yaml.YAMLError:
        log.error("Failed to parse home config %s", fallback_config_file)
        default_config["language"] = _validate_language(default_config, languages)
        default_config["style"] = _validate_style(
            cast(str | None, default_config.get("style"))
        )
        return default_config

    _validate_config_keys(config, DEFAULT_CONFIG)
    config["language"] = _validate_language(config, languages)
    config["style"] = _validate_style(config.get("style"))

    return config


def load_token(
    config: Optional[dict[str, Any]] = None,
    token_template: Optional[dict[str, Any]] = None,
) -> str | None:
    """
    Load an authentication token for a given provider.

    Tokens are always loaded from the user's home configuration directory.

    Args:
        key_name: Provider name.
        tokens_file: Path to the tokens file.
        token_template: Optional token template for initialization.

    Returns:
        Token string if present, otherwise None.
    """
    if config is None:
        log.debug("No config provided, loading default configuration")
        config = load_config()
    log.info("Loading token for provider: %s", config["default"])  # nosemgrep

    if "load_tokens_from" in config:
        tokens_file = Path(config["load_tokens_from"])
        log.info("Using tokens file from config in: %s", tokens_file)  # nosemgrep
    else:
        tokens_file = TOKENS_FILE
        log.info("Using default tokens file: %s", tokens_file)  # nosemgrep

    if token_template is None:
        token_template = TOKEN_TEMPLATE.copy()

    tokens_file.parent.mkdir(parents=True, exist_ok=True)
    key_name = config["default"]

    if not tokens_file.exists():
        log.warning(
            "Token file %s does not exist, creating template", tokens_file  # nosemgrep
        )
        with tokens_file.open("w", encoding="utf-8") as f:
            yaml.safe_dump(token_template, f)
        os.chmod(tokens_file, stat.S_IRUSR | stat.S_IWUSR)
        log.info("Token template written to %s", tokens_file)  # nosemgrep
        return None

    try:
        with tokens_file.open("r", encoding="utf-8") as f:
            tokens = cast(dict[str, Any], yaml.safe_load(f) or {})
        log.debug("Tokens file loaded successfully")
    except yaml.YAMLError as e:
        log.error("Failed to parse tokens file %s: %s", tokens_file, e)  # nosemgrep
        return None

    if key_name not in tokens:
        log.error("Token for provider '%s' not found", key_name)  # nosemgrep
        return None

    log.debug("Token for provider '%s' loaded successfully", key_name)  # nosemgrep
    return tokens[key_name]


def _serialize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in cfg.items():
        if isinstance(v, Path):
            out[k] = str(v)
        else:
            out[k] = v
    return out
