"""
Validation utilities for configuration settings
"""

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)

_AUTH_STATUS_CODES = frozenset({401, 403})
_RATE_LIMIT_STATUS_CODES = frozenset({429})


def _extract_api_error_message(response: requests.Response | None) -> str:
    """Best-effort extraction of an upstream API error body's human message.

    Most providers return JSON like ``{"error": {"message": "...", ...}}``
    or ``{"error": "..."}``. Falls back to the raw text body if the JSON
    can't be parsed. Returns an empty string on any failure.
    """
    if response is None:
        return ""
    try:
        payload = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        text = (response.text or "").strip()
        return text[:500]

    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        msg = err.get("message") or err.get("type") or ""
        return str(msg).strip()
    if isinstance(err, str):
        return err.strip()
    return ""


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
        "branch_context",
        "conventional",
        "language",
        "default",
        "style",
        "emoji",
        "load_tokens_from",
        "prompt_file",
        "squash_prompt_file",
        "full_files_prompt_file",
        "token_logging",
        "measure_time",
        "timeout",
        "full_files",
        "pr_to_file",
        "pr_file_name",
        "pr_prompt_file",
        "stats",
        "stats_db_path",
    }
    # Internal escape-hatch keys: accepted if a user sets them, but never
    # reported as "missing" — they aren't part of the documented surface.
    internal_only_keys = {"stats_db_path"}
    allowed_provider_keys = set(reference.keys()) - allowed_global_keys

    config_keys = set(config.keys())

    # Reject unknown top-level keys
    unknown_keys = config_keys - allowed_global_keys - allowed_provider_keys
    if unknown_keys:
        log.error("Unknown config keys detected: %s", ", ".join(sorted(unknown_keys)))
        raise KeyError("Unknown config keys: " + ", ".join(sorted(unknown_keys)))

    # Info on missing global keys (non-fatal; defaults or global config will be used)
    missing_globals = allowed_global_keys - config_keys - internal_only_keys
    if missing_globals:
        log.info(
            "Config does not define: %s. Global or default values will be used.",
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
    """Validate the configured language code.

    - Returns an allowed language code.
    - Returns "none" if language injection should be disabled.

    Notes:
    - Missing/invalid values fall back to a *supported* default language ("en" if
      available, otherwise the first language in the allowed set).
    """

    if not allowed_languages:
        raise ValueError("allowed_languages must not be empty")

    lang_code = config.get("language")

    # Only treat explicit YAML null as "none". Missing key should fall back.
    if "language" in config and lang_code is None:
        log.info("Language set to None — language instruction disabled in prompt.")
        return "none"

    if isinstance(lang_code, str) and lang_code.strip().lower() == "none":
        log.info("Language set to 'none' — language instruction disabled in prompt.")
        return "none"

    fallback = "en" if "en" in allowed_languages else sorted(allowed_languages)[0]

    if not isinstance(lang_code, str) or not lang_code.strip():
        log.warning(
            "Language code '%s' is not supported. Falling back to '%s'.",
            lang_code,
            fallback,
        )
        return fallback

    normalized = lang_code.strip().lower()
    if normalized not in allowed_languages:
        log.warning(
            "Language code '%s' is not supported. Falling back to '%s'.",
            normalized,
            fallback,
        )
        return fallback

    return normalized


def _validate_llm_call(
    fn,
    *args,
    token: str | None,
    requires_token: bool = True,
    **kwargs,
) -> Any:
    """
    Executes an LLM call and converts authentication-related failures
    into clean, user-facing errors.
    """
    if requires_token and (not token or not token.strip()):
        log.error("LLM API token is missing.")
        log.error(
            "If this is the first run after installation, this is expected. Please configure your API key."
            " Perhaps your chosen model is not able to use certain settings. Run in debug mode for more details."
        )
        raise ValueError("API token is missing. Please configure your API key.")

    try:
        return fn(*args, **kwargs)

    except requests.HTTPError as exc:
        response = exc.response
        status = response.status_code if response is not None else None
        api_msg = _extract_api_error_message(response)

        if status in _AUTH_STATUS_CODES:
            log.error(
                "LLM authentication failed (HTTP %s)%s",
                status,
                f": {api_msg}" if api_msg else ".",
            )
            raise ValueError(
                f"API token is invalid or not authorized (HTTP {status}). "
                f"{api_msg or 'Please check your API key and its permissions.'}"
            ) from None

        if status in _RATE_LIMIT_STATUS_CODES:
            log.error(
                "LLM rate limit hit (HTTP %s)%s",
                status,
                f": {api_msg}" if api_msg else ".",
            )
            raise ValueError(
                f"Rate limit exceeded (HTTP {status}). "
                f"{api_msg or 'Please wait a minute and retry.'}"
            ) from None

        log.exception("LLM call failed (HTTP %s).", status)
        raise ValueError(
            f"LLM call failed (HTTP {status})."
            + (f" Upstream message: {api_msg}" if api_msg else "")
        ) from None

    except Exception:
        # Unexpected non-HTTP error — preserve the original traceback.
        # OpenAI-SDK paths surface their own exception classes whose
        # ``status_code`` attribute (when present) is checked by the
        # SDK-aware caller. Here we just log and re-raise so debug mode
        # users see the full stack.
        sdk_status = _openai_sdk_status_code()
        if sdk_status is not None:
            # Re-raise as ValueError with classification consistent with
            # the requests path so user-facing flow is uniform.
            if sdk_status in _AUTH_STATUS_CODES:
                log.error("LLM authentication failed (SDK status %s).", sdk_status)
                raise ValueError(
                    f"API token is invalid or not authorized (status {sdk_status}). "
                    "Please check your API key and its permissions."
                ) from None
            if sdk_status in _RATE_LIMIT_STATUS_CODES:
                log.error("LLM rate limit hit (SDK status %s).", sdk_status)
                raise ValueError(
                    f"Rate limit exceeded (status {sdk_status}). "
                    "Please wait a minute and retry."
                ) from None
        log.exception("Unexpected error during LLM execution.")
        raise


def _openai_sdk_status_code() -> int | None:
    """Return the HTTP status code from the in-flight OpenAI SDK exception,
    if one is currently being handled. Returns None otherwise.

    Done lazily so importing ``openai`` is not required when only
    ``requests``-based providers are used.
    """
    import sys

    exc = sys.exc_info()[1]
    if exc is None:
        return None

    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status

    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    return None


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
