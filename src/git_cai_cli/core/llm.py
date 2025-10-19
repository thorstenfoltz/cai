"""
Settings and connection of LLM
"""

import logging
from typing import Any, Dict, Type

from git_cai_cli.core.languages import LANGUAGE_MAP
from google import genai  # type: ignore[reportUnknownImport]
from google.genai import types  # type: ignore[reportUnknownImport]
from openai import OpenAI

log = logging.getLogger(__name__)


class CommitMessageGenerator:
    """
    Generates git commit messages from a git diff using LLMs.
    """

    def __init__(self, token: str, config: Dict[str, Any], default_model: str):
        self.token = token
        self.config = config
        self.default_model = default_model

    def generate(self, git_diff: str) -> str:
        """
        Generate a commit message using the default model.
        """
        model_dispatch = {
            "openai": self.generate_openai,
            "gemini": self.generate_gemini,
        }

        try:
            log.debug("Generating commit message using model '%s'", self.default_model)
            return model_dispatch[self.default_model](git_diff)
        except KeyError as e:
            log.error("Unknown default model: '%s'", self.default_model)
            raise ValueError(f"Unknown default model: '{self.default_model}'") from e

    def _system_prompt(self, language_name: str) -> str:
        """
        Shared system prompt for both OpenAI and Gemini.
        """
        return (
            "You are an expert software engineer assistant. "
            "Your task is to generate a concise, professional git commit message. "
            f"Summarizing the provided git diff changes in {language_name}. "
            "Keep the message clear and focused on what was changed and why. "
            "Always include a headline, followed by a bullet-point list of changes. "
            "Should you observe any sensitive information like personal data, passwords, "
            "tokens, etc. in the diff, print 'SENSITIVE INFORMATION DETECTED' "
            "and show what was detected, the file where and the line number. "
            "Print it always to the top of the commit message. "
            "But even if you see sensitive information, still generate the commit message. "
        )

    def generate_openai(self, git_diff: str, openai_cls: Type[Any] = OpenAI) -> str:
        """
        Generate a commit message using OpenAI's API.
        """
        client = openai_cls(api_key=self.token)
        model = self.config["openai"]["model"]
        temperature = self.config["openai"]["temperature"]
        language = self.config["language"]
        language_name = self._language_name(language, LANGUAGE_MAP)

        system_prompt = self._system_prompt(language_name)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Generate a commit message for:\n\n{git_diff}",
            },
        ]

        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        return completion.choices[0].message.content.strip()

    def generate_gemini(
        self, git_diff: str, genai_cls: Type[Any] = genai.Client
    ) -> str:
        """
        Generate a commit message using Gemini's API.
        """
        client = genai_cls(api_key=self.token)
        model = self.config["gemini"]["model"]
        temperature = self.config["gemini"]["temperature"]
        language = self.config["language"]
        language_name = self._language_name(language, LANGUAGE_MAP)
        system_prompt = self._system_prompt(language_name)
        messages = git_diff
        response = client.models.generate_content(
            model=model,
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
            ),
        )
        return response.text

    def _language_name(self, lang_code: str, allowed_languages: dict[str, str]) -> str:
        """
        Convert ISO 639-1 code to human-readable language name.
        Defaults to English if not found.
        """
        return allowed_languages.get(lang_code, "English")
