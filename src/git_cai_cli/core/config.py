"""
Set configuration
"""

import logging
import os
import stat
from pathlib import Path
from typing import Any, Optional

import yaml
from git_cai_cli.core.gitutils import find_git_root

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "cai"
FALLBACK_CONFIG_FILE = CONFIG_DIR / "cai_config.yml"
TOKENS_FILE = CONFIG_DIR / "tokens.yml"

DEFAULT_CONFIG = {"openai": {"model": "gpt-4.1", "temperature": 0}}

TOKEN_TEMPLATE = {
    "openai": "PUT-YOUR-OPENAI-TOKEN-HERE",
    "gemini": "PUT-YOUR-GEMINI-TOKEN-HERE",
}


def load_config(
    fallback_config_file: Path = FALLBACK_CONFIG_FILE,
    default_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Load configuration of LLM
    """
    if default_config is None:
        default_config = DEFAULT_CONFIG.copy()
    log.debug("Loading config...")

    repo_root = find_git_root()
    repo_config_file = Path(repo_root) / "cai_config.yml" if repo_root else None

    if repo_config_file and repo_config_file.exists():
        try:
            with open(repo_config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            if config:
                return config
        except yaml.YAMLError as e:
            log.error("Failed to parse repo config: %s", e)

    if not fallback_config_file.exists() or fallback_config_file.stat().st_size == 0:
        log.warning(
            "No config file provided and default config missing or empty. Creating default config in %s",
            fallback_config_file,
        )
        fallback_config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(fallback_config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(default_config, f)
        return default_config

    try:
        with open(fallback_config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or default_config
    except yaml.YAMLError as e:
        log.error("Failed to parse config at %s: %s", fallback_config_file, e)
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
            tokens = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        log.error("Error parsing %s: %s", tokens_file, e)
        return None

    if key_name not in tokens:
        log.error("Key '%s' not found in %s.", key_name, tokens_file)
        return None

    return tokens[key_name]
