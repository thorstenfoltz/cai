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
