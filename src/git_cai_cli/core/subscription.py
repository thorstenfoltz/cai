"""
Use a Claude, OpenAI or GitHub Copilot subscription instead of an API token.

Subscriptions have no API of their own, so the vendor's official command line
tool does the request. These tools are coding agents: they run in an empty
directory without shell, web or connected apps, so nothing in a diff can make
them act on the repository. Codex cannot drop all of its tools, so it also gets
its read only sandbox.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, NamedTuple


class SubscriptionError(ValueError):
    """A subscription request failed; the message is meant for the user."""


class SubscriptionCli(NamedTuple):
    """The command line tool behind a provider's subscription."""

    command: str
    label: str
    install_url: str
    login: str
    has_api: bool = True


SUBSCRIPTION_CLIS: dict[str, SubscriptionCli] = {
    "anthropic": SubscriptionCli(
        "claude",
        "Claude",
        "https://code.claude.com/docs/en/setup",
        "claude auth login",
    ),
    "openai": SubscriptionCli(
        "codex",
        "OpenAI",
        "https://developers.openai.com/codex/cli",
        "codex login",
    ),
    "copilot": SubscriptionCli(
        "copilot",
        "GitHub Copilot",
        "https://docs.github.com/copilot/how-tos/copilot-cli",
        "copilot login",
        has_api=False,
    ),
}

# The CLIs prefer these over the subscription login and would bill the API
# account (or send the diff to another vendor) without saying so.
_HIDDEN_ENV = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
}
_HIDDEN_ENV_PREFIX = "COPILOT_PROVIDER_"

_OVERFLOW_RE = re.compile(
    r"prompt is too long|context.(?:window|length)|exceeds the maximum length",
    re.IGNORECASE,
)

_SYSTEM_PROMPT_FILE = "system_prompt.md"
_USAGE_FILE = "usage.json"

_Answer = tuple[str, int | None, int | None]


def is_input_too_large(exc: SubscriptionError) -> bool:
    """True if the CLI rejected the input because of its size."""
    return bool(_OVERFLOW_RE.search(str(exc)))


def missing_cli_message(provider: str) -> str | None:
    """Explain that the provider's CLI is missing, or None if it is installed."""
    cli = SUBSCRIPTION_CLIS[provider]
    if shutil.which(cli.command):
        return None
    if cli.has_api:
        alternative = (
            "To use the API instead, pass --no-subscription or set "
            "'subscription: false' in cai_config.yml."
        )
    else:
        alternative = "To use another provider, pass --provider."
    return (
        f"The {cli.label} subscription is used through the '{cli.command}' command, "
        f"which is not installed or not on PATH. Install it from {cli.install_url} "
        f"and log in with '{cli.login}'. {alternative}"
    )


def _arguments(provider: str, model: str) -> list[str]:
    """Command line for one answer. Prompts never go here, see ``_run``."""
    if provider == "anthropic":
        return [
            "--print",
            "--output-format=json",
            f"--model={model}",
            f"--system-prompt-file={_SYSTEM_PROMPT_FILE}",
            "--tools",
            "",
            "--safe-mode",
            "--strict-mcp-config",
            "--no-session-persistence",
        ]
    if provider == "openai":
        return [
            "exec",
            "--json",
            f"--model={model}",
            "--sandbox=read-only",
            # Unknown settings are ignored by default. A renamed one must stop the
            # run instead of silently dropping the prompt or a restriction.
            "--strict-config",
            f'--config=model_instructions_file="{_SYSTEM_PROMPT_FILE}"',
            "--disable=shell_tool",
            "--disable=apps",
            "--disable=plugins",
            '--config=web_search="disabled"',
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "-",
        ]
    return [
        "--silent",
        f"--model={model}",
        # An empty list is ignored and leaves every tool on. Any unknown name
        # removes them all.
        "--available-tools=none",
        "--disable-builtin-mcps",
        "--disallow-temp-dir",
        "--no-custom-instructions",
        "--no-ask-user",
        "--no-auto-update",
        "--no-color",
        f"--usage-output-file={_USAGE_FILE}",
    ]


