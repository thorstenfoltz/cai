"""Unit tests for the `--check` doctor mode (#32)."""

import pytest
import typer
from git_cai_cli.cli import modes
from git_cai_cli.cli.modes import Mode
from git_cai_cli.core import doctor

GOOD_CONFIG = {
    "openai": {"model": "gpt", "temperature": 0},
    "default": "openai",
    "language": "en",
    "style": "professional",
    "emoji": True,
}


class _NoFile:
    def exists(self):
        return False


def _patch_offline(monkeypatch, *, token="sk-realtoken1234567890", config=None, editor="vi"):
    monkeypatch.setattr(doctor, "load_config", lambda: dict(config or GOOD_CONFIG))
    monkeypatch.setattr(doctor, "_find_repo_config", lambda: None)
    monkeypatch.setattr(doctor, "load_token", lambda config=None: token)
    monkeypatch.setattr(doctor, "get_git_editor", lambda: editor)
    monkeypatch.setattr(doctor.shutil, "which", lambda exe: "/usr/bin/" + exe)
    monkeypatch.setattr(doctor, "FALLBACK_CONFIG_FILE", _NoFile())
    monkeypatch.setattr(doctor, "TOKENS_FILE", _NoFile())


# ---- mode resolution ----


def test_resolve_mode_check():
    assert (
        modes.resolve_mode(
            amend=False, check=True, list_flag=False, pr=False, squash=False, update=False
        )
        == Mode.CHECK
    )


def test_resolve_mode_check_conflicts(capsys):
    with pytest.raises(typer.Exit):
        modes.resolve_mode(
            amend=True, check=True, list_flag=False, pr=False, squash=False, update=False
        )


# ---- offline checks ----


def test_run_check_offline_ok(monkeypatch, capsys):
    _patch_offline(monkeypatch)
    assert doctor.run_check(live=False) == 0
    assert "All checks passed" in capsys.readouterr().out


def test_run_check_missing_token_fails(monkeypatch, capsys):
    _patch_offline(monkeypatch, token=None)
    assert doctor.run_check(live=False) == 1


def test_run_check_placeholder_token_fails(monkeypatch):
    _patch_offline(monkeypatch, token="PUT-YOUR-OPENAI-TOKEN-HERE")
    assert doctor.run_check(live=False) == 1


def test_run_check_invalid_config_early_exit(monkeypatch):
    _patch_offline(monkeypatch)

    def boom(*_a, **_k):
        raise KeyError("bad keys")

    monkeypatch.setattr(doctor, "_validate_config_keys", boom)
    assert doctor.run_check(live=False) == 1


# ---- live probe (mocked, never a real call) ----


def test_run_check_live_ok(monkeypatch, capsys):
    _patch_offline(monkeypatch)

    class _StubGen:
        def __init__(self, *_a, **_k):
            self.allow_secrets = False

        def generate(self, _diff):
            return "ok"

        def close(self):
            pass

    import git_cai_cli.core.llm as llm_mod

    monkeypatch.setattr(llm_mod, "CommitMessageGenerator", _StubGen)
    assert doctor.run_check(live=True) == 0
    assert "reachable" in capsys.readouterr().out
