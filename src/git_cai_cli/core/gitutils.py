"""
Check git repo and run git diff
"""

import logging
import subprocess
import sys
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
