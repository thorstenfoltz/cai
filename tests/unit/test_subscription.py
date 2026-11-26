"""
Tests for subscription mode: the provider's own CLI instead of its API.

No CLI is ever started: ``subprocess.run`` and ``shutil.which`` are mocked.
"""

import json
import logging
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from git_cai_cli.cli.cli import app
from git_cai_cli.core import config as config_module
from git_cai_cli.core import doctor
from git_cai_cli.core import init as init_module
from git_cai_cli.core import llm, subscription
from git_cai_cli.core.config import (
    DEFAULT_CONFIG,
    apply_provider_overrides,
    load_token,
    provider_requires_token,
    uses_subscription,
)
from git_cai_cli.core.llm import CommitMessageGenerator
from git_cai_cli.core.options import CliManager
from git_cai_cli.core.secrets import SecretLeakError
from git_cai_cli.core.subscription import SubscriptionError, run_subscription
from git_cai_cli.core.validate import _validate_llm_call
from typer.testing import CliRunner

CLAUDE_OK = json.dumps(
    {
        "is_error": False,
        "result": "Add ping\n",
        "usage": {
            "input_tokens": 2,
            "cache_creation_input_tokens": 600,
            "cache_read_input_tokens": 60,
            "output_tokens": 15,
        },
    }
)
CODEX_OK = "\n".join(
    [
        '{"type":"thread.started","thread_id":"x"}',
        "not json",
        '{"type":"item.completed","item":{"type":"reasoning","text":"hm"}}',
        '{"type":"item.completed","item":{"type":"agent_message","text":"Add ping"}}',
        '{"type":"turn.completed","usage":{"input_tokens":130,"output_tokens":10}}',
    ]
)
COPILOT_USAGE = {
    "modelMetrics": {"m": {"usage": {"inputTokens": 9, "outputTokens": 3}}}
}


class FakeCli:
    """Stands in for ``subprocess.run`` and records how it was called."""

    def __init__(self, stdout="", returncode=0, stderr="", usage=None, exc=None):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.usage, self.exc = usage, exc
        self.calls: list[dict] = []

    def __call__(self, argv, **kwargs):
        cwd = Path(kwargs["cwd"])
        prompt_file = cwd / "system_prompt.md"
        self.calls.append(
            {
                "argv": argv,
                "files": sorted(p.name for p in cwd.iterdir()),
                "system": prompt_file.read_text() if prompt_file.exists() else None,
                **kwargs,
            }
        )
        if self.exc:
            raise self.exc
        if self.usage is not None:
            (cwd / "usage.json").write_text(json.dumps(self.usage))
        return subprocess.CompletedProcess(
            argv, self.returncode, self.stdout, self.stderr
        )


def _install(monkeypatch, fake):
    monkeypatch.setattr(subscription.shutil, "which", lambda cmd: f"/bin/{cmd}")
    monkeypatch.setattr(subscription.subprocess, "run", fake)
    return fake


def _config(provider="anthropic", **extra):
    return {
        "default": provider,
        "subscription": True,
        "anthropic": {"model": "claude-haiku-5-5"},
        "openai": {"model": "gpt-6-luna"},
        "copilot": {"model": "auto"},
        "groq": {"model": "g"},
        **extra,
    }


def _generator(provider="anthropic", **extra):
    return CommitMessageGenerator(None, _config(provider, **extra), provider)


# ---- which mode is active ----


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_api_is_the_default(provider):
    assert DEFAULT_CONFIG["subscription"] is False
    assert not uses_subscription(DEFAULT_CONFIG, provider)
    assert not uses_subscription({}, provider)
    assert provider_requires_token(DEFAULT_CONFIG, provider)


@pytest.mark.parametrize("provider", ["anthropic", "openai", "copilot"])
def test_subscription_needs_no_token(provider, tmp_path):
    config = _config(provider, load_tokens_from=tmp_path / "tokens.yml")
    assert uses_subscription(config, provider)
    assert not provider_requires_token(config, provider)
    assert load_token(config) is None
    assert not (tmp_path / "tokens.yml").exists()


