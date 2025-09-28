"""
Settings and connection of LLM
"""
from typing import Any, Dict, Type
from openai import OpenAI


class CommitMessageGenerator:
    """
    Generates git commit messages from a git diff using LLMs.
    """

    def __init__(self, token: str, config: Dict[str, Any]):
        self.token = token
        self.config = config

    def generate_openai(self, git_diff: str, openai_cls: Type[Any] = OpenAI) -> str:
        """
        Generate a commit message using OpenAI's API.
        """
        client = openai_cls(api_key=self.token)
        model = self.config["openai"]["model"]
        temperature = self.config["openai"]["temperature"]

        system_prompt = (
            "You are an expert software engineer assistant. "
            "Your task is to generate a concise, professional git commit message "
            "summarizing the provided git diff changes. "
            "Keep the message clear and focused on what was changed and why."
            "Make always a list of changes, but use a headline."
        )

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
