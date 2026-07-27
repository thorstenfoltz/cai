"""
Unit tests for git_cai_cli.core.llm module.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from git_cai_cli.core.llm import (
    CommitMessageGenerator,
    _model_rejects_temperature,
    _resolve_temperature,
)


# fixtures
@pytest.fixture
def config():
    """
    Provides a default configuration dictionary for testing.
    """
    return {
        "openai": {"model": "gpt-5.1", "temperature": 0},
        "gemini": {"model": "gemini-3.1-flash-lite", "temperature": 0},
        "anthropic": {"model": "claude-haiku-4-5", "temperature": 0},
        "groq": {"model": "openai/gpt-oss-20b", "temperature": 0},
        "xai": {"model": "grok-4.3", "temperature": 0},
        "ollama": {"model": "llama3.1", "temperature": 0},
        "language": "en",
        "default": "groq",
        "style": "professional",
        "emoji": True,
    }


@pytest.fixture
def generator(config):
    """
    Provides a CommitMessageGenerator instance for testing.
    """
    return CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="openai",
    )


def test_language_name_valid(generator):
    """
    Test that the _language_name method returns the correct language name
    """
    assert generator._language_name("fi", {"fi": "Finnish"}) == "Finnish"


def test_language_name_default(generator):
    """
    Test that the _language_name method defaults to English for unknown codes
    """
    assert generator._language_name("zzz", {}) == "English"


def test_emoji_enabled(generator):
    """
    Test that the _emoji_instruction method returns the correct string when emojis are enabled
    """
    assert (
        "Use relevant emojis at the start of the headline and in bullet points "
        "where they add clarity. Keep emojis purposeful — one per bullet at most."
        in generator._emoji_instruction()
    )


def test_emoji_disabled(generator):
    """
    Test that the _emoji_instruction method returns the correct string when emojis are disabled
    """
    generator.config["emoji"] = False
    assert (
        "Do not use any emojis in the commit message." in generator._emoji_instruction()
    )


def test_build_commit_prompt_contains_base_and_instructions(generator):
    """
    Test that _build_commit_prompt includes the base prompt and config instructions
    """
    out = generator._build_commit_prompt()

    # Base prompt content (from default file or hardcoded)
    assert "expert software engineer" in out
    assert "git commit message" in out

    # Config instructions appended
    assert "English" in out
    assert "professional" in out
    assert "emojis" in out.lower()


def test_build_squash_prompt_contains_base_and_instructions(generator):
    """
    Test that _build_squash_prompt includes the base prompt and config instructions
    """
    out = generator._build_squash_prompt()

    # Base prompt content (from default file or hardcoded)
    assert "expert software engineer" in out
    assert "summarize" in out.lower()

    # Config instructions appended
    assert "English" in out
    assert "professional" in out
    assert "emojis" in out.lower()


# test dispatch
def test_dispatch_valid_model(generator):
    """
    Test that the _dispatch_generate method calls the correct model generation method
    """
    with patch.object(
        generator, "generate_openai_compatible", return_value="ok"
    ) as mock_fn:
        result = generator._dispatch_generate("diff", "prompt")
        assert result == "ok"
        mock_fn.assert_called_once()


def test_dispatch_invalid_model(generator):
    """
    Test that the _dispatch_generate method raises ValueError for unknown model
    """
    generator.default_model = "unknown"
    with pytest.raises(ValueError):
        generator._dispatch_generate("diff", "prompt")


# test openai
def test_generate_openai(generator):
    """
    Test that the OpenAI-compatible call returns the correct message text
    """
    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "  message text  "}}]
    }

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        result = generator.generate_openai_compatible(
            "diff", "openai", system_prompt_override="sys"
        )

    assert result == "message text"
    assert mock_post.call_args[0][0] == "https://api.openai.com/v1/chat/completions"


def test_generate_openai_empty_content_raises(generator):
    """A null message content (empty/refused completion) must raise a clean
    ValueError instead of an AttributeError on .strip()."""
    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": None}}]
    }

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        with pytest.raises(ValueError, match="empty response"):
            generator.generate_openai_compatible(
                "diff", "openai", system_prompt_override="sys"
            )


# test anthropic
def test_generate_anthropic():
    """
    Test that the generate_anthropic method returns the correct message text
    """
    config = {
        "anthropic": {
            "model": "claude-sonnet-4-5",
            "temperature": 0.7,
        }
    }

    gen = CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="anthropic",
    )

    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "content": [{"text": "   test   "}],
    }

    with patch(f"{module_path}._http_post", mock_post):
        result = gen.generate_anthropic("abc", system_prompt_override="sys")

    assert result == "test"
    mock_post.assert_called_once()

    # --- Extract call details ---
    args, kwargs = mock_post.call_args

    # Positional arg 0 = URL
    called_url = args[0]
    assert called_url == "https://api.anthropic.com/v1/messages"

    assert kwargs["timeout"] == 30

    assert kwargs["headers"] == {
        "Content-Type": "application/json",
        "x-api-key": "fake-token",
        "anthropic-version": "2023-06-01",
    }

    assert kwargs["json"] == {
        "model": "claude-sonnet-4-5",
        "max_tokens": 32768,
        "temperature": 0.7,
        "system": "sys",
        "messages": [
            {"role": "user", "content": "abc"},
        ],
    }


# test gemini
def test_generate_gemini():
    """
    Test that the generate_gemini method returns the correct message text
    """
    config = {
        "gemini": {
            "model": "gemini-3.1-flash-lite",
            "temperature": 0.6,
        }
    }

    gen = CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="gemini",
    )

    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "   gemini text   "}]}}]
    }

    with patch(f"{module_path}._http_post", mock_post):
        result = gen.generate_gemini("abc", system_prompt_override="sys")

    assert result == "gemini text"
    mock_post.assert_called_once()

    args, kwargs = mock_post.call_args

    assert args[0] == (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-3.1-flash-lite:generateContent"
    )

    assert kwargs["timeout"] == 30

    assert kwargs["headers"] == {
        "Content-Type": "application/json",
        "x-goog-api-key": "fake-token",
    }

    assert kwargs["json"] == {
        "contents": [{"parts": [{"text": "sys\n\nabc"}]}],
        "generationConfig": {
            "temperature": 0.6,
        },
    }


# test groq
def test_generate_groq():
    """
    Test that the generate_groq method returns the correct message text
    """
    config = {
        "groq": {
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.7,
        }
    }

    gen = CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="groq",
    )

    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "   groq result   "}}]
    }

    with patch(f"{module_path}._http_post", mock_post):
        result = gen.generate_openai_compatible(
            "abc", "groq", system_prompt_override="sys"
        )

    assert result == "groq result"
    mock_post.assert_called_once()

    args, kwargs = mock_post.call_args

    assert args[0] == "https://api.groq.com/openai/v1/chat/completions"

    assert kwargs["timeout"] == 30

    assert kwargs["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer fake-token",
    }

    assert kwargs["json"] == {
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "abc"},
        ],
    }


# test xai
def test_generate_xai():
    """
    Test that the generate_xai method returns the correct message text
    """
    config = {
        "xai": {
            "model": "grok-4.3",
            "temperature": 0.7,
        }
    }

    gen = CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="xai",
    )

    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "   xai content   "}}]
    }

    with patch(f"{module_path}._http_post", mock_post):
        result = gen.generate_openai_compatible(
            "hello x", "xai", system_prompt_override="sys"
        )

    assert result == "xai content"
    mock_post.assert_called_once()

    # --- Extract call details ---
    args, kwargs = mock_post.call_args

    # Positional arg 0 = URL
    called_url = args[0]
    assert called_url == "https://api.x.ai/v1/chat/completions"

    assert kwargs["timeout"] == 30

    assert kwargs["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer fake-token",
    }

    assert kwargs["json"] == {
        "model": "grok-4.3",
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello x"},
        ],
    }


def test_generate_ollama():
    config = {
        "ollama": {
            "model": "llama3.1",
            "temperature": 0.2,
        }
    }

    gen = CommitMessageGenerator(
        token=None,
        config=config,
        default_model="ollama",
    )

    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.status_code = 200
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.return_value = {
        "message": {"content": "   ollama text   "},
    }

    with (
        patch.dict(f"{module_path}.os.environ", {}, clear=True),
        patch(f"{module_path}.shutil.which", return_value="/usr/bin/ollama"),
        patch(f"{module_path}.requests.get", return_value=MagicMock(status_code=200)),
        patch(f"{module_path}._http_post", mock_post),
    ):
        result = gen.generate_ollama("abc", system_prompt_override="sys")

    assert result == "ollama text"
    mock_post.assert_called_once()

    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:11434/api/chat"
    assert kwargs["timeout"] == 300
    assert kwargs["json"] == {
        "model": "llama3.1",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "abc"},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }


def test_generate_ollama_autostarts_and_stops_server():
    config = {
        "ollama": {
            "model": "llama3.1",
            "temperature": 0.0,
        }
    }

    gen = CommitMessageGenerator(
        token=None,
        config=config,
        default_model="ollama",
    )

    module_path = CommitMessageGenerator.__module__

    # First _ollama_is_running() -> False (two calls), then True (one call)
    mock_get = MagicMock(
        side_effect=[
            MagicMock(status_code=404),
            MagicMock(status_code=404),
            MagicMock(status_code=200),
        ]
    )

    mock_post = MagicMock()
    mock_post.return_value.status_code = 200
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.return_value = {
        "message": {"content": "ok"},
    }

    proc = MagicMock()
    proc.poll.return_value = None
    proc.pid = 1234

    with (
        patch.dict(f"{module_path}.os.environ", {}, clear=True),
        patch(f"{module_path}.shutil.which", return_value="/usr/bin/ollama"),
        patch(f"{module_path}.requests.get", mock_get),
        patch(f"{module_path}._http_post", mock_post),
        patch(f"{module_path}.subprocess.Popen", return_value=proc) as popen,
        patch(f"{module_path}.os.killpg") as killpg,
    ):
        assert gen.generate_ollama("abc", system_prompt_override=None) == "ok"
        gen.close()

    popen.assert_called_once()
    killpg.assert_called_once()


# ---------------------------
# Token usage logging tests
# ---------------------------


def test_token_usage_logged_openai(caplog):
    """Verify token usage is logged for OpenAI when token_logging is enabled."""
    config = {
        "openai": {"model": "gpt-5.1", "temperature": 0},
        "token_logging": True,
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="openai")

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }

    with caplog.at_level(logging.INFO):
        with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
            gen.generate_openai_compatible(
                "diff", "openai", system_prompt_override="sys"
            )

    assert "Token usage [openai]: prompt=100, completion=50, total=150" in caplog.text


def test_token_usage_logged_anthropic(caplog):
    """Verify token usage is logged for Anthropic when token_logging is enabled."""
    config = {
        "anthropic": {"model": "claude-haiku-4-5", "temperature": 0},
        "token_logging": True,
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="anthropic")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "content": [{"text": "msg"}],
        "usage": {"input_tokens": 200, "output_tokens": 80},
    }

    with caplog.at_level(logging.INFO):
        with patch(f"{module_path}._http_post", mock_post):
            gen.generate_anthropic("diff", system_prompt_override="sys")

    assert (
        "Token usage [anthropic]: prompt=200, completion=80, total=280" in caplog.text
    )


def test_token_usage_logged_gemini(caplog):
    """Verify token usage is logged for Gemini with usageMetadata format."""
    config = {
        "gemini": {"model": "gemini-3.1-flash-lite", "temperature": 0},
        "token_logging": True,
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="gemini")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "msg"}]}}],
        "usageMetadata": {"promptTokenCount": 150, "candidatesTokenCount": 60},
    }

    with caplog.at_level(logging.INFO):
        with patch(f"{module_path}._http_post", mock_post):
            gen.generate_gemini("diff", system_prompt_override="sys")

    assert "Token usage [gemini]: prompt=150, completion=60, total=210" in caplog.text


def test_token_usage_logged_groq(caplog):
    """Verify token usage is logged for Groq (OpenAI-compatible format)."""
    config = {
        "groq": {"model": "llama-3.3-70b", "temperature": 0},
        "token_logging": True,
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="groq")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 40},
    }

    with caplog.at_level(logging.INFO):
        with patch(f"{module_path}._http_post", mock_post):
            gen.generate_openai_compatible("diff", "groq", system_prompt_override="sys")

    assert "Token usage [groq]: prompt=120, completion=40, total=160" in caplog.text


def test_token_usage_logged_ollama(caplog):
    """Verify token usage is logged for Ollama (eval_count format)."""
    config = {
        "ollama": {"model": "llama3.1", "temperature": 0},
        "token_logging": True,
    }

    gen = CommitMessageGenerator(token=None, config=config, default_model="ollama")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.status_code = 200
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.return_value = {
        "message": {"content": "msg"},
        "prompt_eval_count": 90,
        "eval_count": 35,
    }

    with caplog.at_level(logging.INFO):
        with (
            patch.dict(f"{module_path}.os.environ", {}, clear=True),
            patch(f"{module_path}.shutil.which", return_value="/usr/bin/ollama"),
            patch(
                f"{module_path}.requests.get",
                return_value=MagicMock(status_code=200),
            ),
            patch(f"{module_path}._http_post", mock_post),
        ):
            gen.generate_ollama("diff", system_prompt_override="sys")

    assert "Token usage [ollama]: prompt=90, completion=35, total=125" in caplog.text


def test_token_usage_not_available(caplog):
    """Verify debug log when token usage is not in API response."""
    config = {
        "groq": {"model": "llama-3.3-70b", "temperature": 0},
        "token_logging": True,
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="groq")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    # Response without 'usage' key
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}],
    }

    with caplog.at_level(logging.DEBUG):
        with patch(f"{module_path}._http_post", mock_post):
            gen.generate_openai_compatible("diff", "groq", system_prompt_override="sys")

    assert "Token usage not available" in caplog.text


def test_token_usage_disabled(caplog):
    """Verify no token logging when token_logging is disabled."""
    config = {
        "groq": {"model": "llama-3.3-70b", "temperature": 0},
        "token_logging": False,
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="groq")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }

    with caplog.at_level(logging.DEBUG):
        with patch(f"{module_path}._http_post", mock_post):
            gen.generate_openai_compatible("diff", "groq", system_prompt_override="sys")

    assert "Token usage" not in caplog.text


def test_token_usage_disabled_when_key_missing(caplog):
    """Verify token logging is disabled when token_logging key is not in config (backward compat)."""
    config = {
        "groq": {"model": "llama-3.3-70b", "temperature": 0},
        # token_logging key intentionally absent — simulating old config
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="groq")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }

    with caplog.at_level(logging.DEBUG):
        with patch(f"{module_path}._http_post", mock_post):
            gen.generate_openai_compatible("diff", "groq", system_prompt_override="sys")

    assert "Token usage" not in caplog.text


# ---------------------------
# Tests for generate_mistral
# ---------------------------


def test_generate_mistral():
    """Test that generate_mistral returns the correct message text."""
    config = {
        "mistral": {
            "model": "mistral-large-latest",
            "temperature": 0.7,
        }
    }

    gen = CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="mistral",
    )

    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "   mistral result   "}}]
    }

    with patch(f"{module_path}._http_post", mock_post):
        result = gen.generate_openai_compatible(
            "abc", "mistral", system_prompt_override="sys"
        )

    assert result == "mistral result"
    mock_post.assert_called_once()

    args, kwargs = mock_post.call_args

    assert args[0] == "https://api.mistral.ai/v1/chat/completions"
    assert kwargs["timeout"] == 30

    assert kwargs["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer fake-token",
    }

    assert kwargs["json"] == {
        "model": "mistral-large-latest",
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "abc"},
        ],
    }


def test_generate_mistral_raises_on_http_error():
    """Test that generate_mistral raises on HTTP error via raise_for_status."""
    import requests

    config = {
        "mistral": {
            "model": "mistral-large-latest",
            "temperature": 0.7,
        }
    }

    gen = CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="mistral",
    )

    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.raise_for_status.side_effect = requests.HTTPError(
        "401 Unauthorized"
    )

    with patch(f"{module_path}._http_post", mock_post):
        with pytest.raises(requests.HTTPError):
            gen.generate_openai_compatible(
                "abc", "mistral", system_prompt_override="sys"
            )


def test_token_usage_logged_mistral(caplog):
    """Verify token usage is logged for Mistral when token_logging is enabled."""
    config = {
        "mistral": {"model": "mistral-large-latest", "temperature": 0},
        "token_logging": True,
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="mistral")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}],
        "usage": {"prompt_tokens": 110, "completion_tokens": 45},
    }

    with caplog.at_level(logging.INFO):
        with patch(f"{module_path}._http_post", mock_post):
            gen.generate_openai_compatible(
                "diff", "mistral", system_prompt_override="sys"
            )

    assert "Token usage [mistral]: prompt=110, completion=45, total=155" in caplog.text


# ---------------------------
# Tests for generate_deepseek
# ---------------------------


def test_generate_deepseek():
    """DeepSeek is routed through the shared OpenAI-compatible call."""
    config = {"deepseek": {"model": "deepseek-chat", "temperature": 0.5}}
    gen = CommitMessageGenerator(
        token="fake-token", config=config, default_model="deepseek"
    )

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "  deepseek result  "}}]
    }

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        result = gen.generate_openai_compatible(
            "diff content", "deepseek", system_prompt_override="sys"
        )

    assert result == "deepseek result"
    assert mock_post.call_args[0][0] == "https://api.deepseek.com/v1/chat/completions"
    assert mock_post.call_args[1]["json"]["model"] == "deepseek-chat"
    assert mock_post.call_args[1]["json"]["temperature"] == 0.5


def test_generate_deepseek_missing_temperature_does_not_raise():
    """Regression: a deepseek config without a temperature key (optional per
    validation/doctor) must not KeyError, and the request must omit the key."""
    config = {"deepseek": {"model": "deepseek-chat"}}
    gen = CommitMessageGenerator(
        token="fake-token", config=config, default_model="deepseek"
    )

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "ok"}}]
    }

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        result = gen.generate_openai_compatible("diff content", "deepseek")

    assert result == "ok"
    assert "temperature" not in mock_post.call_args[1]["json"]


def test_generate_deepseek_does_not_leak_openai_temperature():
    """Regression: each provider reads only its own config block, so a
    deepseek call with no temperature must not inherit openai's."""
    config = {
        "deepseek": {"model": "deepseek-chat"},
        "openai": {"model": "gpt-5.4-mini", "temperature": 0.5},
    }
    gen = CommitMessageGenerator(
        token="fake-token", config=config, default_model="deepseek"
    )

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "ok"}}]
    }

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        gen.generate_openai_compatible("diff content", "deepseek")

    assert "temperature" not in mock_post.call_args[1]["json"]


