# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**git-cai** — A Python CLI tool that uses LLMs to generate git commit messages. Installed as `git-cai` (invoked as `git cai`). Supports 8 LLM providers: OpenAI, Anthropic, Gemini, Groq, xAI, Mistral, DeepSeek, and Ollama (local).

## Common Commands

```bash
uv sync --dev          # Install dependencies (including dev deps)
make test              # Run all tests (uv run pytest)
make lint              # Branch name check + MegaLinter (requires npx + Docker)
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

- **config.py** — Config loading. Repo config is **authoritative** (not merged with home config): repo `cai_config.yml` > home `~/.config/cai/cai_config.yml` > bundled `DEFAULT_CONFIG`
- **llm.py** — `CommitMessageGenerator` class with `_dispatch_generate()` routing to
  provider-specific methods. OpenAI/DeepSeek use the OpenAI SDK;
  Anthropic/Gemini/Groq/xAI/Mistral use direct HTTP via `requests`; Ollama uses its
  local HTTP API and auto-starts the server if needed
- **gitutils.py** — Git operations (find root, diff with `.caiignore` support, commit)
- **validate.py** — Config key/structure validation, language/style validation, and LLM call wrapper that converts auth errors to user-facing messages
- **squash.py** — Squash commit workflow (stage → generate summary → editor → reset + commit)
- **options.py** — `CliManager` orchestrating CLI operations

### Prompt Fallback Chain

File (repo-level) → File (user home `~/.config/cai/`) → Hardcoded string (`prompts_fallback.py`)

### Tokens

API tokens loaded from `~/.config/cai/tokens.yml`. Ollama is in `TOKENLESS_PROVIDERS` (no key needed).

## Testing

- Unit tests in `tests/unit/`, integration tests in `tests/integration/`
- Uses `requests-mock` for HTTP mocking
- `tests/conftest.py` inserts `src/` into `sys.path` so local source wins over any installed package
- CI tests against Python 3.10–3.14; CI copies `.github/ci/cai_config.ci.yml` and `tokens.ci.yml` to `~/.config/cai/`

## Build & Versioning

- Package manager: **uv**
- Version: auto-generated from git tags via `setuptools-scm` → `src/git_cai_cli/_version.py`
- Do not edit `_version.py` manually

## Branch Naming

Enforced by CI and `make lint` via `.linters/check_git_branch_name.sh`:

```text
master | (feature|fix|hotfix|chore|refactor|test|docs)/<lowercase-slug>
```
