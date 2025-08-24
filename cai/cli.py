import logging
import subprocess
import sys
from pathlib import Path

from .core.config import load_config, load_token
from .core.gitutils import find_git_root, git_diff_excluding
from .core.openai_utils import get_commit_message

logging.basicConfig(
    level=logging.INFO,  # show INFO and above
    format="%(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


def main() -> None:
    # Ensure invoked as 'git cai'
    invoked_as = Path(sys.argv[0]).name
    if not invoked_as.startswith("git-"):
        print("This command must be run as 'git cai'", file=sys.stderr)
        sys.exit(1)

    # Find the git repo root
    repo_root = find_git_root()
    if not repo_root:
        log.error("Not inside a Git repository.")
        sys.exit(1)

    # Load configuration and token
    config = load_config(log=log)
    token = load_token("openai", log=log)
    if not token:
        log.error("Missing OpenAI token in ~/.config/cai/tokens.yml")
        sys.exit(1)

    # Get git diff
    diff = git_diff_excluding(repo_root, log=log)
    if not diff.strip():
        log.info("No changes to commit. Did you run 'git add'? Files must be staged.")
        sys.exit(0)

    # Generate commit message
    commit_message = get_commit_message(token, config, diff)

    # Open git commit editor with the generated message
    subprocess.run(["git", "commit", "--edit", "-m", commit_message])


if __name__ == "__main__":
    main()
