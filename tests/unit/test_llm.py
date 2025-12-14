"""
Unit tests for git_cai_cli.core.llm module.
"""

from unittest.mock import MagicMock, patch

import pytest
from git_cai_cli.core.llm import CommitMessageGenerator


# fixtures
@pytest.fixture
def config():
    """
    Provides a default configuration dictionary for testing.
    """
    return {
        "openai": {"model": "gpt-5.1", "temperature": 0},
        "gemini": {"model": "gemini-2.5-flash", "temperature": 0},
        "anthropic": {"model": "claude-haiku-4-5", "temperature": 0},
        "groq": {"model": "moonshotai/kimi-k2-instruct", "temperature": 0},
        "xai": {"model": "grok-4-1-fast-reasoning", "temperature": 0},
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
    Test that the _emoji_enabled method returns the correct string when emojis are enabled
    """
    assert (
        "Use relevant emojis in the commit message where appropriate. Emojis should enhance the clarity and tone of the message."
        in generator._emoji_enabled()
    )


def test_emoji_disabled(generator):
    """
    Test that the _emoji_enabled method returns the correct string when emojis are disabled
    """
    generator.config["emoji"] = False
    assert "Do not use any emojis in the commit message." in generator._emoji_enabled()


def test_system_prompt_full(generator):
    """
    Test that the _system_prompt method returns the full system prompt string
    """
    expected = (
        "You are an expert software engineer assistant. "
        "Your task is to generate a concise, professional git commit message, "
        "summarizing the provided git diff changes in Spanish. "
        "Keep the message clear and focused on what was changed and why. "
        "Always include a headline, followed by a bullet-point list of changes. "
        "If you detect sensitive information, mention it at the top, but still generate the message. "
        "Write the commit message in the following tone style: professional. "
        "Use relevant emojis in the commit message where appropriate. Emojis should enhance the clarity and tone of the message.."
    )

    out = generator._system_prompt("Spanish")
    assert out == expected


def test_summary_prompt_full(generator):
    """
    Test that the _summary_prompt method returns the full summary prompt string
    """
    expected = (
        "You are an expert software engineer assistant. "
        "Your task is to summarize multiple existing commit messages "
        "into a single clean git commit message. "
        "Write the final message in Japanese. "
        "Do not list each commit individually. "
        "Instead, infer the main purpose and overall change. "
        "Format:\n"
        "1. One short, clear headline.\n"
        "2. A concise bullet list describing the main themes of the work. "
        "Write the commit message in the following tone style: professional. "
        "Use relevant emojis in the commit message where appropriate. Emojis should enhance the clarity and tone of the message.."
    )

    out = generator._summary_prompt("Japanese")
    assert out == expected


# test dispatch
def test_dispatch_valid_model(generator):
    """
    Test that the _dispatch_generate method calls the correct model generation method
    """
    with patch.object(generator, "generate_openai", return_value="ok") as mock_fn:
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
    Test that the generate_openai method returns the correct message text
    """
    mock_client = MagicMock()
    mock_instance = MagicMock()
    mock_instance.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="  message text  "))]
    )
    mock_client.return_value = mock_instance

    result = generator.generate_openai(
        "diff", openai_cls=mock_client, system_prompt_override="sys"
    )
    assert result == "message text"

    mock_instance.chat.completions.create.assert_called_once()


# test anthropic
def test_generate_anthropic(generator):
    """
    Test that the generate_anthropic method returns the correct message text
    """
    mock_cls = MagicMock()
    mock_client = MagicMock()

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="  test  ")]

    mock_client.messages.create.return_value = mock_response
    mock_cls.return_value = mock_client

    result = generator.generate_anthropic(
        "abc", anthropic_cls=mock_cls, system_prompt_override="sys"
    )
    assert result == "test"
    mock_client.messages.create.assert_called_once()


# test gemini
def test_generate_gemini(generator):
    """
    Test that the generate_gemini method returns the correct message text
    """
    mock_cls = MagicMock()
    mock_client = MagicMock()

    mock_client.models.generate_content.return_value = MagicMock(text="gemini text")
    mock_cls.return_value = mock_client

    result = generator.generate_gemini(
        "abc", genai_cls=mock_cls, system_prompt_override="sys"
    )
    assert result == "gemini text"


# test groq
def test_generate_groq(generator):
    """
    Test that the generate_groq method returns the correct message text
    """
    mock_cls = MagicMock()
    mock_client = MagicMock()

    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=" groq result "))]
    )
    mock_cls.return_value = mock_client

    result = generator.generate_groq(
        "abc", genai_cls=mock_cls, system_prompt_override="sys"
    )
    assert result == "groq result"


# test xai
def test_generate_xai():
    """
    Test that the generate_xai method returns the correct message text
    """
    config = {
        "xai": {
            "model": "grok-4-1-fast-reasoning",
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

    with patch(f"{module_path}.requests.post", mock_post):
        result = gen.generate_xai("hello x", system_prompt_override="sys")

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
        "model": "grok-4-1-fast-reasoning",
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello x"},
        ],
    }
