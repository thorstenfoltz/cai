# cai

cai is a Git extension written automating the creation of commit messages. Simply run `git cai` to automatically generate a commit message based on the changes and new files in your repository.

cai uses a large language model (LLM) to produce commit messages that are meaningful and context-aware.

## Table of Contents

- [About](#about-section)
- [Prerequisites](#prerequisites)
- [Features](#features-section)
- [Installation](#installation-section)
- [Usage](#usage-section)
- [Configuration](#config-section)
- [CLI](#cli)
- [License](#license-section)

<h2 id="about-section">About</h2>

cai is designed to simplify Git workflows by automatically generating commit messages using an LLM. No more struggling to summarize changes, just run `git cai`.

Currently, it supports the API of OpenAI, Gemini, Anthropic, Groq and Xai for message generation.

<h2 id="prerequisites">Prerequisites</h2>

- Python 3.10 or higher
- [Pipx](https://pypi.org/project/pipx/) or [Pip](https://pypi.org/project/pip/) if installed in a virtual environment
- API key, of at least one of the following providers
  - OpenAI
  - Gemini
  - Anthropic
  - Groq
  - Xai

<h2 id="features-section">Features</h2>

- Automatically detects added, modified, and deleted files
- Generates meaningful, context-aware commit messages using an LLM
- Seamless integration with Git as a plugin/extension
- Supports different LLM models and languages for each repository, as well as global configuration
- Allows to squash all commits in a branch and summarizes the commit messages

<h2 id="installation-section">Installation</h2>

Installation:

```sh
pipx install git-cai-cli
```

Afterwards, add to `PATH`:

```sh
pipx ensurepath
```

Finally, restart the shell.

<h2 id="usage-section">Usage</h2>

Once installed, cai works like a standard Git command:

```sh
git cai
```

`cai` uses Git’s `diff` output to generate commit messages. The generated message is then opened within the editor according to your git configuration, allowing reviewing and editing before confirming the commit.  

In short: it behaves like `git commit`, but the commit message is pre-filled.

To exclude specific files or directories from being included in the generated commit message, create a `.caiignore` file in the root of your repository. This file works like a `.gitignore`.  

- Files listed in `.gitignore` are **always excluded**.  
- `.caiignore` is only needed for files that are tracked by Git but should **not** be included in the commit message.

<h2 id="config-section">Configuration</h2>

The first time you run `git cai` two configuration files are automatically created:

- `cai_config.yml` – Stores general settings:

```sh
home/<USERNAME>/.config/cai/cai_config.yml
```

- `tokens.yml` – Stores API token(s):

```sh
home/<USERNAME>/.config/cai/tokens.yml
```

Add provider API token to `tokens.yml` so that cai can use it each time to generate a commit message.

If a `cai_config.yml` file exists in the root of your repository, cai will use the settings defined there. Otherwise, it falls back to the default settings.

To use a repository-specific configuration, copy the config file to the root of your repository and adjust it as needed:

```sh
cp ~/.config/cai/cai_config.yml .
```

Currently, the following options can be customized:

- default: set the default provider
- model: specify which model of the provider to use (please note, perhaps not all models will work)
- temperature: control how creative the model’s responses are
- language: set the language in which the LLM should generate commit messages
- style: choose a certain tone style of the commit message
- emoji: boolean to enable/disable usage of emojis

<h2 id="cli">CLI</h2>

Besides running `git cai` to generate commit messages, you can use the following options:

- `-h` shows a brief help message with available commands
- `-d`, `--debug` enables debug logging to help troubleshoot issues
- `-l`, `--languages` list available languages
- `-s`, `--squash` squash commits on this branch and summarize them
- `--style` show names and examples of available tone styles
- `-u`, `--update` checks for updates the `cai` tool
- `-v`, `--version` displays the currently installed version

<h2 id="license-section">License</h2>
This project is licensed under the MIT License.
