from unittest.mock import MagicMock

import pytest
import requests
from git_cai_cli.core.validate import (
    _validate_config_keys,
    _validate_language,
    _validate_llm_call,
    _validate_style,
)


def _make_http_error(status: int, body: dict | str | None) -> requests.HTTPError:
    """Build a requests.HTTPError carrying a Response with the given body.

    Tests only — never makes a real HTTP call.
    """
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    if isinstance(body, dict):
        resp.json.return_value = body
        resp.text = ""
    elif isinstance(body, str):
        resp.json.side_effect = ValueError("not json")
        resp.text = body
    else:
        resp.json.side_effect = ValueError("not json")
        resp.text = ""
    err = requests.HTTPError(f"{status} error", response=resp)
    return err


def test_validate_config_keys_valid_minimal(caplog):
    caplog.set_level("WARNING")

    reference = {
        "openai": {},
        "gemini": {},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path/to/tokens.yml",
        "prompt_file": "",
        "squash_prompt_file": "",
    }

    config = {
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path/to/tokens.yml",
        "prompt_file": "",
        "squash_prompt_file": "",
    }

    _validate_config_keys(config, reference)

    # No warnings or errors
    assert caplog.text == ""


def test_validate_config_keys_unknown_key():
    reference = {
        "openai": {},
        "language": "en",
        "default": "openai",
    }

    config = {
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "default": "openai",
        "unknown": 123,
    }

    with pytest.raises(KeyError) as exc:
        _validate_config_keys(config, reference)

    assert "Unknown config keys: unknown" in str(exc.value)


def test_validate_config_keys_missing_globals_info(caplog):
    caplog.set_level("INFO")

    reference = {
        "openai": {},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
    }

    config = {
        "openai": {"model": "gpt", "temperature": 0},
    }

    _validate_config_keys(config, reference)

    assert "Config does not define:" in caplog.text
    assert "Global or default values will be used" in caplog.text


def test_validate_config_keys_does_not_complain_about_stats_db_path(caplog):
    """``stats_db_path`` is an internal escape-hatch — accepted if set
    but never reported as "missing" since users aren't expected to
    define it (the default DB path is always the same)."""
    caplog.set_level("INFO")

    reference = {
        "openai": {},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
    }
    # Define every documented top-level key so the only thing absent
    # from the validator's set is ``stats_db_path``.
    config = {
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "branch_context": False,
        "conventional": False,
        "load_tokens_from": None,
        "prompt_file": "",
        "squash_prompt_file": "",
        "full_files_prompt_file": "",
        "token_logging": False,
        "measure_time": False,
        "timeout": 30,
        "full_files": False,
        "pr_to_file": False,
        "pr_file_name": "PR.md",
        "pr_prompt_file": "",
        "stats": False,
    }

    _validate_config_keys(config, reference)

    assert "stats_db_path" not in caplog.text


def test_validate_config_keys_accepts_stats_db_path_when_set(caplog):
    """Setting ``stats_db_path`` is still allowed (e.g. tests use it) —
    it must not be rejected as an unknown key."""
    caplog.set_level("INFO")

    reference = {
        "openai": {},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
    }
    config = {
        "openai": {"model": "gpt", "temperature": 0},
        "stats_db_path": "/tmp/x.db",
    }

    _validate_config_keys(config, reference)  # must not raise


def test_validate_config_keys_no_providers():
    reference = {
        "openai": {},
        "gemini": {},
        "language": "en",
    }

    config = {
        "language": "en",
        "default": "openai",
    }

    with pytest.raises(KeyError) as exc:
        _validate_config_keys(config, reference)

    assert "At least one provider configuration must be defined" in str(exc.value)


def test_validate_config_keys_provider_not_mapping():
    reference = {
        "openai": {},
        "language": "en",
    }

    config = {
        "openai": "not-a-dict",
        "language": "en",
    }

    with pytest.raises(KeyError) as exc:
        _validate_config_keys(config, reference)

    assert "Provider 'openai' must be a mapping" in str(exc.value)


def test_validate_config_keys_provider_missing_fields():
    reference = {
        "openai": {},
        "language": "en",
    }

    config = {
        "openai": {"model": "gpt"},
        "language": "en",
    }

    with pytest.raises(KeyError) as exc:
        _validate_config_keys(config, reference)

    assert "missing required keys: temperature" in str(exc.value)


def test_validate_language_valid(caplog):
    result = _validate_language({"language": "de"}, {"en", "de", "fr"})
    assert result == "de"
    assert caplog.text == ""


def test_validate_language_invalid_fallback(caplog):
    caplog.set_level("WARNING")

    result = _validate_language({"language": "xx"}, {"en", "de"})
    assert result == "en"
    assert "not supported" in caplog.text


def test_validate_language_invalid_fallback_respects_allowed_set(caplog):
    caplog.set_level("WARNING")

    result = _validate_language({"language": "xx"}, {"de"})
    assert result == "de"
    assert "not supported" in caplog.text


