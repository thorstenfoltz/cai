"""
Unit tests for the shared prologue/send-loop used by the read-only
generator modes (--explain, --split, --changelog, --release).

No network calls: the LLM boundary is a MagicMock throughout.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from git_cai_cli.core import generation
from git_cai_cli.core.generation import prepare, run_generation
from git_cai_cli.core.secrets import Finding, SecretLeakError


def _passthrough_validate(monkeypatch):
    """Replace _validate_llm_call with a direct forward to the send fn."""
    monkeypatch.setattr(
        generation,
        "_validate_llm_call",
        lambda fn, content, prompt, **kwargs: fn(content, prompt),
    )


def test_run_generation_returns_text_and_closes(monkeypatch):
    _passthrough_validate(monkeypatch)
    gen = MagicMock()
    gen.send.return_value = "OUTPUT"
    build = MagicMock(return_value=("content", "prompt"))

    out = run_generation(
        provider="openai",
        token="t",
        generator=gen,
        build=build,
        spinner_text="Working",
        measure=False,
    )

    assert out == "OUTPUT"
    gen.close.assert_called_once()
    build.assert_called_once()
    gen.send.assert_called_once_with("content", "prompt")
    gen.record_elapsed.assert_not_called()


def test_run_generation_records_elapsed_when_measuring(monkeypatch):
    _passthrough_validate(monkeypatch)
    gen = MagicMock()
    gen.send.return_value = "OUTPUT"

    run_generation(
        provider="openai",
        token="t",
        generator=gen,
        build=lambda: ("c", "p"),
        spinner_text="Working",
        measure=True,
    )

    gen.record_elapsed.assert_called_once()


def test_run_generation_exits_on_secret_leak(monkeypatch):
    finding = Finding(rule="token", path="a.py", line=1, masked="ab****yz")

    def boom(fn, content, prompt, **kwargs):
        raise SecretLeakError([finding])

    monkeypatch.setattr(generation, "_validate_llm_call", boom)
    gen = MagicMock()

    with pytest.raises(SystemExit):
        run_generation(
            provider="openai",
            token="t",
            generator=gen,
            build=lambda: ("c", "p"),
            spinner_text="Working",
            measure=False,
        )

    gen.close.assert_called_once()


def test_run_generation_exits_on_value_error(monkeypatch):
    def boom(fn, content, prompt, **kwargs):
        raise ValueError("bad key")

    monkeypatch.setattr(generation, "_validate_llm_call", boom)
    gen = MagicMock()

    with pytest.raises(SystemExit):
        run_generation(
            provider="openai",
            token="t",
            generator=gen,
            build=lambda: ("c", "p"),
            spinner_text="Working",
            measure=False,
        )


def test_prepare_exits_outside_git_repo():
    with patch.object(generation, "find_git_root", return_value=None):
        with pytest.raises(typer.Exit):
            prepare(None, None, None, None)


def test_prepare_exits_when_token_missing():
    config = {"default": "openai", "openai": {"model": "gpt"}}
    with (
        patch.object(generation, "find_git_root", return_value=Path("/repo")),
        patch.object(generation, "load_config", return_value=config),
        patch.object(generation, "load_token", return_value=None),
    ):
        with pytest.raises(SystemExit):
            prepare(None, None, None, None)


def test_prepare_allows_tokenless_provider():
    config = {"default": "ollama", "ollama": {"model": "llama3.1"}}
    with (
        patch.object(generation, "find_git_root", return_value=Path("/repo")),
        patch.object(generation, "load_config", return_value=config),
        patch.object(generation, "load_token", return_value=None),
    ):
        repo_root, cfg, provider, token = prepare(None, None, None, None)

    assert repo_root == Path("/repo")
    assert cfg is config
    assert provider == "ollama"
    assert token is None
