import stat
from pathlib import Path
from unittest.mock import patch

import yaml
from git_cai_cli.core.config import (
    DEFAULT_CONFIG,
    TOKEN_TEMPLATE,
    _serialize_config,
    apply_cli_overrides,
    load_config,
    load_token,
    set_config_value,
)


def test_load_config_creates_fallback(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    fallback = tmp_path / "cai_config.yml"

    config = load_config(
        fallback_config_file=fallback,
        allowed_languages={"en"},
    )

    assert fallback.exists()

    # Runtime config keeps Path
    assert isinstance(config["load_tokens_from"], Path)

    # Prompt paths are set and files are created
    assert isinstance(config["prompt_file"], Path)
    assert isinstance(config["squash_prompt_file"], Path)
    assert config["prompt_file"].is_file()
    assert config["squash_prompt_file"].is_file()

    # Serialized file contains string
    data = yaml.safe_load(fallback.read_text())
    assert isinstance(data["load_tokens_from"], str)
    assert isinstance(data["prompt_file"], str)
    assert isinstance(data["squash_prompt_file"], str)


def test_load_config_normalizes_yaml_null_to_none_behavior(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    fallback = tmp_path / "cai_config.yml"

    cfg = {
        "default": "openai",
        "language": None,
        "style": None,
        "emoji": None,
        "openai": {"model": "x", "temperature": 0},
    }

    fallback.write_text(yaml.safe_dump(cfg))

    result = load_config(
        fallback_config_file=fallback,
        allowed_languages={"en"},
    )

    assert result["language"] == "none"
    assert result["style"] == "none"
    assert result["emoji"] == "none"


def test_load_config_reads_existing(tmp_path, monkeypatch):
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    fallback = tmp_path / "cai_config.yml"

    cfg = {
        "default": "openai",
        "language": "en",
        "style": "professional",
        "emoji": True,
        "openai": {"model": "x", "temperature": 0},
        "load_tokens_from": "/tmp/tokens.yml",
    }

    fallback.write_text(yaml.safe_dump(cfg))

    result = load_config(
        fallback_config_file=fallback,
        allowed_languages={"en"},
    )

    assert result["default"] == "openai"
    assert result["load_tokens_from"] == "/tmp/tokens.yml"


def test_repo_config_precedence(tmp_path):
    repo_cfg = tmp_path / "cai_config.yml"

    repo_data = {
        "default": "gemini",
        "language": "en",
        "style": "professional",
        "emoji": True,
        "gemini": {"model": "repo", "temperature": 0},
    }

    repo_cfg.write_text(yaml.safe_dump(repo_data))

    fallback = tmp_path / "fallback.yml"
    fallback.write_text(yaml.safe_dump(_serialize_config(DEFAULT_CONFIG)))

    with patch("git_cai_cli.core.config.find_git_root", return_value=tmp_path):
        config = load_config(fallback_config_file=fallback)

    # Repo config wins for every key it defines; `stats` is the one
    # exception and falls through to the home config.
    home_stats = config.pop("stats", None)
    assert config == repo_data
    assert home_stats == DEFAULT_CONFIG["stats"]
    # The default is the flat boolean, not a nested dict.
    assert home_stats is False


def test_load_token_creates_template(tmp_path):
    tokens = tmp_path / "tokens.yml"

    config = {
        "default": "openai",
        "load_tokens_from": tokens,
    }

    token = load_token(config=config)

    assert token is None
    assert tokens.exists()
    assert stat.S_IMODE(tokens.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR

    loaded = yaml.safe_load(tokens.read_text())
    assert loaded == TOKEN_TEMPLATE


def test_load_token_reads_existing(tmp_path):
    tokens = tmp_path / "tokens.yml"
    tokens.write_text(yaml.safe_dump({"openai": "abc123"}))

    config = {
        "default": "openai",
        "load_tokens_from": tokens,
    }

    token = load_token(config=config)

    assert token == "abc123"


def test_load_token_missing_key(tmp_path, caplog):
    tokens = tmp_path / "tokens.yml"
    tokens.write_text(yaml.safe_dump({"gemini": "xyz"}))

    config = {
        "default": "openai",
        "load_tokens_from": tokens,
    }

    result = load_token(config=config)

    assert result is None
    assert "Token for provider 'openai' not found" in caplog.text


def test_load_token_tokenless_provider_does_not_error(tmp_path, caplog):
    tokens = tmp_path / "tokens.yml"
    tokens.write_text(yaml.safe_dump({"openai": "abc123"}))

    config = {
        "default": "ollama",
        "load_tokens_from": tokens,
    }

    caplog.set_level("ERROR")
    result = load_token(config=config)

    assert result is None
    assert "Token for provider 'ollama' not found" not in caplog.text


def test_serialize_config_converts_path():
    cfg = {"x": Path("/tmp/test")}
    out = _serialize_config(cfg)

    assert out["x"] == "/tmp/test"
    assert isinstance(out["x"], str)


# -------------------------------------------
# Tests for new config keys
# -------------------------------------------


def test_default_config_contains_new_keys():
    """Verify DEFAULT_CONFIG includes token_logging, measure_time, and branch_context."""
    assert "token_logging" in DEFAULT_CONFIG
    assert "measure_time" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["token_logging"] is True
    assert DEFAULT_CONFIG["measure_time"] is False
    assert "branch_context" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["branch_context"] is False


def test_fresh_config_includes_new_keys(tmp_path, monkeypatch):
    """Verify a freshly generated config file includes new keys."""
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    fallback = tmp_path / "cai_config.yml"

    config = load_config(
        fallback_config_file=fallback,
        allowed_languages={"en"},
    )

    # Runtime config has the keys
    assert "token_logging" in config
    assert "measure_time" in config

    # Written YAML file also has the keys
    data = yaml.safe_load(fallback.read_text())
    assert "token_logging" in data
    assert "measure_time" in data


def test_old_config_without_new_keys_loads_fine(tmp_path, monkeypatch):
    """Verify an old config file without new keys loads without error."""
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    fallback = tmp_path / "cai_config.yml"

    # Write old-style config without new keys
    old_cfg = {
        "default": "openai",
        "language": "en",
        "style": "professional",
        "emoji": True,
        "openai": {"model": "gpt", "temperature": 0},
        "load_tokens_from": "/tmp/tokens.yml",
    }
    fallback.write_text(yaml.safe_dump(old_cfg))

    # Should load without error
    config = load_config(
        fallback_config_file=fallback,
        allowed_languages={"en"},
    )

    assert config["default"] == "openai"
    # New keys are absent — consumers must use .get() with defaults
    assert config.get("token_logging", False) is False
    assert config.get("measure_time", False) is False


# -------------------------------------------
# Tests for timeout / full_files / anthropic.max_tokens / ollama.timeout
# -------------------------------------------


def test_default_config_contains_timeout_and_full_files():
    """DEFAULT_CONFIG must define the new global keys."""
    assert DEFAULT_CONFIG["timeout"] == 30
    assert DEFAULT_CONFIG["full_files"] is False


def test_default_config_anthropic_max_tokens():
    """Anthropic block must default max_tokens to 32768."""
    assert DEFAULT_CONFIG["anthropic"]["max_tokens"] == 32768


def test_default_config_ollama_timeout():
    """Ollama block must default its own timeout to 300."""
    assert DEFAULT_CONFIG["ollama"]["timeout"] == 300


def test_fresh_config_contains_timeout_and_full_files(tmp_path, monkeypatch):
    """A freshly generated config file should include the new global keys."""
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    fallback = tmp_path / "cai_config.yml"

    load_config(
        fallback_config_file=fallback,
        allowed_languages={"en"},
    )

    data = yaml.safe_load(fallback.read_text())
    assert data["timeout"] == 30
    assert data["full_files"] is False
    assert data["anthropic"]["max_tokens"] == 32768
    assert data["ollama"]["timeout"] == 300


def test_set_config_value_round_trip_timeout(tmp_path, monkeypatch):
    """set_config_value should persist timeout and load_config should read it back."""
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "FALLBACK_CONFIG_FILE", tmp_path / "cai.yml")
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    # Seed a minimal config file
    (tmp_path / "cai.yml").write_text(
        yaml.safe_dump(
            {
                "default": "openai",
                "language": "en",
                "style": "professional",
                "emoji": True,
                "openai": {"model": "gpt", "temperature": 0},
                "load_tokens_from": "/tmp/tokens.yml",
                "prompt_file": "",
                "squash_prompt_file": "",
            }
        )
    )

    set_config_value("timeout", "45", force_home=True)

    cfg = load_config(
        fallback_config_file=tmp_path / "cai.yml",
        allowed_languages={"en"},
    )
    assert cfg["timeout"] == 45


def test_set_config_value_round_trip_full_files(tmp_path, monkeypatch):
    """set_config_value should parse 'true' to bool and persist it."""
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "FALLBACK_CONFIG_FILE", tmp_path / "cai.yml")
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    (tmp_path / "cai.yml").write_text(
        yaml.safe_dump(
            {
                "default": "openai",
                "language": "en",
                "style": "professional",
                "emoji": True,
                "openai": {"model": "gpt", "temperature": 0},
                "load_tokens_from": "/tmp/tokens.yml",
                "prompt_file": "",
                "squash_prompt_file": "",
            }
        )
    )

    set_config_value("full_files", "true", force_home=True)

    cfg = load_config(
        fallback_config_file=tmp_path / "cai.yml",
        allowed_languages={"en"},
    )
    assert cfg["full_files"] is True


def test_set_config_value_round_trip_anthropic_max_tokens(tmp_path, monkeypatch):
    """Dotted notation should update nested provider keys."""
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "FALLBACK_CONFIG_FILE", tmp_path / "cai.yml")
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    (tmp_path / "cai.yml").write_text(
        yaml.safe_dump(
            {
                "default": "anthropic",
                "language": "en",
                "style": "professional",
                "emoji": True,
                "anthropic": {"model": "claude", "temperature": 0},
                "load_tokens_from": "/tmp/tokens.yml",
                "prompt_file": "",
                "squash_prompt_file": "",
            }
        )
    )

    set_config_value("anthropic.max_tokens", "16384", force_home=True)

    cfg = load_config(
        fallback_config_file=tmp_path / "cai.yml",
        allowed_languages={"en"},
    )
    assert cfg["anthropic"]["max_tokens"] == 16384


