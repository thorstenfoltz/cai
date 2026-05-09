"""Local-only usage analytics for git-cai (FB.11).

Records per-generation events to a SQLite DB under ``XDG_DATA_HOME``
(default: ``~/.local/share/git-cai/stats.db``). No diff content,
commit messages, or file paths are stored — only metadata: timestamp,
provider, model, token counts, latency, success.

Recording is opt-in (``stats: true`` in cai_config.yml, default
``false``) and best-effort: a failed write must never break commit
generation. Cost estimation is intentionally not implemented —
provider prices change too often for any local approximation to stay
accurate.

The optional ``stats_db_path`` top-level config key overrides the
default DB location.
"""

from __future__ import annotations

import functools
import json
import logging
import os
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    import sqlite3
except ImportError:  # minimal CPython builds may ship without _sqlite3
    sqlite3 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# Exceptions worth swallowing during best-effort stats writes. We compute
# this once at module load so call sites can reference a real tuple
# (avoiding broad ``except Exception``). When sqlite is missing we still
# guard against filesystem failures.
_STATS_WRITE_FAILURES: tuple[type[BaseException], ...] = (
    (sqlite3.Error, OSError) if sqlite3 is not None else (OSError,)
)


@functools.lru_cache(maxsize=1)
def _warn_sqlite_missing_once() -> None:
    """Log the once-per-process warning that sqlite3 is unavailable."""
    log.warning(
        "sqlite3 module is not available in this Python build. "
        "git-cai stats will be disabled for this run. "
        "To fix: rebuild Python with sqlite headers, or set "
        "`stats: false` in cai_config.yml to silence this warning."
    )


def _sqlite_available() -> bool:
    """Return True if the runtime's stdlib sqlite3 is importable."""
    if sqlite3 is None:
        _warn_sqlite_missing_once()
        return False
    return True


def _default_db_path() -> Path:
    """Return the default stats DB path under XDG_DATA_HOME."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "git-cai" / "stats.db"


def resolve_db_path(config: dict[str, Any] | None) -> Path:
    """Resolve the stats DB path from config, with default fallback."""
    if config:
        override = config.get("stats_db_path")
        if override:
            return Path(str(override)).expanduser()
    return _default_db_path()


def is_enabled(config: dict[str, Any] | None) -> bool:
    """Stats writing is opt-in: ``stats: true|false`` at the top level
    of the config. Defaults to ``False`` when the key is unset.

    A nested ``stats: {enabled: ...}`` shape is rejected (logged
    once) — only the flat boolean form is supported.
    """
    if not config:
        return False
    raw = config.get("stats", False)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, dict):
        _warn_legacy_stats_shape_once()
        return False
    return bool(raw)


@functools.lru_cache(maxsize=1)
def _warn_legacy_stats_shape_once() -> None:
    """Log the once-per-process deprecation warning for the legacy
    ``stats: {enabled: ...}`` config shape."""
    log.warning(
        "Config key `stats` is a mapping; the supported form is "
        "now a plain boolean (`stats: true` or `stats: false`). "
        "Treating this run as disabled."
    )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    repo TEXT,
    provider TEXT NOT NULL,
    model TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    latency_ms INTEGER,
    success INTEGER NOT NULL DEFAULT 1,
    language TEXT,
    style TEXT,
    emoji INTEGER,
    temperature REAL,
    prompt_file TEXT,
    time_ms INTEGER
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_provider ON events(provider);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind);
CREATE INDEX IF NOT EXISTS events_repo ON events(repo);
"""


