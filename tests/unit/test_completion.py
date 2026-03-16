"""
Unit tests for git_cai_cli.core.completion module.
"""

from unittest.mock import patch

import pytest
import typer
from git_cai_cli.core.completion import (
    _BASH_SCRIPT,
    _FISH_SCRIPT,
    _ZSH_SCRIPT,
    _detect_shell,
    install_completion,
)


def test_detect_shell_zsh():
    """Detect zsh from SHELL env var."""
    with patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
        assert _detect_shell() == "zsh"


def test_detect_shell_bash():
    """Detect bash from SHELL env var."""
    with patch.dict("os.environ", {"SHELL": "/usr/bin/bash"}):
        assert _detect_shell() == "bash"


def test_detect_shell_fish():
    """Detect fish from SHELL env var."""
    with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
        assert _detect_shell() == "fish"


def test_detect_shell_fallback():
    """Falls back to bash when SHELL is not set."""
    with patch.dict("os.environ", {}, clear=True):
        assert _detect_shell() == "bash"


def test_zsh_script_contains_git_cai_function():
    """The zsh script defines a _git-cai function for git subcommand completion."""
    assert "_git-cai()" in _ZSH_SCRIPT
    assert "#compdef git-cai" in _ZSH_SCRIPT


def test_zsh_script_has_all_flags():
    """The zsh script lists all known flags."""
    for flag in [
        "--help",
        "--version",
        "--all",
        "--crazy",
        "--debug",
        "--generate-config",
        "--install-completion",
        "--list",
        "--model",
        "--generate-prompts",
        "--squash",
        "--time",
        "--update",
        "--provider",
    ]:
        assert flag in _ZSH_SCRIPT, f"Missing flag {flag} in zsh script"


def test_zsh_script_has_provider_completions():
    """The zsh script provides provider name completions for --provider."""
    for provider in [
        "anthropic",
        "deepseek",
        "gemini",
        "groq",
        "mistral",
        "ollama",
        "openai",
        "xai",
    ]:
        assert provider in _ZSH_SCRIPT


def test_bash_script_has_all_flags():
    """The bash script lists all known flags."""
    for flag in [
        "--help",
        "--version",
        "--all",
        "--crazy",
        "--debug",
        "--generate-config",
        "--install-completion",
        "--list",
        "--model",
        "--generate-prompts",
        "--squash",
        "--time",
        "--update",
        "--provider",
    ]:
        assert flag in _BASH_SCRIPT, f"Missing flag {flag} in bash script"


def test_bash_script_has_provider_completions():
    """The bash script provides provider name completions for --provider / -P."""
    for provider in [
        "anthropic",
        "deepseek",
        "gemini",
        "groq",
        "mistral",
        "ollama",
        "openai",
        "xai",
    ]:
        assert provider in _BASH_SCRIPT


def test_bash_script_completes_git_cai():
    """The bash script registers completion for git-cai and git cai."""
    assert "complete -o default -F _git_cai_completion git-cai" in _BASH_SCRIPT
    assert "__git_cai()" in _BASH_SCRIPT


def test_fish_script_has_all_flags():
    """The fish script lists all known flags."""
    for flag in [
        "help",
        "version",
        "all",
        "crazy",
        "debug",
        "generate-config",
        "install-completion",
        "list",
        "model",
        "generate-prompts",
        "squash",
        "time",
        "update",
        "provider",
    ]:
        assert flag in _FISH_SCRIPT, f"Missing flag {flag} in fish script"


def test_install_zsh(tmp_path):
    """Verify zsh completion installs to ~/.zfunc/_git-cai."""
    zfunc = tmp_path / ".zfunc"
    zshrc = tmp_path / ".zshrc"

    with (
        patch.dict("os.environ", {"SHELL": "/bin/zsh"}),
        patch("git_cai_cli.core.completion.Path.home", return_value=tmp_path),
    ):
        install_completion()

    target = zfunc / "_git-cai"
    assert target.exists()
    content = target.read_text()
    assert "_git-cai()" in content
    assert "#compdef git-cai" in content

    # .zshrc should have been updated
    assert zshrc.exists()
    zshrc_content = zshrc.read_text()
    assert ".zfunc" in zshrc_content


def test_install_zsh_does_not_duplicate_fpath(tmp_path):
    """Verify zsh install doesn't add fpath if already present."""
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("fpath=(~/.zfunc $fpath)\nautoload -Uz compinit && compinit\n")

    with (
        patch.dict("os.environ", {"SHELL": "/bin/zsh"}),
        patch("git_cai_cli.core.completion.Path.home", return_value=tmp_path),
    ):
        install_completion()

    # Should not duplicate the fpath line
    content = zshrc.read_text()
    assert content.count(".zfunc") == 1


def test_install_bash(tmp_path):
    """Verify bash completion installs to the correct location."""
    bashrc = tmp_path / ".bashrc"

    with (
        patch.dict("os.environ", {"SHELL": "/bin/bash"}),
        patch("git_cai_cli.core.completion.Path.home", return_value=tmp_path),
    ):
        install_completion()

    target = (
        tmp_path / ".local" / "share" / "bash-completion" / "completions" / "git-cai"
    )
    assert target.exists()
    content = target.read_text()
    assert "_git_cai_completion" in content

    # .bashrc should have been updated
    assert bashrc.exists()
    assert "git-cai" in bashrc.read_text()


def test_install_fish(tmp_path):
    """Verify fish completion installs to the correct location."""
    with (
        patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}),
        patch("git_cai_cli.core.completion.Path.home", return_value=tmp_path),
    ):
        install_completion()

    target = tmp_path / ".config" / "fish" / "completions" / "git-cai.fish"
    assert target.exists()
    content = target.read_text()
    assert "git-cai" in content


def test_install_unsupported_shell():
    """Verify unsupported shell exits with error."""
    with (
        patch.dict("os.environ", {"SHELL": "/bin/tcsh"}),
        pytest.raises(typer.Exit) as exc,
    ):
        install_completion()
    assert exc.value.exit_code == 1
