# cai

`cai` is a Git extension written in Python that automates commit message creation. It allows you to run `git cai` to automatically generate a commit message based on changes and new additions in your repository.  

`cai` leverages a **large language model (LLM)** to generate meaningful and context-aware commit messages. Currently, it supports the **OpenAI API** for generating commit messages.

## Table of Contents

- [About](#about-section)
- [Prerequisites](#prerequisites)
- [Features](#features-section)
- [Installation](#installation-section)
- [Usage](#usage-section)
- [License](#license-section)

<h2 id="about-section">About</h2>
`cai` is designed to simplify your Git workflow by automatically generating commit messages using an LLM. No more struggling to summarize changes—`git cai` does it for you.  

Currently, the only supported backend is the OpenAI API, but additional LLM integrations may be added in the future.

<h2 id="prerequisites">Prerequisites</h2>

- Python 3.11 or higher
- [Pip](https://pypi.org/project/pip/) or better [Pipx](https://pypi.org/project/pipx/)
- OpenAI API key

<h2 id="features-section">Features</h2>

- Automatically detects added, modified, and deleted files
- Generates meaningful commit messages using an LLM
- Currently uses **OpenAI API** for commit message generation
- Seamless integration with Git as a plugin/extension
- Written in Python for easy customization

<h2 id="installation-section">Installation</h2>

- Currently by using pipx from local clone
- Clone the repo, change into the directory and install

 ```sh
 git clone https://github.com/thorstenfoltz/cai.git
 cd cai
 pipx install .
 ```

<h2 id="usage-section">Usage</h2>
Once installed, you can use `cai` like a normal Git command:

```sh
git cai
```

`cai` will create a  

<h2 id="license-section">License</h2>
This project is licensed under the MIT License.
