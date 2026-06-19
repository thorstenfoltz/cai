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

import typer
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
    "anthropic": {
        "model": "claude-haiku-4-5",
        "temperature": 0,
        "max_tokens": 32768,
    },
    "openai": {"model": "gpt-5.2", "temperature": 0},
    "deepseek": {"model": "deepseek-chat", "temperature": 0},
    "gemini": {"model": "gemini-2.5-flash", "temperature": 0},
    "groq": {"model": "moonshotai/kimi-k2-instruct", "temperature": 0},
    "xai": {"model": "grok-4-1-fast-reasoning", "temperature": 0},
    "mistral": {"model": "codestral-2508", "temperature": 0},
    "ollama": {"model": "llama3.1", "temperature": 0, "timeout": 300},
    "language": "en",
    "default": "groq",
    "style": "professional",
    "emoji": True,
    "load_tokens_from": TOKENS_FILE,
    "prompt_file": "",
    "squash_prompt_file": "",
    "full_files_prompt_file": "",
    "conventional": False,
    "branch_context": False,
    "token_logging": True,  # nosec B105 - local-only provider that doesn't use API tokens
    "measure_time": False,
    "timeout": 30,
    "full_files": False,
    "max_diff_bytes": 0,
    "pr_to_file": False,
    "pr_file_name": "PR_DESCRIPTION.md",
    "pr_prompt_file": "",
    "stats": False,
    "signoff": False,
    "secret_scan": True,
}

# Providers that do not require an API token in tokens.yml
TOKENLESS_PROVIDERS: set[str] = {
    "ollama"  # nosec B105 - local-only provider that doesn't use API tokens
}

TOKEN_TEMPLATE = {
    "anthropic": "PUT-YOUR-ANTHROPIC-TOKEN-HERE",
    "deepseek": "PUT-YOUR-DEEPSEEK-TOKEN-HERE",
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


def _load_home_stats(home_config_file: Path) -> dict[str, Any] | None:
    """Read the ``stats``-related keys from the home config (if any).

    Used when a repo config exists but doesn't mention ``stats`` —
    we fall through to the user's global preference rather than
    silently disabling analytics. Returns ``None`` if the home
    config has no relevant keys; otherwise a dict containing
    whichever of ``stats`` / ``stats_db_path`` are set.
    """
    try:
        if not home_config_file.exists() or home_config_file.stat().st_size == 0:
            return None
        with home_config_file.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        log.debug("Could not read home stats fallback: %s", exc)
        return None

    if not isinstance(data, dict):
        return None

    out: dict[str, Any] = {}
    if "stats" in data:
        out["stats"] = data["stats"]
    if "stats_db_path" in data:
        out["stats_db_path"] = data["stats_db_path"]
    return out or None


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

        for key in (
            "prompt_file",
            "squash_prompt_file",
            "full_files_prompt_file",
            "pr_prompt_file",
        ):
            if key not in config_dict:
                continue
            value = config_dict.get(key)
            if value is None:
                config_dict[key] = ""

    def _ensure_prompt_files(prompt_dir: Path) -> tuple[Path, Path, Path, Path]:
        """Ensure default prompt files exist in prompt_dir.

        Prompt bodies come from the hardcoded fallback strings in
        `prompts_fallback.py` — there is no separate bundled prompt file.
        """
        from git_cai_cli.core.prompts_fallback import (
            HARDCODED_COMMIT_PROMPT,
            HARDCODED_FULL_FILES_PROMPT,
            HARDCODED_PR_PROMPT,
            HARDCODED_SQUASH_PROMPT,
        )

        prompt_dir.mkdir(parents=True, exist_ok=True)

        commit_path = prompt_dir / "commit_prompt.md"
        squash_path = prompt_dir / "squash_prompt.md"
        full_files_path = prompt_dir / "full_files_prompt.md"
        pr_path = prompt_dir / "pr_prompt.md"

        targets = (
            (commit_path, HARDCODED_COMMIT_PROMPT, "commit"),
            (squash_path, HARDCODED_SQUASH_PROMPT, "squash"),
            (full_files_path, HARDCODED_FULL_FILES_PROMPT, "full-files"),
            (pr_path, HARDCODED_PR_PROMPT, "pr"),
        )

        for path, body, label in targets:
            if not path.exists() or path.stat().st_size == 0:
                path.write_text(body, encoding="utf-8")
                log.info("Default %s prompt written to %s", label, path)

        return commit_path, squash_path, full_files_path, pr_path

    def _normalize_prompt_paths(config_dict: dict[str, Any], base_dir: Path) -> None:
        """Normalize prompt file paths (expand ~/$VARS and resolve relative paths)."""
        for key in (
            "prompt_file",
            "squash_prompt_file",
            "full_files_prompt_file",
            "pr_prompt_file",
        ):
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

        # Stats is the only key that falls back through the home config:
        # users typically configure analytics globally (one DB across
        # repos), so a repo-level config that omits ``stats`` should not
        # silently disable it. If the home config also doesn't define
        # it, the hardcoded default (``stats: false``) wins via
        # ``stats.is_enabled``'s missing-key handling. Same fallback
        # applies to the optional ``stats_db_path`` override.
        if "stats" not in config or "stats_db_path" not in config:
            home_stats = _load_home_stats(fallback_config_file)
            if home_stats is not None:
                for key, value in home_stats.items():
                    config.setdefault(key, value)

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
        (
            commit_prompt_path,
            squash_prompt_path,
            full_files_prompt_path,
            pr_prompt_path,
        ) = _ensure_prompt_files(fallback_config_file.parent)
        default_config["prompt_file"] = commit_prompt_path
        default_config["squash_prompt_file"] = squash_prompt_path
        default_config["full_files_prompt_file"] = full_files_prompt_path
        default_config["pr_prompt_file"] = pr_prompt_path

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
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            log.warning(
                "Home config %s is not a YAML mapping, using defaults",
                fallback_config_file,
            )
            config = default_config
        else:
            config = raw or default_config
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

    if key_name in TOKENLESS_PROVIDERS:
        log.info("Provider '%s' does not require a token.", key_name)
        return None

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
        "conventional",
        "branch_context",
        "load_tokens_from",
        "prompt_file",
        "squash_prompt_file",
        "full_files_prompt_file",
        "token_logging",
        "measure_time",
        "timeout",
        "full_files",
        "max_diff_bytes",
        "pr_to_file",
        "pr_file_name",
        "pr_prompt_file",
        "stats",
        "stats_db_path",
        "signoff",
    ]

    ordered: dict[str, Any] = {}

    for key in priority_keys:
        if key in default_config:
            ordered[key] = default_config[key]

    for key in sorted(k for k in default_config if k not in priority_keys):
        ordered[key] = default_config[key]

    return ordered