def test_set_config_value_round_trip_ollama_timeout(tmp_path, monkeypatch):
    """Dotted notation should update ollama.timeout."""
    from git_cai_cli.core import config as config_module

    monkeypatch.setattr(config_module, "FALLBACK_CONFIG_FILE", tmp_path / "cai.yml")
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: None)

    (tmp_path / "cai.yml").write_text(
        yaml.safe_dump(
            {
                "default": "ollama",
                "language": "en",
                "style": "professional",
                "emoji": True,
                "ollama": {"model": "llama3.1", "temperature": 0},
                "load_tokens_from": "/tmp/tokens.yml",
                "prompt_file": "",
                "squash_prompt_file": "",
            }
        )
    )

    set_config_value("ollama.timeout", "600", force_home=True)

    cfg = load_config(
        fallback_config_file=tmp_path / "cai.yml",
        allowed_languages={"en"},
    )
    assert cfg["ollama"]["timeout"] == 600


# -------------------------------------------
# apply_cli_overrides
# -------------------------------------------


def test_apply_cli_overrides_all_absent_leaves_config_untouched():
    """When no flag is set, the config must be unchanged."""
    cfg = {"conventional": False, "branch_context": False, "timeout": 30}
    snapshot = dict(cfg)

    apply_cli_overrides(cfg)

    assert cfg == snapshot


