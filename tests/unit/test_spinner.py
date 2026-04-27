"""
Unit tests for git_cai_cli.core.spinner module.
"""

import io
import logging
import time
from unittest.mock import patch

from git_cai_cli.core.spinner import Spinner, _LineBreakingStream


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


# ---------------------------------------------------------------------------
# Log lines must land on a new row, not get smashed against the spinner.
# ---------------------------------------------------------------------------


def test_line_breaking_stream_breaks_only_when_cursor_on_spinner_line():
    """A `\\n` is inserted only when the previous write was a spinner frame
    (CR-starting). Consecutive log writes stay tightly packed."""
    base = io.StringIO()
    proxy = _LineBreakingStream(base)

    # Initial state: no spinner yet → log lines pass through unchanged.
    proxy.write("first log line\n")
    proxy.write("second log line\n")

    # Spinner frame lands → cursor is now on a spinner line.
    proxy.write("\r  [bar] message")

    # Next log gets a leading `\n` to break off the spinner line.
    proxy.write("post-spinner log\n")

    # A second log right after stays tight — cursor is already on a fresh line.
    proxy.write("another log\n")

    out = base.getvalue()
    assert out == (
        "first log line\n"
        "second log line\n"
        "\r  [bar] message"
        "\npost-spinner log\n"
        "another log\n"
    )


def test_line_breaking_stream_passes_through_explicit_newline_writes():
    """A write that already starts with `\\n` is not double-prefixed."""
    base = io.StringIO()
    proxy = _LineBreakingStream(base)

    proxy.write("\r  [bar] message")  # cursor on spinner line
    proxy.write("\nexplicit break\n")  # already starts with \n; no extra one

    assert base.getvalue() == "\r  [bar] message\nexplicit break\n"


def test_line_breaking_stream_skips_empty_writes():
    base = io.StringIO()
    proxy = _LineBreakingStream(base)

    proxy.write("")

    assert base.getvalue() == ""


def test_log_during_spinner_lands_on_new_line():
    """When the spinner is active and has rendered a frame, the next log
    line must be preceded by `\\n` so it lands on a fresh row instead of
    smashing against the spinner."""
    mock_stderr = io.StringIO()
    mock_stderr.isatty = lambda: True  # type: ignore[attr-defined]

    log = logging.getLogger("spinner-newline-test")
    log.handlers.clear()
    log.propagate = False

    handler = logging.StreamHandler(mock_stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    with patch("git_cai_cli.core.spinner.sys.stderr", mock_stderr):
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            with Spinner("Generating commit message"):
                # Wait long enough for the spinner thread to render at
                # least one frame so the cursor is on a spinner line.
                time.sleep(0.1)
                log.info("inner log line")
        finally:
            root.removeHandler(handler)
            log.handlers.clear()

    out = mock_stderr.getvalue()
    assert "\ninner log line" in out


def test_consecutive_logs_during_spinner_have_no_empty_rows():
    """Two log lines fired back-to-back while the spinner is active must
    not be separated by an empty row."""
    mock_stderr = io.StringIO()
    mock_stderr.isatty = lambda: True  # type: ignore[attr-defined]

    log = logging.getLogger("spinner-consecutive-logs-test")
    log.handlers.clear()
    log.propagate = False

    handler = logging.StreamHandler(mock_stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    with patch("git_cai_cli.core.spinner.sys.stderr", mock_stderr):
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            with Spinner("Generating commit message"):
                time.sleep(0.1)  # let spinner render at least one frame
                log.info("line one")
                log.info("line two")
        finally:
            root.removeHandler(handler)
            log.handlers.clear()

    out = mock_stderr.getvalue()
    # No double-newline between the two consecutive log lines.
    assert "line one\nline two" in out
    assert "line one\n\nline two" not in out


def test_spinner_restores_handler_streams_on_exit():
    """After the spinner exits, the root handlers' streams must be restored
    to their original objects (not the proxy)."""
    mock_stderr = io.StringIO()
    mock_stderr.isatty = lambda: True  # type: ignore[attr-defined]

    handler = logging.StreamHandler(mock_stderr)
    root = logging.getLogger()
    root.addHandler(handler)

    try:
        with patch("git_cai_cli.core.spinner.sys.stderr", mock_stderr):
            with Spinner("X"):
                assert isinstance(handler.stream, _LineBreakingStream)
        # After exit, the original stream is back.
        assert handler.stream is mock_stderr
    finally:
        root.removeHandler(handler)


def test_spinner_does_not_wrap_when_not_tty():
    """No tty -> no wrapping (and no spinner thread)."""
    mock_stderr = io.StringIO()
    mock_stderr.isatty = lambda: False  # type: ignore[attr-defined]

    handler = logging.StreamHandler(mock_stderr)
    root = logging.getLogger()
    root.addHandler(handler)

    try:
        with patch("git_cai_cli.core.spinner.sys.stderr", mock_stderr):
            with Spinner("X"):
                # Stream stays untouched in non-tty mode.
                assert handler.stream is mock_stderr
        assert handler.stream is mock_stderr
    finally:
        root.removeHandler(handler)