def test_other_providers_keep_using_the_api():
    assert not uses_subscription(_config("groq"), "groq")
    assert provider_requires_token(_config("groq"), "groq")


def test_copilot_has_no_api_so_it_always_uses_the_subscription():
    assert uses_subscription({"subscription": False}, "copilot")


def test_only_a_real_boolean_enables_subscription():
    assert not uses_subscription({"subscription": "false"}, "anthropic")


def test_default_provider_is_claude():
    assert DEFAULT_CONFIG["default"] == "anthropic"


# ---- command line override ----


@pytest.mark.parametrize(
    "args,expected",
    [
        ([], None),
        (["-U"], True),
        (["--subscription"], True),
        (["-K"], False),
        (["--no-subscription"], False),
    ],
)
def test_short_and_long_flags(args, expected):
    with patch("git_cai_cli.cli.cli.run") as run:
        result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["subscription_override"] is expected


def test_flag_enables_subscription():
    config = _config(subscription=False)
    apply_provider_overrides(config, None, None, subscription_override=True)
    assert uses_subscription(config, "anthropic")


def test_flag_disables_subscription():
    config = _config()
    apply_provider_overrides(config, None, None, subscription_override=False)
    assert not uses_subscription(config, "anthropic")


def test_flag_applies_to_the_overridden_provider():
    config = _config("groq", subscription=False)
    apply_provider_overrides(config, "openai", None, subscription_override=True)
    assert uses_subscription(config, "openai")


def test_flag_rejects_provider_without_subscription(capsys):
    with pytest.raises(typer.Exit):
        apply_provider_overrides(
            _config("groq"), None, None, subscription_override=True
        )
    err = capsys.readouterr().err
    assert "groq" in err
    assert "anthropic, copilot, openai" in err


def test_no_subscription_is_fine_for_api_only_provider():
    config = _config("groq")
    apply_provider_overrides(config, None, None, subscription_override=False)
    assert not uses_subscription(config, "groq")


def test_no_subscription_is_rejected_for_copilot(capsys):
    with pytest.raises(typer.Exit):
        apply_provider_overrides(
            _config("copilot"), None, None, subscription_override=False
        )
    assert "no API" in capsys.readouterr().err


def test_missing_provider_block_falls_back_to_bundled_default():
    config = {"default": "groq", "groq": {"model": "g"}}
    apply_provider_overrides(config, "copilot", None)
    assert config["copilot"] == DEFAULT_CONFIG["copilot"]
    assert config["copilot"] is not DEFAULT_CONFIG["copilot"]


def test_model_override_does_not_leak_into_bundled_default():
    config = {"default": "groq", "groq": {"model": "g"}}
    apply_provider_overrides(config, "copilot", "other")
    assert config["copilot"]["model"] == "other"
    assert DEFAULT_CONFIG["copilot"]["model"] == "auto"


def test_plain_model_override_keeps_its_api_block():
    config = {"default": "groq", "groq": {"model": "g"}}
    apply_provider_overrides(config, "openai", "m")
    assert config["openai"] == {"model": "m", "temperature": 0}


# ---- a custom API provider that already used the name "copilot" ----

CUSTOM_COPILOT = {"model": "m", "base_url": "http://localhost:4141/v1"}


def test_custom_copilot_endpoint_keeps_using_its_api():
    gen = _generator("copilot", subscription=False, copilot=CUSTOM_COPILOT)
    assert provider_requires_token(gen.config, "copilot")
    with (
        patch.object(llm, "run_subscription") as cli,
        patch.object(gen, "generate_openai_compatible", return_value="api"),
    ):
        assert gen.send("diff", "sys") == "api"
    cli.assert_not_called()


def test_custom_copilot_endpoint_can_switch_both_ways():
    config = _config("copilot", copilot=CUSTOM_COPILOT)
    assert uses_subscription(config, "copilot")
    apply_provider_overrides(config, None, None, subscription_override=False)
    assert not uses_subscription(config, "copilot")


def test_custom_copilot_endpoint_is_completed_once(monkeypatch, tmp_path):
    path = tmp_path / "cai_config.yml"
    path.write_text("copilot:\n  model: m\n  base_url: http://localhost/v1\n")
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: path)
    assert config_module.completion_provider_names().count("copilot") == 1


