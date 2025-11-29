"""
Validation utilities for configuration settings
"""

import logging
from typing import Any

log = logging.getLogger(__name__)


def _validate_config_keys(config: dict[str, Any], reference: dict[str, Any]) -> None:
    """
    Check for missing or extra keys in config.
    """
    missing_keys = set(reference.keys()) - set(config.keys())
    extra_keys = set(config.keys()) - set(reference.keys())

    if missing_keys:
        log.warning("Config is missing keys: %s", ", ".join(missing_keys))
    if extra_keys:
        raise KeyError(f"Unknown config keys: {', '.join(extra_keys)}")


def _validate_language(config: dict[str, Any], allowed_languages: set[str]) -> str:
    """
    Validate that the language code exists in the allowed set.
    Returns the ISO 639-1 code.
    """
    lang_code = config.get("language")
    if not lang_code or lang_code not in allowed_languages:
        log.warning(
            "Language code '%s' is not supported. Falling back to 'en'.", lang_code
        )
        return "en"
    return lang_code


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

    if not style or not isinstance(style, str):
        raise ValueError(
            f"Style must be a non-empty string. Allowed styles: {', '.join(sorted(allowed_styles))}"
        )

    normalized = style.lower().strip()
    if normalized not in allowed_styles:
        raise ValueError(
            f"Invalid style '{style}'. Allowed styles: {', '.join(sorted(allowed_styles))}"
        )

    log.info("Using style: %s", normalized)
    return normalized
