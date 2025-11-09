"""
Use LLMs to generate git commit messages from diffs or multiple commits.
"""

import logging
from typing import Any, Dict, Optional, Type

from git_cai_cli.core.languages import LANGUAGE_MAP
from google import genai  # type: ignore[reportUnknownImport]
from google.genai import types  # type: ignore[reportUnknownImport]
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

    # ---------------------------
    # PROMPTS
    # ---------------------------

    def _system_prompt(self, language_name: str) -> str:
        """
        Prompt used when generating commit messages from diffs.
        """
        return (
            "You are an expert software engineer assistant. "
            "Your task is to generate a concise, professional git commit message. "
            f"summarizing the provided git diff changes in {language_name}. "
            "Keep the message clear and focused on what was changed and why. "
            "Always include a headline, followed by a bullet-point list of changes. "
            "If you detect sensitive information, mention it at the top, but still generate the message."
        )

    def _summary_prompt(self, language_name: str) -> str:
        """
        Prompt used when summarizing multiple commit messages into a single commit.
        """
        return (
            "You are an expert software engineer assistant. "
            "Your task is to summarize multiple existing commit messages* "
            "into a single clean git commit message. "
            f"Write the final message in {language_name}. "
            "Do not list each commit individually. "
            "Instead, infer the main purpose and overall change. "
            "Format:\n"
            "1. One short, clear headline.\n"
            "2. A concise bullet list describing the main themes of the work."
        )

    # ---------------------------
    # DISPATCH
    # ---------------------------

    def _dispatch_generate(self, content: str, system_prompt: str) -> str:
        """
        Route to correct model (openai or gemini) with the right prompt.
        """
        model_dispatch = {
            "openai": self.generate_openai,
            "gemini": self.generate_gemini,
        }

        if self.default_model not in model_dispatch:
            raise ValueError(f"Unknown model type: '{self.default_model}'")

        return model_dispatch[self.default_model](
            content, system_prompt_override=system_prompt
        )

    # ---------------------------
    # MODEL CALLS
    # ---------------------------

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

    # ---------------------------
    # LANGUAGE HELPER
    # ---------------------------

    def _language_name(self, lang_code: str, allowed_languages: dict[str, str]) -> str:
        return allowed_languages.get(lang_code, "English")
