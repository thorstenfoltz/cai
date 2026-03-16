"""
Inline terminal spinner for long-running operations.

Displays an animated progress indicator on stderr while a block of code runs.
Automatically skipped when stderr is not a TTY (e.g. CI, piped output).
"""

import sys
import threading

# Bouncing bar: a block slides back and forth inside brackets
_BAR_WIDTH = 20
_BLOCK = "███"


class Spinner:
    """Context manager that displays a bouncing progress bar on stderr."""

    def __init__(self, message: str = "Generating commit message"):
        self._message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _spin(self) -> None:
        """Animate a bouncing bar until the stop event is set."""
        pos = 0
        direction = 1
        max_pos = _BAR_WIDTH - len(_BLOCK)

        while not self._stop_event.is_set():
            block = " " * pos + _BLOCK + " " * (max_pos - pos)
            sys.stderr.write(f"\r  [{block}] {self._message}")
            sys.stderr.flush()
            pos += direction
            if pos >= max_pos or pos <= 0:
                direction *= -1
            self._stop_event.wait(0.05)

        # Clear the entire line
        total_len = _BAR_WIDTH + len(self._message) + 6
        sys.stderr.write("\r" + " " * total_len + "\r")
        sys.stderr.flush()

    def __enter__(self) -> "Spinner":
        if sys.stderr.isatty():
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
