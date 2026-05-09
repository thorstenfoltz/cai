"""FB.11 — git cai stats: local-only usage analytics.

All tests are mocked; no real API calls and no real network.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from git_cai_cli.core import stats as stats_module


@pytest.fixture
def db_config(tmp_path: Path) -> dict:
    """A config dict whose stats DB lives under tmp_path."""
    return {
        "stats": True,
        "stats_db_path": str(tmp_path / "stats.db"),
    }


def _read_all(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT * FROM events").fetchall()
    finally:
        conn.close()


def _read_rows(db_path: Path, columns: str = "*") -> list[dict]:
    """Read events as a list of dicts so tests aren't coupled to column order."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT {columns} FROM events").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Opt-in default — stats.enabled defaults to False
# ---------------------------------------------------------------------------


def test_is_enabled_defaults_to_false():
    """Stats writing is opt-in: missing config returns False."""
    assert stats_module.is_enabled(None) is False
    assert stats_module.is_enabled({}) is False
    assert stats_module.is_enabled({"stats": False}) is False


def test_is_enabled_true_when_explicitly_set():
    assert stats_module.is_enabled({"stats": True}) is True


def test_is_enabled_rejects_legacy_dict_shape(caplog):
    """Old-style nested config (`stats: {enabled: true}`) is no longer
    supported: only the flat ``stats: true|false`` boolean form. A
    dict value is treated as disabled and a deprecation warning is
    logged once."""
    stats_module._warn_legacy_stats_shape_once.cache_clear()
    caplog.set_level("WARNING")

    assert stats_module.is_enabled({"stats": {"enabled": True}}) is False
    assert "supported form is now a plain boolean" in caplog.text


# ---------------------------------------------------------------------------
# record() — best-effort, never raises
# ---------------------------------------------------------------------------


def test_record_writes_event_when_enabled(db_config, tmp_path):
    event_id = stats_module.record(
        config=db_config,
        kind="commit",
        provider="anthropic",
        model="claude",
        tokens_in=10,
        tokens_out=5,
        latency_ms=1234,
        repo="git-cai",
        language="en",
        style="professional",
        emoji=True,
        temperature=0.2,
        prompt_file="/tmp/p.md",
    )

    rows = _read_rows(Path(db_config["stats_db_path"]))
    assert len(rows) == 1
    row = rows[0]
    assert event_id == row["id"]
    assert row["kind"] == "commit"
    assert row["provider"] == "anthropic"
    assert row["model"] == "claude"
    assert row["tokens_in"] == 10
    assert row["tokens_out"] == 5
    assert row["latency_ms"] == 1234
    assert row["success"] == 1
    assert row["ts"]  # ISO timestamp
    assert row["repo"] == "git-cai"
    assert row["language"] == "en"
    assert row["style"] == "professional"
    assert row["emoji"] == 1
    assert row["temperature"] == pytest.approx(0.2)
    assert row["prompt_file"] == "/tmp/p.md"
    assert row["time_ms"] is None


def test_record_is_noop_when_disabled(tmp_path):
    """When stats is False, no row is written and no DB created."""
    db = tmp_path / "stats.db"
    config = {"stats": False, "stats_db_path": str(db)}

    stats_module.record(
        config=config,
        kind="commit",
        provider="x",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
    )

    assert not db.exists()


def test_record_swallows_write_errors(tmp_path, caplog):
    """A bad DB path must NOT bubble up — recording is best-effort."""
    bad = tmp_path / "nope" / "is" / "a" / "regular" / "file.db"
    bad.parent.mkdir(parents=True)
    bad.write_text("not a sqlite db")  # so connect() fails to read schema

    # Make the parent read-only so writes fail noisily
    config = {"stats": True, "stats_db_path": str(bad)}

    # Should NOT raise. Whether anything is logged is implementation
    # detail; what matters is no exception leaks.
    stats_module.record(
        config=config,
        kind="commit",
        provider="x",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
    )


# ---------------------------------------------------------------------------
# show() / aggregate
# ---------------------------------------------------------------------------


def test_show_text_summary_after_recording(db_config):
    for prov in ["anthropic", "anthropic", "groq"]:
        stats_module.record(
            config=db_config,
            kind="commit",
            provider=prov,
            model="m",
            tokens_in=100,
            tokens_out=20,
            latency_ms=500,
        )

    out = stats_module.show(db_config, as_json=False)

    assert "Commits generated:" in out
    assert "anthropic" in out
    assert "groq" in out
    assert "Total tokens:" in out


def test_show_json_summary(db_config):
    stats_module.record(
        config=db_config,
        kind="commit",
        provider="anthropic",
        model="m",
        tokens_in=10,
        tokens_out=5,
        latency_ms=100,
    )

    out = stats_module.show(db_config, as_json=True)
    parsed = json.loads(out)

    assert parsed["total_commits"] == 1
    assert parsed["total_tokens_in"] == 10
    assert parsed["total_tokens_out"] == 5
    assert parsed["top_provider"] == "anthropic"


