"""
Unit tests for custom OpenAI compatible providers (``base_url`` blocks).
"""

from unittest.mock import MagicMock, patch

import pytest
import typer
from git_cai_cli.core.config import (
    DEFAULT_CONFIG,
    apply_provider_overrides,
    completion_provider_names,
    custom_providers,
    load_token,
    provider_requires_token,
)
from git_cai_cli.core.llm import CommitMessageGenerator
from git_cai_cli.core.validate import _validate_config_keys


def _config(**blocks):
    return {"default": "openrouter", "language": "en", **blocks}


OPENROUTER = {"base_url": "https://openrouter.ai/api/v1", "model": "m"}
LMSTUDIO = {
    "base_url": "http://localhost:1234/v1/",
    "model": "m",
    "requires_token": False,
}


def _send(config, provider, token):
    """Run one generation with the HTTP layer mocked; return the mock."""
    mock_post = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": "msg"}}]
    }
    gen = CommitMessageGenerator(token=token, config=config, default_model=provider)
    gen.allow_secrets = True
    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        assert gen._dispatch_generate("diff", "sys") == "msg"
    return mock_post


# validation


def test_custom_block_accepted():
    _validate_config_keys(_config(openrouter=OPENROUTER), DEFAULT_CONFIG)


def test_custom_block_missing_model_rejected():
    with pytest.raises(KeyError, match="missing required keys: model"):
        _validate_config_keys(
            _config(openrouter={"base_url": "https://x.io/v1"}), DEFAULT_CONFIG
        )


@pytest.mark.parametrize("url", ["ftp://x.io/v1", "x.io/v1", "", 42])
def test_custom_block_bad_base_url_rejected(url):
    with pytest.raises(KeyError, match="base_url"):
        _validate_config_keys(
            _config(openrouter={"base_url": url, "model": "m"}), DEFAULT_CONFIG
        )


def test_unknown_mapping_without_base_url_still_rejected():
    with pytest.raises(KeyError, match="Unknown config keys"):
        _validate_config_keys(
            _config(groq={"model": "m"}, typo={"model": "m"}), DEFAULT_CONFIG
        )


# routing and auth


def test_custom_provider_posts_to_base_url_with_bearer():
    mock_post = _send(_config(openrouter=OPENROUTER), "openrouter", "sk-or")
    url = mock_post.call_args[0][0]
    headers = mock_post.call_args[1]["headers"]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-or"
    assert mock_post.call_args[1]["json"]["model"] == "m"


def test_tokenless_custom_provider_sends_no_auth_and_trailing_slash_ok():
    mock_post = _send(_config(lmstudio=LMSTUDIO), "lmstudio", None)
    assert mock_post.call_args[0][0] == "http://localhost:1234/v1/chat/completions"
    assert "Authorization" not in mock_post.call_args[1]["headers"]


def test_full_endpoint_url_not_doubled():
    block = {"base_url": "https://x.io/v1/chat/completions", "model": "m"}
    mock_post = _send(_config(x=block), "x", "t")
    assert mock_post.call_args[0][0] == "https://x.io/v1/chat/completions"


@pytest.mark.parametrize(
    "provider,key", [("openai", "max_completion_tokens"), ("x", "max_tokens")]
)
def test_max_output_tokens_sent_only_when_set(provider, key):
    block = {"base_url": "https://x.io/v1", "model": "m", "max_output_tokens": 512}
    body = _send(_config(**{provider: block}), provider, "t").call_args[1]["json"]
    assert body[key] == 512

    del block["max_output_tokens"]
    body = _send(_config(**{provider: block}), provider, "t").call_args[1]["json"]
    assert "max_tokens" not in body and "max_completion_tokens" not in body


def _post_url(provider, block, response):
    mock_post = MagicMock()
    mock_post.return_value.json.return_value = response
    gen = CommitMessageGenerator(
        token="t", config=_config(**{provider: block}), default_model=provider
    )
    gen.allow_secrets = True
    with patch(f"{CommitMessageGenerator.__module__}._http_post", mock_post):
        gen._dispatch_generate("diff", "sys")
    return mock_post.call_args[0][0]


def test_anthropic_and_gemini_default_and_base_url():
    anthropic = {"content": [{"text": "ok"}]}
    gemini = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
    assert (
        _post_url("anthropic", {"model": "c"}, anthropic)
        == "https://api.anthropic.com/v1/messages"
    )
    assert (
        _post_url("anthropic", {"model": "c", "base_url": "https://gw/"}, anthropic)
        == "https://gw/v1/messages"
    )
    assert (
        _post_url("gemini", {"model": "g"}, gemini)
        == "https://generativelanguage.googleapis.com/v1beta/models/g:generateContent"
    )
    assert (
        _post_url("gemini", {"model": "g", "base_url": "https://gw"}, gemini)
        == "https://gw/v1beta/models/g:generateContent"
    )


def test_base_url_overrides_builtin_openai_endpoint():
    block = {"base_url": "https://proxy.corp/v1", "model": "gpt"}
    mock_post = _send(_config(openai=block), "openai", "t")
    assert mock_post.call_args[0][0] == "https://proxy.corp/v1/chat/completions"


# config helpers


def test_provider_requires_token():
    cfg = _config(openrouter=OPENROUTER, lmstudio=LMSTUDIO)
    assert provider_requires_token(cfg, "openrouter")
    assert not provider_requires_token(cfg, "lmstudio")
    assert not provider_requires_token(cfg, "ollama")
    assert provider_requires_token(cfg, "groq")


def test_custom_providers_excludes_builtins():
    cfg = _config(openrouter=OPENROUTER, openai={"base_url": "https://p/v1"})
    assert custom_providers(cfg) == ["openrouter"]


def test_load_token_skips_tokenless_custom_provider(tmp_path):
    cfg = _config(lmstudio=LMSTUDIO)
    cfg["default"] = "lmstudio"
    cfg["load_tokens_from"] = tmp_path / "tokens.yml"
    assert load_token(config=cfg) is None
    assert not (tmp_path / "tokens.yml").exists()


def test_load_token_reads_custom_provider_token(tmp_path):
    tokens = tmp_path / "tokens.yml"
    tokens.write_text("openrouter: sk-or\n", encoding="utf-8")
    cfg = _config(openrouter=OPENROUTER, load_tokens_from=tokens)
    assert load_token(config=cfg) == "sk-or"


def test_provider_override_accepts_custom_and_rejects_unknown():
    cfg = _config(openrouter=OPENROUTER)
    cfg["default"] = "groq"
    apply_provider_overrides(cfg, "openrouter", None)
    assert cfg["default"] == "openrouter"

    with pytest.raises(typer.Exit):
        apply_provider_overrides(cfg, "nope", None)


def test_completion_provider_names_reads_custom_without_side_effects(tmp_path):
    cfg = tmp_path / "cai_config.yml"
    cfg.write_text(
        "openrouter:\n  base_url: https://openrouter.ai/api/v1\n  model: m\n",
        encoding="utf-8",
    )
    with patch("git_cai_cli.core.config._find_repo_config", return_value=cfg):
        names = completion_provider_names()
    assert names[-1] == "openrouter" and "groq" in names

    missing = tmp_path / "nope.yml"
    with (
        patch("git_cai_cli.core.config._find_repo_config", return_value=None),
        patch("git_cai_cli.core.config.FALLBACK_CONFIG_FILE", missing),
    ):
        assert "openrouter" not in completion_provider_names()
    assert not missing.exists()
