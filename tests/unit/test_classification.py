"""Unit tests for mixed code+docs classification guidance (#37)."""

from unittest.mock import patch

from git_cai_cli.core.gitutils import classify_changed_paths, paths_from_diff
from git_cai_cli.core.llm import CommitMessageGenerator


def _gen():
    config = {
        "openai": {"model": "x", "temperature": 0},
        "default": "openai",
        "language": "none",
        "style": "none",
        "emoji": None,
    }
    return CommitMessageGenerator(token="fake", config=config, default_model="openai")


# ---- gitutils helpers ----


def test_classify_changed_paths_counts():
    assert classify_changed_paths(["src/a.py", "docs/x.md", "README.md", "b.js"]) == (
        2,
        2,
    )


def test_paths_from_diff_reads_diff_git_headers():
    diff = (
        "diff --git a/src/a.py b/src/a.py\n+x\ndiff --git a/docs/y.md b/docs/y.md\n+y"
    )
    assert paths_from_diff(diff) == ["src/a.py", "docs/y.md"]


# ---- instruction selection ----


def test_instruction_present_for_mixed():
    gen = _gen()
    gen._classification_counts = (3, 2)
    assert "non-documentation" in gen._classification_instruction()


def test_instruction_empty_for_code_only():
    gen = _gen()
    gen._classification_counts = (3, 0)
    assert gen._classification_instruction() == ""


def test_instruction_empty_for_docs_only():
    gen = _gen()
    gen._classification_counts = (0, 2)
    assert gen._classification_instruction() == ""


# ---- end-to-end through prompt assembly ----


def test_generate_includes_classification_for_mixed_diff():
    gen = _gen()
    mixed = "diff --git a/src/a.py b/src/a.py\n+code\ndiff --git a/docs/x.md b/docs/x.md\n+docs\n"
    with patch.object(gen, "_dispatch_generate", return_value="msg") as disp:
        gen.generate(mixed)
    assert "non-documentation" in disp.call_args.kwargs["system_prompt"]


def test_generate_omits_classification_for_code_only_diff():
    gen = _gen()
    code = "diff --git a/src/a.py b/src/a.py\n+code\n"
    with patch.object(gen, "_dispatch_generate", return_value="msg") as disp:
        gen.generate(code)
    assert "non-documentation" not in disp.call_args.kwargs["system_prompt"]


def test_pr_prompt_includes_classification_for_mixed_files():
    gen = _gen()
    with patch.object(gen, "_dispatch_generate", return_value="msg") as disp:
        gen.generate_pr_description("commit log", "src/a.py\ndocs/x.md")
    assert "non-documentation" in disp.call_args.kwargs["system_prompt"]