def test_show_with_no_db_returns_empty_summary(tmp_path):
    config = {"stats": True, "stats_db_path": str(tmp_path / "nope.db")}
    parsed = json.loads(stats_module.show(config, as_json=True))
    assert parsed["total_commits"] == 0
    assert parsed["per_provider"] == []


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


def test_reset_empties_db(db_config):
    for _ in range(3):
        stats_module.record(
            config=db_config,
            kind="commit",
            provider="p",
            model="m",
            tokens_in=1,
            tokens_out=1,
            latency_ms=1,
        )

    db_path = Path(db_config["stats_db_path"])
    assert len(_read_all(db_path)) == 3

    removed = stats_module.reset(db_config)
    assert removed == 3
    assert _read_all(db_path) == []


def test_reset_no_db_returns_zero(tmp_path):
    config = {"stats": True, "stats_db_path": str(tmp_path / "absent.db")}
    assert stats_module.reset(config) == 0


# ---------------------------------------------------------------------------
# Privacy regression — no message/diff/path content can be persisted
# ---------------------------------------------------------------------------


def test_privacy_schema_has_no_message_diff_or_path_columns(db_config):
    stats_module.record(
        config=db_config,
        kind="commit",
        provider="p",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
    )
    db_path = Path(db_config["stats_db_path"])
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    finally:
        conn.close()

    forbidden = {"message", "diff", "content", "filename", "file"}
    assert cols.isdisjoint(
        forbidden
    ), f"events table contains privacy-sensitive columns: {cols & forbidden}"


# ---------------------------------------------------------------------------
# Extended schema (v2): kind variants, repo, settings snapshot, time_ms
# ---------------------------------------------------------------------------


def test_record_persists_kind_variants(db_config):
    for kind in ("commit", "amend", "squash", "pr"):
        stats_module.record(
            config=db_config,
            kind=kind,
            provider="p",
            model="m",
            tokens_in=1,
            tokens_out=1,
            latency_ms=1,
        )

    rows = _read_rows(Path(db_config["stats_db_path"]), "kind")
    kinds = sorted(r["kind"] for r in rows)
    assert kinds == ["amend", "commit", "pr", "squash"]


def test_record_persists_repo_name(db_config):
    stats_module.record(
        config=db_config,
        kind="commit",
        provider="p",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
        repo="myproj",
    )
    rows = _read_rows(Path(db_config["stats_db_path"]), "repo")
    assert rows[0]["repo"] == "myproj"


def test_record_persists_latency_ms(db_config):
    stats_module.record(
        config=db_config,
        kind="commit",
        provider="p",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=789,
    )
    rows = _read_rows(Path(db_config["stats_db_path"]), "latency_ms")
    assert rows[0]["latency_ms"] == 789


def test_record_persists_settings_snapshot(db_config):
    stats_module.record(
        config=db_config,
        kind="commit",
        provider="p",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
        language="de",
        style="casual",
        emoji=False,
        temperature=0.7,
        prompt_file="~/.config/cai/commit_prompt.md",
    )
    rows = _read_rows(Path(db_config["stats_db_path"]))
    row = rows[0]
    assert row["language"] == "de"
    assert row["style"] == "casual"
    assert row["emoji"] == 0
    assert row["temperature"] == pytest.approx(0.7)
    assert row["prompt_file"] == "~/.config/cai/commit_prompt.md"


def test_record_settings_default_to_null(db_config):
    """Unspecified settings stay NULL — they are not silently filled in."""
    stats_module.record(
        config=db_config,
        kind="commit",
        provider="p",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
    )
    rows = _read_rows(Path(db_config["stats_db_path"]))
    row = rows[0]
    assert row["repo"] is None
    assert row["language"] is None
    assert row["style"] is None
    assert row["emoji"] is None
    assert row["temperature"] is None
    assert row["prompt_file"] is None
    assert row["time_ms"] is None


def test_record_returns_event_id(db_config):
    """The returned id lets callers patch the row later (e.g. set_time_ms)."""
    event_id = stats_module.record(
        config=db_config,
        kind="commit",
        provider="p",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
    )
    assert isinstance(event_id, int)
    assert event_id > 0


def test_record_returns_none_when_disabled(tmp_path):
    """No write → no row id."""
    config = {"stats": False, "stats_db_path": str(tmp_path / "x.db")}
    assert (
        stats_module.record(
            config=config,
            kind="commit",
            provider="p",
            model="m",
            tokens_in=1,
            tokens_out=1,
            latency_ms=1,
        )
        is None
    )


