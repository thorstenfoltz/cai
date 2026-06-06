"""
Core manager for CLI utilities.
"""

import logging
import re
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import requests
import typer
import yaml
from git_cai_cli.core.config import (
    CONFIG_DIR,
    DEFAULT_CONFIG,
    FALLBACK_CONFIG_FILE,
    KNOWN_PROVIDERS,
    TOKENLESS_PROVIDERS,
    TOKENS_FILE,
    _find_repo_config,
    _serialize_config,
    load_config,
    ordered_default_config,
)
from git_cai_cli.core.languages import LANGUAGE_MAP
from git_cai_cli.core.squash import squash_branch

log = logging.getLogger(__name__)


class CliManager:
    """
    Central manager class for CLI-level operations.
    """

    def __init__(
        self,
        package_name: str = "git-cai-cli",
        allowed_languages: dict[str, str] | None = None,
    ):
        self.package_name = package_name
        self.allowed_languages = allowed_languages or LANGUAGE_MAP

    def _extract_numeric_version(self, v: str):
        """
        Extract major.minor.patch and return as tuple of integers.
        Falls back safely if parts are missing.
        Examples:
            "0.1.2.dev8" -> (0, 1, 2)
            "1.4" -> (1, 4, 0)
        """
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
        if match:
            return tuple(int(x) for x in match.groups())
        match = re.match(r"^(\d+)\.(\d+)", v)
        if match:
            major, minor = match.groups()
            return (int(major), int(minor), 0)
        return (0, 0, 0)

    def check_and_update(self, auto_confirm: bool = False) -> None:
        """
        Check for updates on PyPI and optionally apply the update via pipx.

        Args:
            auto_confirm (bool): If True, skip confirmation prompt and update immediately.
        """
        try:
            current_version = version(self.package_name)
        except PackageNotFoundError:
            log.error(
                "Package '%s' not found – unable to determine version.",
                self.package_name,
            )
            return

        # Fetch latest version from PyPI
        try:
            response = requests.get(
                f"https://pypi.org/pypi/{self.package_name}/json", timeout=10
            )
            latest_version = response.json()["info"]["version"]
        except requests.RequestException as e:
            log.error("Could not fetch version info from PyPI: %s", e)
            print("⚠️ Could not check for updates. Please try again later.")
            return

        # Compare only numeric parts
        installed_base = self._extract_numeric_version(current_version)
        latest_base = self._extract_numeric_version(latest_version)

        if installed_base >= latest_base:
            print(
                f"✅ Already up to date (installed {current_version}, PyPI {latest_version})"
            )
            return

        print(f"⬆️  Update available: {current_version} → {latest_version}")

        if not auto_confirm:
            choice = (
                input(
                    "Do you want to update now using 'pipx upgrade git-cai-cli'? [yes/no]: "
                )
                .strip()
                .lower()
            )
            if choice not in ("y", "yes"):
                print("❌ Update cancelled.")
                return

        print("🚀 Running: pipx upgrade git-cai-cli ...")
        try:
            result = subprocess.run(
                ["pipx", "upgrade", self.package_name],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                print(f"✅ Successfully updated to version {latest_version}")
            else:
                log.error("Update failed. stderr: %s", result.stderr)
                print("❌ Update failed. Check logs for details.")
        except (FileNotFoundError, subprocess.SubprocessError, OSError) as update_error:
            log.error("Error during update: %s", update_error)
            print("❌ An error occurred while updating. Check logs for details.")

    def commit_crazy(self, message: str, *, amend: bool = False) -> int:
        """
        Commit immediately using -m, without opening an editor, trusting the LLM output.
        """
        cmd = ["git", "commit"]
        if amend:
            cmd.append("--amend")
        cmd.extend(["-m", message])
        try:
            subprocess.run(cmd, check=True, text=True)
            return 0
        except subprocess.CalledProcessError as e:
            log.error("git commit failed with exit code %d", e.returncode)
            return e.returncode or 1

    def editor_list(self) -> list[str]:
        """
        Return a list of supported editors.
        """
        return [
            "Tested editors, but more should work:",
            "Nano",  # Nano
            "Vi",  # Vi
            "Vim",  # Vim
            "VS Code",  # Visual Studio Code
        ]

    def enable_debug(self) -> None:
        """
        Enable verbose/debug logging.
        """
        log.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)
        log.debug("Debug mode enabled.")

    def generate_config_here(self, filename: str = "cai_config.yml") -> None:
        """
        Generate a default cai_config.yml in the current working directory.
        """
        path = Path.cwd() / filename

        if path.exists():
            raise RuntimeError(f"{filename} already exists in this directory.")

        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                _serialize_config(ordered_default_config()),
                f,
                sort_keys=False,
            )

        log.info("Default configuration written to %s", path)

    def generate_prompts_here(self) -> None:
        """Generate default prompt files in the current working directory.

        Prompt bodies come directly from the hardcoded fallback strings in
        `prompts_fallback.py` — the single source of truth for prompt text.
        """
        from git_cai_cli.core.prompts_fallback import (
            HARDCODED_COMMIT_PROMPT,
            HARDCODED_FULL_FILES_PROMPT,
            HARDCODED_PR_PROMPT,
            HARDCODED_SQUASH_PROMPT,
        )

        cwd = Path.cwd()
        targets = (
            (cwd / "commit_prompt.md", HARDCODED_COMMIT_PROMPT, "commit"),
            (cwd / "squash_prompt.md", HARDCODED_SQUASH_PROMPT, "squash"),
            (cwd / "full_files_prompt.md", HARDCODED_FULL_FILES_PROMPT, "full-files"),
            (cwd / "pr_prompt.md", HARDCODED_PR_PROMPT, "pr"),
        )

        for path, _body, _label in targets:
            if path.exists():
                raise RuntimeError(f"{path.name} already exists in this directory.")

        for path, body, label in targets:
            path.write_text(body, encoding="utf-8")
            log.info("Default %s prompt written to %s", label, path)

    def handle_list(self, list_arg: str | None) -> None:
        """Dispatch the `--list` subcommand to the right listing method.

        With no argument, prints the overview. With a known argument,
        prints the corresponding information. Unknown arguments raise
        `typer.Exit(1)` after printing an error to stderr.
        """
        if list_arg is None:
            typer.echo(self.list())
            return

        option = list_arg.lower()
        if option == "config":
            typer.echo(self.list_config())
            return
        if option == "editor":
            for editor in self.editor_list():
                typer.echo(editor)
            return
        if option == "language":
            typer.echo(self.print_available_languages())
            return
        if option == "model":
            typer.echo(self.list_models())
            return
        if option == "path":
            typer.echo(self.list_paths())
            return
        if option == "provider":
            typer.echo(self.list_providers())
            return
        if option == "style":
            for name, details in self.styles().items():
                typer.echo(f"{name.capitalize()}: {details['description']}")
                typer.echo(f"  Example: {details['example']}\n")
            return

        typer.echo(
            f"Error: unknown list option '{list_arg}'. "
            "Valid values are 'config', 'editor', 'language', 'model', 'path', 'provider', or 'style'.",
            err=True,
        )
        raise typer.Exit(code=1)

    def list(self) -> str:
        """
        Return informational text for the --list / -l flag.
        Used when no argument is provided (git cai -l).
        """
        return """
Available list options:

config    - Show the active (effective) configuration
editor    - List supported and tested editors
language  - List supported languages
model     - Show the default model for each provider
path      - Show resolved configuration file paths
provider  - List supported LLM providers
style     - Show available commit message styles

Usage:
git cai -l config
git cai -l editor
git cai -l language
git cai -l model
git cai -l path
git cai -l provider
git cai -l style
"""

    def list_providers(self) -> str:
        """
        Return a formatted list of supported LLM providers with their
        default models and token requirements.
        """
        lines = ["\nSupported providers:\n"]
        for provider in sorted(KNOWN_PROVIDERS):
            block = DEFAULT_CONFIG.get(provider, {})
            model = block.get("model", "n/a") if isinstance(block, dict) else "n/a"
            token_info = (
                "no token required"
                if provider in TOKENLESS_PROVIDERS
                else "token required"
            )
            lines.append(f"  {provider:<12} model: {model:<35} ({token_info})")
        return "\n".join(lines)

    def list_models(self) -> str:
        """
        Return a formatted list of default models per provider.
        """
        lines = ["\nDefault models:\n"]
        for provider in sorted(KNOWN_PROVIDERS):
            block = DEFAULT_CONFIG.get(provider, {})
            model = block.get("model", "n/a") if isinstance(block, dict) else "n/a"
            lines.append(f"  {provider:<12} → {model}")
        return "\n".join(lines)

    def list_config(self) -> str:
        """
        Return the active (effective) configuration as formatted text.
        """
        try:
            config = load_config()
        except (ValueError, OSError) as e:
            return f"Error loading configuration: {e}"

        lines = ["\nActive configuration:\n"]
        for key, value in config.items():
            if isinstance(value, dict):
                lines.append(f"  {key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"    {sub_key}: {sub_value}")
            else:
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    def list_paths(self) -> str:
        """
        Return resolved configuration file paths.
        """
        repo_config = _find_repo_config()

        lines = ["\nConfiguration file paths:\n"]
        lines.append(f"  Config directory:      {CONFIG_DIR}")
        lines.append(f"  Home config:           {FALLBACK_CONFIG_FILE}")
        lines.append(f"  Tokens file:           {TOKENS_FILE}")

        if repo_config:
            lines.append(f"  Repository config:     {repo_config}  (active)")
        else:
            lines.append("  Repository config:     not found")

        lines.append(
            f"\n  Active config source:  {'repository' if repo_config else 'home'}"
        )
        return "\n".join(lines)

    def print_available_languages(self) -> str:
        """
        Print the list of supported languages and their human-readable names.
        Intended to be used in CLI commands.
        """
        lines = ["\nAvailable languages:"]
        # Sort by the name (value)
        for code, name in sorted(
            self.allowed_languages.items(), key=lambda item: item[1]
        ):
            lines.append(f"  - {name} → {code}")
        return "\n".join(lines)

    def squash_branch(
        self,
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
        Squash commits on the current branch and summarize them.
        """
        return squash_branch(
            provider_override=provider_override,
            model_override=model_override,
            temperature_override=temperature_override,
            time_flag=time_flag,
            squash_arg=squash_arg,
            context=context,
            sql_override=sql_override,
            signoff=signoff,
        )

    def stage_tracked_files(self) -> None:
        """
        Stage all modified and deleted files that are already tracked by Git.

        This mirrors the behavior of `git commit -a` by adding changes to the
        index without staging new, untracked files.

        Raises:
            RuntimeError: If the git command fails or is not executed inside
            a Git repository.
        """
        try:
            result = subprocess.run(
                ["git", "add", "-u"],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            log.error("Failed to execute git add -u: %s", exc)
            raise RuntimeError("Git is not available on PATH.") from exc

        if result.returncode != 0:
            log.error("git add -u failed: %s", result.stderr.strip())
            raise RuntimeError(
                f"Failed to stage tracked files: {result.stderr.strip()}"
            )

    def styles(self) -> dict:
        """
        Return available commit message styles with descriptions and examples.
        """
        return {
            "academic": {
                "description": "Precise and scholarly.",
                "example": "This commit introduces a revised configuration parser based on robust principles.",
            },
            "apologetic": {
                "description": "Humble and apologizing.",
                "example": "Sorry, my bad — this commit fixes the config error.",
            },
            "excited": {
                "description": "Energetic and enthusiastic.",
                "example": "Amazing update! The config loader is now super fast!",
            },
            "friendly": {
                "description": "Casual and warm tone.",
                "example": "Hey! Just cleaned up the config parsing.",
            },
            "funny": {
                "description": "Humorous and light-hearted.",
                "example": "Fixed the bug that was hiding like a ninja in our config.",
            },
            "neutral": {
                "description": "Objective and to the point.",
                "example": "Fix typo in configuration loader.",
            },
            "none": {
                "description": "No style instruction will be included in the prompt, allowing the model to choose its own tone.",
                "example": "Model's choice of style.",
            },
            "professional": {
                "description": "Clear, concise, and formal. Default style.",
                "example": "Refactor logging module to improve reliability.",
            },
            "sarcastic": {
                "description": "Dry, ironic tone.",
                "example": "Oh look, another config bug. Shocking, right?",
            },
        }
