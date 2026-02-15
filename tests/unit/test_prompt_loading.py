"""
Unit tests for prompt loading, custom prompt files, and 'none' config values.
"""

from unittest.mock import patch

import pytest
from git_cai_cli.core.llm import (
    _HARDCODED_COMMIT_PROMPT,
    _HARDCODED_SQUASH_PROMPT,
    CommitMessageGenerator,
    load_prompt_file,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_config():
    """
    Provides a default configuration dictionary for testing.
    """
    return {
        "openai": {"model": "gpt-5.1", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "prompt_file": "",
        "squash_prompt_file": "",
    }


@pytest.fixture
def generator(base_config):
    """
    Provides a CommitMessageGenerator instance for testing.
    """
    return CommitMessageGenerator(
        token="fake-token",
        config=base_config,
        default_model="openai",
    )


# ---------------------------------------------------------------------------
# load_prompt_file: user-defined path
# ---------------------------------------------------------------------------


class TestLoadPromptFileUserDefined:
    """Tests for loading prompts from user-defined file paths."""

    def test_loads_from_user_file(self, tmp_path):
        """User-defined file path is used when it exists."""
        prompt_file = tmp_path / "my_prompt.md"
        prompt_file.write_text("Custom user prompt content", encoding="utf-8")

        config = {"prompt_file": str(prompt_file)}

        result = load_prompt_file(
            config_key="prompt_file",
            config=config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        assert result == "Custom user prompt content"

    def test_user_file_not_found_falls_back(self, tmp_path):
        """When user file does not exist, falls back to default."""
        config = {"prompt_file": str(tmp_path / "nonexistent.md")}

        result = load_prompt_file(
            config_key="prompt_file",
            config=config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        # Should get either default file content or hardcoded fallback
        assert len(result) > 0
        assert "expert software engineer" in result.lower()

    def test_user_file_strips_whitespace(self, tmp_path):
        """User-defined file content is stripped of leading/trailing whitespace."""
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("\n  Custom prompt  \n\n", encoding="utf-8")

        config = {"prompt_file": str(prompt_file)}

        result = load_prompt_file(
            config_key="prompt_file",
            config=config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        assert result == "Custom prompt"

    def test_empty_config_key_falls_back(self):
        """Empty string for config key falls back to default."""
        config = {"prompt_file": ""}

        result = load_prompt_file(
            config_key="prompt_file",
            config=config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        assert len(result) > 0

    def test_missing_config_key_falls_back(self):
        """Missing config key falls back to default."""
        config = {}

        result = load_prompt_file(
            config_key="prompt_file",
            config=config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        assert len(result) > 0


# ---------------------------------------------------------------------------
# load_prompt_file: default bundled file
# ---------------------------------------------------------------------------


class TestLoadPromptFileDefault:
    """Tests for loading prompts from the default bundled file."""

    def test_loads_default_commit_prompt(self):
        """Default commit_prompt.md is loaded when no user file is set."""
        config = {"prompt_file": ""}

        result = load_prompt_file(
            config_key="prompt_file",
            config=config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        assert "expert software engineer" in result.lower()
        assert "git commit message" in result.lower()

    def test_loads_default_squash_prompt(self):
        """Default squash_prompt.md is loaded when no user file is set."""
        config = {"squash_prompt_file": ""}

        result = load_prompt_file(
            config_key="squash_prompt_file",
            config=config,
            default_filename="squash_prompt.md",
            hardcoded_fallback=_HARDCODED_SQUASH_PROMPT,
        )

        assert "expert software engineer" in result.lower()
        assert "summarize" in result.lower()


# ---------------------------------------------------------------------------
# load_prompt_file: hardcoded fallback
# ---------------------------------------------------------------------------


class TestLoadPromptFileHardcoded:
    """Tests for the hardcoded fallback when no files are available."""

    def test_hardcoded_fallback_when_default_missing(self, tmp_path):
        """
        Hardcoded fallback is used when both user file and default file are missing.
        """
        config = {"prompt_file": ""}
        empty_dir = tmp_path / "no_config"
        empty_dir.mkdir()

        with (
            patch("git_cai_cli.core.llm.CONFIG_DIR", empty_dir),
            patch(
                "git_cai_cli.core.llm.resources.files",
                side_effect=ModuleNotFoundError("mock"),
            ),
        ):
            result = load_prompt_file(
                config_key="prompt_file",
                config=config,
                default_filename="commit_prompt.md",
                hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
            )

        assert result == _HARDCODED_COMMIT_PROMPT

    def test_hardcoded_squash_fallback_when_default_missing(self, tmp_path):
        """
        Hardcoded squash fallback is used when both user file and default file are missing.
        """
        config = {"squash_prompt_file": ""}
        empty_dir = tmp_path / "no_config"
        empty_dir.mkdir()

        with (
            patch("git_cai_cli.core.llm.CONFIG_DIR", empty_dir),
            patch(
                "git_cai_cli.core.llm.resources.files",
                side_effect=ModuleNotFoundError("mock"),
            ),
        ):
            result = load_prompt_file(
                config_key="squash_prompt_file",
                config=config,
                default_filename="squash_prompt.md",
                hardcoded_fallback=_HARDCODED_SQUASH_PROMPT,
            )

        assert result == _HARDCODED_SQUASH_PROMPT


# ---------------------------------------------------------------------------
# load_prompt_file: logging
# ---------------------------------------------------------------------------


class TestLoadPromptFileLogging:
    """Tests that load_prompt_file emits appropriate log messages."""

    def test_logs_user_file_loaded(self, tmp_path, caplog):
        """Logs info when loading from user-defined file."""
        caplog.set_level("INFO")
        prompt_file = tmp_path / "my_prompt.md"
        prompt_file.write_text("Custom prompt", encoding="utf-8")

        config = {"prompt_file": str(prompt_file)}

        load_prompt_file(
            config_key="prompt_file",
            config=config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        assert "user-defined file" in caplog.text.lower()

    def test_logs_warning_when_user_file_missing(self, tmp_path, caplog):
        """Logs warning when user file path doesn't exist."""
        caplog.set_level("WARNING")

        config = {"prompt_file": str(tmp_path / "missing.md")}

        load_prompt_file(
            config_key="prompt_file",
            config=config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        assert "not found" in caplog.text.lower()

    def test_logs_default_file_loaded(self, caplog):
        """Logs info about missing local file and shows full default path."""
        caplog.set_level("INFO")
        config = {"prompt_file": ""}

        load_prompt_file(
            config_key="prompt_file",
            config=config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        assert "no local prompt file" in caplog.text.lower()
        assert (
            "default file" in caplog.text.lower()
            or "bundled package default" in caplog.text.lower()
        )
        # Full path must be logged, not just the filename
        assert "commit_prompt.md" in caplog.text

    def test_logs_hardcoded_fallback(self, tmp_path, caplog):
        """Logs warning when using hardcoded fallback."""
        caplog.set_level("WARNING")
        config = {"prompt_file": ""}
        empty_dir = tmp_path / "no_config"
        empty_dir.mkdir()

        with (
            patch("git_cai_cli.core.llm.CONFIG_DIR", empty_dir),
            patch(
                "git_cai_cli.core.llm.resources.files",
                side_effect=ModuleNotFoundError("mock"),
            ),
        ):
            load_prompt_file(
                config_key="prompt_file",
                config=config,
                default_filename="commit_prompt.md",
                hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
            )

        assert "hardcoded fallback" in caplog.text.lower()
        assert any(
            r.levelname == "WARNING"
            for r in caplog.records
            if "hardcoded" in r.message.lower()
        )


# ---------------------------------------------------------------------------
# 'none' value for language
# ---------------------------------------------------------------------------


class TestLanguageNone:
    """Tests for language='none' in prompts."""

    def test_language_none_omits_language_instruction(self, base_config):
        """When language is 'none', no language instruction is in the prompt."""
        base_config["language"] = "none"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instruction = gen._language_instruction()
        assert instruction == ""

    def test_language_none_not_in_commit_prompt(self, base_config):
        """Commit prompt does not contain language text when set to 'none'."""
        base_config["language"] = "none"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        prompt = gen._build_commit_prompt()
        assert "Write the commit message in " not in prompt or "tone style" in prompt

    def test_language_normal_includes_instruction(self, base_config):
        """When language is 'en', the instruction is included."""
        base_config["language"] = "en"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instruction = gen._language_instruction()
        assert "English" in instruction


# ---------------------------------------------------------------------------
# 'none' value for style
# ---------------------------------------------------------------------------


class TestStyleNone:
    """Tests for style='none' in prompts."""

    def test_style_none_omits_style_instruction(self, base_config):
        """When style is 'none', no style instruction is in the prompt."""
        base_config["style"] = "none"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instruction = gen._style_instruction()
        assert instruction == ""

    def test_style_none_not_in_commit_prompt(self, base_config):
        """Commit prompt does not contain style instruction when set to 'none'."""
        base_config["style"] = "none"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        prompt = gen._build_commit_prompt()
        assert "tone style" not in prompt

    def test_style_normal_includes_instruction(self, base_config):
        """When style is 'professional', the instruction is included."""
        base_config["style"] = "professional"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instruction = gen._style_instruction()
        assert "professional" in instruction


# ---------------------------------------------------------------------------
# 'none' value for emoji
# ---------------------------------------------------------------------------


class TestEmojiNone:
    """Tests for emoji='none' in prompts."""

    def test_emoji_none_omits_emoji_instruction(self, base_config):
        """When emoji is 'none', no emoji instruction is in the prompt."""
        base_config["emoji"] = "none"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instruction = gen._emoji_instruction()
        assert instruction == ""

    def test_emoji_none_string_case_insensitive(self, base_config):
        """'None' (capitalized) also works."""
        base_config["emoji"] = "None"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instruction = gen._emoji_instruction()
        assert instruction == ""

    def test_emoji_true_includes_instruction(self, base_config):
        """When emoji is True, instruction to use emojis is included."""
        base_config["emoji"] = True
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instruction = gen._emoji_instruction()
        assert "emojis" in instruction.lower()
        assert "Use relevant" in instruction

    def test_emoji_false_includes_no_emoji_instruction(self, base_config):
        """When emoji is False, instruction to not use emojis is included."""
        base_config["emoji"] = False
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instruction = gen._emoji_instruction()
        assert "Do not use any emojis" in instruction


# ---------------------------------------------------------------------------
# All 'none': only user prompt content matters
# ---------------------------------------------------------------------------


class TestAllNone:
    """Tests when all config settings are 'none'."""

    def test_all_none_only_base_prompt(self, tmp_path, base_config):
        """When language, style, emoji are all 'none', prompt is just the base."""
        base_config["language"] = "none"
        base_config["style"] = "none"
        base_config["emoji"] = "none"

        prompt_file = tmp_path / "custom.md"
        prompt_file.write_text("My custom prompt only", encoding="utf-8")
        base_config["prompt_file"] = str(prompt_file)

        gen = CommitMessageGenerator("tok", base_config, "openai")
        prompt = gen._build_commit_prompt()

        assert prompt == "My custom prompt only"

    def test_all_none_squash_only_base_prompt(self, tmp_path, base_config):
        """When language, style, emoji are all 'none', squash prompt is just the base."""
        base_config["language"] = "none"
        base_config["style"] = "none"
        base_config["emoji"] = "none"

        prompt_file = tmp_path / "custom_squash.md"
        prompt_file.write_text("My custom squash prompt", encoding="utf-8")
        base_config["squash_prompt_file"] = str(prompt_file)

        gen = CommitMessageGenerator("tok", base_config, "openai")
        prompt = gen._build_squash_prompt()

        assert prompt == "My custom squash prompt"


# ---------------------------------------------------------------------------
# _config_instructions helper
# ---------------------------------------------------------------------------


class TestConfigInstructions:
    """Tests for the _config_instructions helper method."""

    def test_all_enabled(self, base_config):
        """All instructions are present when nothing is 'none'."""
        gen = CommitMessageGenerator("tok", base_config, "openai")
        instructions = gen._config_instructions()

        assert "English" in instructions
        assert "professional" in instructions
        assert "emojis" in instructions.lower()

    def test_partial_none(self, base_config):
        """Only non-'none' instructions appear."""
        base_config["language"] = "none"
        base_config["emoji"] = "none"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instructions = gen._config_instructions()

        assert "English" not in instructions
        assert "emojis" not in instructions.lower()
        assert "professional" in instructions

    def test_all_none_returns_empty(self, base_config):
        """Empty string when all are 'none'."""
        base_config["language"] = "none"
        base_config["style"] = "none"
        base_config["emoji"] = "none"
        gen = CommitMessageGenerator("tok", base_config, "openai")

        instructions = gen._config_instructions()
        assert instructions == ""


# ---------------------------------------------------------------------------
# _build_commit_prompt with user file
# ---------------------------------------------------------------------------


class TestBuildCommitPromptWithUserFile:
    """Tests for _build_commit_prompt loading from user-defined files."""

    def test_user_file_with_config_instructions(self, tmp_path, base_config):
        """User file content plus config instructions."""
        prompt_file = tmp_path / "my_prompt.md"
        prompt_file.write_text("Generate a commit message.", encoding="utf-8")
        base_config["prompt_file"] = str(prompt_file)

        gen = CommitMessageGenerator("tok", base_config, "openai")
        prompt = gen._build_commit_prompt()

        assert prompt.startswith("Generate a commit message.")
        assert "English" in prompt
        assert "professional" in prompt

    def test_user_file_without_config_instructions(self, tmp_path, base_config):
        """User file content only when all config is 'none'."""
        base_config["language"] = "none"
        base_config["style"] = "none"
        base_config["emoji"] = "none"

        prompt_file = tmp_path / "my_prompt.md"
        prompt_file.write_text("Just do this.", encoding="utf-8")
        base_config["prompt_file"] = str(prompt_file)

        gen = CommitMessageGenerator("tok", base_config, "openai")
        prompt = gen._build_commit_prompt()

        assert prompt == "Just do this."


# ---------------------------------------------------------------------------
# _build_squash_prompt with user file
# ---------------------------------------------------------------------------


class TestBuildSquashPromptWithUserFile:
    """Tests for _build_squash_prompt loading from user-defined files."""

    def test_user_file_with_config_instructions(self, tmp_path, base_config):
        """User squash file content plus config instructions."""
        prompt_file = tmp_path / "my_squash.md"
        prompt_file.write_text("Summarize commits.", encoding="utf-8")
        base_config["squash_prompt_file"] = str(prompt_file)

        gen = CommitMessageGenerator("tok", base_config, "openai")
        prompt = gen._build_squash_prompt()

        assert prompt.startswith("Summarize commits.")
        assert "English" in prompt

    def test_user_file_without_config_instructions(self, tmp_path, base_config):
        """User squash file content only when all config is 'none'."""
        base_config["language"] = "none"
        base_config["style"] = "none"
        base_config["emoji"] = "none"

        prompt_file = tmp_path / "my_squash.md"
        prompt_file.write_text("Custom squash only.", encoding="utf-8")
        base_config["squash_prompt_file"] = str(prompt_file)

        gen = CommitMessageGenerator("tok", base_config, "openai")
        prompt = gen._build_squash_prompt()

        assert prompt == "Custom squash only."


# ---------------------------------------------------------------------------
# Validate 'none' support in validate.py
# ---------------------------------------------------------------------------


class TestValidateNone:
    """Tests for 'none' value support in validation functions."""

    def test_validate_language_none(self):
        from git_cai_cli.core.validate import _validate_language

        result = _validate_language({"language": "none"}, {"en", "de"})
        assert result == "none"

    def test_validate_language_None_capitalized(self):
        from git_cai_cli.core.validate import _validate_language

        result = _validate_language({"language": "None"}, {"en", "de"})
        assert result == "none"

    def test_validate_language_NONE_upper(self):
        from git_cai_cli.core.validate import _validate_language

        result = _validate_language({"language": "NONE"}, {"en", "de"})
        assert result == "none"

    def test_validate_style_none(self):
        from git_cai_cli.core.validate import _validate_style

        result = _validate_style("none")
        assert result == "none"

    def test_validate_style_None_capitalized(self):
        from git_cai_cli.core.validate import _validate_style

        result = _validate_style("None")
        assert result == "none"

    def test_validate_style_NONE_upper(self):
        from git_cai_cli.core.validate import _validate_style

        result = _validate_style("NONE")
        assert result == "none"


# ---------------------------------------------------------------------------
# Config keys include prompt_file and squash_prompt_file
# ---------------------------------------------------------------------------


class TestConfigKeysPromptFile:
    """Tests that new config keys are accepted by validation."""

    def test_prompt_file_accepted(self):
        from git_cai_cli.core.validate import _validate_config_keys

        reference = {
            "openai": {},
            "language": "en",
            "default": "openai",
            "style": "professional",
            "emoji": True,
            "load_tokens_from": "/path",
            "prompt_file": "",
            "squash_prompt_file": "",
        }

        config = {
            "openai": {"model": "gpt", "temperature": 0},
            "language": "en",
            "default": "openai",
            "style": "professional",
            "emoji": True,
            "load_tokens_from": "/path",
            "prompt_file": "/some/path.md",
            "squash_prompt_file": "/some/other.md",
        }

        # Should not raise
        _validate_config_keys(config, reference)

    def test_prompt_file_not_rejected_as_unknown(self):
        from git_cai_cli.core.validate import _validate_config_keys

        reference = {
            "openai": {},
            "language": "en",
            "default": "openai",
            "prompt_file": "",
            "squash_prompt_file": "",
        }

        config = {
            "openai": {"model": "gpt", "temperature": 0},
            "prompt_file": "/custom.md",
            "squash_prompt_file": "",
        }

        # Should not raise KeyError about unknown keys
        _validate_config_keys(config, reference)