# ------------------------------------------
# Tests for None system_prompt_override guard
# ------------------------------------------


def test_generate_openai_none_system_prompt_omits_system_message():
    """OpenAI should not include system message when system_prompt_override is None."""
    config = {
        "openai": {"model": "gpt-5.1", "temperature": 0},
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="openai")

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}]
    }

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        gen.generate_openai_compatible("diff", "openai", system_prompt_override=None)

    messages = mock_post.call_args[1]["json"]["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


def test_generate_mistral_none_system_prompt_omits_system_message():
    """Mistral should not include system message when system_prompt_override is None."""
    config = {
        "mistral": {"model": "mistral-large-latest", "temperature": 0},
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="mistral")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}],
    }

    with patch(f"{module_path}._http_post", mock_post):
        gen.generate_openai_compatible("diff", "mistral", system_prompt_override=None)

    call_kwargs = mock_post.call_args[1]
    messages = call_kwargs["json"]["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


def test_generate_xai_none_system_prompt_omits_system_message():
    """xAI should not include system message when system_prompt_override is None."""
    config = {
        "xai": {"model": "grok-4.3", "temperature": 0},
    }

    gen = CommitMessageGenerator(token="fake", config=config, default_model="xai")
    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}],
    }

    with patch(f"{module_path}._http_post", mock_post):
        gen.generate_openai_compatible("diff", "xai", system_prompt_override=None)

    call_kwargs = mock_post.call_args[1]
    messages = call_kwargs["json"]["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


# ------------------------------------------
# Tests for raise_for_status in xAI
# ------------------------------------------


def test_generate_xai_raises_on_http_error():
    """Test that generate_xai raises on HTTP error via raise_for_status."""
    import requests

    config = {
        "xai": {
            "model": "grok-4.3",
            "temperature": 0.7,
        }
    }

    gen = CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="xai",
    )

    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.raise_for_status.side_effect = requests.HTTPError(
        "403 Forbidden"
    )

    with patch(f"{module_path}._http_post", mock_post):
        with pytest.raises(requests.HTTPError):
            gen.generate_openai_compatible("abc", "xai", system_prompt_override="sys")