def test_set_time_ms_updates_existing_event(db_config):
    event_id = stats_module.record(
        config=db_config,
        kind="commit",
        provider="p",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
    )
    stats_module.set_time_ms(db_config, event_id, 4242)

    rows = _read_rows(Path(db_config["stats_db_path"]), "time_ms")
    assert rows[0]["time_ms"] == 4242


def test_set_time_ms_noop_with_missing_id(db_config):
    """A None event_id (writer disabled or failed) must not raise or
    touch the table."""
    stats_module.set_time_ms(db_config, None, 100)
    # No DB created, no exception — that's the contract.


def test_set_time_ms_noop_when_disabled(tmp_path):
    """When stats are disabled, set_time_ms is a clean no-op even if a
    DB happens to exist on disk."""
    db = tmp_path / "x.db"
    enabled = {"stats": True, "stats_db_path": str(db)}
    event_id = stats_module.record(
        config=enabled,
        kind="commit",
        provider="p",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
    )

    disabled = {"stats": False, "stats_db_path": str(db)}
    stats_module.set_time_ms(disabled, event_id, 999)

    rows = _read_rows(db, "time_ms")
    assert rows[0]["time_ms"] is None


def test_aggregate_counts_each_kind(db_config):
    """`_aggregate` exposes per-kind totals so the summary doesn't lump
    squash/pr/amend under 'commit' anymore."""
    plan = {"commit": 2, "amend": 1, "squash": 3, "pr": 4}
    for kind, n in plan.items():
        for _ in range(n):
            stats_module.record(
                config=db_config,
                kind=kind,
                provider="p",
                model="m",
                tokens_in=1,
                tokens_out=1,
                latency_ms=1,
            )

    summary = json.loads(stats_module.show(db_config, as_json=True))
    assert summary["total_commits"] == 2
    assert summary["total_amends"] == 1
    assert summary["total_squashes"] == 3
    assert summary["total_prs"] == 4


# ---------------------------------------------------------------------------
# SQLite-missing handling
# ---------------------------------------------------------------------------


def test_record_silently_disabled_when_sqlite_missing(monkeypatch, db_config):
    """If sqlite isn't available, record() must be a clean no-op
    (no exception, no DB created)."""
    monkeypatch.setattr(stats_module, "sqlite3", None)

    stats_module.record(
        config=db_config,
        kind="commit",
        provider="p",
        model="m",
        tokens_in=1,
        tokens_out=1,
        latency_ms=1,
    )

    assert not Path(db_config["stats_db_path"]).exists()


def test_show_when_sqlite_missing_returns_clear_message(monkeypatch, db_config):
    """The stats subcommand must explain why it's unavailable rather
    than returning empty output."""
    monkeypatch.setattr(stats_module, "sqlite3", None)

    msg = stats_module.show(db_config)
    assert "sqlite3" in msg
    assert "stats.enabled" in msg or "rebuild" in msg.lower()


def test_sqlite_missing_warning_logged_once(monkeypatch, caplog):
    """The first miss logs a clear warning; subsequent calls don't spam.

    With the lru-cached warn helper, the warning naturally fires exactly
    once per process — clearing the cache simulates a fresh process.
    """
    monkeypatch.setattr(stats_module, "sqlite3", None)
    stats_module._warn_sqlite_missing_once.cache_clear()

    caplog.set_level("WARNING")
    assert stats_module._sqlite_available() is False
    first = caplog.text.count("sqlite3 module is not available")
    stats_module._sqlite_available()
    second = caplog.text.count("sqlite3 module is not available")

    assert first == 1
    assert second == 1


# ---------------------------------------------------------------------------
# CLI override — --sql true/false threading
# ---------------------------------------------------------------------------


def test_apply_cli_overrides_sql_true_enables_writing():
    from git_cai_cli.core.config import apply_cli_overrides

    cfg: dict = {}
    apply_cli_overrides(cfg, sql_override=True)
    assert cfg["stats"] is True


def test_apply_cli_overrides_sql_false_disables_writing():
    from git_cai_cli.core.config import apply_cli_overrides

    cfg: dict = {"stats": True}
    apply_cli_overrides(cfg, sql_override=False)
    assert cfg["stats"] is False


def test_apply_cli_overrides_sql_none_preserves_config():
    from git_cai_cli.core.config import apply_cli_overrides

    cfg: dict = {"stats": True}
    apply_cli_overrides(cfg, sql_override=None)
    assert cfg["stats"] is True


# ---------------------------------------------------------------------------
# Startup logging — every run announces stats state and DB path
# ---------------------------------------------------------------------------


def test_log_stats_state_enabled_includes_db_path(caplog, tmp_path):
    """When stats are enabled, the run logs that fact AND the DB path
    so users always know where their analytics live."""
    from git_cai_cli.main import _log_stats_state

    config = {"stats": True, "stats_db_path": str(tmp_path / "x.db")}

    caplog.set_level("INFO")
    _log_stats_state(config)

    assert "Stats writing enabled" in caplog.text
    assert str(tmp_path / "x.db") in caplog.text


