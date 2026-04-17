# cai

![Python](https://img.shields.io/pypi/pyversions/git-cai-cli)
[![MegaLinter](https://img.shields.io/github/actions/workflow/status/thorstenfoltz/cai/python-tests.yml?label=MegaLinter)](https://github.com/thorstenfoltz/cai/actions/workflows/python-tests.yml)
![License](https://img.shields.io/github/license/thorstenfoltz/cai?label=License)
[![CI](https://img.shields.io/github/actions/workflow/status/thorstenfoltz/cai/python-tests.yml?label=Tests)](https://github.com/thorstenfoltz/cai/actions/workflows/python-tests.yml)

cai is a Git extension that automates the creation of commit messages.  
Simply run `git cai` to generate a meaningful, context-aware commit message based on the changes in your repository.

cai uses a Large Language Model (LLM) to analyse diffs and new files, producing concise and informative commit messages.

Currently supported providers:

- OpenAI
- Gemini
- Anthropic
- Groq
- xAI
- Mistral
- DeepSeek
- Ollama (local)

---

## Prerequisites

- Python 3.10 or higher
- [pipx](https://pypi.org/project/pipx/)
- Either:
  - Ollama installed and running locally, or
  - An API key for at least one of the following providers:
  - OpenAI
  - Gemini (free tier available)
  - Anthropic
  - Groq (free tier available)
  - xAI
  - Mistral
  - DeepSeek

---

## Features

- Automatically detects added, modified, and deleted files
- Generates meaningful, context-aware commit messages using an LLM
- Seamless integration with Git
- Supports multiple LLM providers and models
- Global configuration with per-repository overrides
- Repository-specific language, style, and model selection
- Amend the last commit message with a regenerated one
- Conventional Commits format support
- Change configuration from the command line
- Optional commit squashing with automatic summary generation (all, last N, or up to a specific commit)
- List providers, models, active config, and file paths
- Token usage logging for API calls
- Branch name as LLM context
- Extra context for the LLM
- Generation time measurement
- Shell completion for bash, zsh, and fish

---

## Installation

Install cai using pipx:

```sh
pipx install git-cai-cli
```

Ensure that pipx binaries are available in your PATH:

```sh
pipx ensurepath
```

**Restart your shell after installation.**

If you are running Arch Linux or an Arch-based distribution such as EndeavourOS, CachyOS, etc.,
you can install the package from the AUR using a package manager like Paru.

```sh
paru -S cai
```

---

## Usage

Once installed, cai works like a standard Git command:

```sh
git cai
```

cai uses the output of `git diff` to generate a commit message or, if optional, with the complete file content.
The generated message is opened in your configured Git editor, allowing you to review or edit it before committing.

In short: it behaves like `git commit`, but the commit message is pre-filled.

### Ignoring files

To exclude specific files or directories from being considered when generating commit messages, create a `.caiignore` file in the root of your repository.

- Files listed in `.gitignore` are **always excluded**
- `.caiignore` is intended for tracked files that should **not** influence commit messages

The syntax is identical to `.gitignore`.

---

## Configuration

On first execution, cai automatically creates the base configuration in your home directory.

- Global configuration:  
  ~/.config/cai/cai_config.yml

- API tokens:  
  ~/.config/cai/tokens.yml

It also creates three Markdown prompt files:

- Default commit prompt:  
  ~/.config/cai/commit_prompt.md
- Default squash prompt:  
  ~/.config/cai/squash_prompt.md
- Default full-files prompt (used with `-F` / `--full-files`):  
  ~/.config/cai/full_files_prompt.md

Don't be scared the first run will show an error. It only misses a token.
Add your provider API keys to `tokens.yml`. Once configured, cai will reuse them automatically.
Optional for each repository a file containing tokens can be set.
Set your preferred LLM in `cai_config.yml` (Groq by default).

If you want to use Ollama, install it, set `default: ollama` and configure the `ollama:` block (model/temperature). Ollama is automatically started when used.

### Custom prompts (Markdown)

The generated commit message is guided by prompt files.

- By default, `cai_config.yml` points to the auto-created prompt files in `~/.config/cai/`.
- To use your own prompts in a repository, generate templates at the root of the repository:

```sh
git cai -p
```

This creates:

- `commit_prompt.md`
- `squash_prompt.md`
- `full_files_prompt.md`
  so the LLM knows the full working-tree contents of each changed file are
  attached and can reason about *why* each edit was made, not just what
  the diff shows.

Then set `prompt_file`, `squash_prompt_file`, and/or `full_files_prompt_file` in your `cai_config.yml` (also repo) to point to those files.

### Repository-specific configuration

Each repository can be configured independently.

If a `cai_config.yml` file exists in the root of a repository, cai will use it instead of the global configuration.  
This allows different projects to use different providers, models, languages, and styles.

Examples of per-repository customization:

- Different LLM providers or models
- Different commit message languages
- Different writing styles or tones
- Emojis enabled or disabled per project

To create a repository-specific configuration:

```sh
cp ~/.config/cai/cai_config.yml .
```

Modify the copied file as needed.
As an alternative execute:

```sh
git cai -g
```

### Available configuration options

- `default` – default LLM provider
- `model` – model to use for the selected provider  
  (note: not all models may be compatible)
- `temperature` – controls how creative the generated messages are
- `language` – language used for commit messages
- `style` – tone or style of the commit message
- `emoji` – enable or disable emojis
- `load_tokens_from` – path to the file where API tokens are stored
- `prompt_file` - path to the file where the prompt for the commit is stored
- `squash_prompt_file` - path to the file where the prompt for the squash is stored
- `full_files_prompt_file` - path to the prompt used when `-F` / `--full-files` attaches full file contents
- `full_files` – attach always the full working-tree contents of affected files alongside the diff
- `timeout` – HTTP timeout for LLM calls in seconds
- `branch_context` – include current branch name as LLM context
- `conventional` – use Conventional Commits format
- `token_logging` – log token usage after each LLM call
- `measure_time` – log generation time

---

## CLI

In addition to `git cai`, the following options are available:

- `-A`, `--amend` – regenerate and amend the last commit message
- `-a`, `--all` – stage all tracked modified and deleted files
- `-b`, `--branch` – include current branch name as context for the LLM
- `-C`, `--conventional` – use Conventional Commits format (`type(scope): description`)
- `-c`, `--crazy` – Trust the LLM and commit without checking
- `-d`, `--debug` – enable debug logging
- `-F`, `--full-files` – attach the full contents of affected files alongside the diff (uses `full_files_prompt.md`)
- `-f`, `--files` `PATH` – limit the diff (and full-file content, if enabled) to PATH; repeat for multiple files
- `-g`, `--generate-config` – generate the default `cai_config.yml` in the current directory
- `-H`, `--set-home` – set a config value in home config (`key=value`), always targets `~/.config/cai/`
- `-h`, `--help` – show help and available commands
- `-i`, `--install-completion` – install shell completion for bash, zsh, or fish
- `-l`, `--list` – list available information (`config`, `editor`, `language`, `model`, `path`, `provider`, `style`)
- `-m`, `--model` – override the model for this invocation (requires `-P`)
- `-p`, `--generate-prompts` – generate default `commit_prompt.md` and `squash_prompt.md` in the current directory (for customization)
- `-P`, `--provider` – override the LLM provider for this invocation
- `-S`, `--set` – set a config value (`key=value`) in repo config (requires existing repo config)
- `-s`, `--squash` `[N|HASH]` – squash commits on the current branch and summarize them. Without argument: squash all since branch checkout. With a number: squash the last N commits. With a commit hash: squash up to and including that commit
- `-T`, `--timeout` `SECONDS` – HTTP timeout for this invocation (overrides config)
- `-t`, `--time` – measure and log commit message generation time
- `-x`, `--context` – provide extra context for the LLM (e.g. ticket number, reason for change)
- `-u`, `--update` – check for updates
- `-v`, `--version` – show the installed version

## Examples

### Amend

To regenerate the last commit message and amend it:

```sh
git cai -A
```

This reads the diff from the most recent commit, sends it to the LLM, and opens the editor for review.
Use with `-c` to amend immediately without the editor: `git cai -A -c`.

### Conventional Commits

To generate commit messages in [Conventional Commits](https://www.conventionalcommits.org/) format:

```sh
git cai -C
```

This enforces the `type(scope): description` structure. Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. Use `!` after the type/scope for breaking changes.

To enable it permanently:

```sh
git cai -S conventional=true
```

### Attaching full file contents and restricting to specific files

Sometimes the diff alone is too little context for the LLM to explain *why* a
change was made. `-F` / `--full-files` attaches the complete working-tree
contents of every staged file alongside the diff and switches to a dedicated
prompt (`full_files_prompt.md`) that instructs the LLM to use that full
context to infer intent rather than just describe the mechanical edit.

```sh
git cai -F                         # attach full contents of all staged files
git cai -F -f src/foo.py -f src/bar.py   # only these files
git cai -f docs/README.md          # restrict diff to one file (no full files)
```

Both flags log the affected files at INFO level as paths relative to the
repository root, so you can see exactly what ends up in the prompt — binaries,
deleted files, and paths matched by `.caiignore` are filtered out and skipped.

Persist the default:

```sh
git cai -S full_files=true
```

### Changing configuration from the CLI

Instead of editing YAML files manually, use `--set` or `--set-home` to update config values.

`--set` (`-S`) targets the **repo config** (requires an existing `cai_config.yml` in the repo root):

```sh
git cai -S default=anthropic           # change the default provider
git cai -S emoji=false                 # disable emojis
git cai -S groq.model=llama-3.3-70b    # nested key (dot notation)
git cai -S openai.temperature=0.7      # set temperature as float
```

If no repo config exists, an error is shown. Use `git cai -g` to create one first.

`--set-home` (`-H`) always targets the **home (default) config** (`~/.config/cai/`):

```sh
git cai -H language=de
git cai -H emoji=false
```

---

## License

This project is licensed under the MIT License.
