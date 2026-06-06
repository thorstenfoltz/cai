"""
Unit and integration tests for git_cai_cli.core.gitutils.

These tests verify:
- Git root detection
- git diff exclusion logic
- editor resolution
- hash computation
- commit template workflow

All subprocess and filesystem interactions are mocked so no real Git repo
or external tools are required.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from git_cai_cli.core.gitutils import (
    collect_staged_file_contents,
    commit_with_edit_template,
    find_git_root,
    get_current_branch,
    get_git_editor,
    git_diff_excluding,
    sha256_of_file,
    truncate_diff,
)

# ------------------------------------------------------------------------------
# truncate_diff
# ------------------------------------------------------------------------------


def test_truncate_diff_no_limit_returns_unchanged():
    """max_bytes <= 0 means no limit."""
    text = "a" * 1000
    out, truncated = truncate_diff(text, 0)
    assert out == text
    assert truncated is False


def test_truncate_diff_under_limit_returns_unchanged():
    text = "hello"
    out, truncated = truncate_diff(text, 100)
    assert out == text
    assert truncated is False


def test_truncate_diff_equal_to_limit_returns_unchanged():
    text = "abcde"  # 5 bytes
    out, truncated = truncate_diff(text, 5)
    assert out == text
    assert truncated is False


def test_truncate_diff_over_limit_truncates_with_marker():
    text = "a" * 100
    out, truncated = truncate_diff(text, 10)
    assert truncated is True
    assert out.startswith("a" * 10)
    assert "diff truncated" in out
    assert "max_diff_bytes=10" in out


def test_truncate_diff_handles_multibyte_boundary():
    """Cutting mid-multibyte-char must not raise and must drop the partial."""
    # '€' is 3 bytes in UTF-8; 4 of them = 12 bytes. Limit at 10 lands mid-char.
    text = "€" * 4
    out, truncated = truncate_diff(text, 10)
    assert truncated is True
    # 10 bytes -> 3 full euro signs (9 bytes), partial 4th dropped.
    assert out.startswith("€€€")
    assert "diff truncated" in out


# ------------------------------------------------------------------------------
# find_git_root
# ------------------------------------------------------------------------------


def test_find_git_root_success():
    """
    Find_git_root() should return the path returned by git.
    """
    mock_proc = MagicMock()
    mock_proc.stdout = "/fake/repo\n"

    def fake_run(*args, **kwargs):
        return mock_proc

    path = find_git_root(run_cmd=fake_run)
    assert path == Path("/fake/repo")


def test_find_git_root_failure_returns_none():
    """
    Find_git_root() should return None when git rev-parse fails.
    """

    def fake_run(*_, **__):
        raise subprocess.CalledProcessError(1, "cmd")

    assert find_git_root(run_cmd=fake_run) is None


# ------------------------------------------------------------------------------
# get_current_branch
# ------------------------------------------------------------------------------


def test_get_current_branch_returns_name():
    """get_current_branch() should return the branch name."""
    mock_proc = MagicMock()
    mock_proc.stdout = "feature/auth\n"

    def fake_run(*args, **kwargs):
        return mock_proc

    assert get_current_branch(run_cmd=fake_run) == "feature/auth"


def test_get_current_branch_detached_head():
    """get_current_branch() should return None when HEAD is detached."""
    mock_proc = MagicMock()
    mock_proc.stdout = "HEAD\n"

    def fake_run(*args, **kwargs):
        return mock_proc

    assert get_current_branch(run_cmd=fake_run) is None


def test_get_current_branch_not_in_repo():
    """get_current_branch() should return None on CalledProcessError."""

    def fake_run(*_, **__):
        raise subprocess.CalledProcessError(1, "cmd")

    assert get_current_branch(run_cmd=fake_run) is None


# ------------------------------------------------------------------------------
# git_diff_excluding
# ------------------------------------------------------------------------------


def test_git_diff_excluding_reads_ignore_file_and_excludes_patterns(tmp_path):
    """
    git_diff_excluding() should append :!pattern for each line in .caiignore.
    """
    repo_root = tmp_path
    ignore_file = repo_root / ".caiignore"
    ignore_file.write_text("*.pyc\n# comment\nbuild/\n")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "diff output"

    def fake_run(cmd, capture_output, text, check):
        # Ensure ignore patterns were added
        assert ":!*.pyc" in cmd
        assert ":!build/" in cmd
        return mock_proc

    output = git_diff_excluding(repo_root, run_cmd=fake_run)
    assert output == "diff output"


def test_git_diff_excluding_exits_on_failure(tmp_path):
    """
    git_diff_excluding() should call exit_func(1) when diff returns error.
    """
    repo_root = tmp_path
    (repo_root / ".caiignore").write_text("node_modules/\n")

    mock_proc = MagicMock()
    mock_proc.returncode = 123  # triggers exit

    def fake_run(*args, **kwargs):
        return mock_proc

    exit_called = False

    def fake_exit(code):
        nonlocal exit_called
        exit_called = True
        assert code == 1

    git_diff_excluding(repo_root, run_cmd=fake_run, exit_func=fake_exit)
    assert exit_called is True


def test_git_diff_excluding_uses_check_false(tmp_path):
    """
    git_diff_excluding() should pass check=False so manual error handling works.
    """
    repo_root = tmp_path

    captured_kwargs = {}

    def fake_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "diff"
        return mock_proc

    git_diff_excluding(repo_root, run_cmd=fake_run)
    assert captured_kwargs.get("check") is False


def test_git_diff_excluding_no_caiignore(tmp_path):
    """
    git_diff_excluding() should work without a .caiignore file.
    """
    repo_root = tmp_path

    def fake_run(cmd, **kwargs):
        # No :! patterns should be in the command
        assert not any(arg.startswith(":!") for arg in cmd)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "diff output"
        return mock_proc

    result = git_diff_excluding(repo_root, run_cmd=fake_run)
    assert result == "diff output"


def test_git_diff_excluding_empty_caiignore(tmp_path):
    """
    git_diff_excluding() should handle an empty .caiignore file.
    """
    repo_root = tmp_path
    (repo_root / ".caiignore").write_text("# only comments\n\n")

    def fake_run(cmd, **kwargs):
        assert not any(arg.startswith(":!") for arg in cmd)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "diff output"
        return mock_proc

    result = git_diff_excluding(repo_root, run_cmd=fake_run)
    assert result == "diff output"


# ------------------------------------------------------------------------------
# git_diff_excluding — files filter
# ------------------------------------------------------------------------------


def test_git_diff_excluding_with_files_filter(tmp_path):
    """When `files` is provided, the diff command targets those paths."""
    repo_root = tmp_path
    (repo_root / ".caiignore").write_text("*.pyc\n")

    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "diff output"
        return mock_proc

    git_diff_excluding(repo_root, run_cmd=fake_run, files=["a.py", "b.py"])

    # Command should contain the selected files after `--`
    assert "a.py" in captured_cmd
    assert "b.py" in captured_cmd
    # Excludes still apply
    assert ":!*.pyc" in captured_cmd
    # The generic `.` pathspec must NOT be present when files are passed
    assert "." not in captured_cmd


def test_git_diff_excluding_without_files_uses_dot(tmp_path):
    """When `files` is None, `.` is used as pathspec."""
    repo_root = tmp_path

    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "diff output"
        return mock_proc

    git_diff_excluding(repo_root, run_cmd=fake_run)

    # Make sure it contains `.` as the generic pathspec
    assert "." in captured_cmd


# ------------------------------------------------------------------------------
# collect_staged_file_contents
# ------------------------------------------------------------------------------


def test_collect_staged_file_contents_happy_path(tmp_path):
    """Returns each file's working-tree contents under a `--- File: ---` header."""
    repo_root = tmp_path
    (repo_root / "a.py").write_text("print('a')\n", encoding="utf-8")
    (repo_root / "b.py").write_text("print('b')\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "a.py\nb.py\n"
        return mock_proc

    out = collect_staged_file_contents(repo_root, run_cmd=fake_run)

    assert "--- File: a.py ---" in out
    assert "--- File: b.py ---" in out
    assert "print('a')" in out
    assert "print('b')" in out


def test_collect_staged_file_contents_skips_binary(tmp_path, caplog):
    """Binary files (NUL byte) must be excluded and logged."""
    caplog.set_level("DEBUG")
    repo_root = tmp_path
    (repo_root / "text.py").write_text("hello\n", encoding="utf-8")
    (repo_root / "binary.bin").write_bytes(b"abc\x00def")

    def fake_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "text.py\nbinary.bin\n"
        return mock_proc

    out = collect_staged_file_contents(repo_root, run_cmd=fake_run)

    assert "--- File: text.py ---" in out
    assert "--- File: binary.bin ---" not in out
    assert "binary.bin" in caplog.text


def test_collect_staged_file_contents_respects_caiignore(tmp_path):
    """Files matching `.caiignore` patterns are skipped."""
    repo_root = tmp_path
    (repo_root / ".caiignore").write_text("*.log\n")
    (repo_root / "keep.py").write_text("keep\n", encoding="utf-8")
    (repo_root / "drop.log").write_text("drop\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "keep.py\ndrop.log\n"
        return mock_proc

    out = collect_staged_file_contents(repo_root, run_cmd=fake_run)

    assert "--- File: keep.py ---" in out
    assert "--- File: drop.log ---" not in out


def test_collect_staged_file_contents_empty_when_no_staged_files(tmp_path):
    """Returns empty string when no staged files."""
    repo_root = tmp_path

    def fake_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        return mock_proc

    assert collect_staged_file_contents(repo_root, run_cmd=fake_run) == ""


def test_collect_staged_file_contents_handles_deleted_file(tmp_path):
    """A staged file that no longer exists in the working tree is skipped."""
    repo_root = tmp_path
    (repo_root / "still_here.py").write_text("x\n", encoding="utf-8")
    # `gone.py` is in the staged list but not present on disk

    def fake_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "still_here.py\ngone.py\n"
        return mock_proc

    out = collect_staged_file_contents(repo_root, run_cmd=fake_run)

    assert "--- File: still_here.py ---" in out
    assert "--- File: gone.py ---" not in out


def test_collect_staged_file_contents_logs_included_files(tmp_path, caplog):
    """Emits an INFO log listing the files whose full contents were attached."""
    caplog.set_level("INFO")
    repo_root = tmp_path
    (repo_root / "a.py").write_text("print('a')\n", encoding="utf-8")
    (repo_root / "b.py").write_text("print('b')\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "a.py\nb.py\n"
        return mock_proc

    collect_staged_file_contents(repo_root, run_cmd=fake_run)

    log_text = caplog.text.lower()
    assert "full file contents attached" in log_text
    assert "a.py" in caplog.text
    assert "b.py" in caplog.text


def test_collect_staged_file_contents_logs_when_nothing_qualifies(tmp_path, caplog):
    """Logs an INFO message when all staged files are filtered out."""
    caplog.set_level("INFO")
    repo_root = tmp_path
    (repo_root / ".caiignore").write_text("*.log\n")
    (repo_root / "drop.log").write_text("drop\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "drop.log\n"
        return mock_proc

    collect_staged_file_contents(repo_root, run_cmd=fake_run)

    assert "no staged files qualified" in caplog.text.lower()


def test_collect_staged_file_contents_files_arg_passed_to_command(tmp_path):
    """When `files` is provided, those paths go into the name-only command."""
    repo_root = tmp_path
    (repo_root / "x.py").write_text("x\n", encoding="utf-8")

    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "x.py\n"
        return mock_proc

    collect_staged_file_contents(repo_root, run_cmd=fake_run, files=["x.py"])

    assert "x.py" in captured_cmd
    # When files is given, dot should not be appended
    assert captured_cmd.count(".") == 0


# ------------------------------------------------------------------------------
# get_git_editor
# ------------------------------------------------------------------------------


def test_get_git_editor_prefers_git_var():
    """
    get_git_editor() should return output of git var GIT_EDITOR when available.
    """
    mock_proc = MagicMock()
    mock_proc.stdout = "vim\n"

    with patch("subprocess.run", return_value=mock_proc):
        assert get_git_editor() == "vim"


def test_get_git_editor_falls_back_to_env():
    """
    get_git_editor() should fall back to environment variables if git var fails.
    """
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")):
        with patch.dict(os.environ, {"EDITOR": "nano"}, clear=True):
            assert get_git_editor() == "nano"


def test_get_git_editor_fallback_system_editor():
    """
    get_git_editor() should fall back to vi/nano when no env vars are set.
    """
    with (
        patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")),
        patch.dict(os.environ, {}, clear=True),
        patch("shutil.which", return_value="vi"),
    ):
        assert get_git_editor() == "vi"


# ------------------------------------------------------------------------------
# sha256_of_file
# ------------------------------------------------------------------------------


def test_sha256_of_file(tmp_path):
    """
    sha256_of_file() should compute correct SHA256.
    """
    file = tmp_path / "data.txt"
    file.write_text("hash test")

    h = sha256_of_file(file)
    import hashlib

    assert h == hashlib.sha256(b"hash test").hexdigest()


# ------------------------------------------------------------------------------
# commit_with_edit_template
# ------------------------------------------------------------------------------


def test_commit_with_edit_template_abort_on_unchanged(tmp_path):
    """
    commit_with_edit_template() should abort if editor does not modify the file.
    """

    # Editor does nothing but return success
    def fake_editor_run(cmd, check):
        return MagicMock(returncode=0)

    # Git commit should not be called because file unchanged
    with (
        patch("git_cai_cli.core.gitutils.get_git_editor", return_value="true"),
        patch("subprocess.run", side_effect=fake_editor_run),
    ):
        rc = commit_with_edit_template("initial\n")
        assert rc == 1


def test_commit_with_edit_template_runs_git_commit(tmp_path):
    """
    commit_with_edit_template() should perform git commit when file is modified.
    """

    # Fake editor modifies file by rewriting its content
    def fake_editor_run(cmd, check):
        path = cmd[-1]
        Path(path).write_text("edited message")
        return MagicMock(returncode=0)

    # Fake git commit success
    def fake_git_commit(cmd, check):
        return MagicMock()

    with (
        patch("git_cai_cli.core.gitutils.get_git_editor", return_value="true"),
        patch(
            "subprocess.run",
            side_effect=lambda cmd, **kw: (
                fake_editor_run(cmd, kw) if "true" in cmd else fake_git_commit(cmd, kw)
            ),
        ),
    ):

        rc = commit_with_edit_template("initial\n")
        assert rc == 0


# ---------------------------------------------------------------------------
# F1.4 — .caiignore must use gitignore semantics, not bare fnmatch
# ---------------------------------------------------------------------------


from git_cai_cli.core.gitutils import _matches_caiignore as _ci_matches  # noqa: E402


def test_caiignore_double_star_recurses():
    """`**/foo` must match `foo`, `a/foo`, and `a/b/foo` — fnmatch did not."""
    patterns = ["**/foo.txt"]
    assert _ci_matches("foo.txt", patterns)
    assert _ci_matches("a/foo.txt", patterns)
    assert _ci_matches("a/b/c/foo.txt", patterns)


def test_caiignore_negation_re_includes():
    """`!pattern` re-includes a previously-excluded path."""
    patterns = ["*.log", "!keep.log"]
    assert _ci_matches("a.log", patterns)
    assert not _ci_matches("keep.log", patterns)


def test_caiignore_directory_anchored_pattern_only_matches_root():
    """`/foo` matches at the repo root only — not in subdirectories."""
    patterns = ["/foo.txt"]
    assert _ci_matches("foo.txt", patterns)
    assert not _ci_matches("sub/foo.txt", patterns)


def test_caiignore_unanchored_pattern_matches_anywhere():
    """`foo` (no leading slash) matches at any depth."""
    patterns = ["foo.txt"]
    assert _ci_matches("foo.txt", patterns)
    assert _ci_matches("a/foo.txt", patterns)


def test_caiignore_empty_patterns_no_match():
    """Empty pattern list never matches."""
    assert not _ci_matches("anything.txt", [])