# ---------------------------
# Tests for context in generate()
# ---------------------------


def test_generate_appends_context_to_diff(generator):
    """generate() should append context to the diff content."""
    with patch.object(generator, "_dispatch_generate", return_value="msg") as mock:
        generator.generate("diff output", context="Fixes JIRA-1234")

    call_args = mock.call_args
    content = call_args[1]["content"] if "content" in call_args[1] else call_args[0][0]
    assert "diff output" in content
    assert "Additional context from the author" in content
    assert "Fixes JIRA-1234" in content


def test_generate_without_context_passes_diff_only(generator):
    """generate() without context should pass only the diff."""
    with patch.object(generator, "_dispatch_generate", return_value="msg") as mock:
        generator.generate("diff output")

    call_args = mock.call_args
    content = call_args[1]["content"] if "content" in call_args[1] else call_args[0][0]
    assert content == "diff output"
    assert "Additional context:" not in content


def test_generate_with_none_context_passes_diff_only(generator):
    """generate() with context=None should pass only the diff."""
    with patch.object(generator, "_dispatch_generate", return_value="msg") as mock:
        generator.generate("diff output", context=None)

    call_args = mock.call_args
    content = call_args[1]["content"] if "content" in call_args[1] else call_args[0][0]
    assert content == "diff output"


