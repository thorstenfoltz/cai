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
- Interactive `--init` wizard for first-time setup (provider, token, language, style)
- Repository-specific language, style, and model selection
- Amend the last commit message with a regenerated one
- Conventional Commits format support
- `Signed-off-by:` (DCO) trailer support via `--signoff`
- `--print` mode that emits the generated message to stdout for scripting
- Change configuration from the command line
- Optional commit squashing with automatic summary generation (all, last N, or up to a specific commit)
- Pull Request description generator (`--PR`) that summarizes the commits between the current branch and its base
- List providers, models, active config, and file paths
- Token usage logging for API calls
- Branch name as LLM context
- Extra context for the LLM
- Per-invocation overrides for temperature, style, language, and emoji
- Optional large-diff guard (`max_diff_bytes`) that truncates oversized diffs before sending
- Generation time measurement
- Local-only usage analytics (per-provider commits, tokens, latency) with opt-in SQLite storage
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

The fastest way to get started is the interactive wizard:

```sh
git cai --init     # or: git cai -I
```

It asks for a default provider, language, style, and emoji preference,
then collects the API key (input is hidden while you type). The wizard
writes `~/.config/cai/cai_config.yml` and, for providers that need one,
`~/.config/cai/tokens.yml` with mode `0600`. Existing entries for other
providers in `tokens.yml` are preserved. `--init` only writes home-scope
files — use `-g` / `--generate-config` to bootstrap a repo-level config.

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
- `max_diff_bytes` – maximum size (in UTF-8 bytes) of the diff/commit-log sent to the LLM; oversized input is truncated with a marker. `0` (default) means no limit
- `timeout` – HTTP timeout for LLM calls in seconds
- `branch_context` – include current branch name as LLM context
- `conventional` – use Conventional Commits format
- `token_logging` – log token usage after each LLM call
- `measure_time` – log generation time
- `pr_to_file` – when `--PR` is used, write the generated description to a Markdown file in the repo root instead of stdout (default `false`)
- `pr_file_name` – filename used when `pr_to_file` is `true` (default `PR_DESCRIPTION.md`)
- `pr_prompt_file` – optional path to a custom Markdown prompt for `--PR` (falls back to `~/.config/cai/pr_prompt.md`, then a built-in default)
- `stats` – opt in to local-only usage analytics (per-run row in a SQLite DB at `~/.local/share/git-cai/stats.db`); default `false`.
No diff content, commit messages, or file paths are stored — only metadata (provider, model, kind, repo name, token counts, latency, settings)
- `signoff` – append a `Signed-off-by:` trailer (built from git `user.name` / `user.email`) to every commit message; default `false`

---

## CLI

In addition to `git cai`, the following options are available:

- `-A`, `--amend` – regenerate and amend the last commit message
- `-a`, `--all` – stage all tracked modified and deleted files
- `-b`, `--branch` – include current branch name as context for the LLM
- `-C`, `--conventional` – use Conventional Commits format (`type(scope): description`)
- `-c`, `--crazy` – Trust the LLM and commit without checking
- `-d`, `--debug` – enable debug logging
- `-e`, `--temperature` `TEMPERATURE` – override the active provider's sampling temperature for this invocation (provider-scoped, like `-m`)
- `-F`, `--full-files` – attach the full contents of affected files alongside the diff (uses `full_files_prompt.md`)
- `-f`, `--files` `PATH` – limit the diff (and full-file content, if enabled) to PATH; repeat for multiple files
- `-g`, `--generate-config` – generate the default `cai_config.yml` in the current directory
- `-H`, `--set-home` – set a config value in home config (`key=value`), always targets `~/.config/cai/`
- `-h`, `--help` – show help and available commands
- `-I`, `--init` – interactive setup wizard (writes home config and tokens.yml)
- `-i`, `--install-completion` – install shell completion for bash, zsh, or fish
- `-l`, `--list` – list available information. Valid types: `config`, `editor`, `language`, `model`, `path`, `provider`, `style`
- `-m`, `--model` – override the model for this invocation (requires `-P`)
- `-o`, `--signoff` / `--no-signoff` – append a `Signed-off-by:` trailer (uses git `user.name` / `user.email`); applies to commit, amend, and squash modes
- `-P`, `--provider` – override the LLM provider for this invocation
- `-p`, `--generate-prompts` – generate default `commit_prompt.md` and `squash_prompt.md` in the current directory (for customization)
- `--print` – print the generated commit message to stdout and exit without committing (commit/amend modes only; mutually exclusive with `-c`)
- `-q`, `--sql true|false` – override stats writing for this run (wins over the persisted `stats` config)
- `-z`, `--stats` – show local-only usage analytics (commits/squashes/PRs per provider, tokens, average latency)
  - `--since YYYY-MM-DD` – filter `--stats` to events on or after this date
  - `--json` – render `--stats` output as JSON
  - `--reset-stats` – delete all rows from the local stats DB
