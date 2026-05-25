"""
Tests for the --signoff trailer feature.

Covers ``get_git_identity`` and ``append_signoff`` in
``git_cai_cli.core.gitutils``. All subprocess calls are mocked.
"""

from unittest.mock import MagicMock

import pytest
from git_cai_cli.core.gitutils import append_signoff, get_git_identity


def _identity_runner(name: str, email: str):
    """Return a fake subprocess.run that returns name/email for git config queries."""

    def runner(cmd, *args, **kwargs):
        result = MagicMock()
        if cmd == ["git", "config", "--get", "user.name"]:
            result.stdout = f"{name}\n"
        elif cmd == ["git", "config", "--get", "user.email"]:
            result.stdout = f"{email}\n"
        else:
            result.stdout = ""
        return result

    return runner


def test_get_git_identity_returns_name_and_email():
    name, email = get_git_identity(
        run_cmd=_identity_runner("Alice", "alice@example.com")
    )
    assert name == "Alice"
    assert email == "alice@example.com"


def test_get_git_identity_strips_whitespace():
    def runner(cmd, *args, **kwargs):
        result = MagicMock()
        if cmd[-1] == "user.name":
            result.stdout = "  Bob  \n"
        else:
            result.stdout = "  bob@example.com\n"
        return result

    name, email = get_git_identity(run_cmd=runner)
    assert name == "Bob"
    assert email == "bob@example.com"


def test_get_git_identity_raises_on_missing_name():
    runner = _identity_runner("", "alice@example.com")
    with pytest.raises(RuntimeError, match="user.name and user.email"):
        get_git_identity(run_cmd=runner)


def test_get_git_identity_raises_on_missing_email():
    runner = _identity_runner("Alice", "")
    with pytest.raises(RuntimeError, match="user.name and user.email"):
        get_git_identity(run_cmd=runner)


def test_append_signoff_adds_trailer_with_blank_line_separator():
    msg = "Fix typo in config loader"
    out = append_signoff(msg, identity=("Alice", "alice@example.com"))
    assert out == (
        "Fix typo in config loader\n\nSigned-off-by: Alice <alice@example.com>"
    )


def test_append_signoff_preserves_existing_body():
    msg = "Refactor logging\n\nMove handler setup into a single helper."
    out = append_signoff(msg, identity=("Alice", "alice@example.com"))
    assert out.startswith(msg)
    assert out.endswith("Signed-off-by: Alice <alice@example.com>")
    # blank line separates body from trailer
    assert "\n\nSigned-off-by:" in out


def test_append_signoff_does_not_end_with_newline():
    """No trailing newline — the editor flow relies on vim/nano adding
    one on save to detect that the user accepted the message."""
    out = append_signoff(
        "Fix typo in config loader", identity=("Alice", "alice@example.com")
    )
    assert not out.endswith("\n")


def test_append_signoff_idempotent_for_same_identity():
    msg = "Fix typo\n\nSigned-off-by: Alice <alice@example.com>"
    out = append_signoff(msg, identity=("Alice", "alice@example.com"))
    assert out == msg
    # exactly one Signed-off-by line
    assert out.count("Signed-off-by:") == 1


def test_append_signoff_appends_to_existing_trailer_block():
    msg = "Fix bug\n\nCo-authored-by: Carol <carol@example.com>"
    out = append_signoff(msg, identity=("Alice", "alice@example.com"))
    assert out == (
        "Fix bug\n\n"
        "Co-authored-by: Carol <carol@example.com>\n"
        "Signed-off-by: Alice <alice@example.com>"
    )


def test_append_signoff_when_other_signoff_already_present():
    msg = "Fix bug\n\nSigned-off-by: Bob <bob@example.com>"
    out = append_signoff(msg, identity=("Alice", "alice@example.com"))
    # No blank line between trailers
    assert out == (
        "Fix bug\n\n"
        "Signed-off-by: Bob <bob@example.com>\n"
        "Signed-off-by: Alice <alice@example.com>"
    )


def test_append_signoff_on_empty_message_just_returns_trailer():
    out = append_signoff("", identity=("Alice", "alice@example.com"))
    assert out == "Signed-off-by: Alice <alice@example.com>"


def test_append_signoff_calls_get_git_identity_when_no_identity_passed(monkeypatch):
    called: list[bool] = []

    def fake_identity(*args, **kwargs):
        called.append(True)
        return ("Alice", "alice@example.com")

    monkeypatch.setattr(
        "git_cai_cli.core.gitutils.get_git_identity", fake_identity
    )
    out = append_signoff("Fix typo")
    assert called
    assert "Signed-off-by: Alice <alice@example.com>" in out