def test_generate_with_empty_context_passes_diff_only(generator):
    """generate() with empty string context should pass only the diff."""
    with patch.object(generator, "_dispatch_generate", return_value="msg") as mock:
        generator.generate("diff output", context="")

    call_args = mock.call_args
    content = call_args[1]["content"] if "content" in call_args[1] else call_args[0][0]
    assert content == "diff output"


def test_summarize_appends_context_to_commit_messages(generator):
    """summarize_commit_history() with context appends it after the messages."""
    with patch.object(generator, "_dispatch_generate", return_value="summary") as mock:
        generator.summarize_commit_history("commit messages", context="Closes #42")

    call_args = mock.call_args
    content = call_args[1]["content"] if "content" in call_args[1] else call_args[0][0]
    assert "commit messages" in content
    assert "--- Additional context from the author ---" in content
    assert "Closes #42" in content


def test_summarize_without_context_passes_messages_only(generator):
    """summarize_commit_history() without context passes only the messages."""
    with patch.object(generator, "_dispatch_generate", return_value="summary") as mock:
        generator.summarize_commit_history("commit messages")

    call_args = mock.call_args
    content = call_args[1]["content"] if "content" in call_args[1] else call_args[0][0]
    assert content == "commit messages"


def test_summarize_with_none_context_passes_messages_only(generator):
    """summarize_commit_history() with None context should pass only the messages."""
    with patch.object(generator, "_dispatch_generate", return_value="summary") as mock:
        generator.summarize_commit_history("commit messages", context=None)

    call_args = mock.call_args
    content = call_args[1]["content"] if "content" in call_args[1] else call_args[0][0]
    assert content == "commit messages"


