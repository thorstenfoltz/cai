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

---

## Prerequisites

- Python 3.10 or higher
- [pipx](https://pypi.org/project/pipx/)
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
- Global configuration with **per-repository overrides**
- Repository-specific language, style, and model selection
- Optional commit squashing with automatic summary generation

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

cai uses the output of `git diff` to generate a commit message.  
The generated message is opened in your configured Git editor, allowing you to review or edit it before committing.

In short: it behaves like `git commit`, but the commit message is pre-filled.

### Ignoring files

To exclude specific files or directories from being considered when generating commit messages, create a `.caiignore` file in the root of your repository.

- Files listed in `.gitignore` are **always excluded**
- `.caiignore` is intended for tracked files that should **not** influence commit messages

The syntax is identical to `.gitignore`.

---

## Configuration

On first execution, cai automatically creates two configuration files:

- Global configuration:  
  ~/.config/cai/cai_config.yml

- API tokens:  
  ~/.config/cai/tokens.yml

Don't be scared the first run will show an error. It only misses a token.
Add your provider API keys to `tokens.yml`. Once configured, cai will reuse them automatically.
Set your preferred LLM in `cai_config.yml` (Groq by default).

### Repository-specific configuration

Each repository can be configured **independently**.

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

### Available configuration options

- `default` – default LLM provider
- `model` – model to use for the selected provider  
  (note: not all models may be compatible)
- `temperature` – controls how creative the generated messages are
- `language` – language used for commit messages
- `style` – tone or style of the commit message
- `emoji` – enable or disable emojis
- `load_tokens_from` – path to the file where API tokens are stored

---

## CLI

In addition to `git cai`, the following options are available:

- `-h` `--help` – show help and available commands
- `-a`, `--all` – stage all tracked modified and deleted files
- `-d`, `--debug` – enable debug logging
- `-l`, `--list` – list available languages and styles
- `-s`, `--squash` – squash commits on the current branch and summarize them
- `-u`, `--update` – check for updates
- `-v`, `--version` – show the installed version

---

## License

This project is licensed under the MIT License.
