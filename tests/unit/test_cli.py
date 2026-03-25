from unittest.mock import patch

from git_cai_cli.cli import cli
from typer.testing import CliRunner

runner = CliRunner()


def test_no_args_invokes_callback(monkeypatch):
    """Patch run so CLI can be invoked without errors."""
    # Patch the run function already used in the cli module
    monkeypatch.setattr(cli, "run", lambda **kwargs: None)

    result = runner.invoke(cli.app, [])
    assert result.exit_code == 0


def test_list_flag(monkeypatch):
    """Test --list flag."""
    monkeypatch.setattr(cli, "run", lambda **kwargs: None)
    monkeypatch.setattr(cli, "resolve_mode", lambda **kwargs: "list_mode")
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    result = runner.invoke(cli.app, ["--list"])
    assert result.exit_code == 0


def test_all_flags_combined(monkeypatch):
    """Test multiple flags together."""
    monkeypatch.setattr(cli, "run", lambda **kwargs: None)
    monkeypatch.setattr(cli, "resolve_mode", lambda **kwargs: "mode")
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    args = ["--list", "--all", "--squash", "--update", "--debug"]
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 0


def test_generate_prompts_flag(monkeypatch):
    """Test -p / --generate-prompts flag."""

    called = {"ok": False}

    def _fake_generate(self):
        called["ok"] = True

    monkeypatch.setattr(
        "git_cai_cli.core.options.CliManager.generate_prompts_here",
        _fake_generate,
        raising=True,
    )

    result = runner.invoke(cli.app, ["-p"])
    assert result.exit_code == 0
    assert called["ok"] is True
    assert "commit_prompt.md" in result.stdout


# -----------------------------------------
# Tests for --provider / -P and --model / -m
# -----------------------------------------


def test_provider_flag_passed_to_run(monkeypatch):
    """Verify --provider value reaches run()."""
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    result = runner.invoke(cli.app, ["--provider", "anthropic"])
    assert result.exit_code == 0
    assert captured["provider_override"] == "anthropic"


def test_model_flag_passed_to_run(monkeypatch):
    """Verify --model value reaches run() together with --provider."""
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    result = runner.invoke(cli.app, ["--provider", "openai", "--model", "gpt-4o"])
    assert result.exit_code == 0
    assert captured["provider_override"] == "openai"
    assert captured["model_override"] == "gpt-4o"


def test_short_provider_flag(monkeypatch):
    """Verify -P short flag works."""
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    result = runner.invoke(cli.app, ["-P", "groq"])
    assert result.exit_code == 0
    assert captured["provider_override"] == "groq"


def test_short_model_flag(monkeypatch):
    """Verify -m short flag works."""
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    result = runner.invoke(cli.app, ["-P", "openai", "-m", "gpt-4o-mini"])
    assert result.exit_code == 0
    assert captured["model_override"] == "gpt-4o-mini"


# ---------------------
# Tests for --time / -t
# ---------------------


def test_time_flag_passed_to_run(monkeypatch):
    """Verify --time / -t value reaches run()."""
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    result = runner.invoke(cli.app, ["-t"])
    assert result.exit_code == 0
    assert captured["time_flag"] is True


# -----------------------------------------
# Tests for --install-completion / -i
# -----------------------------------------


def test_install_completion_calls_install():
    """Verify --install-completion calls our custom install_completion."""
    with patch("git_cai_cli.core.completion.install_completion") as mock_install:
        result = runner.invoke(cli.app, ["--install-completion"])

    assert result.exit_code == 0
    mock_install.assert_called_once()


def test_install_completion_short_flag():
    """Verify -i short flag works for completion install."""
    with patch("git_cai_cli.core.completion.install_completion") as mock_install:
        result = runner.invoke(cli.app, ["-i"])

    assert result.exit_code == 0
    mock_install.assert_called_once()


def test_completion_exits_before_run(monkeypatch):
    """Verify completion flags exit before run() is called."""
    run_called = {"called": False}

    def _fake_run(**kwargs):
        run_called["called"] = True

    monkeypatch.setattr(cli, "run", _fake_run)

    with patch("git_cai_cli.core.completion.install_completion"):
        runner.invoke(cli.app, ["-i"])

    assert run_called["called"] is False


# ---------------------
# Tests for --context / -x
# ---------------------


def test_context_flag_passed_to_run(monkeypatch):
    """Verify --context value reaches run()."""
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    result = runner.invoke(cli.app, ["--context", "Fixes JIRA-1234"])
    assert result.exit_code == 0
    assert captured["context"] == "Fixes JIRA-1234"


def test_context_short_flag_passed_to_run(monkeypatch):
    """Verify -x short flag works."""
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    result = runner.invoke(cli.app, ["-x", "Performance fix"])
    assert result.exit_code == 0
    assert captured["context"] == "Performance fix"


def test_context_none_by_default(monkeypatch):
    """Verify context is None when not provided."""
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "run", _fake_run)
    monkeypatch.setattr(cli, "validate_options", lambda **kwargs: None)

    result = runner.invoke(cli.app, [])
    assert result.exit_code == 0
    assert captured["context"] is None


def test_context_passed_to_validate_options(monkeypatch):
    """Verify --context is passed to validate_options."""
    captured = {}

    def _fake_validate(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, "run", lambda **kwargs: None)
    monkeypatch.setattr(cli, "validate_options", _fake_validate)

    result = runner.invoke(cli.app, ["-x", "ticket info"])
    assert result.exit_code == 0
    assert captured["context"] == "ticket info"
