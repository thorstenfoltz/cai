"""
Set configuration
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

DEFAULT_CONFIG = {
    "openai": {"model": "gpt-5.1", "temperature": 0},
    "gemini": {"model": "gemini-2.5-flash", "temperature": 0},
    "anthropic": {"model": "claude-haiku-4-5", "temperature": 0},
    "groq": {"model": "moonshotai/kimi-k2-instruct", "temperature": 0},
    "xai": {"model": "grok-4-1-fast-reasoning", "temperature": 0},
    "language": "en",
    "default": "groq",
    "style": "professional",
    "emoji": "true",
}

TOKEN_TEMPLATE = {
    "openai": "PUT-YOUR-OPENAI-TOKEN-HERE",
    "gemini": "PUT-YOUR-GEMINI-TOKEN-HERE",
    "anthropic": "PUT-YOUR-ANTHROPIC-TOKEN-HERE",
    "groq": "PUT-YOUR-GROQ-TOKEN-HERE",
    "xai": "PUT-YOUR-XAI-TOKEN-HERE",
}


def load_config(
    fallback_config_file: Path = FALLBACK_CONFIG_FILE,
    default_config: Optional[dict[str, Any]] = None,
    allowed_languages: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    Load configuration of LLM and validate structure and language.
    """
    if default_config is None:
        default_config = DEFAULT_CONFIG.copy()
    log.debug("Loading config...")

    languages: set[str] = (
        ALLOWED_LANGUAGES.copy() if allowed_languages is None else allowed_languages
    )
    log.debug("Loading allowed languages...")

    repo_root = find_git_root()
    repo_config_file = Path(repo_root) / "cai_config.yml" if repo_root else None

    if repo_config_file and repo_config_file.exists():
        try:
            with open(repo_config_file, "r", encoding="utf-8") as f:
                config = cast(dict[str, Any], yaml.safe_load(f) or {})
            if config:
                _validate_config_keys(config, DEFAULT_CONFIG)
                config["language"] = _validate_language(config, languages)
                config["style"] = _validate_style(config.get("style"))
                return config
        except yaml.YAMLError as e:
            log.error("Failed to parse repo config: %s", e)

    if not fallback_config_file.exists() or fallback_config_file.stat().st_size == 0:
        log.warning(
            "No config file provided and default config missing or empty. Creating default config in %s",
            fallback_config_file,
        )
        fallback_config_file.parent.mkdir(parents=True, exist_ok=True)
        priority_keys = ["default", "language", "style", "emoji"]
        ordered = {}
        for key in priority_keys:
            if key in default_config:
                ordered[key] = default_config[key]

        for key in sorted(k for k in default_config if k not in priority_keys):
            ordered[key] = default_config[key]

        with open(fallback_config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(ordered, f, sort_keys=False)
        default_config["language"] = _validate_language(default_config, languages)
        default_config["style"] = _validate_style(
            cast(str | None, default_config.get("style"))
        )
        return default_config

    try:
        with open(fallback_config_file, "r", encoding="utf-8") as f:
            config = cast(dict[str, Any], yaml.safe_load(f) or default_config)
        _validate_config_keys(config, DEFAULT_CONFIG)
        config["language"] = _validate_language(config, languages)
        config["style"] = _validate_style(config.get("style"))
        return config
    except yaml.YAMLError as e:
        log.error("Failed to parse config at %s: %s", fallback_config_file, e)
        default_config["language"] = _validate_language(default_config, languages)
        default_config["style"] = _validate_style(
            cast(str | None, default_config.get("style"))
        )
        return default_config


def load_token(
    key_name: str,
    tokens_file: Path = TOKENS_FILE,
    token_template: Optional[dict[str, Any]] = None,
) -> str | None:
    """
    Load token to connecto to LLM
    """
    if token_template is None:
        token_template = TOKEN_TEMPLATE.copy()
    log.debug("Loading token...")
    tokens_file.parent.mkdir(parents=True, exist_ok=True)

    if not tokens_file.exists():
        log.debug("Check whether file containing tokens exist")
        log.warning("%s does not exist. Creating a token template file.", tokens_file)
        with open(tokens_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(token_template, f)
        os.chmod(tokens_file, stat.S_IRUSR | stat.S_IWUSR)
        log.info("Created token template at %s", tokens_file)  # nosemgrep
        return None

    try:
        with open(tokens_file, "r", encoding="utf-8") as f:
            tokens = cast(dict[str, Any], yaml.safe_load(f) or {})
    except yaml.YAMLError as e:
        log.error("Error parsing %s: %s", tokens_file, e)
        return None

    if key_name not in tokens:
        log.error("Key '%s' not found in %s.", key_name, tokens_file)
        return None

    return tokens[key_name]


def get_default_config() -> str:
    """
    Looks for cai_config.yml in the repo root,
    else in ~/.config/cai/cai_config.yml.
    Returns the value of the 'default' key if it exists.
    Raises FileNotFoundError or KeyError otherwise.
    """
    repo_root = find_git_root()
    repo_config = repo_root / "cai_config.yml" if repo_root else None
    home_config = Path.home() / ".config" / "cai" / "cai_config.yml"

    if repo_config and repo_config.is_file():
        config_path = repo_config
        log.info("Using config file from repo root: %s", config_path)
    elif home_config.is_file():
        config_path = home_config
        log.info("Using config file from user config dir: %s", config_path)
    else:
        log.error("No cai_config.yml found in repo root or %s", home_config)
        raise FileNotFoundError(
            f"No cai_config.yml found in repo root or {home_config}"
        )

    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
            log.debug("Loaded configuration from %s: %s", config_path, config)
    except yaml.YAMLError as e:
        log.exception("Error parsing YAML file %s", config_path)
        raise ValueError(f"Error parsing YAML file {config_path}: {e}") from e

    if "default" not in config:
        log.error("'default' key not found in %s", config_path)
        raise KeyError(f"'default' key not found in {config_path}")

    default_value = config["default"]
    log.info("Using provider: %s", default_value)
    return default_value