def test_log_stats_state_disabled_says_disabled(caplog):
    """When stats are off, the disabled state is also surfaced."""
    from git_cai_cli.main import _log_stats_state

    caplog.set_level("INFO")
    _log_stats_state({"stats": False})

    assert "Stats writing disabled" in caplog.text


def test_log_stats_state_uses_default_path_when_unset(caplog, monkeypatch):
    """If stats are enabled but no path override is set, the default
    ``~/.local/share/git-cai/stats.db`` is logged."""
    from git_cai_cli.main import _log_stats_state

    caplog.set_level("INFO")
    _log_stats_state({"stats": True})

    assert "Stats writing enabled" in caplog.text
    assert "stats.db" in caplog.text


# ---------------------------------------------------------------------------
# Stats wiring must be consistent across all modes (commit / squash / PR)
# ---------------------------------------------------------------------------


def test_squash_logs_stats_state(monkeypatch, caplog, tmp_path):
    """`git cai -s` must log the stats state and DB path just like
    `git cai`. Regression for the bug where squash silently bypassed
    the stats log line."""
    from git_cai_cli.core import squash as squash_module

    config = {
        "default": "openai",
        "stats": True,
        "stats_db_path": str(tmp_path / "x.db"),
    }

    monkeypatch.setattr(squash_module, "find_git_root", lambda: tmp_path)
    monkeypatch.setattr(squash_module, "_is_shallow_clone", lambda: False)
    monkeypatch.setattr(squash_module, "subprocess", squash_module.subprocess)

    # Make every other thing return early after the log line — we just
    # want to assert the stats state log fires.
    monkeypatch.setattr(squash_module, "load_config", lambda: dict(config))
    monkeypatch.setattr(squash_module, "apply_provider_overrides", lambda *a, **k: None)

    def fake_check_output(cmd, **kwargs):
        return ""

    monkeypatch.setattr(squash_module.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(squash_module, "load_token", lambda config=None: "tok")

    # After load_token, the rest of squash needs more mocks; raise to
    # short-circuit since we've already passed the log point.
    class _StopHere(Exception):
        pass

    def boom(*a, **kw):
        raise _StopHere()

    monkeypatch.setattr(squash_module, "CommitMessageGenerator", boom)

    caplog.set_level("INFO")
    try:
        squash_module.squash_branch()
    except _StopHere:
        pass

    assert "Stats writing enabled" in caplog.text
    assert str(tmp_path / "x.db") in caplog.text


def test_squash_sql_override_disables_writing(monkeypatch, tmp_path):
    """`git cai -s --sql false` must override a persisted `stats: true`
    just like the COMMIT path does."""
    from git_cai_cli.core import squash as squash_module

    captured_config = {}

    monkeypatch.setattr(squash_module, "find_git_root", lambda: tmp_path)
    monkeypatch.setattr(squash_module, "_is_shallow_clone", lambda: False)
    monkeypatch.setattr(
        squash_module,
        "load_config",
        lambda: {
            "default": "openai",
            "stats": True,
            "stats_db_path": str(tmp_path / "x.db"),
        },
    )
    monkeypatch.setattr(squash_module, "apply_provider_overrides", lambda *a, **k: None)

    def fake_check_output(cmd, **kwargs):
        return ""

    monkeypatch.setattr(squash_module.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(squash_module, "load_token", lambda config=None: "tok")

    class _StopHere(Exception):
        pass

    def capture_and_stop(token, config, provider, **kwargs):
        captured_config["stats"] = config.get("stats")
        raise _StopHere()

    monkeypatch.setattr(squash_module, "CommitMessageGenerator", capture_and_stop)

    try:
        squash_module.squash_branch(sql_override=False)
    except _StopHere:
        pass

    assert captured_config["stats"] is False


def test_pr_logs_stats_state(monkeypatch, caplog, tmp_path):
    """`git cai -r` must also log the stats state."""
    from git_cai_cli.core import pr as pr_module

    monkeypatch.setattr(pr_module, "find_git_root", lambda: tmp_path)
    monkeypatch.setattr(
        pr_module,
        "load_config",
        lambda: {"default": "openai", "stats": False},
    )
    monkeypatch.setattr(pr_module, "apply_provider_overrides", lambda *a, **k: None)
    monkeypatch.setattr(pr_module, "load_token", lambda config=None: "tok")

    class _StopHere(Exception):
        pass

    monkeypatch.setattr(
        pr_module, "detect_base_branch", lambda: (_ for _ in ()).throw(_StopHere())
    )

    caplog.set_level("INFO")
    try:
        pr_module.run_pr()
    except (_StopHere, Exception):
        pass

    assert "Stats writing disabled" in caplog.text
