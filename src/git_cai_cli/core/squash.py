"""
Squash all commits in the current branch into a single commit with an LLM-generated message.
"""

import logging
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from git_cai_cli.core.config import get_default_config, load_config, load_token
from git_cai_cli.core.gitutils import (
    _has_upstream,
    commit_with_edit_template,
    find_git_root,
    get_git_editor,
    git_diff_excluding,
    sha256_of_file,
)
from git_cai_cli.core.llm import CommitMessageGenerator

log = logging.getLogger(__name__)


def _get_branch_base() -> str:
    """
    Determine commit where the branch diverged
    """
    # Try remote default branch (origin/main, origin/master, etc.)
    try:
        ref = subprocess.check_output(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"], text=True
        ).strip()
        default_branch = ref.replace("refs/remotes/", "")
        log.info("Using default branch for base detection: %s", default_branch)
        base = subprocess.check_output(
            ["git", "merge-base", "--fork-point", default_branch, "HEAD"], text=True
        ).strip()
        return base
    except subprocess.CalledProcessError as e:
        log.info(
            "Unable to determine default branch. Falling back to initial commit..."
        )
        log.debug("Default branch detection failed: %r", e)

    # Fallback to repo root commit
    try:
        base = subprocess.check_output(
            ["git", "rev-list", "--max-parents=0", "HEAD"], text=True
        ).strip()
        log.info("Using repository root commit as base: %s", base)
        return base

    except subprocess.CalledProcessError as e:
        # This case is extremely rare and would be truly unexpected.
        log.debug("Failed to determine repository root commit: %r", e)
        raise


def squash_branch() -> None:
    """
    Squash all commits in the current branch into a single commit with an LLM-generated message.
    """
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        return

    staged = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"], text=True
    ).strip()
    unstaged = subprocess.check_output(
        ["git", "diff", "--name-only"], text=True
    ).strip()

    config = load_config()
    default_model = get_default_config()
    token = load_token(default_model)
    if not token:
        log.error("Missing %s token in ~/.config/cai/tokens.yml", default_model)
        sys.exit(1)
    generator = CommitMessageGenerator(token, config, default_model)

    # 1) Working tree handling
    if staged:
        log.info("Staged changes detected — committing them first before squashing...")
        diff = git_diff_excluding(repo_root)

        if not diff.strip():
            log.error("Staged changes detected, but diff is empty. Aborting.")
            return

        msg = generator.generate(diff)

        result = commit_with_edit_template(msg)
        if result != 0:
            log.info("Commit aborted — squash cancelled.")
            return

    else:
        if unstaged:
            log.error(
                "Unstaged changes present. Please stage or discard them before squashing."
            )
            return
        log.info("Working tree clean — proceeding to squash history.")

    # 2) Determine branch base
    merge_base = _get_branch_base()

    # 3) Summarize commit history
    commit_log = subprocess.check_output(
        ["git", "--no-pager", "log", f"{merge_base}..HEAD", "--pretty=format:%B"],
        text=True,
    ).strip()

    if not commit_log:
        log.info("Nothing to squash — branch contains only one commit.")
        return

    log.info("Summarizing commit history using LLM...")
    summary_message = generator.summarize_commit_history(commit_log)

    # 4) Let user edit the summary without making a commit yet
    log.info(
        "Opening editor for final squash commit message. Save = continue, exit w/o save = cancel..."
    )

    # write to temp file
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        tf.write(summary_message)
        tf.flush()
        tf_name = Path(tf.name)

    original_hash = sha256_of_file(tf_name)

    editor = get_git_editor()
    parts = shlex.split(editor)
    if not shutil.which(parts[0]):
        # This editor command requires shell interpretation
        rc = subprocess.run(
            f'{editor} "{tf_name}"', shell=True, check=False  # nosemgrep
        ).returncode  # nosec # nosemgrep
    else:
        rc = subprocess.run(parts + [str(tf_name)], check=False).returncode

    if rc != 0:
        log.info("Editor exited non-zero — squash cancelled.")
        tf_name.unlink(missing_ok=True)
        return

    new_hash = sha256_of_file(tf_name)

    if new_hash == original_hash:
        log.info("Squash cancelled (user did not save message).")
        tf_name.unlink(missing_ok=True)
        return

    # User saved → read message into final_message
    final_message = tf_name.read_text(encoding="utf-8").strip()
    tf_name.unlink(missing_ok=True)

    # 5) Perform squash
    subprocess.run(["git", "reset", "--soft", merge_base], check=True)
    subprocess.run(["git", "commit", "-m", final_message], check=True)

    log.info("🎉 Branch successfully squashed into one commit. ✅")

    if _has_upstream():
        log.warning(
            "Your branch has a remote upstream.\n"
            "Since squashing rewrites commit history, your next push will require:\n\n"
            "    git push --force-with-lease\n\n"
            "This is a safe force-push that prevents overwriting others' commits."
        )
    else:
        log.info(
            "No upstream branch detected. Normal `git push` will work as expected."
        )
