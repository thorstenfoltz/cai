"""Local secret detection for content about to be sent to an LLM provider.

Dependency-free (stdlib only) so it can be imported anywhere without import
cycles. The point is to catch likely credentials *before* the diff leaves the
machine, rather than relying on the model to warn after the fact.

`ponytail:` a compact, high-signal regex set with a known false-positive
ceiling. Swap in gitleaks/detect-secrets only if the FP rate becomes a problem.
"""

import re
from typing import NamedTuple


class Finding(NamedTuple):
    """A single suspected secret: rule, the file path it was in, line, masked value.

    ``path``/``line`` are derived from the surrounding diff headers when scanning
    a diff; they are ``None`` for plain (non-diff) text.
    """

    rule: str
    path: str | None
    line: int | None
    masked: str


class SecretLeakError(Exception):
    """Raised when scanning finds likely secrets and the send is not bypassed."""

    def __init__(self, findings: list[Finding]):
        self.findings = findings
        super().__init__(f"{len(findings)} potential secret(s) detected")


# (label, compiled pattern). Only distinctive, prefix-anchored credential
# formats — these almost never false-positive. A generic `keyword = value` rule
# was removed because it flagged ordinary code, config, hashes, and test data.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[opsur]_[A-Za-z0-9]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b|\bxapp-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
]


# Obvious non-secret markers found in docs, examples, and templates.
_DUMMY_MARKERS = (
    "example",
    "sample",
    "dummy",
    "placeholder",
    "changeme",
    "redacted",
    "put-your",
)
# Strips a known credential prefix so the random "body" can be inspected.
_PREFIX_RE = re.compile(
    r"^(?:sk-(?:proj-)?|gh[opsur]_|AKIA|AIza|xox[baprs]-|xapp-)", re.IGNORECASE
)


def _looks_like_placeholder(value: str) -> bool:
    """True for clearly fake values: dummy markers or repeated-character filler."""
    low = value.lower()
    if any(marker in low for marker in _DUMMY_MARKERS):
        return True
    body = _PREFIX_RE.sub("", value)
    return len(body) >= 8 and len(set(body)) <= 2


# Diff-structure markers used to attribute each match to a file and line.
_DIFF_GIT = re.compile(r"^diff --git a/.+ b/(.+)$")
_FULL_FILE = re.compile(r"^--- File: (.+) ---\s*$")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _mask(value: str) -> str:
    """Show only the first/last few characters so output never echoes a full secret."""
    value = value.strip().strip("'\"")
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}…{value[-2:]}"


def scan_for_secrets(text: str) -> list[Finding]:
    """Scan ``text`` and return findings, attributing each to its file and line.

    Tracks the surrounding diff headers (``diff --git``, ``+++ b/``, hunk
    ``@@`` lines) and full-file dump markers (``--- File: <path> ---``) so each
    finding reports *where* the secret is, not an opaque payload offset.
    """
    findings: list[Finding] = []
    seen: set[tuple[str, str | None, str]] = set()

    current_file: str | None = None
    new_lineno: int | None = None  # line in the new file within a diff hunk
    file_lineno: int | None = None  # line within a full-file dump block

    for raw in text.splitlines():
        m = _DIFF_GIT.match(raw)
        if m:
            current_file, new_lineno, file_lineno = m.group(1).strip(), None, None
            continue
        if raw.startswith("+++ b/"):
            current_file, new_lineno, file_lineno = raw[6:].strip(), None, None
            continue
        ff = _FULL_FILE.match(raw)
        if ff:
            current_file, new_lineno, file_lineno = ff.group(1).strip(), None, 0
            continue
        h = _HUNK.match(raw)
        if h:
            new_lineno = int(h.group(1))
            continue

        # Resolve the reported line for a content line.
        if file_lineno is not None:
            file_lineno += 1
            report_line: int | None = file_lineno
        elif new_lineno is not None and not raw.startswith("-"):
            report_line = new_lineno
            new_lineno += 1
        else:
            report_line = None

        for rule, pattern in _PATTERNS:
            match = pattern.search(raw)
            if not match:
                continue
            value = match.group(0)
            if _looks_like_placeholder(value):
                continue
            key = (rule, current_file, value)
            if key in seen:
                continue
            seen.add(key)
            findings.append(Finding(rule, current_file, report_line, _mask(value)))
    return findings


def format_findings(findings: list[Finding]) -> str:
    """Render findings as a human-readable, multi-line warning block."""
    lines = ["⚠️  Potential secret(s) detected in the content to be sent:"]
    for finding in findings:
        if finding.path and finding.line is not None:
            loc = f"{finding.path}:{finding.line}"
        elif finding.path:
            loc = finding.path
        elif finding.line is not None:
            loc = f"line {finding.line}"
        else:
            loc = "(unknown location)"
        lines.append(f"    {loc}: {finding.rule} ({finding.masked})")
    return "\n".join(lines)
