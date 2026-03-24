# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**git-cai** — A Python CLI tool that uses LLMs to generate git commit messages. Installed as `git-cai` (invoked as `git cai`). Supports 8 LLM providers: OpenAI, Anthropic, Gemini, Groq, xAI, Mistral, DeepSeek, and Ollama (local).

## Common Commands

```bash
make test              # Run all tests (uv run pytest)
make lint              # Branch name check + MegaLinter
make lint-fix          # Auto-fix lint issues
make clean             # Clean uv cache and .venv

# Single test file
uv run pytest tests/unit/test_llm.py -v

# Single test function
uv run pytest tests/unit/test_llm.py::test_function_name -v
```

## Architecture

Entry point: `src/git_cai_cli/cli/cli.py` (Typer app) → `main.py` (dispatcher)

### Modes (cli/modes.py)

- **COMMIT** (default): git diff → LLM → user edits → commit
- **LIST**: show supported languages/styles/editors
- **SQUASH**: squash branch commits with generated summary
- **UPDATE**: check PyPI for updates

### Core Modules (core/)

- **config.py** — Config loading with precedence: repo `cai_config.yml` > home `~/.config/cai/cai_config.yml` > bundled defaults
- **llm.py** — `CommitMessageGenerator` class with `_dispatch_generate()` routing to provider-specific methods (`generate_openai()`, `generate_anthropic()`, etc.)
- **gitutils.py** — Git operations (find root, diff with `.caiignore` support, commit)
- **validate.py** — Config and LLM call validation
- **squash.py** — Squash commit workflow (stage → generate summary → editor → reset + commit)
- **options.py** — `CliManager` orchestrating CLI operations

### Prompt Fallback Chain

File (repo-level) → File (user home) → Bundled package (`defaults/*.md`) → Hardcoded string (`prompts_fallback.py`)

### Tokens

API tokens loaded from `~/.config/cai/tokens.yml`. Ollama is in `TOKENLESS_PROVIDERS` (no key needed).

## Testing

- Unit tests in `tests/unit/`, integration tests in `tests/integration/`
- Uses `requests-mock` for HTTP mocking
- CI tests against Python 3.10–3.14

## Build & Versioning

- Package manager: **uv**
- Version: auto-generated from git tags via `setuptools-scm` → `src/git_cai_cli/_version.py`
- Do not edit `_version.py` manually
