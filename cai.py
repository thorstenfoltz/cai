import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Type

import yaml
from openai import OpenAI

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

CONFIG_DIR = Path.home() / ".config" / "cai"
FALLBACK_CONFIG_FILE = CONFIG_DIR / "cai_config.yml"
KEYS_FILE = CONFIG_DIR / "keys.yml"
TOKENS_FILE = Path.home() / ".config" / "cai" / "tokens.yml"

DEFAULT_CONFIG = {"openai": {"model": "gpt-4.1", "temperature": 0}}

TOKEN_TEMPLATE = {
    "openai": "PUT-YOUR-OPENAI-TOKEN-HERE",
    "huggingface": "PUT-YOUR-HUGGINGFACE-TOKEN-HERE",
}


def load_config(
    fallback_config_file: Path = FALLBACK_CONFIG_FILE,
    default_config: dict[str, Any] = DEFAULT_CONFIG,
    log: logging.Logger = log,
) -> dict[str, Any]:
    """
    Load configuration from the repo root if available and valid, otherwise fallback to fallback_config_file.
    If neither exists or is valid, create the fallback with default_config.
    """
    repo_root = find_git_root()
    repo_config_file = Path(repo_root) / "cai_config.yml" if repo_root else None

    # 1. Try repo config
    if repo_config_file and repo_config_file.exists():
        if repo_config_file.stat().st_size == 0:
            log.info(f"{repo_config_file} is empty. Falling back to home config.")
        else:
            try:
                with open(repo_config_file, "r") as f:
                    config = yaml.safe_load(f) or {}
                if config:
                    return config
                else:
                    log.info(
                        f"{repo_config_file} contains no valid data. Falling back to home config."
                    )
            except yaml.YAMLError as e:
                log.error(
                    f"Failed to parse repo config: {e}. Falling back to home config."
                )

    # 2. Fallback to home config
    if not fallback_config_file.exists() or fallback_config_file.stat().st_size == 0:
        log.warning(
            f"{fallback_config_file} missing or empty. Creating default config."
        )
        fallback_config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(fallback_config_file, "w") as f:
            yaml.safe_dump(default_config, f)
        return default_config

    try:
        with open(fallback_config_file, "r") as f:
            config = yaml.safe_load(f) or {}
        if not config:
            log.warning(
                f"{fallback_config_file} is empty. Reinitializing with defaults."
            )
            with open(fallback_config_file, "w") as f:
                yaml.safe_dump(default_config, f)
            return default_config
        return config
    except yaml.YAMLError as e:
        log.error(f"Failed to parse config at {fallback_config_file}: {e}")
        raise


def load_token(
    key_name: str,
    tokens_file: Path = TOKENS_FILE,
    token_template: dict[str, Any] = TOKEN_TEMPLATE,
    log: logging.Logger = log,
) -> str | None:
    """
    Loads a token from the given tokens_file.
    Creates the file with a template if it does not exist (with correct permissions).
    Logs errors and returns None if file is empty or the requested key is missing.
    """
    # Ensure directory exists
    tokens_file.parent.mkdir(parents=True, exist_ok=True)

    # Create file with template if it doesn't exist
    if not tokens_file.exists():
        log.warning(f"{tokens_file} does not exist. Creating a token template file.")
        with open(tokens_file, "w") as f:
            yaml.safe_dump(token_template, f)
        os.chmod(tokens_file, stat.S_IRUSR | stat.S_IWUSR)  # permissions 600
        log.info(
            f"Token file {tokens_file} created with template. Please add your token for key '{key_name}'."
        )
        return None

    # Load and validate file
    with open(tokens_file, "r") as f:
        try:
            tokens = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            log.error(f"Error parsing {tokens_file}: {e}")
            return None

    if not tokens:
        log.error(
            f"Token file {tokens_file} is empty. Please add your token for key '{key_name}'."
        )
        return None

    if key_name not in tokens:
        log.error(f"Key '{key_name}' not found in {tokens_file}.")
        return None

    return tokens[key_name]


def find_git_root(
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path | None:
    """
    Returns the root directory of the current Git repository, or None if not in a Git repo.
    """
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
    repo_root: str,
    log: logging.Logger = log,
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    exit_func: Callable[[int], None] = sys.exit,
) -> str:
    """
    Run `git diff` excluding files listed in a .caiignore file located at the repo root.
    """
    ignore_filename = ".caiignore"
    ignore_path = os.path.join(repo_root, ignore_filename)

    if not os.path.isfile(ignore_path):
        log.info(f"{ignore_filename} not found in {repo_root}, no files excluded.")
        exclude_files: list[str] = []
    else:
        with open(ignore_path, "r") as f:
            exclude_files = [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
        if not exclude_files:
            log.info(f"{ignore_filename} is empty. No files will be excluded.")

    cmd = ["git", "diff", "HEAD", "--", "."]
    cmd.extend(f":!{pattern}" for pattern in exclude_files)

    result = run_cmd(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"git diff failed: {result.stderr.strip()}")
        exit_func(1)

    return result.stdout


def get_commit_message(
    token: str, config: Dict[str, Any], git_diff: str, openai_cls: Type[Any] = OpenAI
) -> str:
    """
    Generate a professional git commit message based on the given git_diff,
    using model settings from the config.

    Parameters:
    - token: API key for OpenAI
    - config: configuration dictionary containing model settings
    - git_diff: the git diff string to summarize
    - openai_cls: OpenAI client class/factory to instantiate (default: OpenAI)

    Returns:
    - Generated commit message string
    """
    client = openai_cls(api_key=token)

    model = config["openai"]["model"]
    temperature = config["openai"]["temperature"]

    system_prompt = (
        "You are an expert software engineer assistant. "
        "Your task is to generate a concise, professional git commit message "
        "summarizing the provided git diff changes. "
        "Keep the message clear and focused on what was changed and why."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Generate a git commit message for the following diff:\n\n{git_diff}",
        },
    ]

    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )

    commit_message = completion.choices[0].message.content.strip()
    return commit_message


# print(git_diff_excluding(find_git_root()))

print(
    get_commit_message(
        load_token("openai"), load_config(), git_diff_excluding(find_git_root())
    )
)