# ---- calling the CLI ----


def test_claude_call(monkeypatch):
    fake = _install(monkeypatch, FakeCli(CLAUDE_OK))
    result = run_subscription("anthropic", "claude-haiku-5-5", "diff", "sys", 30)

    assert result == ("Add ping", 662, 15)
    call = fake.calls[0]
    assert call["argv"][0] == "/bin/claude"
    assert "--model=claude-haiku-5-5" in call["argv"]
    assert call["input"] == "diff"
    assert call["system"] == "sys"
    assert call["timeout"] == 30


def test_claude_gets_no_tools(monkeypatch):
    fake = _install(monkeypatch, FakeCli(CLAUDE_OK))
    run_subscription("anthropic", "m", "diff", "sys", 30)
    argv = fake.calls[0]["argv"]
    assert argv[argv.index("--tools") + 1] == ""
    assert "--safe-mode" in argv


def test_codex_call(monkeypatch):
    fake = _install(monkeypatch, FakeCli(CODEX_OK))
    result = run_subscription("openai", "gpt-6-luna", "diff", "sys", 30)

    assert result == ("Add ping", 130, 10)
    call = fake.calls[0]
    assert call["argv"][:2] == ["/bin/codex", "exec"]
    assert "--model=gpt-6-luna" in call["argv"]
    assert "--sandbox=read-only" in call["argv"]
    assert call["input"] == "diff"
    assert call["system"] == "sys"


def test_codex_instructions_are_replaced_or_the_run_stops(monkeypatch):
    """Codex ignores unknown settings, which would drop the prompt unnoticed."""
    fake = _install(monkeypatch, FakeCli(CODEX_OK))
    run_subscription("openai", "m", "diff", "sys", 30)
    argv = fake.calls[0]["argv"]
    assert '--config=model_instructions_file="system_prompt.md"' in argv
    assert "--strict-config" in argv


def test_codex_cannot_reach_shell_web_or_connected_apps(monkeypatch):
    """Text in a diff must not be able to use the user's ChatGPT apps."""
    fake = _install(monkeypatch, FakeCli(CODEX_OK))
    run_subscription("openai", "m", "diff", "sys", 30)
    argv = fake.calls[0]["argv"]
    for feature in ("shell_tool", "apps", "plugins"):
        assert f"--disable={feature}" in argv
    assert '--config=web_search="disabled"' in argv
    assert "--ignore-user-config" in argv


def test_copilot_call(monkeypatch):
    fake = _install(monkeypatch, FakeCli("Add ping\n", usage=COPILOT_USAGE))
    result = run_subscription("copilot", "auto", "diff", "sys", 30)

    assert result == ("Add ping", 9, 3)
    call = fake.calls[0]
    assert call["argv"][0] == "/bin/copilot"
    assert "--model=auto" in call["argv"]
    assert "--available-tools=none" in call["argv"]
    assert call["input"] == "sys\n\ndiff"


def test_copilot_without_usage_file(monkeypatch):
    _install(monkeypatch, FakeCli("Add ping\n"))
    assert run_subscription("copilot", "auto", "diff", "sys", 30) == (
        "Add ping",
        None,
        None,
    )


@pytest.mark.parametrize("provider", ["anthropic", "openai", "copilot"])
def test_prompt_text_never_reaches_the_command_line(monkeypatch, provider):
    out = {"anthropic": CLAUDE_OK, "openai": CODEX_OK, "copilot": "Add ping"}
    fake = _install(monkeypatch, FakeCli(out[provider]))
    run_subscription(provider, "m", "DIFFTEXT", "SYSTEXT", 30)
    argv = " ".join(fake.calls[0]["argv"])
    assert "DIFFTEXT" not in argv
    assert "SYSTEXT" not in argv


def test_cli_runs_outside_the_repository(monkeypatch):
    fake = _install(monkeypatch, FakeCli(CODEX_OK))
    run_subscription("openai", "m", "diff", "sys", 30)
    cwd = Path(fake.calls[0]["cwd"])
    assert cwd != Path.cwd()
    assert fake.calls[0]["files"] == ["system_prompt.md"]
    assert not cwd.exists()  # removed afterwards


