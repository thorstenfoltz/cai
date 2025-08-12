#!/usr/bin/env python
# coding: utf-8

# In[31]:


import logging
import os
import stat
import subprocess
import sys
from pathlib import Path

import yaml

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


# In[37]:


def load_config() -> dict:
    """
    Load configuration from the repo root if available and valid, otherwise fallback to ~/.config/cai.
    If neither exists or is valid, create the fallback with default config.
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
    fallback = FALLBACK_CONFIG_FILE
    if not fallback.exists() or fallback.stat().st_size == 0:
        log.warning(f"{fallback} missing or empty. Creating default config.")
        fallback.parent.mkdir(parents=True, exist_ok=True)
        with open(fallback, "w") as f:
            yaml.safe_dump(DEFAULT_CONFIG, f)
        return DEFAULT_CONFIG

    try:
        with open(fallback, "r") as f:
            config = yaml.safe_load(f) or {}
        if not config:
            log.warning(f"{fallback} is empty. Reinitializing with defaults.")
            with open(fallback, "w") as f:
                yaml.safe_dump(DEFAULT_CONFIG, f)
            return DEFAULT_CONFIG
        return config
    except yaml.YAMLError as e:
        log.error(f"Failed to parse config at {fallback}: {e}")
        raise


def load_token(key_name: str) -> str | None:
    """
    Loads a token from ~/.config/cai/tokens.yml.
    Creates the file with a template if it does not exist (with correct permissions).
    Logs errors and returns None if file is empty or the requested key is missing.
    """
    # Ensure directory exists
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Create file with template if it doesn't exist
    if not TOKENS_FILE.exists():
        log.warning(f"{TOKENS_FILE} does not exist. Creating a token template file.")
        with open(TOKENS_FILE, "w") as f:
            yaml.safe_dump(TOKEN_TEMPLATE, f)
        os.chmod(TOKENS_FILE, stat.S_IRUSR | stat.S_IWUSR)  # permissions 600
        log.error(
            f"Token file {TOKENS_FILE} created with template. Please add your token for key '{key_name}'."
        )
        return None

    # Load and validate file
    with open(TOKENS_FILE, "r") as f:
        try:
            tokens = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            log.error(f"Error parsing {TOKENS_FILE}: {e}")
            return None

    if not tokens:
        log.error(
            f"Token file {TOKENS_FILE} is empty. Please add your token for key '{key_name}'."
        )
        return None

    if key_name not in tokens:
        log.error(f"Key '{key_name}' not found in {TOKENS_FILE}.")
        return None

    return tokens[key_name]


# In[38]:


load_config()


# In[24]:


def find_git_root() -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def git_diff_excluding(repo_root: str) -> str:
    """
    Run `git diff` excluding files listed in a .caiignore file located at the repo root.
    """
    ignore_filename = ".caiignore"
    ignore_path = os.path.join(repo_root, ignore_filename)

    if not os.path.isfile(ignore_path):
        log.warning(f"{ignore_filename} not found in {repo_root}, no files excluded.")
        exclude_files = []
    else:
        with open(ignore_path, "r") as f:
            exclude_files = [
                line.strip()
                for line in f.readlines()
                if line.strip() and not line.strip().startswith("#")
            ]

        if not exclude_files:
            log.warning(f"{ignore_filename} is empty. No files will be excluded.")

    cmd = ["git", "diff", "--", "."]
    cmd.extend(f":!{pattern}" for pattern in exclude_files)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"git diff failed: {result.stderr.strip()}")
        sys.exit(1)

    return result.stdout


# In[25]:


find_git_root()


# In[27]:


git_diff_excluding(find_git_root())


# In[ ]:
