"""
Inline terminal spinner for long-running operations.

Displays an animated progress indicator on stderr while a block of code runs.
Automatically skipped when stderr is not a TTY (e.g. CI, piped output).
"""

import logging
import sys
import threading

# Bouncing bar: a block slides back and forth inside brackets
_BAR_WIDTH = 20
_BLOCK = "███"


class _LineBreakingStream:
    """Stream proxy that breaks the current spinner line before logging.

    While the spinner is active, log messages are routed through this
    proxy. The proxy tracks whether the cursor is currently on a line
    that the spinner has rendered. When it is, a single `\\n` is
    inserted before the log write so the log lands on a fresh row below
    the spinner. When it is not (e.g. the previous write was already a
    log line ending in `\\n`), nothing is inserted — consecutive log
    messages stay tightly packed without empty rows between them.

    Spinner frames start with `\\r` and are forwarded unchanged.
    """

    def __init__(self, base):  # type: ignore[no-untyped-def]
        self._base = base
        self._cursor_on_spinner_line = False
        self._lock = threading.Lock()

    def write(self, data: str) -> int:
        """Write data to the stream, prefixing with a newline if the cursor is on a spinner line."""
        if not data:
            return 0
        with self._lock:
            if data.startswith("\r"):
                # Spinner frame — cursor returns to col 0 and overwrites
                # the line with bouncing-bar content.
                self._cursor_on_spinner_line = True
                return self._base.write(data)

            if data.startswith("\n"):
                # Already starts with a break; don't double it.
                self._cursor_on_spinner_line = False
                return self._base.write(data)

            prefix = "\n" if self._cursor_on_spinner_line else ""
            self._cursor_on_spinner_line = False
            return self._base.write(prefix + data)

    def flush(self) -> None:
        """Flush the stream."""
        self._base.flush()

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return getattr(self._base, name)


class Spinner:
    """Context manager that displays a bouncing progress bar on stderr."""

    def __init__(self, message: str = "Generating commit message"):
        self._message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._proxy: _LineBreakingStream | None = None
        self._original_streams: dict[logging.StreamHandler, object] = {}

    def _spin(self) -> None:
        """Animate a bouncing bar until the stop event is set."""
        pos = 0
        direction = 1
        max_pos = _BAR_WIDTH - len(_BLOCK)
        # Route spinner output through the shared proxy so its CR-prefixed
        # frames update the proxy's cursor-state. This is what lets log
        # lines that fire mid-spinner correctly insert a leading newline.
        out = self._proxy if self._proxy is not None else sys.stderr

        while not self._stop_event.is_set():
            block = " " * pos + _BLOCK + " " * (max_pos - pos)
            out.write(f"\r  [{block}] {self._message}")
            out.flush()
            pos += direction
            if pos >= max_pos or pos <= 0:
                direction *= -1
            self._stop_event.wait(0.05)

        # Clear the entire line
        total_len = _BAR_WIDTH + len(self._message) + 6
        out.write("\r" + " " * total_len + "\r")
        out.flush()

    def _wrap_log_streams(self) -> None:
        """Redirect StreamHandlers writing to stderr through the spinner's
        proxy so spinner frames and log lines share cursor-state."""
        if self._proxy is None:
            return
        for handler in logging.getLogger().handlers:
            if (
                isinstance(handler, logging.StreamHandler)
                and handler.stream is sys.stderr
                and not isinstance(handler.stream, _LineBreakingStream)
            ):
                self._original_streams[handler] = handler.stream
                handler.stream = self._proxy

    def _unwrap_log_streams(self) -> None:
        for handler, original in self._original_streams.items():
            handler.stream = original
        self._original_streams.clear()

    def __enter__(self) -> "Spinner":
        if sys.stderr.isatty():
            self._proxy = _LineBreakingStream(sys.stderr)
            self._wrap_log_streams()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._unwrap_log_streams()
        self._proxy = None