def test_api_credentials_are_hidden_from_the_cli(monkeypatch):
    """A leftover API key would silently bill the API account instead."""
    hidden = [
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "COPILOT_PROVIDER_BASE_URL",
    ]
    for name in hidden:
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/keep")
    fake = _install(monkeypatch, FakeCli(CLAUDE_OK))
    run_subscription("anthropic", "m", "diff", "sys", 30)
    env = fake.calls[0]["env"]
    assert not set(hidden) & env.keys()
    assert env["CLAUDE_CONFIG_DIR"] == "/keep"


# ---- failures ----


@pytest.mark.parametrize(
    "provider,command",
    [("anthropic", "claude"), ("openai", "codex"), ("copilot", "copilot")],
)
def test_missing_cli_explains_what_happened(monkeypatch, provider, command):
    monkeypatch.setattr(subscription.shutil, "which", lambda cmd: None)
    with pytest.raises(SubscriptionError) as exc:
        run_subscription(provider, "m", "diff", "sys", 30)
    message = str(exc.value)
    assert f"'{command}'" in message
    assert "not installed" in message
    assert "https://" in message
    # Only providers with an API can be told to switch back to it.
    assert ("--no-subscription" in message) == (provider != "copilot")


def test_claude_error_is_reported_with_login_hint(monkeypatch):
    out = json.dumps({"is_error": True, "result": "Not logged in"})
    _install(monkeypatch, FakeCli(out, returncode=1))
    with pytest.raises(SubscriptionError, match="Not logged in") as exc:
        run_subscription("anthropic", "m", "diff", "sys", 30)
    assert "claude auth login" in str(exc.value)


def test_claude_error_with_exit_code_zero(monkeypatch):
    out = json.dumps({"is_error": True, "result": "Usage limit reached"})
    _install(monkeypatch, FakeCli(out))
    with pytest.raises(SubscriptionError, match="Usage limit reached"):
        run_subscription("anthropic", "m", "diff", "sys", 30)


def test_codex_error_is_reported(monkeypatch):
    out = '{"type":"turn.failed","error":{"message":"401 Unauthorized"}}'
    _install(monkeypatch, FakeCli(out, returncode=1, stderr="noise"))
    with pytest.raises(SubscriptionError, match="401 Unauthorized"):
        run_subscription("openai", "m", "diff", "sys", 30)


def test_stderr_is_reported_when_the_cli_prints_nothing_else(monkeypatch):
    _install(monkeypatch, FakeCli("", returncode=1, stderr="Error: bad model\n"))
    with pytest.raises(SubscriptionError, match="Error: bad model"):
        run_subscription("copilot", "m", "diff", "sys", 30)


@pytest.mark.parametrize("provider", ["anthropic", "openai", "copilot"])
@pytest.mark.parametrize("stdout", ["", "[]", "null", '"text"'])
def test_odd_output_never_crashes(monkeypatch, provider, stdout):
    _install(monkeypatch, FakeCli(stdout, returncode=1))
    with pytest.raises(SubscriptionError):
        run_subscription(provider, "m", "diff", "sys", 30)


@pytest.mark.parametrize("provider", ["anthropic", "openai", "copilot"])
def test_empty_answer_is_an_error(monkeypatch, provider):
    _install(monkeypatch, FakeCli(""))
    with pytest.raises(SubscriptionError, match="empty response"):
        run_subscription(provider, "m", "diff", "sys", 30)


def test_timeout_names_the_setting(monkeypatch):
    _install(monkeypatch, FakeCli(exc=subprocess.TimeoutExpired("claude", 30)))
    with pytest.raises(SubscriptionError, match="30 seconds") as exc:
        run_subscription("anthropic", "m", "diff", "sys", 30)
    assert "--timeout" in str(exc.value)


def test_cli_that_cannot_start(monkeypatch):
    _install(monkeypatch, FakeCli(exc=OSError("exec format error")))
    with pytest.raises(SubscriptionError, match="exec format error"):
        run_subscription("anthropic", "m", "diff", "sys", 30)