@contextmanager
def _connect(db_path: Path) -> Iterator[Any]:
    # Callers gate on ``_sqlite_available()`` first, so ``sqlite3`` is
    # guaranteed to be a real module here — but we re-check defensively
    # rather than ``assert`` (which is stripped under ``python -O``).
    if sqlite3 is None:
        raise RuntimeError(
            "sqlite3 unavailable; caller must gate on _sqlite_available()"
        )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def record(
    *,
    config: dict[str, Any] | None,
    kind: str,
    provider: str,
    model: str | None,
    tokens_in: int | None,
    tokens_out: int | None,
    latency_ms: int | None,
    success: bool = True,
    repo: str | None = None,
    language: str | None = None,
    style: str | None = None,
    emoji: bool | None = None,
    temperature: float | None = None,
    prompt_file: str | None = None,
) -> int | None:
    """Record one analytics event. Best-effort, never raises.

    Returns the inserted row id on success, or ``None`` when stats are
    disabled, sqlite is unavailable, or the write fails. The id lets a
    caller patch the row later (e.g. ``set_time_ms`` once the
    user-perceived elapsed time is known).
    """
    if not is_enabled(config):
        return None
    if not _sqlite_available():
        return None
    try:
        from datetime import datetime, timezone

        db_path = resolve_db_path(config)
        ts = datetime.now(timezone.utc).isoformat()
        emoji_int = None if emoji is None else (1 if emoji else 0)
        with _connect(db_path) as conn:
            cur = conn.execute(
                "INSERT INTO events ("
                "ts, kind, repo, provider, model, tokens_in, tokens_out, "
                "latency_ms, success, language, style, emoji, temperature, "
                "prompt_file"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    kind,
                    repo,
                    provider,
                    model,
                    tokens_in,
                    tokens_out,
                    latency_ms,
                    1 if success else 0,
                    language,
                    style,
                    emoji_int,
                    temperature,
                    prompt_file,
                ),
            )
            return cur.lastrowid
    except _STATS_WRITE_FAILURES as exc:
        log.debug("stats.record failed (non-fatal): %s", exc)
        return None


def set_time_ms(
    config: dict[str, Any] | None,
    event_id: int | None,
    time_ms: int | None,
) -> None:
    """Patch an existing event's ``time_ms`` column. Best-effort no-op
    when stats are disabled, sqlite is unavailable, or inputs are
    missing — used to record the user-perceived elapsed time once it's
    known (only when ``-t`` / ``--time`` is set)."""
    if event_id is None or time_ms is None:
        return
    if not is_enabled(config):
        return
    if not _sqlite_available():
        return
    try:
        db_path = resolve_db_path(config)
        if not db_path.exists():
            return
        with _connect(db_path) as conn:
            conn.execute(
                "UPDATE events SET time_ms = ? WHERE id = ?",
                (time_ms, event_id),
            )
    except _STATS_WRITE_FAILURES as exc:
        log.debug("stats.set_time_ms failed (non-fatal): %s", exc)


def reset(config: dict[str, Any] | None) -> int:
    """Drop all rows. Returns the number of rows deleted, or 0 on failure."""
    if not _sqlite_available():
        return 0
    try:
        db_path = resolve_db_path(config)
        if not db_path.exists():
            return 0
        with _connect(db_path) as conn:
            cur = conn.execute("DELETE FROM events")
            return cur.rowcount or 0
    except _STATS_WRITE_FAILURES as exc:
        log.error("Failed to reset stats DB: %s", exc)
        return 0