def test_validate_language_missing_fallback(caplog):
    caplog.set_level("WARNING")

    result = _validate_language({}, {"en", "de"})
    assert result == "en"
    assert "not supported" in caplog.text


def test_validate_language_missing_fallback_respects_allowed_set(caplog):
    caplog.set_level("WARNING")

    result = _validate_language({}, {"de"})
    assert result == "de"
    assert "not supported" in caplog.text


@pytest.mark.parametrize(
    "style",
    [
        "professional",
        " neutral ",
        "Friendly",
        "FUNNY",
        "excited",
        "sarcastic",
        "apologetic",
        "academic",
    ],
)
def test_validate_style_accepts(style):
    result = _validate_style(style)
    assert isinstance(result, str)


def test_validate_style_invalid_value():
    with pytest.raises(ValueError) as exc:
        _validate_style("angry")

    assert "Invalid style" in str(exc.value)


def test_validate_style_none_is_allowed():
    assert _validate_style(None) == "none"


@pytest.mark.parametrize("style", ["", 123])
def test_validate_style_invalid_type(style):
    with pytest.raises(ValueError) as exc:
        _validate_style(style)  # type: ignore[arg-type]

    assert "Style must be a non-empty string" in str(exc.value)


# -------------------------------------------
# Tests for new config keys (token_logging, measure_time)
# -------------------------------------------


def test_new_config_keys_accepted_by_validator(caplog):
    """Verify token_logging and measure_time are accepted as valid global keys."""
    caplog.set_level("WARNING")

    reference = {
        "openai": {},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path/to/tokens.yml",
        "prompt_file": "",
        "squash_prompt_file": "",
        "token_logging": True,
        "measure_time": False,
    }

    config = {
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path/to/tokens.yml",
        "prompt_file": "",
        "squash_prompt_file": "",
        "token_logging": True,
        "measure_time": True,
    }

    _validate_config_keys(config, reference)

    # No warnings or errors
    assert caplog.text == ""


def test_branch_context_accepted_by_validator(caplog):
    """Verify branch_context is accepted as a valid global config key."""
    caplog.set_level("WARNING")

    reference = {
        "openai": {},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path/to/tokens.yml",
        "prompt_file": "",
        "squash_prompt_file": "",
        "token_logging": True,
        "measure_time": False,
        "branch_context": False,
    }

    config = {
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "branch_context": True,
    }

    _validate_config_keys(config, reference)

    assert caplog.text == ""


def test_missing_new_config_keys_non_fatal(caplog):
    """Verify missing token_logging/measure_time keys are non-fatal (backward compat)."""
    caplog.set_level("INFO")

    reference = {
        "openai": {},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path",
        "prompt_file": "",
        "squash_prompt_file": "",
        "token_logging": True,
        "measure_time": False,
    }

    # Config WITHOUT the new keys — simulates old config file
    config = {
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path",
        "prompt_file": "",
        "squash_prompt_file": "",
    }

    # Should NOT raise
    _validate_config_keys(config, reference)

    # Should log info about missing keys
    assert "Config does not define:" in caplog.text
    assert "measure_time" in caplog.text
    assert "token_logging" in caplog.text


# -------------------------------------------
# Tests for timeout / full_files (global) and
# anthropic.max_tokens / ollama.timeout (provider extras)
# -------------------------------------------


def test_timeout_and_full_files_accepted_by_validator(caplog):
    """timeout and full_files are accepted as valid global keys."""
    caplog.set_level("WARNING")

    reference = {
        "openai": {},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path",
        "prompt_file": "",
        "squash_prompt_file": "",
        "timeout": 30,
        "full_files": False,
    }

    config = {
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path",
        "prompt_file": "",
        "squash_prompt_file": "",
        "timeout": 45,
        "full_files": True,
    }

    _validate_config_keys(config, reference)
    assert caplog.text == ""


def test_anthropic_max_tokens_subkey_accepted(caplog):
    """Extra provider subkeys like anthropic.max_tokens are tolerated."""
    caplog.set_level("WARNING")

    reference = {
        "anthropic": {},
        "language": "en",
        "default": "anthropic",
        "style": "professional",
        "emoji": True,
    }

    config = {
        "anthropic": {
            "model": "claude",
            "temperature": 0,
            "max_tokens": 32768,
        },
        "language": "en",
        "default": "anthropic",
        "style": "professional",
        "emoji": True,
    }

    _validate_config_keys(config, reference)
    assert caplog.text == ""


def test_ollama_timeout_subkey_accepted(caplog):
    """Extra provider subkeys like ollama.timeout are tolerated."""
    caplog.set_level("WARNING")

    reference = {
        "ollama": {},
        "language": "en",
        "default": "ollama",
        "style": "professional",
        "emoji": True,
    }

    config = {
        "ollama": {
            "model": "llama3.1",
            "temperature": 0,
            "timeout": 600,
        },
        "language": "en",
        "default": "ollama",
        "style": "professional",
        "emoji": True,
    }

    _validate_config_keys(config, reference)
    assert caplog.text == ""