def test_error_reaches_the_user_without_a_traceback(caplog):
    def fail():
        raise SubscriptionError("not installed")

    with pytest.raises(SubscriptionError, match="not installed"):
        _validate_llm_call(fail, token=None, requires_token=False)
    assert "Traceback" not in caplog.text
    assert "Unexpected error" not in caplog.text


# ---- generator ----


@pytest.mark.parametrize("provider", ["anthropic", "openai", "copilot"])
def test_generator_uses_the_cli_and_not_the_api(provider):
    gen = _generator(provider)
    with (
        patch.object(llm, "run_subscription", return_value=("ok", 5, 2)) as cli,
        patch.object(llm, "_http_post") as http,
    ):
        assert gen.send("diff", "sys") == "ok"
    http.assert_not_called()
    assert cli.call_args.args[:2] == (provider, gen.config[provider]["model"])


@pytest.mark.parametrize(
    "provider,method",
    [
        ("anthropic", "generate_anthropic"),
        ("openai", "generate_openai_compatible"),
        ("groq", "generate_openai_compatible"),
    ],
)
def test_generator_still_uses_the_api(provider, method):
    gen = _generator(provider, subscription=provider == "groq")
    with (
        patch.object(llm, "run_subscription") as cli,
        patch.object(gen, method, return_value="api") as api,
    ):
        assert gen.send("diff", "sys") == "api"
    api.assert_called_once()
    cli.assert_not_called()


@pytest.mark.parametrize("provider", ["anthropic", "openai", "copilot"])
@pytest.mark.parametrize("source", ["configured", "home", "code"])
def test_prompt_fallback_reaches_the_cli(monkeypatch, tmp_path, provider, source):
    """Configured file, then ~/.config/cai, then the prompt in the code."""
    out = {"anthropic": CLAUDE_OK, "openai": CODEX_OK, "copilot": "Add ping"}
    fake = _install(monkeypatch, FakeCli(out[provider]))
    monkeypatch.setattr(llm, "CONFIG_DIR", tmp_path)
    if source != "code":
        (tmp_path / "commit_prompt.md").write_text("HOME PROMPT")
    if source == "configured":
        (tmp_path / "mine.md").write_text("CONFIGURED PROMPT")

    gen = _generator(provider, prompt_file=str(tmp_path / "mine.md"))
    gen.send(*gen.build_commit_request("diff"))

    expected = {
        "configured": "CONFIGURED PROMPT",
        "home": "HOME PROMPT",
        "code": llm.HARDCODED_COMMIT_PROMPT.strip(),
    }
    call = fake.calls[0]
    assert (call["system"] or call["input"]).startswith(expected[source])


def test_secret_scan_still_runs():
    """No token is needed, but the diff does leave the machine."""
    gen = _generator("copilot")
    with patch.object(llm, "run_subscription") as cli:
        with pytest.raises(SecretLeakError):
            gen.send("diff --git a/x b/x\n+AKIA" "Z2Q7K9PLMN3WX1VD\n", "sys")
    cli.assert_not_called()


def test_token_usage_is_logged(caplog):
    gen = _generator(token_logging=True)
    with (
        patch.object(llm, "run_subscription", return_value=("ok", 5, 2)),
        caplog.at_level(logging.INFO),
    ):
        gen.send("diff", "sys")
    assert "Token usage [anthropic]: prompt=5, completion=2, total=7" in caplog.text


def test_temperature_is_ignored_with_a_warning(caplog):
    gen = _generator(anthropic={"model": "m", "temperature": 0.5})
    with patch.object(llm, "run_subscription", return_value=("ok", 5, 2)):
        gen.send("diff", "sys")
    assert "temperature" in caplog.text
    assert gen._settings_snapshot("anthropic")["temperature"] is None


def test_log_names_the_active_mode(caplog):
    with caplog.at_level(logging.INFO):
        _generator()._log_target()
        _generator(subscription=False)._log_target()
    assert "subscription" in caplog.messages[0]
    assert "API" in caplog.messages[1]


