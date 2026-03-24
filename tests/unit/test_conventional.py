"""
Unit tests for the --conventional feature.
"""

from git_cai_cli.core.config import DEFAULT_CONFIG
from git_cai_cli.core.llm import CommitMessageGenerator


def _make_generator(conventional=False):
    config = {
        "openai": {"model": "gpt-5.1", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "conventional": conventional,
    }
    return CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="openai",
    )


def test_conventional_instruction_disabled():
    """When conventional is False, no instruction should be returned."""
    gen = _make_generator(conventional=False)
    assert gen._conventional_instruction() == ""


def test_conventional_instruction_enabled():
    """When conventional is True, instruction should contain format rules."""
    gen = _make_generator(conventional=True)
    instruction = gen._conventional_instruction()
    assert "Conventional Commits" in instruction
    assert "<type>(<optional scope>): <description>" in instruction
    assert "feat" in instruction
    assert "fix" in instruction
    assert "refactor" in instruction
    assert "breaking changes" in instruction.lower()


def test_conventional_included_in_config_instructions():
    """When conventional is True, _config_instructions should include it."""
    gen = _make_generator(conventional=True)
    instructions = gen._config_instructions()
    assert "Conventional Commits" in instructions


def test_conventional_not_in_config_instructions_when_disabled():
    """When conventional is False, _config_instructions should not include it."""
    gen = _make_generator(conventional=False)
    instructions = gen._config_instructions()
    assert "Conventional Commits" not in instructions


def test_conventional_in_commit_prompt():
    """_build_commit_prompt should include conventional instruction when enabled."""
    gen = _make_generator(conventional=True)
    prompt = gen._build_commit_prompt()
    assert "Conventional Commits" in prompt


def test_conventional_in_squash_prompt():
    """_build_squash_prompt should include conventional instruction when enabled."""
    gen = _make_generator(conventional=True)
    prompt = gen._build_squash_prompt()
    assert "Conventional Commits" in prompt


def test_default_config_contains_conventional():
    """DEFAULT_CONFIG should include conventional key set to False."""
    assert "conventional" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["conventional"] is False