def test_summarize_with_empty_context_passes_messages_only(generator):
    """summarize_commit_history() with empty string context should pass only the messages."""
    with patch.object(generator, "_dispatch_generate", return_value="summary") as mock:
        generator.summarize_commit_history("commit messages", context="")

    call_args = mock.call_args
    content = call_args[1]["content"] if "content" in call_args[1] else call_args[0][0]
    assert content == "commit messages"


# ---- timeout resolution ----


def test_timeout_defaults_30_for_remote_providers(generator):
    assert generator._timeout("anthropic") == 30
    assert generator._timeout("groq") == 30


def test_timeout_defaults_300_for_ollama():
    gen = CommitMessageGenerator(token=None, config={}, default_model="ollama")
    assert gen._timeout("ollama") == 300


def test_timeout_global_override(generator):
    generator.config["timeout"] = 90
    assert generator._timeout("anthropic") == 90
    assert generator._timeout("ollama") == 90


def test_timeout_ollama_subconfig_wins_over_global():
    gen = CommitMessageGenerator(
        token=None,
        config={
            "timeout": 15,
            "ollama": {"model": "x", "temperature": 0, "timeout": 600},
        },
        default_model="ollama",
    )
    assert gen._timeout("ollama") == 600
    assert gen._timeout("groq") == 15


