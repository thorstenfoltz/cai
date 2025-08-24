import subprocess
import sys
import logging

from .core.config import load_config, load_token
from .core.gitutils import find_git_root, git_diff_excluding
from .core.openai_utils import get_commit_message

log = logging.getLogger(__name__)


def main() -> None:
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        sys.exit(1)

    config = load_config(log=log)
    token = load_token("openai", log=log)
    if not token:
        log.error("Missing OpenAI token in ~/.config/cai/tokens.yml")
        sys.exit(1)

    diff = git_diff_excluding(repo_root, log=log)
    if not diff.strip():
        log.info("No changes to commit.")
        sys.exit(0)

    commit_message = get_commit_message(token, config, diff)

    # Open git commit editor with the generated message
    subprocess.run(["git", "commit", "--edit", "-m", commit_message])

if __name__ == "__main__":
    main()