def test_apply_cli_overrides_conventional_sets_true():
    cfg = {}
    apply_cli_overrides(cfg, conventional=True)
    assert cfg["conventional"] is True


def test_apply_cli_overrides_branch_context_sets_true():
    cfg = {}
    apply_cli_overrides(cfg, branch_context=True)
    assert cfg["branch_context"] is True


def test_apply_cli_overrides_timeout_writes_value():
    cfg = {"timeout": 30}
    apply_cli_overrides(cfg, timeout_override=90)
    assert cfg["timeout"] == 90


def test_apply_cli_overrides_timeout_none_preserves_existing():
    """timeout_override=None must NOT overwrite a configured timeout."""
    cfg = {"timeout": 45}
    apply_cli_overrides(cfg, timeout_override=None)
    assert cfg["timeout"] == 45


def test_apply_cli_overrides_full_files_true_sets_true():
    cfg = {"full_files": False}
    apply_cli_overrides(cfg, full_files_override=True)
    assert cfg["full_files"] is True


def test_apply_cli_overrides_none_preserves_true_config():
    """``None`` (no flag passed) must not clobber a config-level `full_files: true`."""
    cfg = {"full_files": True}
    apply_cli_overrides(cfg, full_files_override=None)
    assert cfg["full_files"] is True


