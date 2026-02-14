"""
Use LLMs to generate git commit messages from diffs or multiple commits.
"""

import logging
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Optional, Type
from urllib.parse import urlparse

import requests
from git_cai_cli.core.languages import LANGUAGE_MAP
from openai import OpenAI

log = logging.getLogger(__name__)

# Hardcoded fallback prompts (last resort when no file is found)
_HARDCODED_COMMIT_PROMPT = (
    "You are an expert software engineer assistant. "
    "Your task is to generate a concise, professional git commit message, "
    "summarizing the provided git diff changes. "
    "Keep the message clear and focused on what was changed and why. "
    "Always include a headline, followed by a bullet-point list of changes. "
    "If you detect sensitive information, mention it at the top, but still generate the message."
)

_HARDCODED_SQUASH_PROMPT = (
    "You are an expert software engineer assistant. "
    "Your task is to summarize multiple existing commit messages "
    "into a single clean git commit message. "
    "Do not list each commit individually. "
    "Instead, infer the main purpose and overall change. "
    "Format:\n"
    "1. One short, clear headline.\n"
    "2. A concise bullet list describing the main themes of the work."
)


def load_prompt_file(
    config_key: str,
    config: Dict[str, Any],
    default_filename: str,
    hardcoded_fallback: str,
) -> str:
    """
    Load a prompt with a three-tier fallback strategy:

    1. User-defined file path from config (config_key).
    2. Default bundled file from the package defaults/ directory.
    3. Hardcoded fallback string.

    Args:
        config_key: Config key that holds the path (e.g. "prompt_file").
        config: The full configuration dictionary.
        default_filename: Name of the default file (e.g. "commit_prompt.md").
        hardcoded_fallback: Hardcoded prompt string used as last resort.

    Returns:
        The prompt text.
    """
    # 1) Try user-defined path from config
    user_path = config.get(config_key, "")
    if isinstance(user_path, Path):
        user_path = str(user_path)

    if user_path and isinstance(user_path, str) and user_path.strip():
        expanded = os.path.expandvars(user_path.strip())
        path = Path(expanded).expanduser()
        if not path.is_absolute():
            path = path.resolve()

        if path.is_file():
            log.info(
                "Loading prompt from user-defined file: %s (config key: '%s')",
                path,
                config_key,
            )
            content = path.read_text(encoding="utf-8").strip()
            log.debug("User prompt loaded (%d characters).", len(content))
            return content

        log.warning(
            "Prompt file '%s' from config key '%s' not found. Falling back to default.",
            path,
            config_key,
        )

    # 2) Try default bundled file
    try:
        defaults_pkg = resources.files("git_cai_cli.defaults")
        default_file = defaults_pkg / default_filename
        if default_file.is_file():  # type: ignore[union-attr]
            content = default_file.read_text(encoding="utf-8").strip()  # type: ignore[union-attr]
            log.info(
                "Loading prompt from default file: %s",
                default_filename,
            )
            log.debug("Default prompt loaded (%d characters).", len(content))
            return content
    except (TypeError, FileNotFoundError, ModuleNotFoundError) as exc:
        log.debug(
            "Could not load default prompt file '%s': %s",
            default_filename,
            exc,
        )

    # 3) Hardcoded fallback
    log.info(
        "Using hardcoded fallback prompt (no file found for config key '%s').",
        config_key,
    )
    return hardcoded_fallback


