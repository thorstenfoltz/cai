import sys
from pathlib import Path


def pytest_configure() -> None:
    """Ensure local `src/` imports win over any installed package."""
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    sys.path.insert(0, str(src))
