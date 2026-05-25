"""
Check git repo and run git diff
"""

import hashlib
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Sequence

from git_cai_cli.core.editors import EDITOR_BLOCK_FLAGS, TERMINAL_EDITORS

log = logging.getLogger(__name__)


def commit_direct(commit_message: str, *, amend: bool = False) -> int:
    """
    Commit directly using -m without opening an editor.
    """
    cmd = ["git", "commit"]
    if amend:
        cmd.append("--amend")
    cmd.extend(["-m", commit_message])
    try:
        subprocess.run(cmd, check=True, text=True)
        return 0
    except subprocess.CalledProcessError as e:
        log.error("git commit failed with exit code %d", e.returncode)
        return e.returncode or 1


def get_last_commit_diff(
    repo_root: Path,
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str:
    """Get the diff of the most recent commit."""
    result = run_cmd(
        ["git", "diff", "HEAD~1..HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        log.error("Failed to get last commit diff: %s", result.stderr.strip())
        return ""
    return result.stdout


def _editor_executable(argv: list[str]) -> str:
    """
    Extract the executable name from an argv list.
    """
    exe = os.path.basename(argv[0])
    return os.path.splitext(exe)[0]


def find_git_root(
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path | None:
    """Returns the root directory of the current Git repository, or None if not in a Git repo."""
    try:
        result = run_cmd(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def get_git_identity(
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[str, str]:
    """Return the configured git ``user.name`` and ``user.email``.

    Raises ``RuntimeError`` if either is missing or empty — the caller
    surfaces a friendly message instead of producing a malformed
    ``Signed-off-by:`` trailer.
    """

    def _query(key: str) -> str:
        try:
            result = run_cmd(
                ["git", "config", "--get", key],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeError("Git is not available on PATH.") from exc
        return (result.stdout or "").strip()

    name = _query("user.name")
    email = _query("user.email")
    if not name or not email:
        raise RuntimeError(
            "--signoff requires git user.name and user.email to be set."
        )
    return name, email


_TRAILER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:\s")


def append_signoff(message: str, identity: tuple[str, str] | None = None) -> str:
    """Append a ``Signed-off-by:`` trailer to ``message``.

    Idempotent: if the exact trailer for the active git identity is
    already present, the message is returned unchanged. When the
    message already ends in a trailer block (any ``Key: value`` line
    such as ``Co-authored-by:`` or another ``Signed-off-by:``), the new
    one is appended directly to that block; otherwise a blank-line
    separator is inserted between body and trailer.

    No trailing newline is appended: the editor flow uses a hash check
    to decide whether the user saved the message, and vim's default of
    adding a final newline on write is what tells us the user accepted.
    Pre-adding ``\\n`` here would defeat that signal.
    """
    name, email = identity if identity is not None else get_git_identity()
    trailer = f"Signed-off-by: {name} <{email}>"

    if trailer in message:
        return message

    stripped = message.rstrip()
    if not stripped:
        return trailer

    last_line = stripped.rsplit("\n", 1)[-1]
    if _TRAILER_LINE_RE.match(last_line):
        return f"{stripped}\n{trailer}"

    return f"{stripped}\n\n{trailer}"


def repo_name_from_root(repo_root: Path | None) -> str | None:
    """Return the basename of a git root path, or None if unset/empty."""
    if repo_root is None:
        return None
    name = repo_root.name
    return name or None


def _load_caiignore_patterns(repo_root: Path) -> list[str]:
    """Read `.caiignore` from the repo root and return its non-empty patterns."""
    ignore_file = repo_root / ".caiignore"
    if not ignore_file.exists():
        return []

    with open(ignore_file, "r", encoding="utf-8") as f:
        patterns = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    if not patterns:
        log.info("%s is empty. No files excluded.", ignore_file)

    return patterns


def git_diff_excluding(
    repo_root: Path,
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    exit_func: Callable[[int], None] = sys.exit,
    files: Sequence[str] | None = None,
) -> str:
    """Run `git diff --cached` honoring `.caiignore` and an optional file whitelist."""
    exclude_files = _load_caiignore_patterns(repo_root)

    cmd = ["git", "diff", "--cached", "--"]
    if files:
        cmd.extend(files)
    else:
        cmd.append(".")
    cmd.extend(f":!{pattern}" for pattern in exclude_files)

    result = run_cmd(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        log.error("git diff failed: %s", result.stderr.strip())
        exit_func(1)

    return result.stdout


def _matches_caiignore(path: str, patterns: Sequence[str]) -> bool:
    """Return True if `path` matches any of the `.caiignore` patterns.

    Uses gitignore semantics via ``pathspec.GitWildMatchPattern`` so
    users get the behavior they expect: ``**`` recursion, ``!negation``
    re-inclusion, and directory-anchored patterns (``/foo`` matches at
    the repo root only; ``foo`` matches anywhere).
    """
    if not patterns:
        return False

    import pathspec

    spec = pathspec.GitIgnoreSpec.from_lines(patterns)
    return spec.match_file(path)


def _is_binary_file(path: Path) -> bool:
    """Heuristic binary-file check: look for a NUL byte in the first 8KB."""
    try:
        with path.open("rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def collect_staged_file_contents(
    repo_root: Path,
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    files: Sequence[str] | None = None,
) -> str:
    """Collect the full working-tree contents of staged files.

    Honors `.caiignore` exclusions and an optional `files` whitelist. Skips
    files that have been deleted from the working tree and binary files.
    Returns an empty string if nothing qualifies.
    """
    exclude_patterns = _load_caiignore_patterns(repo_root)

    cmd = ["git", "diff", "--cached", "--name-only", "--"]
    if files:
        cmd.extend(files)
    else:
        cmd.append(".")

    result = run_cmd(cmd, capture_output=True, text=True, check=False, cwd=repo_root)
    if result.returncode != 0:
        log.error("git diff --name-only failed: %s", result.stderr.strip())
        return ""

    staged_names = [n for n in result.stdout.splitlines() if n.strip()]
    if not staged_names:
        return ""

    chunks: list[str] = []
    included: list[str] = []
    for name in staged_names:
        if exclude_patterns and _matches_caiignore(name, exclude_patterns):
            log.debug("Skipping %s (matches .caiignore)", name)
            continue

        abs_path = repo_root / name
        if not abs_path.is_file():
            log.debug("Skipping %s (not a file in the working tree)", name)
            continue

        if _is_binary_file(abs_path):
            log.debug("Skipping %s (binary)", name)
            continue

        try:
            body = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.debug("Skipping %s (read error: %s)", name, exc)
            continue

        chunks.append(f"--- File: {name} ---\n{body}")
        included.append(name)

    if included:
        log.info(
            "Full file contents attached for %d file(s): %s",
            len(included),
            ", ".join(included),
        )
    else:
        log.info(
            "No staged files qualified for full-file content "
            "(all skipped or excluded)."
        )

    return "\n\n".join(chunks)


def get_current_branch(
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str | None:
    """Return the current Git branch name, or None if detached/not in a repo."""
    try:
        result = run_cmd(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        return branch if branch and branch != "HEAD" else None
    except subprocess.CalledProcessError:
        return None


def detect_base_branch(
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str:
    """Resolve the repository's base branch.

    Order of attempts:
    1. `origin/HEAD` (the remote's default branch).
    2. local `main`.
    3. local `master`.

    Raises ValueError if none of these are present.
    """
    try:
        result = run_cmd(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        ref = result.stdout.strip()
        if ref.startswith("origin/"):
            return ref[len("origin/") :]  # type: ignore[misc]  # mypy E203
        if ref:
            return ref
    except subprocess.CalledProcessError:
        log.debug("origin/HEAD not set; trying local fallbacks.")

    for candidate in ("main", "master"):
        rc = run_cmd(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"],
            capture_output=True,
            text=True,
            check=False,
        ).returncode
        if rc == 0:
            log.debug("Using local '%s' as base branch.", candidate)
            return candidate

    raise ValueError(
        "Could not determine base branch. Set origin/HEAD or pass --base <branch>."
    )


def _has_upstream() -> bool:
    try:
        subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_git_editor() -> str:
    """Return the editor git would use (GIT_EDITOR, core.editor, VISUAL, EDITOR, fallback)."""
    # Ask git for its editor; falls back if git returns nothing or error
    try:
        p = subprocess.run(
            ["git", "var", "GIT_EDITOR"], capture_output=True, text=True, check=True
        )
        editor = p.stdout.strip()
        if editor:
            return editor
    except subprocess.CalledProcessError:
        pass

    # fallback lookup similar to git's precedence
    for env in ("GIT_EDITOR", "VISUAL", "EDITOR"):
        val = os.environ.get(env)
        if val:
            return val

    return shutil.which("vi") or shutil.which("nano") or "vi"


def _normalize_editor(editor: str) -> list[str]:
    parts = shlex.split(editor)
    exe = os.path.basename(parts[0])

    block_flag = EDITOR_BLOCK_FLAGS.get(exe)
    if block_flag and block_flag not in parts:
        parts.insert(1, block_flag)

    return parts


def sha256_of_file(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def commit_with_edit_template(commit_message: str, *, amend: bool = False) -> int:
    """Open git commit editor with a pre-filled commit message template."""

    # 1. Resolve editor
    editor = get_git_editor()
    argv = _normalize_editor(editor)

    if not shutil.which(argv[0]):
        log.error(
            "Editor %r not found in PATH; please set GIT_EDITOR properly.", argv[0]
        )
        return 1

    editor_exe = _editor_executable(argv)

    # 2. Create temp file with correct semantics
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        if editor_exe not in TERMINAL_EDITORS:
            tf.write("# DELETE THIS LINE TO ACCEPT THE COMMIT\n\n")
        tf.write(commit_message)
        tf.flush()
        tf_name = Path(tf.name)

    try:
        original_hash = sha256_of_file(tf_name)

        # 3. Launch editor
        rc = subprocess.run(argv + [str(tf_name)], check=False).returncode
        if rc != 0:
            log.error("Editor exited with non-zero status -> aborting commit.")
            return rc or 1

        # 4. Evaluate result
        new_hash = sha256_of_file(tf_name)
        content = tf_name.read_text(encoding="utf-8")

        if editor_exe in TERMINAL_EDITORS:
            # vim / nano behavior
            if new_hash == original_hash:
                log.warning("Aborting commit: message not saved.")
                return 1
        else:
            # GUI editor behavior
            if content.lstrip().startswith("# DELETE THIS LINE"):
                log.warning("Aborting commit: commit not explicitly accepted.")
                return 1

        # 5. Commit
        cmd = ["git", "commit"]
        if amend:
            cmd.append("--amend")
        cmd.extend(["-F", str(tf_name)])
        subprocess.run(cmd, check=True)
        return 0

    except subprocess.CalledProcessError as e:
        log.error("git commit failed with exit code %d", e.returncode)
        return e.returncode or 1

    finally:
        try:
            os.remove(tf_name)
        except OSError as e:
            log.warning(
                "Failed to remove temporary commit message file %s: %r", tf_name, e
            )
