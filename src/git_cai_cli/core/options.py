"""
Core manager for CLI utilities.
"""

from importlib.metadata import version, PackageNotFoundError
import logging

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
                self.package_name
            )
            raise
