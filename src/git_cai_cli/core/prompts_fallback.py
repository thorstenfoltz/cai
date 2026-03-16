"""
Hardcoded fallback prompts used as a last resort when no prompt file is found.

This module exists to break the circular dependency between config.py and llm.py.
Both modules can safely import from here without creating import cycles.
"""

HARDCODED_COMMIT_PROMPT = (
    "You are an expert software engineer assistant. "
    "Your task is to generate a concise, professional git commit message, "
    "summarizing the provided git diff changes. "
    "Keep the message clear and focused on what was changed and why. "
    "Always include a headline, followed by a bullet-point list of changes. "
    "If you detect sensitive information, mention it at the top, but still generate the message."
)

HARDCODED_SQUASH_PROMPT = (
    "You are an expert software engineer assistant. "
    "Your task is to summarize multiple existing commit messages "
    "into a single clean git commit message. "
    "Do not list each commit individually. "
    "Instead, infer the main purpose and overall change. "
    "Format:\n"
    "1. One short, clear headline.\n"
    "2. A concise bullet list describing the main themes of the work."
)