class CommitMessageGenerator:
    """
    Generates git commit messages from diffs or from multiple commit messages.
    """

    def __init__(self, token: str | None, config: Dict[str, Any], default_model: str):
        self.token = token
        self.config = config
        self.default_model = default_model

        # Ollama lifecycle tracking (only used when provider == "ollama")
        self._ollama_proc: subprocess.Popen[str] | None = None
        self._ollama_started_by_us: bool = False

    def close(self) -> None:
        """Release resources started by this generator (best-effort)."""
        self._stop_ollama_server_if_started_by_us()

    def generate(self, git_diff: str) -> str:
        """
        Generate a commit message from a diff.
        """
        prompt = self._build_commit_prompt()
        log.debug("Commit system prompt preview: %r", prompt[:400])
        return self._dispatch_generate(content=git_diff, system_prompt=prompt)

    def summarize_commit_history(self, commit_messages: str) -> str:
        """
        Summarize multiple commit messages into one high-level commit message.
        """
        prompt = self._build_squash_prompt()
        log.debug("Squash system prompt preview: %r", prompt[:400])
        return self._dispatch_generate(content=commit_messages, system_prompt=prompt)

    def _emoji_instruction(self) -> str:
        """
        Returns an emoji instruction string, or empty string if emoji is set to "none".
        """
        emoji_value = self.config.get("emoji", True)

        if emoji_value is None:
            log.info("Emoji setting is None — no emoji instruction added to prompt.")
            return ""

        if isinstance(emoji_value, str) and emoji_value.strip().lower() == "none":
            log.info("Emoji setting is 'none' — no emoji instruction added to prompt.")
            return ""

        if emoji_value:
            emoji_instruction = (
                "Use relevant emojis in the commit message where appropriate. "
                "Emojis should enhance the clarity and tone of the message."
            )
            log.info("Emojis are enabled for commit messages.")
        else:
            emoji_instruction = "Do not use any emojis in the commit message."
            log.info("Emojis are disabled for commit messages.")
        return emoji_instruction

    def _language_instruction(self) -> str:
        """
        Returns a language instruction string, or empty string if language is "none".
        """
        lang_code = self.config.get("language", "en")

        if lang_code is None:
            log.info(
                "Language setting is None — no language instruction added to prompt."
            )
            return ""

        if isinstance(lang_code, str) and lang_code.strip().lower() == "none":
            log.info(
                "Language setting is 'none' — no language instruction added to prompt."
            )
            return ""

        language_name = self._language_name(lang_code, LANGUAGE_MAP)
        return f"Write the commit message in {language_name}."

    def _style_instruction(self) -> str:
        """
        Returns a style instruction string, or empty string if style is "none".
        """
        style = self.config.get("style", "professional")

        if style is None:
            log.info("Style setting is None — no style instruction added to prompt.")
            return ""

        if isinstance(style, str) and style.strip().lower() == "none":
            log.info("Style setting is 'none' — no style instruction added to prompt.")
            return ""

        return f"Write the commit message in the following tone style: {style}."

    def _config_instructions(self) -> str:
        """
        Build the config-driven instruction suffix (language, style, emoji).
        Only non-empty parts are included.
        """
        parts = [
            self._language_instruction(),
            self._style_instruction(),
            self._emoji_instruction(),
        ]
        return " ".join(p for p in parts if p)

    # ---------------------------
    # PROMPTS
    # ---------------------------

    def _build_commit_prompt(self) -> str:
        """
        Build the full commit prompt by loading the base prompt from file
        (with fallback) and appending config-driven instructions.
        """
        base = load_prompt_file(
            config_key="prompt_file",
            config=self.config,
            default_filename="commit_prompt.md",
            hardcoded_fallback=_HARDCODED_COMMIT_PROMPT,
        )

        suffix = self._config_instructions()
        if suffix:
            prompt = f"{base} {suffix}"
        else:
            prompt = base

        log.debug("Final commit prompt (%d characters).", len(prompt))
        return prompt

    def _build_squash_prompt(self) -> str:
        """
        Build the full squash prompt by loading the base prompt from file
        (with fallback) and appending config-driven instructions.
        """
        base = load_prompt_file(
            config_key="squash_prompt_file",
            config=self.config,
            default_filename="squash_prompt.md",
            hardcoded_fallback=_HARDCODED_SQUASH_PROMPT,
        )

        suffix = self._config_instructions()
        if suffix:
            prompt = f"{base} {suffix}"
        else:
            prompt = base

        log.debug("Final squash prompt (%d characters).", len(prompt))
        return prompt

    # Keep old method names as aliases for backward compatibility in tests
    def _system_prompt(self, language_name: str) -> str:
        """
        Legacy method — builds the commit prompt with config instructions.
        Kept for backward compatibility.
        """
        return self._build_commit_prompt()

    def _summary_prompt(self, language_name: str) -> str:
        """
        Legacy method — builds the squash prompt with config instructions.
        Kept for backward compatibility.
        """
        return self._build_squash_prompt()

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
            "anthropic": self.generate_anthropic,
            "groq": self.generate_groq,
            "xai": self.generate_xai,
            "mistral": self.generate_mistral,
            "deepseek": self.generate_deepseek,
            "ollama": self.generate_ollama,
        }

        if self.default_model not in model_dispatch:
            raise ValueError(f"Unknown model type: '{self.default_model}'")

        log.info("Using provider '%s' for generation.", self.default_model)

        return model_dispatch[self.default_model](
            content, system_prompt_override=system_prompt
        )

    # ---------------------------
    # MODEL CALLS
    # ---------------------------

    def generate_anthropic(
        self,
        content: str,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared Anthropic call for commit generation or commit history summarization.
        Uses direct HTTP API instead of the Anthropic SDK.
        """
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.token,
            "anthropic-version": "2023-06-01",
        }

        model = self.config["anthropic"]["model"]
        temperature = self.config["anthropic"]["temperature"]

        log.info("Using anthropic model '%s'.", model)

        # Anthropic Messages API expects system prompt via the top-level "system" field.
        messages = [{"role": "user", "content": content}]

        request: dict[str, Any] = {
            "model": model,
            "max_tokens": 8192,
            "temperature": temperature,
            "messages": messages,
        }

        if system_prompt_override:
            request["system"] = system_prompt_override

        response = requests.post(url, json=request, headers=headers, timeout=30)
        response.raise_for_status()

        return response.json()["content"][0]["text"].strip()

    def generate_deepseek(
        self,
        content: str,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared Deepseek call for commit generation or commit history summarization.
        It uses the OpenAI SDK.
        """
        url = "https://api.deepseek.com"
        model = self.config["deepseek"]["model"]
        temperature = self.config["deepseek"]["temperature"]
        return self.generate_openai(
            content=content,
            system_prompt_override=system_prompt_override,
            base_url=url,
            model_override=model,
            temperature_override=temperature,
            provider_name="deepseek",
        )

    def generate_gemini(
        self,
        content: str,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared Gemini call for commit generation or commit history summarization.
        Uses direct HTTP API instead of the Google SDK.
        """
        model = self.config["gemini"]["model"]
        temperature = self.config["gemini"]["temperature"]

        log.info("Using gemini model '%s'.", model)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.token,
        }

        text = content
        if system_prompt_override:
            text = f"{system_prompt_override}\n\n{text}"

        request = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "temperature": temperature,
            },
        }

        response = requests.post(url, json=request, headers=headers, timeout=30)
        response.raise_for_status()

        return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def generate_groq(
        self,
        content: str,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared Groq call for commit generation or commit history summarization.
        Uses direct HTTP API instead of the Groq SDK.
        """
        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        model = self.config["groq"]["model"]
        temperature = self.config["groq"]["temperature"]

        log.info("Using groq model '%s'.", model)

        messages = []

        if system_prompt_override:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt_override,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": content,
            }
        )

        request = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        response = requests.post(url, json=request, headers=headers, timeout=30)
        response.raise_for_status()

        return response.json()["choices"][0]["message"]["content"].strip()

    def generate_mistral(
        self,
        content: str,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """
        Shared Mistral call for commit generation or commit history summarization.
        """
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        model = self.config["mistral"]["model"]
        temperature = self.config["mistral"]["temperature"]

        log.info("Using mistral model '%s'.", model)

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

    def _ollama_base_url(self) -> str:
        host = os.environ.get("OLLAMA_HOST", "").strip()
        if not host:
            return "http://localhost:11434"

        # Ollama commonly accepts values like "127.0.0.1:11434" without scheme.
        if "://" not in host:
            host = f"http://{host}"

        return host.rstrip("/")

    def _ollama_is_running(self) -> bool:
        base = self._ollama_base_url()
        for path in ("/api/version", "/api/tags"):
            try:
                r = requests.get(f"{base}{path}", timeout=1)
                if r.status_code == 200:
                    return True
            except requests.RequestException:
                continue
        return False

    def _start_ollama_server_if_needed(self) -> None:
        if self._ollama_is_running():
            return

        base = self._ollama_base_url()
        parsed = urlparse(base)
        hostname = parsed.hostname
        if hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError(
                f"Failed to reach Ollama at {base}. If you set OLLAMA_HOST to a remote host, ensure it is reachable."
            )

        if self._ollama_proc is None or self._ollama_proc.poll() is not None:
            log.info("Ollama is not running; starting 'ollama serve'...")
            try:
                self._ollama_proc = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    start_new_session=True,
                )
            except OSError as exc:
                raise ValueError("Failed to start Ollama server.") from exc
            self._ollama_started_by_us = True

        deadline = time.time() + 8
        while time.time() < deadline:
            if self._ollama_proc is not None and self._ollama_proc.poll() is not None:
                raise ValueError(
                    "Ollama failed to start. Try running `ollama serve` manually to see the error."
                )
            if self._ollama_is_running():
                return
            time.sleep(0.1)

        raise ValueError(
            "Timed out waiting for Ollama to start. Try running `ollama serve` manually."
        )

    def _stop_ollama_server_if_started_by_us(self) -> None:
        if not self._ollama_started_by_us:
            return
        if self._ollama_proc is None:
            return
        if self._ollama_proc.poll() is not None:
            return

        log.info("Stopping Ollama server started by cai...")

        try:
            os.killpg(self._ollama_proc.pid, signal.SIGTERM)
        except Exception:
            try:
                self._ollama_proc.terminate()
            except Exception:
                return

        try:
            self._ollama_proc.wait(timeout=2)
        except Exception:
            try:
                os.killpg(self._ollama_proc.pid, signal.SIGKILL)
            except Exception:
                try:
                    self._ollama_proc.kill()
                except Exception:
                    pass

    def _ensure_ollama_installed(self) -> None:
        if shutil.which("ollama") is None:
            raise ValueError(
                "Ollama is not installed or not on PATH. Install it from https://ollama.com and try again."
            )

    def generate_ollama(
        self,
        content: str,
        system_prompt_override: Optional[str] = None,
    ) -> str:
        """Generate using the local Ollama HTTP API."""
        self._ensure_ollama_installed()
        self._start_ollama_server_if_needed()

        model = self.config["ollama"]["model"]
        temperature = self.config["ollama"]["temperature"]

        log.info("Using ollama model '%s'.", model)

        url = f"{self._ollama_base_url()}/api/chat"

        messages: list[dict[str, str]] = []
        if system_prompt_override:
            messages.append({"role": "system", "content": system_prompt_override})
        messages.append({"role": "user", "content": content})

        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        try:
            response = requests.post(url, json=request, timeout=300)
        except requests.RequestException as exc:
            raise ValueError(
                "Failed to reach Ollama. Ensure it is running (try: `ollama serve`)."
            ) from exc

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            # Try to surface Ollama's error message if possible.
            err = ""
            try:
                err = str(response.json().get("error", "")).strip()
            except Exception:
                err = response.text.strip()
            suffix = f" ({err})" if err else ""
            raise ValueError(
                f"Ollama request failed with HTTP {response.status_code}{suffix}."
            ) from exc

        data = response.json()

        # /api/chat format
        if isinstance(data, dict) and isinstance(data.get("message"), dict):
            out = str(data["message"].get("content", "")).strip()
            if out:
                return out

        # /api/generate fallback format (some setups proxy this endpoint)
        out = str(data.get("response", "")).strip() if isinstance(data, dict) else ""
        if out:
            return out

        raise ValueError("Ollama returned an empty response.")

    def generate_openai(
        self,
        content: str,
        openai_cls: Type[Any] = OpenAI,
        system_prompt_override: Optional[str] = None,
        base_url: Optional[str] = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        provider_name: str = "openai",
    ) -> str:
        """
        Shared OpenAI call for commit generation or commit history summarization.
        """
        client_kwargs = {"api_key": self.token}
        if base_url is not None:
            client_kwargs["base_url"] = base_url

        client = openai_cls(**client_kwargs)
        model = (
            model_override
            if model_override is not None
            else self.config["openai"]["model"]
        )
        temperature = (
            temperature_override
            if temperature_override is not None
            else self.config["openai"]["temperature"]
        )

        log.info("Using %s model '%s'.", provider_name, model)

        messages = [
            {"role": "system", "content": system_prompt_override},
            {"role": "user", "content": content},
        ]

        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=False,
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

        log.info("Using xai model '%s'.", model)

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
