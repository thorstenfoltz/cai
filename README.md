# cai

`cai` is a Git extension written in Python that automates commit message creation. It allows you to run `git cai` to automatically generate a commit message based on changes and new additions in your repository.  

`cai` leverages a **large language model (LLM)** to generate meaningful and context-aware commit messages. Currently, it supports the **OpenAI API** for generating commit messages.

## Table of Contents
- [About](#about-section)
- [Features](#features-section)
- [Installation](#installation-section)
- [Usage](#usage-section)
- [License](#license-section)

<h2 id="about-section">About</h2>
`cai` is designed to simplify your Git workflow by automatically generating commit messages using an LLM. No more struggling to summarize changes—`git cai` does it for you.  

Currently, the only supported backend is the OpenAI API, but additional LLM integrations may be added in the future.

<h2 id="features-section">Features</h2>
- Automatically detects added, modified, and deleted files
- Generates meaningful commit messages using an LLM
- Currently uses **OpenAI API** for commit message generation
- Seamless integration with Git as a plugin/extension
- Written in Python for easy customization

<h2 id="installation-section">Installation</h2>



<h2 id="usage-section">Usage</h2>
Once installed, you can use `cai` like a normal Git command:

```bash
git cai

<h2 id="license-section">License</h2>
<!-- markdownlint-disable-next-line -->
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