@pytest.mark.parametrize(
    "message",
    [
        "Prompt is too long",
        "Your input exceeds the context window of this model",
        "Input exceeds the maximum length of 1048576 characters",
    ],
)
def test_oversized_input_is_shortened_and_retried(message):
    gen = _generator()
    diff = "diff --git a/x b/x\n" + "+line\n" * 500
    with patch.object(
        llm, "run_subscription", side_effect=[SubscriptionError(message), ("ok", 1, 1)]
    ) as cli:
        assert gen.send(diff, "sys") == "ok"
    first, second = (call.args[2] for call in cli.call_args_list)
    assert len(second) < len(first)


def test_usage_limit_is_not_mistaken_for_oversized_input():
    gen = _generator()
    error = SubscriptionError("You have exceeded your weekly limit")
    with patch.object(llm, "run_subscription", side_effect=error) as cli:
        with pytest.raises(SubscriptionError):
            gen.send("diff", "sys")
    cli.assert_called_once()


# ---- doctor, wizard, listings ----


class _NoFile:
    def exists(self):
        return False


def _run_doctor(monkeypatch, config, found):
    monkeypatch.setattr(doctor, "load_config", lambda: config)
    monkeypatch.setattr(doctor, "_find_repo_config", lambda: None)
    monkeypatch.setattr(doctor, "get_git_editor", lambda: "vi")
    monkeypatch.setattr(doctor, "FALLBACK_CONFIG_FILE", _NoFile())
    monkeypatch.setattr(
        doctor.shutil, "which", lambda c: f"/bin/{c}" if found or c == "vi" else None
    )
    return doctor.run_check()


def test_check_passes_when_the_cli_is_installed(monkeypatch, capsys):
    config = _config(style="neutral")
    assert _run_doctor(monkeypatch, config, found=True) == 0
    assert "'claude'" in capsys.readouterr().out


def test_check_fails_when_the_cli_is_missing(monkeypatch, capsys):
    config = _config(style="neutral")
    assert _run_doctor(monkeypatch, config, found=False) == 1
    assert "not installed" in capsys.readouterr().out


def test_check_accepts_a_missing_provider_block(monkeypatch):
    config = {"default": "copilot", "groq": {"model": "g"}, "style": "neutral"}
    assert _run_doctor(monkeypatch, config, found=True) == 0


def _run_wizard(monkeypatch, tmp_path, provider, confirms):
    answers = iter([provider, "en", "neutral"])
    confirms = iter(confirms)
    monkeypatch.setattr(init_module.typer, "prompt", lambda *a, **k: next(answers))
    monkeypatch.setattr(init_module.typer, "confirm", lambda *a, **k: next(confirms))
    monkeypatch.setattr(init_module.getpass, "getpass", lambda *a, **k: "key")
    config_path, tokens_path = tmp_path / "c.yml", tmp_path / "t.yml"
    assert init_module.run_init_wizard(config_path, tokens_path) == 0
    import yaml

    return yaml.safe_load(config_path.read_text()), tokens_path.exists()


@pytest.mark.parametrize("answer", [True, False])
def test_wizard_offers_the_subscription(monkeypatch, tmp_path, answer):
    config, has_token = _run_wizard(monkeypatch, tmp_path, "anthropic", [False, answer])
    assert config["subscription"] is answer
    assert has_token is not answer


def test_wizard_does_not_ask_for_copilot(monkeypatch, tmp_path):
    config, has_token = _run_wizard(monkeypatch, tmp_path, "copilot", [False])
    assert config["default"] == "copilot"
    assert not has_token


def test_provider_list_mentions_the_subscription(monkeypatch):
    monkeypatch.setattr("git_cai_cli.core.options.load_config", dict)
    lines = {
        line.split()[0]: line
        for line in CliManager().list_providers().splitlines()
        if line.startswith("  ")
    }
    assert "token or subscription" in lines["anthropic"]
    assert "token or subscription" in lines["openai"]
    assert "subscription, no token required" in lines["copilot"]
    assert "subscription" not in lines["groq"]


def test_copilot_is_a_known_provider():
    assert "copilot" in config_module.KNOWN_PROVIDERS
