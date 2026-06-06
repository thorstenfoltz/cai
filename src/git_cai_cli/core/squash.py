"""
Squash all commits in the current branch into a single commit with an LLM-generated message.
"""

import logging
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from git_cai_cli.core.config import (
    TOKENLESS_PROVIDERS,
    apply_provider_overrides,
    load_config,
    load_token,
)
from git_cai_cli.core.gitutils import (
    _has_upstream,
    append_signoff,
    commit_with_edit_template,
    find_git_root,
    get_git_editor,
    git_diff_excluding,
    repo_name_from_root,
    sha256_of_file,
    truncate_diff,
)
from git_cai_cli.core.llm import CommitMessageGenerator
from git_cai_cli.core.spinner import Spinner
from git_cai_cli.core.validate import _validate_llm_call

log = logging.getLogger(__name__)


def _apply_diff_limit(text: str, config: dict) -> str:
    """Truncate ``text`` per the ``max_diff_bytes`` config, logging a warning."""
    max_diff_bytes = int(config.get("max_diff_bytes", 0) or 0)
    text, was_truncated = truncate_diff(text, max_diff_bytes)
    if was_truncated:
        log.warning(
            "Input exceeded max_diff_bytes=%d and was truncated before sending "
            "to the LLM.",
            max_diff_bytes,
        )
    return text


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


def _count_commits_on_branch(merge_base: str) -> int:
    """Count how many commits exist between the merge base and HEAD."""
    output = subprocess.check_output(
        ["git", "rev-list", "--count", f"{merge_base}..HEAD"], text=True
    ).strip()
    return int(output)


def _count_total_commits() -> int:
    """Count the total number of commits in the repository."""
    output = subprocess.check_output(
        ["git", "rev-list", "--count", "HEAD"], text=True
    ).strip()
    return int(output)


def _is_shallow_clone() -> bool:
    """Return True if the current repo is a shallow clone.

    Squash relies on traversing branch history (``HEAD~N``,
    ``merge-base``); a shallow clone may lack the commits required and
    git emits cryptic ``unknown revision`` errors. We pre-flight this
    check so the user gets a clear message.
    """
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--is-shallow-repository"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        return False
    return out == "true"


def _resolve_squash_target(squash_arg: str) -> str:
    """
    Resolve the squash target from a user-provided argument.

    The argument can be:
    - A number: squash the last N commits (returns the parent of the Nth commit)
    - A commit hash: squash up to and including that commit (returns its parent)

    Returns the commit hash to reset to.
    """
    # Try as a number first
    try:
        count = int(squash_arg)
        if count < 1:
            log.error("Commit count must be a positive number.")
            sys.exit(1)

        total_commits = _count_total_commits()
        if count > total_commits:
            log.error(
                "Cannot squash %d commits — the repository only has %d commits in total.",
                count,
                total_commits,
            )
            sys.exit(1)

        merge_base = _get_branch_base()
        branch_commits = _count_commits_on_branch(merge_base)

        if count > branch_commits:
            log.warning(
                "You requested to squash %d commits, but this branch only has %d commits "
                "since it diverged from the base branch.",
                count,
                branch_commits,
            )
            choice = input("Continue anyway? [yes/no]: ").strip().lower()
            if choice not in ("y", "yes"):
                log.info("Squash cancelled.")
                sys.exit(0)

        # HEAD~N is the parent of the Nth-to-last commit
        target = subprocess.check_output(
            ["git", "rev-parse", f"HEAD~{count}"], text=True
        ).strip()
        return target

    except ValueError:
        pass

    # Treat as a commit hash
    try:
        full_hash = subprocess.check_output(
            ["git", "rev-parse", "--verify", squash_arg], text=True
        ).strip()
    except subprocess.CalledProcessError:
        log.error("Invalid commit reference: %s", squash_arg)
        sys.exit(1)

    # Verify the commit is in the current branch history
    rc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", full_hash, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode
    if rc != 0:
        log.error("Commit %s is not in the current branch history.", squash_arg)
        sys.exit(1)

    # Return the commit itself as the reset target (squash up to and including it,
    # so we reset to its parent)
    try:
        parent = subprocess.check_output(
            ["git", "rev-parse", f"{full_hash}~1"], text=True
        ).strip()
        return parent
    except subprocess.CalledProcessError:
        log.error("Commit %s is the root commit — cannot squash past it.", squash_arg)
        sys.exit(1)


