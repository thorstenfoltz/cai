import pytest
from git_cai_cli.core.validate import (
    _validate_config_keys,
    _validate_language,
    _validate_style,
)


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


def test_validate_config_keys_missing_globals_warn(caplog):
    caplog.set_level("WARNING")

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

    assert "Config is missing global keys" in caplog.text


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


def test_validate_language_missing_fallback(caplog):
    caplog.set_level("WARNING")

    result = _validate_language({}, {"en", "de"})
    assert result == "en"
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