# Known provider names derived from DEFAULT_CONFIG provider blocks
KNOWN_PROVIDERS = frozenset(
    {
        "openai",
        "gemini",
        "anthropic",
        "groq",
        "xai",
        "mistral",
        "deepseek",
        "ollama",
    }
)


def _parse_config_value(raw: str) -> Any:
    """
    Parse a raw string value into the appropriate Python type.
    Handles booleans, integers, floats, and strings.
    """
    if raw.lower() in ("true", "yes"):
        return True
    if raw.lower() in ("false", "no"):
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def set_config_value(key: str, raw_value: str, *, force_home: bool = False) -> Path:
    """
    Set a configuration value in the appropriate config file.

    Supports dot notation for nested keys (e.g., 'groq.model').

    Args:
        key: Config key or dotted key (e.g., 'language' or 'groq.model').
        raw_value: Raw string value to set (auto-parsed to bool/int/float/str).
        force_home: If True, always target home config. Otherwise, target
                    repo config if it exists, else home config.

    Returns:
        Path to the config file that was updated.

    Raises:
        ValueError: If the key or value is invalid.
    """
    if not key or not key.strip():
        raise ValueError("Config key must not be empty.")

    parsed_value = _parse_config_value(raw_value)

    # Determine target config file
    if force_home:
        target = FALLBACK_CONFIG_FILE
        log.info("Targeting home config: %s", target)
    else:
        repo_config = _find_repo_config()
        if repo_config:
            target = repo_config
            log.info("Targeting repo config: %s", target)
        else:
            raise ValueError(
                "No repository config found. "
                "Use 'git cai --set-home key=value' to change the default config, "
                "or 'git cai -g' to create a repo config first."
            )

    # Load existing config or start fresh
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        try:
            with target.open("r", encoding="utf-8") as f:
                config = cast(dict[str, Any], yaml.safe_load(f) or {})
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse config file {target}: {e}") from e
    else:
        config = {}

    # Apply the value (support dot notation for nested keys)
    parts = key.strip().split(".", 1)
    if len(parts) == 2:
        section, subkey = parts
        if section not in config or not isinstance(config[section], dict):
            config[section] = {}
        config[section][subkey] = parsed_value
        log.info("Set %s.%s = %r in %s", section, subkey, parsed_value, target)
    else:
        config[parts[0]] = parsed_value
        log.info("Set %s = %r in %s", parts[0], parsed_value, target)

    # Write back
    with target.open("w", encoding="utf-8") as f:
        yaml.safe_dump(_serialize_config(config), f, sort_keys=False)

    return target