def _has_commits() -> bool:
    """
    Check if the current Git repository has any commits.
    """
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def squash_branch(
    provider_override: str | None = None,
    model_override: str | None = None,
    temperature_override: float | None = None,
    time_flag: bool = False,
    squash_arg: str | None = None,
    context: str | None = None,
    sql_override: bool | None = None,
    signoff: bool | None = None,
) -> None:
    """
    Squash commits in the current branch into a single commit with an LLM-generated message.

    Args:
        squash_arg: Optional. A number (squash last N commits) or a commit hash
                    (squash up to and including that commit). If None, squash all
                    commits since the branch diverged.
        context: Optional. Extra context for the LLM (e.g. ticket number, reason for change).
    """
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        return

    if _is_shallow_clone():
        log.error(
            "This repository is a shallow clone. Squash needs full branch "
            "history (HEAD~N and merge-base). Run "
            "`git fetch --unshallow` (or `git fetch --depth=<N>`) to fetch "
            "the missing commits, then retry."
        )
        return

    staged = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"], text=True
    ).strip()
    unstaged = subprocess.check_output(
        ["git", "diff", "--name-only"], text=True
    ).strip()

    config = load_config()

    # Apply provider/model/temperature overrides
    apply_provider_overrides(
        config, provider_override, model_override, temperature_override
    )

    # `--sql true|false` honored in squash mode too: stats writing
    # must behave consistently across `git cai`, `git cai -s`, and
    # `git cai -r`.
    from git_cai_cli.core.config import apply_cli_overrides

    apply_cli_overrides(config, sql_override=sql_override)

    apply_signoff = signoff if signoff is not None else config.get("signoff", False)

    from git_cai_cli.core import stats as stats_module

    stats_module.log_state(config)

    provider = config["default"]
    token = load_token(config=config)

    if provider not in TOKENLESS_PROVIDERS and not token:
        log.error(
            "Missing %s token in %s/.config/cai/tokens.yml",  # nosemgrep
            provider,
            Path.home(),
        )
        sys.exit(1)
    generator = CommitMessageGenerator(token, config, provider)
    generator.repo = repo_name_from_root(repo_root)

    measure = time_flag or config.get("measure_time", False)

    try:
        # 1) Working tree handling
        if staged:
            log.info(
                "Staged changes detected — committing them first before squashing..."
            )
            diff = git_diff_excluding(repo_root)

            if not diff.strip():
                log.error("Staged changes detected, but diff is empty. Aborting.")
                return

            diff = _apply_diff_limit(diff, config)

            start = time.perf_counter() if measure else None

            generator.kind = "commit"
            try:
                with Spinner("Generating commit message for staged changes"):
                    msg = _validate_llm_call(
                        generator.generate,
                        diff,
                        token=token,
                        requires_token=provider not in TOKENLESS_PROVIDERS,
                    )
            except ValueError as e:
                log.error("%s", e)
                sys.exit(1)

            if start is not None:
                elapsed = time.perf_counter() - start
                log.info("Commit message generated in %.2fs", elapsed)
                generator.record_elapsed(int(elapsed * 1000))

            if apply_signoff:
                try:
                    msg = append_signoff(msg)
                except RuntimeError as e:
                    log.error("%s", e)
                    sys.exit(1)

            result = commit_with_edit_template(msg)
            if result != 0:
                log.warning(
                    "Commit aborted — squash cancelled.\n"
                    "Your previously staged changes were already committed before "
                    "the squash step ran. To roll that commit back into the staging "
                    "area without losing any work, run:\n\n"
                    "    git reset HEAD~1 --soft\n"
                )
                return

        else:
            if unstaged:
                log.error(
                    "Unstaged changes present. Please stage or discard them before squashing."
                )
                return
            log.info("Working tree clean — proceeding to squash history.")

        # 2) Determine squash target
        if not _has_commits():
            log.info("Repository has no commits — nothing to squash.")
            return

        if squash_arg:
            merge_base = _resolve_squash_target(squash_arg)
        else:
            merge_base = _get_branch_base()

        # 3) Summarize commit history
        commit_log = subprocess.check_output(
            [
                "git",
                "--no-pager",
                "log",
                f"{merge_base}..HEAD",
                "--pretty=format:%B",
            ],
            text=True,
        ).strip()

        if not commit_log:
            log.info("Nothing to squash — branch contains only one commit.")
            return

        commit_log = _apply_diff_limit(commit_log, config)

        log.info("Summarizing commit history using LLM...")

        start = time.perf_counter() if measure else None

        generator.kind = "squash"
        try:
            with Spinner("Summarizing commit history"):
                summary_message = _validate_llm_call(
                    generator.summarize_commit_history,
                    commit_log,
                    context=context,
                    token=token,
                    requires_token=provider not in TOKENLESS_PROVIDERS,
                )
        except ValueError as e:
            log.error("%s", e)
            sys.exit(1)

        if start is not None:
            elapsed = time.perf_counter() - start
            log.info("Squash summary generated in %.2fs", elapsed)
            generator.record_elapsed(int(elapsed * 1000))

        # 4) Let user edit the summary without making a commit yet
        log.info(
            "Opening editor for final squash commit message. Save = continue, exit w/o save = cancel."
        )

        # write to temp file
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
            tf.write(summary_message)
            tf.flush()
            tf_name = Path(tf.name)

        try:
            original_hash = sha256_of_file(tf_name)

            editor = get_git_editor()
            parts = shlex.split(editor)
            if not parts or not shutil.which(parts[0]):
                log.error(
                    "Editor %r not found in PATH; please set GIT_EDITOR properly.",
                    editor,
                )
                return

            rc = subprocess.run(parts + [str(tf_name)], check=False).returncode

            if rc != 0:
                log.info("Editor exited non-zero — squash cancelled.")
                return

            new_hash = sha256_of_file(tf_name)

            if new_hash == original_hash:
                log.info("Squash cancelled (user did not save message).")
                return

            # User saved → read message into final_message
            final_message = tf_name.read_text(encoding="utf-8").strip()
        finally:
            tf_name.unlink(missing_ok=True)

        if apply_signoff:
            try:
                final_message = append_signoff(final_message)
            except RuntimeError as e:
                log.error("%s", e)
                sys.exit(1)

        # 5) Perform squash
        subprocess.run(["git", "reset", "--soft", merge_base], check=True)
        subprocess.run(["git", "commit", "-m", final_message], check=True)

        log.info("🎉 Branch successfully squashed into one commit. ✅")

        if _has_upstream():
            log.warning(
                "Your branch has a remote upstream.\n"
                "Since squashing rewrites commit history, your next push will require:\n\n"
                "    git push --force-with-lease\n\n"
                "This is a safe force-push that prevents overwriting others' commits.\n\n"
            )
            choice = input("Shall I execute it for you now? [yes/no]: ").strip().lower()
            if choice in ("y", "yes"):
                subprocess.run(["git", "push", "--force-with-lease"], check=True)
                log.info("✅ Successfully pushed the squashed branch to remote.")
        else:
            log.info(
                "No upstream branch detected. Normal `git push` will work as expected."
            )

    finally:
        generator.close()