def test_old_config_missing_timeout_and_full_files_loads_cleanly(caplog):
    """Old configs without timeout/full_files keys must not raise."""
    caplog.set_level("INFO")

    reference = {
        "openai": {},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path",
        "prompt_file": "",
        "squash_prompt_file": "",
        "timeout": 30,
        "full_files": False,
    }

    # Old-style config without the new keys
    config = {
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "load_tokens_from": "/path",
        "prompt_file": "",
        "squash_prompt_file": "",
    }

    _validate_config_keys(config, reference)

    assert "timeout" in caplog.text
    assert "full_files" in caplog.text


# ---------------------------------------------------------------------------
# _validate_llm_call — F0.1: status-code based error classification
# ---------------------------------------------------------------------------


def test_validate_llm_call_missing_token_raises():
    """Missing token short-circuits before the function is invoked."""
    with pytest.raises(ValueError, match="API token is missing"):
        _validate_llm_call(lambda: "ok", token=None)


def test_validate_llm_call_token_not_required_runs_callable():
    """Token-less providers (e.g. Ollama) must pass through."""
    result = _validate_llm_call(lambda: "ok", token=None, requires_token=False)
    assert result == "ok"


def test_validate_llm_call_passes_through_args():
    """Positional and keyword args reach the wrapped callable."""

    def fn(a, *, b):
        return f"{a}-{b}"

    result = _validate_llm_call(fn, "x", token="t", b="y")
    assert result == "x-y"


@pytest.mark.parametrize("status", [401, 403])
def test_validate_llm_call_auth_status_raises_clear_value_error(status):
    """401/403 must classify as auth and surface the upstream message."""
    err = _make_http_error(status, {"error": {"message": "invalid api key"}})

    def fn():
        raise err

    with pytest.raises(ValueError) as exc_info:
        _validate_llm_call(fn, token="bad")

    assert str(status) in str(exc_info.value)
    assert "invalid api key" in str(exc_info.value)


def test_validate_llm_call_rate_limit_status_raises_clear_message():
    """429 must classify as rate-limit, not auth."""
    err = _make_http_error(429, {"error": {"message": "too many requests"}})

    def fn():
        raise err

    with pytest.raises(ValueError) as exc_info:
        _validate_llm_call(fn, token="t")

    assert "Rate limit exceeded" in str(exc_info.value)
    assert "429" in str(exc_info.value)
    assert "too many requests" in str(exc_info.value)


def test_validate_llm_call_400_is_not_misclassified_as_auth():
    """The old substring matcher misclassified 400 as auth — it must not anymore."""
    err = _make_http_error(400, {"error": {"message": "malformed request"}})

    def fn():
        raise err

    with pytest.raises(ValueError) as exc_info:
        _validate_llm_call(fn, token="t")

    msg = str(exc_info.value)
    assert "authentication" not in msg.lower()
    assert "invalid or not authorized" not in msg.lower()
    assert "400" in msg
    assert "malformed request" in msg


def test_validate_llm_call_5xx_raises_with_upstream_message():
    err = _make_http_error(503, {"error": {"message": "service unavailable"}})

    def fn():
        raise err

    with pytest.raises(ValueError) as exc_info:
        _validate_llm_call(fn, token="t")

    assert "503" in str(exc_info.value)
    assert "service unavailable" in str(exc_info.value)


def test_validate_llm_call_handles_non_json_body():
    """Some providers (e.g. nginx 502) return HTML — must not crash."""
    err = _make_http_error(502, "<html>bad gateway</html>")

    def fn():
        raise err

    with pytest.raises(ValueError) as exc_info:
        _validate_llm_call(fn, token="t")

    assert "502" in str(exc_info.value)


def test_validate_llm_call_openai_sdk_auth_error_classifies_as_auth():
    """An exception with a status_code of 401 (OpenAI SDK style) is
    classified as auth even when it is not requests.HTTPError."""

    class FakeOpenAIAuthError(Exception):
        status_code = 401

    def fn():
        raise FakeOpenAIAuthError("Incorrect API key provided")

    with pytest.raises(ValueError) as exc_info:
        _validate_llm_call(fn, token="t")

    assert "401" in str(exc_info.value)
    assert "invalid or not authorized" in str(exc_info.value)


def test_validate_llm_call_openai_sdk_rate_limit_classifies_as_rate_limit():
    class FakeOpenAIRateLimit(Exception):
        status_code = 429

    def fn():
        raise FakeOpenAIRateLimit("rate limited")

    with pytest.raises(ValueError) as exc_info:
        _validate_llm_call(fn, token="t")

    assert "Rate limit exceeded" in str(exc_info.value)
    assert "429" in str(exc_info.value)


def test_validate_llm_call_unrelated_exception_propagates():
    """Non-HTTP, non-SDK errors must propagate (preserves stack for debug)."""

    def fn():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _validate_llm_call(fn, token="t")