def test_apply_cli_overrides_full_files_false_overrides_true_config():
    """Explicit ``--no-full-files`` must flip a persisted `full_files: true` off."""
    cfg = {"full_files": True}
    apply_cli_overrides(cfg, full_files_override=False)
    assert cfg["full_files"] is False


def test_apply_cli_overrides_conventional_false_overrides_true_config():
    """Explicit ``--no-conventional`` must flip a persisted `conventional: true` off."""
    cfg = {"conventional": True}
    apply_cli_overrides(cfg, conventional=False)
    assert cfg["conventional"] is False


def test_apply_cli_overrides_branch_context_false_overrides_true_config():
    """Explicit ``--no-branch`` must flip a persisted `branch_context: true` off."""
    cfg = {"branch_context": True}
    apply_cli_overrides(cfg, branch_context=False)
    assert cfg["branch_context"] is False


def test_apply_cli_overrides_all_flags_at_once():
    cfg = {}
    apply_cli_overrides(
        cfg,
        conventional=True,
        branch_context=True,
        timeout_override=75,
        full_files_override=True,
    )
    assert cfg == {
        "conventional": True,
        "branch_context": True,
        "timeout": 75,
        "full_files": True,
    }


# ---------------------------------------------------------------------------
# `git cai -g` must include the `stats` block in the generated config
# ---------------------------------------------------------------------------


def test_ordered_default_config_includes_stats():
    from git_cai_cli.core.config import DEFAULT_CONFIG, ordered_default_config

    ordered = ordered_default_config()
    assert "stats" in ordered
    assert ordered["stats"] == DEFAULT_CONFIG["stats"]
    assert ordered["stats"] is False


def test_generated_config_yaml_contains_stats(tmp_path):
    """The YAML written by `git cai -g` must surface the stats setting
    as a flat boolean so users see and can toggle it."""
    import yaml
    from git_cai_cli.core.options import CliManager

    manager = CliManager(package_name="git-cai-cli")
    target = tmp_path / "cai_config.yml"

    cwd = tmp_path
    import os

    prev = os.getcwd()
    os.chdir(cwd)
    try:
        manager.generate_config_here(filename=str(target))
    finally:
        os.chdir(prev)

    with target.open() as f:
        loaded = yaml.safe_load(f)

    assert "stats" in loaded
    assert loaded["stats"] is False


# ---------------------------------------------------------------------------
# stats fallback chain: repo > home > hardcoded false
# ---------------------------------------------------------------------------


