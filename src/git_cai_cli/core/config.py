import logging
import os
import stat
from pathlib import Path
from typing import Any
from git_cai_cli.core.gitutils import find_git_root
import yaml

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "cai"
FALLBACK_CONFIG_FILE = CONFIG_DIR / "cai_config.yml"
TOKENS_FILE = CONFIG_DIR / "tokens.yml"

DEFAULT_CONFIG = {"openai": {"model": "gpt-4.1", "temperature": 0}}

TOKEN_TEMPLATE = {
    "openai": "PUT-YOUR-OPENAI-TOKEN-HERE",
    "huggingface": "PUT-YOUR-HUGGINGFACE-TOKEN-HERE",
}


def load_config(
    fallback_config_file: Path = FALLBACK_CONFIG_FILE,
    default_config: dict[str, Any] = DEFAULT_CONFIG,
    log: logging.Logger = log,
) -> dict[str, Any]:
    from .gitutils import find_git_root

    repo_root = find_git_root()
    repo_config_file = Path(repo_root) / "cai_config.yml" if repo_root else None

    if repo_config_file and repo_config_file.exists():
        try:
            with open(repo_config_file, "r") as f:
                config = yaml.safe_load(f) or {}
            if config:
                return config
        except yaml.YAMLError as e:
            log.error(f"Failed to parse repo config: {e}")

    if not fallback_config_file.exists() or fallback_config_file.stat().st_size == 0:
        log.warning(
            f"No config file provided and default config missing or empty. Creating default config in {fallback_config_file}"
        )
        fallback_config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(fallback_config_file, "w") as f:
            yaml.safe_dump(default_config, f)
        return default_config

    try:
        with open(fallback_config_file, "r") as f:
            return yaml.safe_load(f) or default_config
    except yaml.YAMLError as e:
        log.error(f"Failed to parse config at {fallback_config_file}: {e}")
        return default_config


def load_token(
    key_name: str,
    tokens_file: Path = TOKENS_FILE,
    token_template: dict[str, Any] = TOKEN_TEMPLATE,
    log: logging.Logger = log,
) -> str | None:
    tokens_file.parent.mkdir(parents=True, exist_ok=True)

    if not tokens_file.exists():
        log.warning(f"{tokens_file} does not exist. Creating a token template file.")
        with open(tokens_file, "w") as f:
            yaml.safe_dump(token_template, f)
        os.chmod(tokens_file, stat.S_IRUSR | stat.S_IWUSR)
        log.info(f"Created token template at {tokens_file}")
        return None

    try:
        with open(tokens_file, "r") as f:
            tokens = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        log.error(f"Error parsing {tokens_file}: {e}")
        return None

    if key_name not in tokens:
        log.error(f"Key '{key_name}' not found in {tokens_file}.")
        return None

    return tokens[key_name]