- `-r`, `--PR` – generate a Pull Request description from the commits between the current branch and its base (prints to stdout by default; set `pr_to_file=true` to write a Markdown file)
- `--base` `BRANCH` – explicit base branch for `--PR` (overrides auto-detection: `origin/HEAD` → `main` → `master`)
- `-S`, `--set` – set a config value (`key=value`) in repo config (requires existing repo config)
- `-s`, `--squash` `[N|HASH]` – squash commits on the current branch and summarize them. Without argument: squash all since branch checkout. With a number: squash the last N commits. With a commit hash: squash up to and including that commit
- `--style` `STYLE` – override the commit message style for this invocation (e.g. `funny`, `neutral`, `none`); validated against the supported styles
- `--language` `CODE` – override the commit message language for this invocation (e.g. `de`, `fr`, `none`); validated against supported codes
- `--emoji` / `--no-emoji` – override emoji usage for this invocation (use `--no-emoji` to disable when config enables it)
- `-T`, `--timeout` `SECONDS` – HTTP timeout for this invocation (overrides config)
- `-t`, `--time` – measure and log commit message generation time
- `-u`, `--update` – check for updates
- `-v`, `--version` – show the installed version
- `-x`, `--context` – provide extra context for the LLM (e.g. ticket number, reason for change)

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

### Pull Request descriptions

`-r` / `--PR` generates a Markdown Pull Request description from the commits
between the current branch and its base branch. The output has two sections —
`## Summary` (bullet list following the same best practices as commit messages:
imperative mood, capitalized, no trailing period, 72-char wrap) and
`## Test plan` (a checklist a reviewer can run).

This mode never modifies git state — no commit, no reset, no force push.

```sh
git cai -r                      # print to stdout (default)
git cai --PR                    # long form
git cai -r --base develop       # explicit base branch
git cai -r -x "Closes JIRA-1234"  # add extra context
```

The base branch is auto-detected in this order: `origin/HEAD`, then local
`main`, then local `master`. Use `--base` for repositories with non-standard
layouts or no `origin/HEAD`.

By default the description is printed to stdout. To write it to a file in the
repository root instead, set `pr_to_file: true`:

```sh
git cai -S pr_to_file=true
git cai -S pr_file_name=PR.md   # optional: change the filename
git cai -r                       # writes ./PR.md (or PR_DESCRIPTION.md by default)
```

Configuration follows the usual precedence: repo `cai_config.yml` wins,
otherwise `~/.config/cai/cai_config.yml`, otherwise the built-in defaults.

### Local usage analytics

Opt in by setting `stats: true` in `cai_config.yml` (or pass `-q true` for a single run). Each generation appends one row to a local SQLite DB at `~/.local/share/git-cai/stats.db` with metadata only — no diff, message, or file content.

```sh
git cai -S stats=true            # enable persistently in the repo config
git cai -H stats=true            # or in the home config
git cai -q true                  # one-off opt-in regardless of config
git cai -q false                 # one-off opt-out

git cai -z                       # text summary
git cai -z --json                # machine-readable
git cai --stats --since 2026-01-01  # date filter
git cai --stats --reset-stats    # wipe all rows
```

Rows are split by `kind` (`commit`, `amend`, `squash`, `pr`) and capture provider, model, repo name, token counts, real LLM latency, and a snapshot of the active settings (language, style, emoji, temperature, prompt file).

### DCO sign-off

Projects that require Developer Certificate of Origin sign-off (Linux
kernel, many CNCF projects) can have cai append the trailer
automatically:

```sh
git cai --signoff                # one-off
git cai -o -A                    # short flag, with amend
git cai -S signoff=true          # enable persistently in the repo config
```

The trailer is built from your git `user.name` and `user.email`. When
the message already ends in a trailer block (e.g. an existing
`Co-authored-by:` or another `Signed-off-by:` line), the new sign-off
is appended to that block without an extra blank line. Re-running with
`--signoff` on a message that already carries the same trailer is a
no-op.

### Print-only output (no commit)

`--print` generates the commit message and writes it to stdout instead
of opening the editor or committing. Useful for scripting:

```sh
MSG=$(git cai --print)
git cai --print --conventional --signoff
```

Diagnostic output (spinner, `--time`, `--debug`) goes to stderr, so the
command substitution above captures only the message. Limited to commit
and amend modes. Mutually exclusive with `-c` / `--crazy` (which
commits immediately).

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