def test_generate_anthropic_uses_configured_max_tokens():
    config = {
        "anthropic": {
            "model": "claude-opus-4-6",
            "temperature": 0,
            "max_tokens": 12345,
        }
    }
    gen = CommitMessageGenerator(token="fake", config=config, default_model="anthropic")
    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {"content": [{"text": "ok"}]}

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        gen.generate_anthropic("abc", system_prompt_override="sys")

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["max_tokens"] == 12345


def test_generate_anthropic_defaults_max_tokens_to_32768():
    config = {"anthropic": {"model": "m", "temperature": 0}}
    gen = CommitMessageGenerator(token="t", config=config, default_model="anthropic")
    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {"content": [{"text": "ok"}]}

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        gen.generate_anthropic("abc", system_prompt_override="sys")

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["max_tokens"] == 32768


@pytest.mark.parametrize(
    "provider, model_key, response_json, url",
    [
        (
            "anthropic",
            {"model": "claude-haiku-4-5", "temperature": 0},
            {"content": [{"text": "t"}]},
            "https://api.anthropic.com/v1/messages",
        ),
        (
            "gemini",
            {"model": "gemini-3.1-flash-lite", "temperature": 0},
            {"candidates": [{"content": {"parts": [{"text": "t"}]}}]},
            None,
        ),
        (
            "groq",
            {"model": "m", "temperature": 0},
            {"choices": [{"message": {"content": "t"}}]},
            "https://api.groq.com/openai/v1/chat/completions",
        ),
        (
            "mistral",
            {"model": "m", "temperature": 0},
            {"choices": [{"message": {"content": "t"}}]},
            "https://api.mistral.ai/v1/chat/completions",
        ),
        (
            "xai",
            {"model": "m", "temperature": 0},
            {"choices": [{"message": {"content": "t"}}]},
            "https://api.x.ai/v1/chat/completions",
        ),
    ],
)
def test_remote_providers_respect_configured_timeout(
    provider, model_key, response_json, url
):
    config = {provider: model_key, "timeout": 77}
    gen = CommitMessageGenerator(token="t", config=config, default_model=provider)

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = response_json

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        gen._dispatch_generate("abc", "sys")

    _, kwargs = mock_post.call_args
    assert kwargs["timeout"] == 77
    if url is not None:
        assert mock_post.call_args[0][0] == url


def test_generate_ollama_uses_ollama_timeout():
    config = {
        "ollama": {"model": "llama3.1", "temperature": 0, "timeout": 42},
    }
    gen = CommitMessageGenerator(token=None, config=config, default_model="ollama")

    module_path = CommitMessageGenerator.__module__
    mock_post = MagicMock()
    mock_post.return_value.status_code = 200
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.return_value = {"message": {"content": "x"}}

    with (
        patch.dict(f"{module_path}.os.environ", {}, clear=True),
        patch(f"{module_path}.shutil.which", return_value="/usr/bin/ollama"),
        patch(f"{module_path}.requests.get", return_value=MagicMock(status_code=200)),
        patch(f"{module_path}._http_post", mock_post),
    ):
        gen.generate_ollama("abc", system_prompt_override="sys")

    _, kwargs = mock_post.call_args
    assert kwargs["timeout"] == 42


def test_generate_openai_receives_timeout():
    config = {"openai": {"model": "gpt-5.1", "temperature": 0}, "timeout": 55}
    gen = CommitMessageGenerator(token="t", config=config, default_model="openai")

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "ok"}}]
    }

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        gen.generate_openai_compatible("abc", "openai", system_prompt_override="sys")

    _, kwargs = mock_post.call_args
    assert kwargs["timeout"] == 55


# ---------------------------------------------------------------------------
# F0.4 — retry/backoff layer for transient HTTP failures
# ---------------------------------------------------------------------------