def _aggregate(
    config: dict[str, Any] | None,
    *,
    since: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Build the summary dict consumed by the renderers."""
    summary: dict[str, Any] = {
        "since": since,
        "provider_filter": provider,
        "total_commits": 0,
        "total_amends": 0,
        "total_squashes": 0,
        "total_prs": 0,
        "total_tokens_in": 0,
        "total_tokens_out": 0,
        "avg_latency_ms": None,
        "top_provider": None,
        "per_provider": [],
    }

    if not _sqlite_available():
        return summary

    db_path = resolve_db_path(config)
    if not db_path.exists():
        return summary

    where: list[str] = []
    params: list[Any] = []
    if since:
        where.append("ts >= ?")
        params.append(since)
    if provider:
        where.append("provider = ?")
        params.append(provider)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    with _connect(db_path) as conn:
        # Per-provider rollups
        rows = conn.execute(
            f"SELECT provider, COUNT(*), "
            f"COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0), "
            f"AVG(latency_ms) "
            f"FROM events {where_clause} GROUP BY provider ORDER BY COUNT(*) DESC",
            params,
        ).fetchall()

        per_provider = []
        for prov, count, tin, tout, avg_lat in rows:
            per_provider.append(
                OrderedDict(
                    [
                        ("provider", prov),
                        ("count", count),
                        ("tokens_in", tin),
                        ("tokens_out", tout),
                        ("avg_latency_ms", round(avg_lat) if avg_lat else None),
                    ]
                )
            )
        summary["per_provider"] = per_provider

        if per_provider:
            summary["top_provider"] = per_provider[0]["provider"]

        # Totals
        totals = conn.execute(
            f"SELECT "
            f"  SUM(CASE WHEN kind = 'commit' THEN 1 ELSE 0 END), "
            f"  SUM(CASE WHEN kind = 'amend'  THEN 1 ELSE 0 END), "
            f"  SUM(CASE WHEN kind = 'squash' THEN 1 ELSE 0 END), "
            f"  SUM(CASE WHEN kind = 'pr'     THEN 1 ELSE 0 END), "
            f"  COALESCE(SUM(tokens_in), 0), "
            f"  COALESCE(SUM(tokens_out), 0), "
            f"  AVG(latency_ms) "
            f"FROM events {where_clause}",
            params,
        ).fetchone()
        if totals:
            commits, amends, squashes, prs, tin, tout, avg_lat = totals
            summary["total_commits"] = commits or 0
            summary["total_amends"] = amends or 0
            summary["total_squashes"] = squashes or 0
            summary["total_prs"] = prs or 0
            summary["total_tokens_in"] = tin or 0
            summary["total_tokens_out"] = tout or 0
            summary["avg_latency_ms"] = round(avg_lat) if avg_lat else None

    return summary


def render_text(summary: dict[str, Any]) -> str:
    """Render the human-readable text view."""
    lines = [
        "git-cai usage"
        + (f" (since {summary['since']})" if summary.get("since") else "")
    ]
    lines.append("─" * 33)
    lines.append(f"Commits generated:        {summary['total_commits']}")
    lines.append(f"Amends:                   {summary.get('total_amends', 0)}")
    lines.append(f"Squashes:                 {summary['total_squashes']}")
    lines.append(f"PR descriptions:          {summary.get('total_prs', 0)}")
    if summary.get("top_provider"):
        lines.append(f"Top provider:             {summary['top_provider']}")
    lines.append(
        f"Total tokens:             {summary['total_tokens_in']:,} in / "
        f"{summary['total_tokens_out']:,} out"
    )
    if summary.get("avg_latency_ms") is not None:
        lines.append(f"Avg latency:              {summary['avg_latency_ms']/1000:.1f}s")
    lines.append("─" * 33)
    if summary["per_provider"]:
        lines.append("Per provider:")
        for row in summary["per_provider"]:
            lat = (
                f"{row['avg_latency_ms']/1000:.1f}s avg"
                if row.get("avg_latency_ms") is not None
                else "—"
            )
            lines.append(
                f"  {row['provider']:<10} {row['count']:>4}   "
                f"{row['tokens_in']:>7,} in / {row['tokens_out']:>5,} out   {lat}"
            )
    return "\n".join(lines)


def log_state(config: dict[str, Any] | None) -> None:
    """Log whether stats writing is enabled, and where the DB lives.

    Lives in ``stats`` (rather than ``main``) so ``core.pr`` and
    ``core.squash`` can call it without re-introducing a cyclic
    import back into the entry point module.
    """
    if is_enabled(config):
        log.info("Stats writing enabled — recording to %s", resolve_db_path(config))
    else:
        log.info("Stats writing disabled")


def show(
    config: dict[str, Any] | None,
    *,
    since: str | None = None,
    provider: str | None = None,
    as_json: bool = False,
) -> str:
    """Build the user-facing stats output as a string."""
    if not _sqlite_available():
        return (
            "git-cai stats unavailable: this Python build has no sqlite3 "
            "module. Rebuild Python with sqlite support or set "
            "`stats: false` to silence this warning."
        )
    summary = _aggregate(config, since=since, provider=provider)
    if as_json:
        return json.dumps(summary, default=str, indent=2)
    return render_text(summary)
