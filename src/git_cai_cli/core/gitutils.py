"""
Check git repo and run git diff
"""

import hashlib
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


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


def git_diff_excluding(
    repo_root: Path,
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    exit_func: Callable[[int], None] = sys.exit,
) -> str:
    """Run `git diff` excluding files listed in .caiignore."""
    ignore_file = repo_root / ".caiignore"

    exclude_files: list[str] = []
    if ignore_file.exists():
        with open(ignore_file, "r", encoding="utf-8") as f:
            exclude_files = [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
        if not exclude_files:
            log.info("%s is empty. No files excluded.", ignore_file)

    cmd = ["git", "diff", "--cached", "--", "."]
    cmd.extend(f":!{pattern}" for pattern in exclude_files)

    result = run_cmd(cmd, capture_output=True, text=True, check=True)
    if result.returncode != 0:
        log.error("git diff failed: %s", result.stderr.strip())
        exit_func(1)

    return result.stdout


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


def commit_with_edit_template(commit_message: str) -> int:
    """Open git commit editor with a pre-filled commit message template."""
    # create temp file with initial message
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        tf.write(commit_message)
        tf.flush()
        tf_name = Path(tf.name)

    try:
        original_hash = sha256_of_file(tf_name)

        editor = get_git_editor()
        parts = shlex.split(editor)
        if not shutil.which(parts[0]):
            log.error(
                "Editor %r not found in PATH; please set GIT_EDITOR properly.", parts[0]
            )
            return 1
        rc = subprocess.run(parts + [str(tf_name)], check=False).returncode

        if rc != 0:
            log.error("Editor exited with non-zero status -> aborting commit.")
            return rc or 1

        new_hash = sha256_of_file(tf_name)

        # If the file was not changed, treat as "user didn't save" and abort.
        if new_hash == original_hash:
            log.warning("Aborting commit: commit message not saved.")
            return 1

        # file changed (or saved). Run git commit using the file as message.
        try:
            subprocess.run(["git", "commit", "-F", str(tf_name)], check=True)
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
