"""
Core manager for CLI utilities.
"""

import logging
import re
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import requests
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

    def get_version(self) -> str:
        """
        Return the installed version of the CLI package.

        Returns:
            str: The version string.

        Raises:
            PackageNotFoundError: If the package is not installed.
        """
        try:
            ver = f"git-cai-cli version: {version(self.package_name)}"
            return ver
        except PackageNotFoundError:
            log.error(
                "Package '%s' not found – unable to determine version.",
                self.package_name,
            )
            raise

    def get_help(self) -> str:
        """
        Return a help message for the CLI.
        """
        home = Path.home()
        return f"""
Git CAI - AI-powered commit message generator

Usage:
  git cai        Generate commit message from staged changes

Flags:
  -h                Show this help message
  -d, --debug       Enable debug logging
  -l, --languages   List supported languages
  -s, --squash      Squash commits on this branch and summarize them
      --style       Show available commit message styles
  -u, --update      Check for updates
  -v, --version     Show installed version

Configuration:
  Tokens are loaded from {home}/.config/cai/tokens.yml

Examples:
  git add .
  git cai           Generates commit message

"""

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
                f"https://pypi.org/pypi/{self.package_name}/json", timeout=3
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

    def enable_debug(self) -> None:
        """
        Enable verbose/debug logging.
        """
        log.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)
        log.debug("Debug mode enabled.")

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

    def squash_branch(self) -> None:
        """
        Squash commits on the current branch and summarize them.
        """
        return squash_branch()

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
            "professional": {
                "description": "Clear, concise, and formal. Default style.",
                "example": "Refactor logging module to improve reliability.",
            },
            "sarcastic": {
                "description": "Dry, ironic tone.",
                "example": "Oh look, another config bug. Shocking, right?",
            },
        }
