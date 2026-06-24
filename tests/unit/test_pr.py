"""
Unit tests for git_cai_cli.core.pr.run_pr and supporting helpers.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from git_cai_cli.core.gitutils import detect_base_branch
from git_cai_cli.core.llm import CommitMessageGenerator
from git_cai_cli.core.pr import run_pr
from git_cai_cli.core.prompts_fallback import HARDCODED_PR_PROMPT


@pytest.fixture
def mock_repo_root(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def base_config():
    return {
        "default": "openai",
        "openai": {"model": "gpt", "temperature": 0},
        "language": "en",
        "style": "professional",
        "emoji": True,
        "prompt_file": "",
        "squash_prompt_file": "",
        "pr_prompt_file": "",
        "pr_to_file": False,
        "pr_file_name": "PR_DESCRIPTION.md",
    }


# ---------------------------------------------------------------------------
# detect_base_branch
# ---------------------------------------------------------------------------


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess[str](
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_detect_base_branch_uses_origin_head():
    def fake_run(cmd, **kwargs):
        if "symbolic-ref" in cmd:
            return _completed(0, stdout="origin/develop\n")
        raise AssertionError(f"unexpected cmd: {cmd}")

    assert detect_base_branch(run_cmd=fake_run) == "develop"


def test_detect_base_branch_falls_back_to_main():
    def fake_run(cmd, **kwargs):
        if "symbolic-ref" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        if "show-ref" in cmd and "refs/heads/main" in cmd:
            return _completed(0)
        if "show-ref" in cmd and "refs/heads/master" in cmd:
            return _completed(1)
        raise AssertionError(f"unexpected cmd: {cmd}")

    assert detect_base_branch(run_cmd=fake_run) == "main"


def test_detect_base_branch_falls_back_to_master():
    def fake_run(cmd, **kwargs):
        if "symbolic-ref" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        if "show-ref" in cmd and "refs/heads/main" in cmd:
            return _completed(1)
        if "show-ref" in cmd and "refs/heads/master" in cmd:
            return _completed(0)
        raise AssertionError(f"unexpected cmd: {cmd}")

    assert detect_base_branch(run_cmd=fake_run) == "master"


def test_detect_base_branch_raises_when_nothing_found():
    def fake_run(cmd, **kwargs):
        if "symbolic-ref" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        if "show-ref" in cmd:
            return _completed(1)
        raise AssertionError(f"unexpected cmd: {cmd}")

    with pytest.raises(ValueError) as exc:
        detect_base_branch(run_cmd=fake_run)
    assert "Could not determine base branch" in str(exc.value)


# ---------------------------------------------------------------------------
# generate_pr_description / _build_pr_prompt
# ---------------------------------------------------------------------------


def test_build_pr_prompt_falls_back_to_hardcoded(base_config):
    gen = CommitMessageGenerator(
        token="fake", config=base_config, default_model="openai"
    )
    with patch(
        "git_cai_cli.core.llm.load_prompt_file", return_value=HARDCODED_PR_PROMPT
    ):
        prompt = gen._build_pr_prompt()
    assert "## Summary" in prompt
    assert "## Test plan" in prompt


def test_build_pr_prompt_appends_language_style_emoji(base_config):
    """language/style/emoji should be appended to PR prompt the same way
    they are appended to commit, full-files, and squash prompts."""
    base_config["language"] = "de"
    base_config["style"] = "funny"
    base_config["emoji"] = True
    gen = CommitMessageGenerator(
        token="fake", config=base_config, default_model="openai"
    )
    with patch(
        "git_cai_cli.core.llm.load_prompt_file", return_value=HARDCODED_PR_PROMPT
    ):
        prompt = gen._build_pr_prompt()
    assert "German" in prompt
    assert "funny" in prompt
    assert "emoji" in prompt.lower()


def test_build_pr_prompt_excludes_commit_specific_instructions(base_config):
    """conventional + branch_context are commit-message specific and must
    NOT be appended to the PR prompt."""
    base_config["conventional"] = True
    base_config["branch_context"] = True
    base_config["branch_name"] = "feature/x"
    gen = CommitMessageGenerator(
        token="fake", config=base_config, default_model="openai"
    )
    with patch(
        "git_cai_cli.core.llm.load_prompt_file", return_value=HARDCODED_PR_PROMPT
    ):
        prompt = gen._build_pr_prompt()
    assert "Conventional Commits specification" not in prompt
    assert "feature/x" not in prompt


def test_generate_pr_description_includes_log_and_files(base_config):
    gen = CommitMessageGenerator(
        token="fake", config=base_config, default_model="openai"
    )
    with patch.object(gen, "_dispatch_generate", return_value="DRAFT") as disp:
        result = gen.generate_pr_description(
            commit_log="msg1\nmsg2", changed_files="a.py\nb.py"
        )

    assert result == "DRAFT"
    sent_content = disp.call_args.kwargs["content"]
    assert "msg1" in sent_content
    assert "a.py" in sent_content
    assert "Commit log" in sent_content
    assert "Changed files" in sent_content


def test_generate_pr_description_appends_context(base_config):
    gen = CommitMessageGenerator(
        token="fake", config=base_config, default_model="openai"
    )
    with patch.object(gen, "_dispatch_generate", return_value="DRAFT") as disp:
        gen.generate_pr_description(
            commit_log="msg", changed_files="a.py", context="Closes #42"
        )

    sent_content = disp.call_args.kwargs["content"]
    assert "Closes #42" in sent_content


# ---------------------------------------------------------------------------
# run_pr
# ---------------------------------------------------------------------------


def test_run_pr_aborts_outside_git_repo(caplog):
    with patch("git_cai_cli.core.pr.find_git_root", return_value=None):
        with pytest.raises(typer.Exit) as exc:
            run_pr()
    assert exc.value.exit_code == 1
    assert "Not inside a Git repository" in caplog.text


def test_run_pr_writes_to_stdout_by_default(mock_repo_root, base_config, capsys):
    """When pr_to_file is False, the PR description is printed to stdout."""

    def fake_check_output(cmd, text=True, **kwargs):
        if cmd[:2] == ["git", "merge-base"]:
            return "BASE"
        if cmd[:3] == ["git", "--no-pager", "log"]:
            return "feat: add thing\n\nbody\n"
        if cmd[:3] == ["git", "diff", "--name-only"]:
            return "src/foo.py\n"
        raise AssertionError(f"unexpected cmd: {cmd}")

    gen = MagicMock()
    gen.build_pr_request.return_value = ("content", "prompt")
    gen.send.return_value = "## Summary\n- did stuff\n\n## Test plan\n- [ ] check"

    with (
        patch("git_cai_cli.core.pr.find_git_root", return_value=mock_repo_root),
        patch("git_cai_cli.core.pr.load_config", return_value=base_config),
        patch("git_cai_cli.core.pr.load_token", return_value="token"),
        patch("git_cai_cli.core.pr.detect_base_branch", return_value="main"),
        patch("subprocess.check_output", side_effect=fake_check_output),
        patch("git_cai_cli.core.pr.CommitMessageGenerator", return_value=gen),
    ):
        run_pr()

    captured = capsys.readouterr()
    assert "## Summary" in captured.out
    assert "## Test plan" in captured.out
    # No file was written
    assert not (mock_repo_root / "PR_DESCRIPTION.md").exists()


def test_run_pr_writes_to_file_when_configured(mock_repo_root, base_config):
    base_config["pr_to_file"] = True
    base_config["pr_file_name"] = "MY_PR.md"

    def fake_check_output(cmd, text=True, **kwargs):
        if cmd[:2] == ["git", "merge-base"]:
            return "BASE"
        if cmd[:3] == ["git", "--no-pager", "log"]:
            return "feat: add thing"
        if cmd[:3] == ["git", "diff", "--name-only"]:
            return "src/foo.py"
        raise AssertionError(f"unexpected cmd: {cmd}")

    gen = MagicMock()
    gen.build_pr_request.return_value = ("content", "prompt")
    gen.send.return_value = "## Summary\n- ok"

    with (
        patch("git_cai_cli.core.pr.find_git_root", return_value=mock_repo_root),
        patch("git_cai_cli.core.pr.load_config", return_value=base_config),
        patch("git_cai_cli.core.pr.load_token", return_value="token"),
        patch("git_cai_cli.core.pr.detect_base_branch", return_value="main"),
        patch("subprocess.check_output", side_effect=fake_check_output),
        patch("git_cai_cli.core.pr.CommitMessageGenerator", return_value=gen),
    ):
        run_pr()

    written = (mock_repo_root / "MY_PR.md").read_text(encoding="utf-8")
    assert "## Summary" in written


def test_run_pr_uses_explicit_base_override(mock_repo_root, base_config, capsys):
    """When base_override is passed, detect_base_branch must not be called."""
    seen_merge_base_args: list[str] = []

    def fake_check_output(cmd, text=True, **kwargs):
        if cmd[:2] == ["git", "merge-base"]:
            seen_merge_base_args.extend(cmd[2:])
            return "BASE"
        if cmd[:3] == ["git", "--no-pager", "log"]:
            return "msg"
        if cmd[:3] == ["git", "diff", "--name-only"]:
            return "f.py"
        raise AssertionError(f"unexpected cmd: {cmd}")

    gen = MagicMock()
    gen.build_pr_request.return_value = ("content", "prompt")
    gen.send.return_value = "BODY"

    with (
        patch("git_cai_cli.core.pr.find_git_root", return_value=mock_repo_root),
        patch("git_cai_cli.core.pr.load_config", return_value=base_config),
        patch("git_cai_cli.core.pr.load_token", return_value="token"),
        patch(
            "git_cai_cli.core.pr.detect_base_branch",
            side_effect=AssertionError("should not auto-detect"),
        ),
        patch("subprocess.check_output", side_effect=fake_check_output),
        patch("git_cai_cli.core.pr.CommitMessageGenerator", return_value=gen),
    ):
        run_pr(base_override="develop")

    assert "develop" in seen_merge_base_args


def test_run_pr_classifies_auth_error(mock_repo_root, base_config, caplog):
    """A 401 from the provider must surface as a friendly message + clean exit,
    not an uncaught requests.HTTPError traceback."""
    import requests

    def fake_check_output(cmd, text=True, **kwargs):
        if cmd[:2] == ["git", "merge-base"]:
            return "BASE"
        if cmd[:3] == ["git", "--no-pager", "log"]:
            return "feat: add thing"
        if cmd[:3] == ["git", "diff", "--name-only"]:
            return "src/foo.py"
        raise AssertionError(f"unexpected cmd: {cmd}")

    resp = MagicMock()
    resp.status_code = 401
    resp.json.return_value = {"error": {"message": "bad key"}}

    gen = MagicMock()
    gen.build_pr_request.return_value = ("content", "prompt")
    gen.send.side_effect = requests.HTTPError(response=resp)

    with (
        patch("git_cai_cli.core.pr.find_git_root", return_value=mock_repo_root),
        patch("git_cai_cli.core.pr.load_config", return_value=base_config),
        patch("git_cai_cli.core.pr.load_token", return_value="token"),
        patch("git_cai_cli.core.pr.detect_base_branch", return_value="main"),
        patch("subprocess.check_output", side_effect=fake_check_output),
        patch("git_cai_cli.core.pr.CommitMessageGenerator", return_value=gen),
        pytest.raises(SystemExit),
    ):
        run_pr()

    assert "invalid or not authorized" in caplog.text


def test_run_pr_skips_when_no_commits(mock_repo_root, base_config, caplog):
    def fake_check_output(cmd, text=True, **kwargs):
        if cmd[:2] == ["git", "merge-base"]:
            return "BASE"
        if cmd[:3] == ["git", "--no-pager", "log"]:
            return ""  # no commits
        raise AssertionError(f"unexpected cmd: {cmd}")

    with (
        patch("git_cai_cli.core.pr.find_git_root", return_value=mock_repo_root),
        patch("git_cai_cli.core.pr.load_config", return_value=base_config),
        patch("git_cai_cli.core.pr.load_token", return_value="token"),
        patch("git_cai_cli.core.pr.detect_base_branch", return_value="main"),
        patch("subprocess.check_output", side_effect=fake_check_output),
    ):
        with caplog.at_level("INFO"):
            run_pr()

    assert "nothing to describe" in caplog.text
