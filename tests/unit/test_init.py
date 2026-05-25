"""
Tests for the --init interactive setup wizard.

All user-input primitives (``typer.prompt``, ``typer.confirm``,
``getpass.getpass``) are monkey-patched. Filesystem writes go to a
temporary directory.
"""

import os
import stat

import yaml
from git_cai_cli.core import init as init_module


class _InputDriver:
    """Sequence-based test driver for the wizard's three input primitives.

    Each list holds the queued answers; they are popped in order as
    the wizard asks.
    """

    def __init__(
        self,
        prompts: list[str],
        confirms: list[bool],
        passwords: list[str] | None = None,
    ):
        self.prompts = list(prompts)
        self.confirms = list(confirms)
        self.passwords = list(passwords or [])

    def prompt(self, *args, **kwargs):
        return self.prompts.pop(0)

    def confirm(self, *args, **kwargs):
        return self.confirms.pop(0)

    def getpass(self, *args, **kwargs):
        return self.passwords.pop(0)


def _install(monkeypatch, driver: _InputDriver):
    monkeypatch.setattr(init_module.typer, "prompt", driver.prompt)
    monkeypatch.setattr(init_module.typer, "confirm", driver.confirm)
    monkeypatch.setattr(init_module.getpass, "getpass", driver.getpass)


def test_wizard_writes_config_and_tokens_for_provider_requiring_key(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "cai_config.yml"
    tokens_path = tmp_path / "tokens.yml"

    driver = _InputDriver(
        prompts=["openai", "en", "professional"],
        confirms=[True],  # emoji
        passwords=["sk-test-123"],
    )
    _install(monkeypatch, driver)

    rc = init_module.run_init_wizard(config_path=config_path, tokens_path=tokens_path)
    assert rc == 0

    assert config_path.exists()
    config = yaml.safe_load(config_path.read_text())
    assert config["default"] == "openai"
    assert config["language"] == "en"
    assert config["style"] == "professional"
    assert config["emoji"] is True
    assert "openai" in config and isinstance(config["openai"], dict)
    assert "model" in config["openai"]

    assert tokens_path.exists()
    tokens = yaml.safe_load(tokens_path.read_text())
    assert tokens == {"openai": "sk-test-123"}

    # tokens.yml must be 0600
    mode = stat.S_IMODE(os.stat(tokens_path).st_mode)
    assert mode == 0o600


def test_wizard_skips_token_prompt_for_ollama(tmp_path, monkeypatch):
    config_path = tmp_path / "cai_config.yml"
    tokens_path = tmp_path / "tokens.yml"

    driver = _InputDriver(
        prompts=["ollama", "en", "neutral"],
        confirms=[False],  # emoji disabled
        passwords=[],  # no token prompt expected
    )
    _install(monkeypatch, driver)

    rc = init_module.run_init_wizard(config_path=config_path, tokens_path=tokens_path)
    assert rc == 0

    config = yaml.safe_load(config_path.read_text())
    assert config["default"] == "ollama"
    assert config["emoji"] is False

    # No tokens.yml created for tokenless provider
    assert not tokens_path.exists()


def test_wizard_aborts_when_existing_config_and_user_declines(tmp_path, monkeypatch):
    config_path = tmp_path / "cai_config.yml"
    tokens_path = tmp_path / "tokens.yml"
    config_path.write_text("default: groq\n")
    original = config_path.read_text()

    driver = _InputDriver(prompts=[], confirms=[False], passwords=[])
    _install(monkeypatch, driver)

    rc = init_module.run_init_wizard(config_path=config_path, tokens_path=tokens_path)
    assert rc == 0
    # File contents preserved
    assert config_path.read_text() == original


def test_wizard_preserves_other_providers_in_tokens_file(tmp_path, monkeypatch):
    config_path = tmp_path / "cai_config.yml"
    tokens_path = tmp_path / "tokens.yml"
    tokens_path.write_text(yaml.safe_dump({"anthropic": "sk-ant-old"}))

    driver = _InputDriver(
        prompts=["openai", "en", "professional"],
        confirms=[True],  # emoji
        passwords=["sk-openai-new"],
    )
    _install(monkeypatch, driver)

    rc = init_module.run_init_wizard(config_path=config_path, tokens_path=tokens_path)
    assert rc == 0

    tokens = yaml.safe_load(tokens_path.read_text())
    assert tokens == {
        "anthropic": "sk-ant-old",
        "openai": "sk-openai-new",
    }


def test_wizard_rejects_unknown_provider_then_accepts_valid(tmp_path, monkeypatch):
    config_path = tmp_path / "cai_config.yml"
    tokens_path = tmp_path / "tokens.yml"

    # First prompt answer is junk; second is valid
    driver = _InputDriver(
        prompts=["definitely-not-a-provider", "groq", "en", "professional"],
        confirms=[True],
        passwords=["gsk_test"],
    )
    _install(monkeypatch, driver)

    rc = init_module.run_init_wizard(config_path=config_path, tokens_path=tokens_path)
    assert rc == 0

    config = yaml.safe_load(config_path.read_text())
    assert config["default"] == "groq"


def test_wizard_accepts_provider_by_number(tmp_path, monkeypatch):
    from git_cai_cli.core.config import KNOWN_PROVIDERS

    providers = sorted(KNOWN_PROVIDERS)
    target = providers[2]
    is_tokenless = target == "ollama"

    config_path = tmp_path / "cai_config.yml"
    tokens_path = tmp_path / "tokens.yml"

    driver = _InputDriver(
        prompts=["3", "en", "professional"],
        confirms=[True],
        passwords=[] if is_tokenless else ["test-key"],
    )
    _install(monkeypatch, driver)

    rc = init_module.run_init_wizard(config_path=config_path, tokens_path=tokens_path)
    assert rc == 0

    config = yaml.safe_load(config_path.read_text())
    assert config["default"] == target


def test_wizard_handles_keyboard_interrupt(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "cai_config.yml"
    tokens_path = tmp_path / "tokens.yml"

    def raise_interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(init_module.typer, "prompt", raise_interrupt)

    rc = init_module.run_init_wizard(config_path=config_path, tokens_path=tokens_path)
    assert rc == 130
    assert not config_path.exists()
    assert not tokens_path.exists()
    captured = capsys.readouterr()
    assert "Aborted" in captured.err