def apply_cli_overrides(
    config: dict,
    *,
    conventional: bool | None = None,
    branch_context: bool | None = None,
    timeout_override: int | None = None,
    full_files_override: bool | None = None,
    sql_override: bool | None = None,
    style_override: str | None = None,
    language_override: str | None = None,
    emoji_override: bool | None = None,
) -> None:
    """Apply per-invocation CLI flag overrides to the config dict in-place.

    Boolean overrides use ``None`` to mean "no override; keep the
    persisted config value." ``True`` and ``False`` both override —
    so a user can pass ``--no-conventional`` to flip a persisted
    ``conventional: true`` off for one invocation.

    ``sql_override`` mirrors ``--sql true|false`` and overrides the
    top-level ``stats`` boolean.

    ``style_override`` / ``language_override`` / ``emoji_override`` mirror
    ``--style`` / ``--language`` / ``--emoji`` and override the top-level
    generation knobs. Style and language are validated here (the normal
    config validation already ran during ``load_config``, before these
    overrides are applied); invalid values raise ``typer.Exit``.
    """
    if conventional is not None:
        config["conventional"] = conventional
    if branch_context is not None:
        config["branch_context"] = branch_context
    if timeout_override is not None:
        config["timeout"] = timeout_override
    if full_files_override is not None:
        config["full_files"] = full_files_override
    if sql_override is not None:
        config["stats"] = sql_override
    if style_override is not None:
        try:
            config["style"] = _validate_style(style_override)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    if language_override is not None:
        normalized = language_override.strip().lower()
        if normalized != "none" and normalized not in ALLOWED_LANGUAGES:
            typer.echo(
                f"Error: unknown language '{language_override}'. "
                "Run 'git cai -l language' to see supported codes.",
                err=True,
            )
            raise typer.Exit(code=1)
        config["language"] = normalized
    if emoji_override is not None:
        config["emoji"] = emoji_override


def apply_provider_overrides(
    config: dict,
    provider_override: str | None,
    model_override: str | None,
    temperature_override: float | None = None,
) -> None:
    """
    Apply --provider, --model and --temperature overrides to the config
    dict in-place.

    ``temperature_override`` is provider-scoped (like ``--model``): it
    sets ``config[<active provider>]["temperature"]`` for this run only.

    Raises typer.Exit on validation errors.
    """
    if model_override and not provider_override:
        log.error(
            "Cannot specify --model without --provider. Model: '%s'",
            model_override,
        )
        typer.echo(
            f"Error: --model requires --provider. Model: '{model_override}'",
            err=True,
        )
        raise typer.Exit(code=1)

    if provider_override:
        if provider_override not in KNOWN_PROVIDERS:
            log.error(
                "Unknown provider '%s'. Available: %s",
                provider_override,
                ", ".join(sorted(KNOWN_PROVIDERS)),
            )
            typer.echo(
                f"Error: Unknown provider '{provider_override}'. "
                f"Available: {', '.join(sorted(KNOWN_PROVIDERS))}",
                err=True,
            )
            raise typer.Exit(code=1)

        config["default"] = provider_override
        log.info("Provider overridden to '%s'.", provider_override)

    if model_override:
        provider = config["default"]
        if provider not in config or not isinstance(config[provider], dict):
            config[provider] = {"model": model_override, "temperature": 0}
        else:
            config[provider]["model"] = model_override
        log.info(
            "Model overridden to '%s' for provider '%s'.",
            model_override,
            provider,
        )

    if temperature_override is not None:
        provider = config["default"]
        if provider not in config or not isinstance(config[provider], dict):
            config[provider] = {"temperature": temperature_override}
        else:
            config[provider]["temperature"] = temperature_override
        log.info(
            "Temperature overridden to %s for provider '%s'.",
            temperature_override,
            provider,
        )
