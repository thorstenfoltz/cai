"""
Validation utilities for configuration settings
"""

import logging
from typing import Any

log = logging.getLogger(__name__)


def _validate_config_keys(config: dict[str, Any], reference: dict[str, Any]) -> None:
    """
    Validate configuration structure.

    Rules:
    - Only global keys (language, default, style, emoji) are validated explicitly
    - At least one provider block must be present
    - Each provider block must define 'model' and 'temperature'
    - Unknown top-level keys are rejected
    """
    log.debug("Validating configuration keys")

    allowed_global_keys = {
        "language",
        "default",
        "style",
        "emoji",
        "load_tokens_from",
        "prompt_file",
        "squash_prompt_file",
    }
    allowed_provider_keys = set(reference.keys()) - allowed_global_keys

    config_keys = set(config.keys())

    # Reject unknown top-level keys
    unknown_keys = config_keys - allowed_global_keys - allowed_provider_keys
    if unknown_keys:
        log.error("Unknown config keys detected: %s", ", ".join(sorted(unknown_keys)))
        raise KeyError("Unknown config keys: " + ", ".join(sorted(unknown_keys)))

    # Warn on missing global keys (non-fatal)
    missing_globals = allowed_global_keys - config_keys
    if missing_globals:
        log.warning(
            "Config is missing global keys: %s. Using defaults for missing keys.",
            ", ".join(sorted(missing_globals)),
        )

    # Validate provider blocks
    provider_keys = config_keys & allowed_provider_keys

    if not provider_keys:
        log.error("No provider configuration found")
        raise KeyError("At least one provider configuration must be defined")

    for provider in sorted(provider_keys):
        provider_block = config.get(provider)

        if not isinstance(provider_block, dict):
            log.error("Provider '%s' configuration must be a mapping", provider)
            raise KeyError("Provider '" + provider + "' must be a mapping")

        missing_provider_keys = {"model", "temperature"} - provider_block.keys()
        if missing_provider_keys:
            log.error(
                "Provider '%s' missing required keys: %s",
                provider,
                ", ".join(sorted(missing_provider_keys)),
            )
            raise KeyError(
                "Provider '"
                + provider
                + "' missing required keys: "
                + ", ".join(sorted(missing_provider_keys))
            )

    log.debug("Configuration key validation completed successfully")


def _validate_language(config: dict[str, Any], allowed_languages: set[str]) -> str:
    """
    Validate that the language code exists in the allowed set.
    Returns the ISO 639-1 code, or "none" to disable language injection.
    """
    lang_code = config.get("language")

    # Only treat explicit YAML null as "none". Missing key should fall back to 'en'.
    if "language" in config and lang_code is None:
        log.info("Language set to None — language instruction disabled in prompt.")
        return "none"

    if isinstance(lang_code, str) and lang_code.strip().lower() == "none":
        log.info("Language set to 'none' — language instruction disabled in prompt.")
        return "none"

    if not lang_code or lang_code not in allowed_languages:
        log.warning(
            "Language code '%s' is not supported. Falling back to 'en'.", lang_code
        )
        return "en"
    return lang_code


def _validate_llm_call(fn, *args, token: str | None, **kwargs) -> Any:
    """
    Executes an LLM call and converts authentication-related failures
    into clean, user-facing errors.
    """
    if not token or not token.strip():
        log.error("LLM API token is missing.")
        log.error(
            "If this is the first run after installation, this is expected. Please configure your API key."
            " Perhaps your chosen model is not able to use certain settings. Run in debug mode for more details."
        )
        raise ValueError("API token is missing. Please configure your API key.")

    try:
        return fn(*args, **kwargs)

    except Exception as exc:
        msg = str(exc).lower()

        auth_markers = (
            "api key",
            "apikey",
            "authorization",
            "unauthorized",
            "forbidden",
            "400",
            "401",
            "403",
            "invalid token",
            "invalid api key",
            "authentication",
            "permission denied",
        )

        if any(marker in msg for marker in auth_markers):
            log.error("LLM authentication failed.")
            log.error(
                "If this is the first run after installation, this is expected. Please configure your API key."
            )
            raise ValueError(
                "API token is invalid or not authorized. Please check your API key."
            ) from None

        log.exception("Unexpected error during LLM execution.")
        raise


def _validate_style(style: str | None) -> str:
    """
    Validate the commit message tone style.

    Allowed styles:
        - professional : "Refactor logging module to improve reliability."
        - neutral      : "Fix typo in configuration loader."
        - friendly     : "Hey! Just cleaned up the config parsing."
        - funny        : "Fixed the bug that was hiding like a ninja in our config."
        - excited      : "Amazing update! The config loader is now super fast!"
        - sarcastic    : "Oh look, another config bug. Shocking, right?"
        - apologetic   : "Sorry, my bad — this commit fixes the config error."
        - academic     : "This commit introduces a revised configuration parser based on robust principles."
        - None         : "No style instruction will be included in the prompt, allowing the model to choose its own tone".

    Parameters
    ----------
    style : str
        The tone style to validate.

    Returns
    -------
    str
        The validated style.

    Raises
    ------
    ValueError
        If the style is empty or not in the allowed list.
    """

    allowed_styles = {
        "professional",
        "neutral",
        "friendly",
        "funny",
        "excited",
        "sarcastic",
        "apologetic",
        "academic",
    }

    if style is None:
        log.info("Style set to None — style instruction disabled in prompt.")
        return "none"

    if not style or not isinstance(style, str):
        raise ValueError(
            f"Style must be a non-empty string. Allowed styles: {', '.join(sorted(allowed_styles))}, none"
        )

    normalized = style.lower().strip()

    if normalized == "none":
        log.info("Style set to 'none' — style instruction disabled in prompt.")
        return "none"

    if normalized not in allowed_styles:
        raise ValueError(
            f"Invalid style '{style}'. Allowed styles: {', '.join(sorted(allowed_styles))}, none"
        )

    log.info("Using style: %s", normalized)
    return normalized
