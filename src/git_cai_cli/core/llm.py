"""
Use LLMs to generate git commit messages from diffs or multiple commits.
"""

import logging
from collections.abc import Callable
from typing import Any, Dict, Optional, Type

import requests
from anthropic import Anthropic
from git_cai_cli.core.languages import LANGUAGE_MAP
from google import genai  # type: ignore[reportUnknownImport]
from google.genai import types  # type: ignore[reportUnknownImport]
from groq import Groq
from openai import OpenAI

log = logging.getLogger(__name__)


class CommitMessageGenerator:
    """
    Generates git commit messages from diffs or from multiple commit messages.
    """

    def __init__(self, token: str, config: Dict[str, Any], default_model: str):
        self.token = token
        self.config = config
        self.default_model = default_model

    def generate(self, git_diff: str) -> str:
        """
        Generate a commit message from a diff.
        """
        language_name = self._language_name(self.config["language"], LANGUAGE_MAP)
        prompt = self._system_prompt(language_name=language_name)
        return self._dispatch_generate(content=git_diff, system_prompt=prompt)

    def summarize_commit_history(self, commit_messages: str) -> str:
        """
        Summarize multiple commit messages into one high-level commit message.
        """
        language_name = self._language_name(self.config["language"], LANGUAGE_MAP)
        prompt = self._summary_prompt(language_name=language_name)
        return self._dispatch_generate(content=commit_messages, system_prompt=prompt)

    def _emoji_enabled(self) -> str:
        """
        Returns whether emojis are enabled in commit messages.
        """
        if self.config.get("emoji", True):
            emoiji_instruction = (
                "Use relevant emojis in the commit message where appropriate. "
                "Emojis should enhance the clarity and tone of the message."
            )
            log.info("Emojis are enabled for commit messages.")
        else:
            emoiji_instruction = "Do not use any emojis in the commit message."
            log.info("Emojis are disabled for commit messages.")
        return emoiji_instruction

    # ---------------------------
    # PROMPTS
    # ---------------------------

    def _system_prompt(self, language_name: str) -> str:
        """
        Prompt used when generating commit messages from diffs.
        """
        return (
            "You are an expert software engineer assistant. "
            "Your task is to generate a concise, professional git commit message, "
            f"summarizing the provided git diff changes in {language_name}. "
            "Keep the message clear and focused on what was changed and why. "
            "Always include a headline, followed by a bullet-point list of changes. "
            "If you detect sensitive information, mention it at the top, but still generate the message. "
            f"Write the commit message in the following tone style: {self.config['style']}. "
            f"{self._emoji_enabled()}."
        )

    def _summary_prompt(self, language_name: str) -> str:
        """
        Prompt used when summarizing multiple commit messages into a single commit.
        """
        return (
            "You are an expert software engineer assistant. "
            "Your task is to summarize multiple existing commit messages "
            "into a single clean git commit message. "
            f"Write the final message in {language_name}. "
            "Do not list each commit individually. "
            "Instead, infer the main purpose and overall change. "
            "Format:\n"
            "1. One short, clear headline.\n"
            "2. A concise bullet list describing the main themes of the work. "
            f"Write the commit message in the following tone style: {self.config['style']}. "
            f"{self._emoji_enabled()}."
        )

    # ---------------------------
    # DISPATCH
    # ---------------------------

    def _dispatch_generate(self, content: str, system_prompt: str) -> str:
        """
        Route to correct model with the right prompt. System prompt is
        _system_prompt or _summary_prompt depending on use case.
        Content is output of git diff.
        """
        model_dispatch: Dict[str, Callable[..., str]] = {
            "openai": self.generate_openai,
            "gemini": self.generate_gemini,
            "anthropic": self.generate_claude,
            "groq": self.generate_groq,
            "xai": self.generate_xai,
        }

        if self.default_model not in model_dispatch:
            raise ValueError(f"Unknown model type: '{self.default_model}'")

        return model_dispatch[self.default_model](
            content, system_prompt_override=system_prompt
        )

    # ---------------------------
    # MODEL CALLS
    # ---------------------------

    def generate_claude(
        self,
        content: str,
        anthropic_cls: Type[Any] = Anthropic,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared Anthropic call for commit generation or commit history summarization.
        """
        client = anthropic_cls(api_key=self.token)
        model = self.config["anthropic"]["model"]
        temperature = self.config["anthropic"]["temperature"]

        prompt = [
            {
                "role": "assistant",
                "content": system_prompt_override,
            },
            {
                "role": "user",
                "content": content,
            },
        ]

        response = client.messages.create(
            model=model,
            messages=prompt,
            temperature=temperature,
            max_tokens=1024,
        )
        return response.content[0].text.strip()

    def generate_gemini(
        self,
        content: str,
        genai_cls: Type[Any] = genai.Client,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared Gemini call for commit generation or commit history summarization.
        """
        client = genai_cls(api_key=self.token)
        model = self.config["gemini"]["model"]
        temperature = self.config["gemini"]["temperature"]

        response = client.models.generate_content(
            model=model,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt_override,
                temperature=temperature,
            ),
        )
        return response.text

    def generate_groq(
        self,
        content: str,
        genai_cls: Type[Any] = Groq,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared Groq call for commit generation or commit history summarization.
        """
        client = genai_cls(api_key=self.token)
        model = self.config["groq"]["model"]
        temperature = self.config["groq"]["temperature"]

        prompt = [
            {
                "role": "system",
                "content": system_prompt_override,
            },
            {
                "role": "user",
                "content": content,
            },
        ]

        response = client.chat.completions.create(
            model=model,
            messages=prompt,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()

    def generate_openai(
        self,
        content: str,
        openai_cls: Type[Any] = OpenAI,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared OpenAI call for commit generation or commit history summarization.
        """
        client = openai_cls(api_key=self.token)
        model = self.config["openai"]["model"]
        temperature = self.config["openai"]["temperature"]

        messages = [
            {"role": "system", "content": system_prompt_override},
            {"role": "user", "content": content},
        ]

        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        return completion.choices[0].message.content.strip()

    def generate_xai(
        self,
        content: str,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared Xai call for commit generation or commit history summarization.
        """
        url = "https://api.x.ai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        model = self.config["xai"]["model"]
        temperature = self.config["xai"]["temperature"]

        prompt = [
            {
                "role": "system",
                "content": system_prompt_override,
            },
            {
                "role": "user",
                "content": content,
            },
        ]

        request = {
            "model": model,
            "messages": prompt,
            "temperature": temperature,
        }
        response = requests.post(url, json=request, headers=headers, timeout=30)
        return response.json()["choices"][0]["message"]["content"].strip()

    # ---------------------------
    # LANGUAGE HELPER
    # ---------------------------

    def _language_name(self, lang_code: str, allowed_languages: dict[str, str]) -> str:
        return allowed_languages.get(lang_code, "English")
