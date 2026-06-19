"""Unit tests for the local pre-send secret scan (#25)."""

from unittest.mock import patch

import pytest
from git_cai_cli.core.llm import CommitMessageGenerator
from git_cai_cli.core.secrets import (
    SecretLeakError,
    format_findings,
    scan_for_secrets,
)

# Realistic-looking (but fake) values that the detectors should catch. These
# deliberately avoid placeholder markers and repeated-char filler.
REAL_AWS = "AKIAZ2Q7K9PLMN3WX1VD"
REAL_OPENAI = "sk-abcdef0123456789abcdef"
REAL_GITHUB = "ghp_0123456789ABCDEFabcdef0123456789"

SECRET_DIFF = f"diff --git a/x b/x\n+{REAL_AWS}\n"


def _gen(default_model="openai", **cfg):
    config = {
        "openai": {"model": "x", "temperature": 0},
        "ollama": {"model": "y", "temperature": 0},
        "default": default_model,
        "secret_scan": True,
    }
    config.update(cfg)
    return CommitMessageGenerator(token="fake", config=config, default_model=default_model)


# ---- scan_for_secrets ----


@pytest.mark.parametrize(
    "text,rule",
    [
        (REAL_AWS, "AWS access key"),
        (f"token = {REAL_OPENAI}", "OpenAI-style key"),
        (REAL_GITHUB, "GitHub token"),
        ("-----BEGIN RSA PRIVATE KEY-----", "private key"),
    ],
)
def test_scan_detects(text, rule):
    assert any(f.rule == rule for f in scan_for_secrets(text))


def test_scan_clean_text_has_no_findings():
    assert scan_for_secrets("just normal code\nx = 1\nreturn x") == []


@pytest.mark.parametrize(
    "text",
    [
        'password = "supersecretvalue123"',  # generic keyword=value: too noisy
        "api_key = config.get('api_key')",
        "secret_token = compute_hash(payload)",
        "sk-spinner-loading-animation-wrapper",  # css-ish, not an OpenAI key
    ],
)
def test_scan_ignores_generic_false_positives(text):
    assert scan_for_secrets(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "AKIAIOSFODNN7EXAMPLE",  # AWS docs' literal example key
        "AKIAEXAMPLEKEY123456",  # contains a dummy marker
        "ghp_" + "a" * 36,  # repeated-character filler
        "sk-" + "0" * 24,  # repeated-character filler
    ],
)
def test_scan_ignores_placeholders(text):
    assert scan_for_secrets(text) == []


def test_mask_does_not_echo_full_secret():
    finding = scan_for_secrets(REAL_AWS)[0]
    assert REAL_AWS not in finding.masked


def test_format_findings_names_the_rule():
    out = format_findings(scan_for_secrets(REAL_AWS))
    assert "AWS access key" in out


# ---- generator gating at the dispatch chokepoint ----


def test_dispatch_blocks_on_secret_and_does_not_send():
    gen = _gen()
    with patch.object(gen, "generate_openai") as mock_fn:
        with pytest.raises(SecretLeakError):
            gen._dispatch_generate(SECRET_DIFF, "prompt")
    mock_fn.assert_not_called()


def test_allow_secrets_bypasses_gate():
    gen = _gen()
    gen.allow_secrets = True
    with patch.object(gen, "generate_openai", return_value="ok") as mock_fn:
        assert gen._dispatch_generate(SECRET_DIFF, "prompt") == "ok"
    mock_fn.assert_called_once()


def test_secret_scan_disabled_in_config():
    gen = _gen(secret_scan=False)
    with patch.object(gen, "generate_openai", return_value="ok"):
        assert gen._dispatch_generate(SECRET_DIFF, "prompt") == "ok"


def test_tokenless_provider_skips_gate():
    gen = _gen(default_model="ollama")
    with patch.object(gen, "generate_ollama", return_value="ok") as mock_fn:
        assert gen._dispatch_generate(SECRET_DIFF, "prompt") == "ok"
    mock_fn.assert_called_once()