def test_load_config_repo_without_stats_falls_back_to_home(tmp_path, monkeypatch):
    """If the repo config exists but lacks `stats`, load_config must
    pull the `stats` block from the home config so users don't lose
    their global analytics preference per-repo."""
    import yaml
    from git_cai_cli.core import config as config_module

    # Repo config — no `stats` key
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo_config = repo_dir / "cai_config.yml"
    repo_config.write_text(
        yaml.safe_dump(
            {
                "openai": {"model": "gpt-5.1", "temperature": 0},
                "default": "openai",
                "language": "en",
                "style": "professional",
                "emoji": True,
                "load_tokens_from": "/tmp/tokens.yml",
                "prompt_file": "",
                "squash_prompt_file": "",
            }
        )
    )

    # Home config — defines stats
    home_config = tmp_path / "home_cai_config.yml"
    home_config.write_text(yaml.safe_dump({"stats": True}))

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    result = config_module.load_config(fallback_config_file=home_config)

    assert result["stats"] is True


def test_load_config_repo_with_stats_does_not_fall_back(tmp_path, monkeypatch):
    """If the repo config defines `stats`, the repo value wins —
    home config is not consulted."""
    import yaml
    from git_cai_cli.core import config as config_module

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo_config = repo_dir / "cai_config.yml"
    repo_config.write_text(
        yaml.safe_dump(
            {
                "openai": {"model": "gpt-5.1", "temperature": 0},
                "default": "openai",
                "language": "en",
                "style": "professional",
                "emoji": True,
                "load_tokens_from": "/tmp/tokens.yml",
                "prompt_file": "",
                "squash_prompt_file": "",
                "stats": False,
            }
        )
    )

    home_config = tmp_path / "home_cai_config.yml"
    home_config.write_text(yaml.safe_dump({"stats": True}))

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    result = config_module.load_config(fallback_config_file=home_config)

    # Repo wins
    assert result["stats"] is False


def test_load_config_no_stats_anywhere_means_disabled(tmp_path, monkeypatch):
    """Repo config has no stats, home config has no stats — the
    hardcoded default kicks in via stats.is_enabled."""
    import yaml
    from git_cai_cli.core import config as config_module
    from git_cai_cli.core import stats as stats_module

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo_config = repo_dir / "cai_config.yml"
    repo_config.write_text(
        yaml.safe_dump(
            {
                "openai": {"model": "gpt-5.1", "temperature": 0},
                "default": "openai",
                "language": "en",
                "style": "professional",
                "emoji": True,
                "load_tokens_from": "/tmp/tokens.yml",
                "prompt_file": "",
                "squash_prompt_file": "",
            }
        )
    )

    home_config = tmp_path / "home_cai_config.yml"  # absent on disk

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(config_module, "_find_repo_config", lambda: repo_config)

    result = config_module.load_config(fallback_config_file=home_config)

    # No `stats` key in repo, no home file → key absent in loaded config
    assert "stats" not in result
    # Hardcoded default → False
    assert stats_module.is_enabled(result) is False


def test_load_home_stats_returns_none_when_home_missing(tmp_path):
    from git_cai_cli.core.config import _load_home_stats

    assert _load_home_stats(tmp_path / "absent.yml") is None


def test_load_home_stats_returns_none_when_block_missing(tmp_path):
    import yaml
    from git_cai_cli.core.config import _load_home_stats

    home = tmp_path / "home.yml"
    home.write_text(yaml.safe_dump({"language": "en"}))

    assert _load_home_stats(home) is None


def test_load_home_stats_returns_dict_when_present(tmp_path):
    """When home config defines `stats` and/or `stats_db_path`, the
    helper returns a dict with whichever keys are set so the caller
    can merge them."""
    import yaml
    from git_cai_cli.core.config import _load_home_stats

    home = tmp_path / "home.yml"
    home.write_text(yaml.safe_dump({"stats": True, "stats_db_path": "/tmp/x.db"}))

    block = _load_home_stats(home)
    assert block == {"stats": True, "stats_db_path": "/tmp/x.db"}


def test_load_home_stats_partial_returns_only_present_keys(tmp_path):
    """If only `stats` (or only `stats_db_path`) is in home, only that
    key is returned."""
    import yaml
    from git_cai_cli.core.config import _load_home_stats

    home = tmp_path / "home.yml"
    home.write_text(yaml.safe_dump({"stats_db_path": "/tmp/x.db"}))

    block = _load_home_stats(home)
    assert block == {"stats_db_path": "/tmp/x.db"}
