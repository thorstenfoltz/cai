"""
Unit tests for the --branch / -b feature (branch context).
"""

from git_cai_cli.core.config import DEFAULT_CONFIG
from git_cai_cli.core.llm import CommitMessageGenerator


def _make_generator(branch_context=False, branch_name=""):
    config = {
        "openai": {"model": "gpt-5.1", "temperature": 0},
        "language": "en",
        "default": "openai",
        "style": "professional",
        "emoji": True,
        "conventional": False,
        "branch_context": branch_context,
    }
    return CommitMessageGenerator(
        token="fake-token",
        config=config,
        default_model="openai",
        branch_name=branch_name or None,
    )


def test_branch_instruction_disabled():
    """When branch_context is False, no instruction should be returned."""
    gen = _make_generator(branch_context=False, branch_name="feature/auth")
    assert gen._branch_instruction() == ""


def test_branch_instruction_enabled_with_branch():
    """When enabled with branch_name in config, returns instruction containing the branch name."""
    gen = _make_generator(branch_context=True, branch_name="fix/login-timeout")
    instruction = gen._branch_instruction()
    assert "fix/login-timeout" in instruction
    assert "branch" in instruction.lower()


def test_branch_instruction_enabled_without_branch_name():
    """When enabled but no branch_name key, returns empty string."""
    gen = _make_generator(branch_context=True, branch_name="")
    assert gen._branch_instruction() == ""


def test_branch_included_in_config_instructions():
    """When enabled, _config_instructions should include branch text."""
    gen = _make_generator(branch_context=True, branch_name="feature/new-api")
    instructions = gen._config_instructions()
    assert "feature/new-api" in instructions


def test_branch_not_in_config_instructions_when_disabled():
    """When disabled, branch name should not appear in _config_instructions."""
    gen = _make_generator(branch_context=False, branch_name="feature/new-api")
    instructions = gen._config_instructions()
    assert "feature/new-api" not in instructions


def test_branch_in_commit_prompt():
    """_build_commit_prompt should include branch instruction when enabled."""
    gen = _make_generator(branch_context=True, branch_name="feat/user-auth")
    prompt = gen._build_commit_prompt()
    assert "feat/user-auth" in prompt


def test_branch_in_squash_prompt():
    """_build_squash_prompt should include branch instruction when enabled."""
    gen = _make_generator(branch_context=True, branch_name="feat/user-auth")
    prompt = gen._build_squash_prompt()
    assert "feat/user-auth" in prompt


def test_default_config_contains_branch_context():
    """DEFAULT_CONFIG should include branch_context key set to False."""
    assert "branch_context" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["branch_context"] is False


def test_branch_name_does_not_leak_into_config():
    """F1.6 regression: branch name is constructor state, not config.

    The previous implementation stuffed branch_name into the config
    dict so it surfaced in `git cai -l config` output. It must now live
    on the generator instance only.
    """
    gen = _make_generator(branch_context=True, branch_name="feat/x")
    assert "branch_name" not in gen.config
    assert gen.branch_name == "feat/x"
