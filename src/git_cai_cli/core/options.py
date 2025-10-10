"""
Core manager for CLI utilities.
"""

import logging
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

log = logging.getLogger(__name__)


class CliManager:
    """
    Central manager class for CLI-level operations.
    """

    def __init__(self, package_name: str = "git-cai-cli"):
        self.package_name = package_name

    def get_version(self) -> str:
        """
        Return the installed version of the CLI package.

        Returns:
            str: The version string.

        Raises:
            PackageNotFoundError: If the package is not installed.
        """
        try:
            return version(self.package_name)
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
  -h             Show this help message
  -v, --version  Show installed version  

Configuration:
  Tokens are loaded from {home}/.config/cai/tokens.yml

Examples:
  git add .
  git cai        Generates commit message

"""