def test_retry_session_configures_status_forcelist():
    """The session's adapter must retry on 429 and the 5xx codes that
    typically signal transient upstream failures. Verifies the config
    contract directly because requests-mock intercepts above the
    urllib3 retry layer and would bypass the actual retry machinery."""
    from git_cai_cli.core.llm import _build_retrying_session

    session = _build_retrying_session()
    adapter = session.get_adapter("https://example.com/")
    retry = adapter.max_retries

    for code in (429, 500, 502, 503, 504):
        assert code in retry.status_forcelist, f"{code} must be retried"


def test_retry_session_allows_retries_on_post():
    """POST must be in the allowed retry methods — provider calls are POSTs."""
    from git_cai_cli.core.llm import _build_retrying_session

    session = _build_retrying_session()
    adapter = session.get_adapter("https://example.com/")
    allowed = {m.upper() for m in adapter.max_retries.allowed_methods}
    assert "POST" in allowed
    assert "GET" in allowed


def test_retry_session_uses_backoff_and_finite_attempts():
    """Retry config must have a positive backoff and a small bounded total
    so a permanently-down provider fails the commit, not hangs forever."""
    from git_cai_cli.core.llm import _build_retrying_session

    session = _build_retrying_session()
    adapter = session.get_adapter("https://example.com/")
    retry = adapter.max_retries

    assert retry.total is not None and retry.total >= 1
    assert retry.backoff_factor is not None and retry.backoff_factor > 0
    # Don't raise inside urllib3 — we want validate.py to classify the
    # final HTTPError.
    assert retry.raise_on_status is False


def test_http_post_routes_through_retrying_session(monkeypatch):
    """The provider-facing helper _http_post must use the retrying
    session, not raw requests.post."""
    import git_cai_cli.core.llm as llm_module

    # Reset the lru-cached session so we observe a fresh build
    llm_module._get_http_session.cache_clear()

    captured = {}
    real_get_session = llm_module._get_http_session

    def spy_get_session():
        s = real_get_session()
        captured["session"] = s
        return s

    monkeypatch.setattr(llm_module, "_get_http_session", spy_get_session)

    sentinel = MagicMock(name="response")

    def fake_post(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(llm_module, "_get_http_session", spy_get_session)
    spy_get_session().post = fake_post  # type: ignore[method-assign]

    result = llm_module._http_post("https://x", json={"a": 1}, timeout=5)

    assert result is sentinel
    assert captured["args"] == ("https://x",)
    assert captured["kwargs"] == {"json": {"a": 1}, "timeout": 5}


# ---------------------------------------------------------------------------
# F1.7 — max_output_tokens config (anthropic), backward-compatible with max_tokens
# ---------------------------------------------------------------------------


def test_anthropic_max_output_tokens_overrides_max_tokens():
    """max_output_tokens (canonical) wins over the legacy max_tokens key."""
    config = {
        "anthropic": {
            "model": "m",
            "temperature": 0,
            "max_tokens": 1000,
            "max_output_tokens": 5000,
        }
    }
    gen = CommitMessageGenerator(token="t", config=config, default_model="anthropic")

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {"content": [{"text": "ok"}]}

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        gen.generate_anthropic("abc", system_prompt_override="sys")

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["max_tokens"] == 5000


def test_anthropic_legacy_max_tokens_still_works():
    """Existing user configs that only use max_tokens must keep working."""
    config = {"anthropic": {"model": "m", "temperature": 0, "max_tokens": 7777}}
    gen = CommitMessageGenerator(token="t", config=config, default_model="anthropic")

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {"content": [{"text": "ok"}]}

    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        gen.generate_anthropic("abc", system_prompt_override="sys")

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["max_tokens"] == 7777


# ---------------------------------------------------------------------------
# F1.3 — Ollama startup timeout config + Windows gate
# ---------------------------------------------------------------------------


def test_ollama_startup_timeout_uses_config_value():
    config = {"ollama": {"model": "llama3", "temperature": 0, "startup_timeout": 30}}
    gen = CommitMessageGenerator(token=None, config=config, default_model="ollama")
    assert gen._ollama_startup_timeout() == 30.0


def test_ollama_startup_timeout_default():
    config = {"ollama": {"model": "llama3", "temperature": 0}}
    gen = CommitMessageGenerator(token=None, config=config, default_model="ollama")
    assert gen._ollama_startup_timeout() == 8.0


def test_ollama_start_skips_start_new_session_on_windows(monkeypatch, generator):
    """On Windows, start_new_session is invalid and would raise; the
    code must omit it."""
    import git_cai_cli.core.llm as llm_module

    monkeypatch.setattr(llm_module.sys, "platform", "win32")
    monkeypatch.setattr(generator, "_ollama_is_running", lambda: True)

    # Should not raise; running check returns True so Popen isn't called
    generator._start_ollama_server_if_needed()


# ---------------------------------------------------------------------------
# Task 1 — temperature detection + resolution helpers
# ---------------------------------------------------------------------------


def test_model_rejects_temperature_openai_gpt5():
    assert _model_rejects_temperature("gpt-5.4-mini") is True
    assert _model_rejects_temperature("gpt-5.2") is True
    assert _model_rejects_temperature("o3-mini") is True


def test_model_rejects_temperature_anthropic_opus_new():
    assert _model_rejects_temperature("claude-opus-4-7") is True
    assert _model_rejects_temperature("claude-opus-4-8") is True
    assert _model_rejects_temperature("claude-opus-5-1") is True


def test_model_accepts_temperature_kept_models():
    for m in (
        "claude-haiku-4-5",
        "openai/gpt-oss-20b",
        "gemini-3.1-flash-lite",
        "grok-4.3",
        "deepseek-chat",
        "codestral-2508",
        "llama3.1",
    ):
        assert _model_rejects_temperature(m) is False


def test_resolve_temperature_none_stays_none():
    assert _resolve_temperature("gpt-5.4-mini", None) is None


def test_resolve_temperature_accepted_returns_float():
    assert _resolve_temperature("gemini-3.1-flash-lite", 0) == 0.0


def test_resolve_temperature_rejected_warns_and_drops(caplog):
    with caplog.at_level(logging.WARNING):
        result = _resolve_temperature("gpt-5.4-mini", 0.7)
    assert result is None
    assert "does not support temperature" in caplog.text


# ---------------------------------------------------------------------------
# Task 3 — wiring _resolve_temperature into provider call sites
# ---------------------------------------------------------------------------


def test_groq_includes_temperature_for_accepting_model():
    """Groq model that accepts temperature keeps it in the request body."""
    config = {
        "groq": {"model": "openai/gpt-oss-20b", "temperature": 0},
    }

    gen = CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="groq",
    )

    module_path = CommitMessageGenerator.__module__

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}],
        "usage": {},
    }

    with patch(f"{module_path}._http_post", mock_post):
        gen.generate_openai_compatible("diff", "groq")

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["temperature"] == 0


