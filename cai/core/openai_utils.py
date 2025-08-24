from typing import Any, Dict, Type

from openai import OpenAI


def get_commit_message(
    token: str, config: Dict[str, Any], git_diff: str, openai_cls: Type[Any] = OpenAI
) -> str:
    client = openai_cls(api_key=token)

    model = config["openai"]["model"]
    temperature = config["openai"]["temperature"]

    system_prompt = (
        "You are an expert software engineer assistant. "
        "Your task is to generate a concise, professional git commit message "
        "summarizing the provided git diff changes. "
        "Keep the message clear and focused on what was changed and why."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Generate a commit message for:\n\n{git_diff}"},
    ]

    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )

    return completion.choices[0].message.content.strip()
