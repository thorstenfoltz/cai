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
from importlib import resources
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
    "openai": {"model": "gpt-5.2", "temperature": 0},
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
    "prompt_file": "",
    "squash_prompt_file": "",
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

    def _normalize_none_like(config_dict: dict[str, Any]) -> None:
        """Normalize None/'None'/'none' consistently across config keys."""
        none_like = {"none"}

        for key in ("language", "style", "emoji"):
            if key not in config_dict:
                continue
            value = config_dict.get(key)
            if value is None:
                config_dict[key] = "none"
                continue
            if isinstance(value, str) and value.strip().lower() in none_like:
                config_dict[key] = "none"

        for key in ("prompt_file", "squash_prompt_file"):
            if key not in config_dict:
                continue
            value = config_dict.get(key)
            if value is None:
                config_dict[key] = ""

    def _ensure_prompt_files(prompt_dir: Path) -> tuple[Path, Path]:
        """Ensure default prompt files exist in prompt_dir."""
        prompt_dir.mkdir(parents=True, exist_ok=True)

        commit_path = prompt_dir / "commit_prompt.md"
        squash_path = prompt_dir / "squash_prompt.md"

        def _read_bundled(name: str) -> str:
            try:
                defaults_pkg = resources.files("git_cai_cli.defaults")
                default_file = defaults_pkg / name
                if default_file.is_file():  # type: ignore[union-attr]
                    return default_file.read_text(encoding="utf-8")  # type: ignore[union-attr]
            except (TypeError, FileNotFoundError, ModuleNotFoundError):
                pass

            # last resort: import hardcoded strings
            from git_cai_cli.core.llm import (  # local import to avoid cycles
                _HARDCODED_COMMIT_PROMPT,
                _HARDCODED_SQUASH_PROMPT,
            )

            return (
                _HARDCODED_COMMIT_PROMPT
                if name == "commit_prompt.md"
                else _HARDCODED_SQUASH_PROMPT
            )

        if not commit_path.exists() or commit_path.stat().st_size == 0:
            commit_path.write_text(_read_bundled("commit_prompt.md"), encoding="utf-8")
            log.info("Default commit prompt written to %s", commit_path)

        if not squash_path.exists() or squash_path.stat().st_size == 0:
            squash_path.write_text(_read_bundled("squash_prompt.md"), encoding="utf-8")
            log.info("Default squash prompt written to %s", squash_path)

        return commit_path, squash_path

    def _normalize_prompt_paths(config_dict: dict[str, Any], base_dir: Path) -> None:
        """Normalize prompt file paths (expand ~/$VARS and resolve relative paths)."""
        for key in ("prompt_file", "squash_prompt_file"):
            raw = config_dict.get(key)
            if not isinstance(raw, str):
                continue
            if not raw.strip():
                continue

            expanded = os.path.expandvars(raw.strip())
            path = Path(expanded).expanduser()
            if not path.is_absolute():
                path = (base_dir / path).resolve()

            config_dict[key] = str(path)
            log.debug("Normalized %s to %s", key, path)

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

        _normalize_none_like(config)
        _validate_config_keys(config, DEFAULT_CONFIG)
        config["language"] = _validate_language(config, languages)
        config["style"] = _validate_style(cast(str | None, config.get("style")))

        _normalize_prompt_paths(config, base_dir=repo_config_file.parent)

        log.info("Repository configuration validated successfully")
        return config

    log.info("No repository config found, using home configuration")

    if not fallback_config_file.exists() or fallback_config_file.stat().st_size == 0:
        log.warning(
            "Home config missing or empty, creating default at %s",
            fallback_config_file,
        )

        fallback_config_file.parent.mkdir(parents=True, exist_ok=True)

        # Create default prompt files in the config directory and reference them
        commit_prompt_path, squash_prompt_path = _ensure_prompt_files(
            fallback_config_file.parent
        )
        default_config["prompt_file"] = commit_prompt_path
        default_config["squash_prompt_file"] = squash_prompt_path

        ordered = ordered_default_config(default_config)

        with fallback_config_file.open("w", encoding="utf-8") as f:
            yaml.safe_dump(_serialize_config(ordered), f, sort_keys=False)

        log.info("Default home configuration written")

        _normalize_none_like(default_config)
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

    _normalize_none_like(config)
    _validate_config_keys(config, DEFAULT_CONFIG)
    config["language"] = _validate_language(config, languages)
    config["style"] = _validate_style(cast(str | None, config.get("style")))

    _normalize_prompt_paths(config, base_dir=fallback_config_file.parent)

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
            "Token file %s does not exist, creating template",
            tokens_file,  # nosemgrep
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


def ordered_default_config(
    default_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Return DEFAULT_CONFIG ordered for human-readable YAML output.
    """
    if default_config is None:
        default_config = DEFAULT_CONFIG

    priority_keys = [
        "default",
        "language",
        "style",
        "emoji",
        "load_tokens_from",
        "prompt_file",
        "squash_prompt_file",
    ]

    ordered: dict[str, Any] = {}

    for key in priority_keys:
        if key in default_config:
            ordered[key] = default_config[key]

    for key in sorted(k for k in default_config if k not in priority_keys):
        ordered[key] = default_config[key]

    return ordered
