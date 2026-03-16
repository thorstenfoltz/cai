"""
Unit tests for git_cai_cli.core.spinner module.
"""

import io
import time
from unittest.mock import patch

from git_cai_cli.core.spinner import Spinner


def test_spinner_starts_and_stops():
    """Verify the spinner thread starts and stops within timeout."""
    mock_stderr = io.StringIO()
    mock_stderr.isatty = lambda: True  # type: ignore[attr-defined]

    with patch("git_cai_cli.core.spinner.sys.stderr", mock_stderr):
        spinner = Spinner("Testing")
        spinner.__enter__()

        assert spinner._thread is not None
        assert spinner._thread.is_alive()

        spinner.__exit__(None, None, None)

        assert not spinner._thread.is_alive()


def test_spinner_shows_bouncing_bar():
    """Verify the spinner displays a bouncing bar with the message."""
    mock_stderr = io.StringIO()
    mock_stderr.isatty = lambda: True  # type: ignore[attr-defined]

    with patch("git_cai_cli.core.spinner.sys.stderr", mock_stderr):
        with Spinner("Loading"):
            time.sleep(0.15)

    output = mock_stderr.getvalue()
    # Should contain the bar brackets and the message
    assert "[" in output
    assert "]" in output
    assert "Loading" in output
    # Should contain the block character
    assert "█" in output
    # Should end with a clear line (carriage return)
    assert output.endswith("\r")


def test_spinner_skipped_when_not_tty():
    """Verify the spinner does not start a thread if stderr is not a TTY."""
    mock_stderr = io.StringIO()
    mock_stderr.isatty = lambda: False  # type: ignore[attr-defined]

    with patch("git_cai_cli.core.spinner.sys.stderr", mock_stderr):
        with Spinner("Test") as sp:
            assert sp._thread is None

    # No output should be written
    assert mock_stderr.getvalue() == ""


def test_spinner_context_manager_preserves_value():
    """Verify that code inside the spinner context works normally."""
    mock_stderr = io.StringIO()
    mock_stderr.isatty = lambda: True  # type: ignore[attr-defined]

    result = None
    with patch("git_cai_cli.core.spinner.sys.stderr", mock_stderr):
        with Spinner("Computing"):
            result = 42

    assert result == 42


def test_spinner_handles_exception_in_body():
    """Verify the spinner stops cleanly even if the body raises."""
    mock_stderr = io.StringIO()
    mock_stderr.isatty = lambda: True  # type: ignore[attr-defined]

    spinner = Spinner("Failing")
    try:
        with patch("git_cai_cli.core.spinner.sys.stderr", mock_stderr):
            with spinner:
                raise ValueError("boom")
    except ValueError:
        pass

    # Thread should have stopped
    assert spinner._stop_event.is_set()
    if spinner._thread is not None:
        assert not spinner._thread.is_alive()