def _loads(text: str) -> dict[str, Any]:
    """Parse a JSON object, or return an empty one for anything else."""
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_claude(stdout: str) -> tuple[_Answer, str]:
    data = _loads(stdout)
    text = str(data.get("result") or "")
    usage = data.get("usage") or {}
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    tokens_in = sum(usage.get(key) or 0 for key in keys) if usage else None
    answer = (text, tokens_in, usage.get("output_tokens"))
    return answer, text if data.get("is_error") else ""


def _parse_codex(stdout: str) -> tuple[_Answer, str]:
    text, error = "", ""
    usage: dict[str, Any] = {}
    for event in map(_loads, stdout.splitlines()):
        kind, item = event.get("type"), event.get("item") or {}
        if kind == "item.completed" and item.get("type") == "agent_message":
            text = str(item.get("text") or "")
        elif kind == "turn.completed":
            usage = event.get("usage") or {}
        elif kind == "turn.failed":
            error = str((event.get("error") or {}).get("message") or "")
    return (text, usage.get("input_tokens"), usage.get("output_tokens")), error


def _parse_copilot(stdout: str, usage_file: Path) -> tuple[_Answer, str]:
    models: dict[str, Any] = {}
    if usage_file.is_file():
        data = _loads(usage_file.read_text(encoding="utf-8"))
        models = data.get("modelMetrics") or {}
    usages = [metrics.get("usage") or {} for metrics in models.values()]
    if not usages:
        return (stdout, None, None), ""
    tokens_in = sum(usage.get("inputTokens") or 0 for usage in usages)
    tokens_out = sum(usage.get("outputTokens") or 0 for usage in usages)
    return (stdout, tokens_in, tokens_out), ""


def run_subscription(
    provider: str, model: str, content: str, system_prompt: str, timeout: int
) -> _Answer:
    """Ask the provider's CLI for one answer.

    Returns ``(text, prompt_tokens, completion_tokens)`` and raises
    ``SubscriptionError`` with a readable message on every failure.
    """
    cli = SUBSCRIPTION_CLIS[provider]
    if missing := missing_cli_message(provider):
        raise SubscriptionError(missing)

    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _HIDDEN_ENV and not key.startswith(_HIDDEN_ENV_PREFIX)
    }
    # Prompts go through stdin or a file: a command line is limited in size and
    # readable by other users, and Windows runs the CLIs through cmd.exe.
    stdin = content
    with tempfile.TemporaryDirectory(prefix="git-cai-") as workdir:
        if provider == "copilot":  # takes no system prompt file
            stdin = f"{system_prompt}\n\n{content}"
        else:
            prompt_file = Path(workdir) / _SYSTEM_PROMPT_FILE
            prompt_file.write_text(system_prompt, encoding="utf-8")
        try:
            # ``which`` again for the full path: Windows needs the extension.
            process = subprocess.run(  # nosec B603
                [
                    shutil.which(cli.command) or cli.command,
                    *_arguments(provider, model),
                ],
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=workdir,
                env=env,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise SubscriptionError(
                f"The '{cli.command}' command did not answer within {timeout} seconds. "
                "Allow more time with --timeout or 'timeout' in cai_config.yml."
            ) from None
        except OSError as exc:
            raise SubscriptionError(
                f"The '{cli.command}' command could not be started: {exc}"
            ) from exc

        if provider == "anthropic":
            answer, error = _parse_claude(process.stdout)
        elif provider == "openai":
            answer, error = _parse_codex(process.stdout)
        else:
            usage_file = Path(workdir) / _USAGE_FILE
            answer, error = _parse_copilot(process.stdout, usage_file)

    if error or process.returncode != 0:
        detail = error or process.stderr.strip() or process.stdout.strip()
        detail = detail[-500:] or f"exit code {process.returncode}"
        raise SubscriptionError(
            f"The '{cli.command}' command failed: {detail}\n"
            f"If you are not logged in, run '{cli.login}'."
        )

    text, tokens_in, tokens_out = answer
    if not text.strip():
        raise SubscriptionError(f"{cli.label} returned an empty response.")
    return text.strip(), tokens_in, tokens_out