def test_openai_omits_temperature_for_gpt5(caplog):
    """gpt-5.4-mini rejects temperature -> create() is called without it,
    and a warning is logged because a temperature was configured."""
    config = {
        "openai": {"model": "gpt-5.4-mini", "temperature": 0},
    }

    gen = CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="openai",
    )

    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}]
    }

    with caplog.at_level(logging.WARNING):
        with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
            gen.generate_openai_compatible("diff", "openai")

    assert "temperature" not in mock_post.call_args[1]["json"]
    assert "does not support temperature" in caplog.text
    assert "gpt-5.4-mini" in caplog.text


# ------------------------------------------------------------------------------
# Request builders for the read-only modes (explain / split / changelog / tag)
# ------------------------------------------------------------------------------


def _readonly_gen():
    config = {
        "default": "openai",
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "style": "professional",
        "emoji": False,
        "explain_prompt_file": "",
        "split_prompt_file": "",
        "changelog_prompt_file": "",
        "release_prompt_file": "",
    }
    return CommitMessageGenerator("tok", config, "openai")


def test_build_explain_request_includes_diff_and_context():
    gen = _readonly_gen()
    gen.kind = "explain"
    content, prompt = gen.build_explain_request("DIFFTEXT", context="ticket-9")
    assert "DIFFTEXT" in content
    assert "ticket-9" in content
    assert "explain" in prompt.lower()


def test_build_split_request_lists_files():
    gen = _readonly_gen()
    gen.kind = "split"
    content, prompt = gen.build_split_request("DIFF", ["a.py", "b.py"])
    assert "a.py" in content and "b.py" in content
    assert "commit" in prompt.lower()


def test_build_changelog_request_has_commits_and_files():
    gen = _readonly_gen()
    gen.kind = "changelog"
    content, prompt = gen.build_changelog_request("- feat: x", "a.py")
    assert "feat: x" in content and "a.py" in content
    assert "changelog" in prompt.lower()


def test_build_release_request_groups_by_type():
    gen = _readonly_gen()
    gen.kind = "release"
    content, prompt = gen.build_release_request("- fix: y")
    assert "fix: y" in content
    assert "release notes" in prompt.lower()
    # Headings are requested, and empty ones must be suppressed.
    assert "bug fixes" in prompt.lower()
    assert "omit any heading" in prompt.lower()


def test_split_prompt_has_no_style_suffix():
    """--split output is structured, so language/style/emoji must not leak in."""
    gen = _readonly_gen()
    gen.kind = "split"
    _, prompt = gen.build_split_request("DIFF", ["a.py"])
    assert "tone style" not in prompt


def test_explain_prompt_appends_language_and_style():
    gen = _readonly_gen()
    gen.kind = "explain"
    _, prompt = gen.build_explain_request("DIFF")
    assert "English" in prompt
    assert "tone style: professional" in prompt
