"""
Use LLMs to generate git commit messages from diffs or multiple commits.
"""

import functools
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Dict, Optional, Type
from urllib.parse import urlparse

import requests
from git_cai_cli.core.config import CONFIG_DIR
from git_cai_cli.core.gitutils import classify_changed_paths, paths_from_diff
from git_cai_cli.core.languages import LANGUAGE_MAP
from git_cai_cli.core.prompts_fallback import (
    HARDCODED_COMMIT_PROMPT,
    HARDCODED_FULL_FILES_PROMPT,
    HARDCODED_PR_PROMPT,
    HARDCODED_SQUASH_PROMPT,
)
from openai import OpenAI
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)


_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
_RETRY_TOTAL = 3
_RETRY_BACKOFF_FACTOR = 0.5


def _build_retrying_session() -> requests.Session:
    """Build a requests.Session with urllib3-level retry/backoff.

    Retries idempotent and POST requests on 429 + 5xx with exponential
    backoff. ``raise_for_status`` is still required at the call site so
    final non-retried failures surface as ``requests.HTTPError`` for the
    central error classifier in ``validate.py``.
    """
    retry = Retry(
        total=_RETRY_TOTAL,
        backoff_factor=_RETRY_BACKOFF_FACTOR,
        status_forcelist=_RETRY_STATUS_CODES,
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    # http:// adapter is required for local Ollama (http://localhost:11434).
    session.mount(
        "http://",  # nosemgrep: python.lang.security.audit.insecure-transport.requests.request-session-with-http.request-session-with-http
        adapter,
    )
    session.mount("https://", adapter)
    return session


@functools.lru_cache(maxsize=1)
def _get_http_session() -> requests.Session:
    """Process-wide retrying session, built lazily on first use.

    ``lru_cache(maxsize=1)`` is used as a thread-safe singleton holder so
    we avoid the module-level mutable + ``global`` statement pattern.
    """
    return _build_retrying_session()


def _http_post(*args, **kwargs):
    """POST via the module-level retrying session.

    Single patch-point for tests; never uses ``requests.post`` directly so
    every provider call benefits from urllib3 retry/backoff on transient
    failures (429 / 5xx).
    """
    return _get_http_session().post(*args, **kwargs)


def load_prompt_file(
    config_key: str,
    config: Dict[str, Any],
    default_filename: str,
    hardcoded_fallback: str,
) -> str:
    """
    Load a prompt with a three-tier fallback strategy:

    1. User-defined file path from config (config_key).
    2. Default file in ~/.config/cai/<default_filename>.
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

    # 2) Try global config directory (~/.config/cai/)
    log.info("No local prompt file configured for '%s'.", config_key)
    global_path = CONFIG_DIR / default_filename
    if global_path.is_file():
        content = global_path.read_text(encoding="utf-8").strip()
        log.info(
            "Loading prompt from default file: %s",
            global_path,
        )
        log.debug("Default prompt loaded (%d characters).", len(content))
        return content

    # 3) Hardcoded fallback
    log.warning(
        "No prompt file found for config key '%s'. Using hardcoded fallback values.",
        config_key,
    )
    return hardcoded_fallback


class CommitMessageGenerator:
    """
    Generates git commit messages from diffs or from multiple commit messages.
    """

    def __init__(
        self,
        token: str | None,
        config: Dict[str, Any],
        default_model: str,
        *,
        branch_name: str | None = None,
    ):
        self.token = token
        self.config = config
        self.default_model = default_model
        self.branch_name = branch_name

        # Mutated by callers (main / squash / pr) before generation so
        # the resulting stats row carries the right kind/repo. Default
        # "commit" because that is the most common entry point.
        self.kind: str = "commit"
        self.repo: str | None = None

        # Per-run secret-scan bypass: set true by --allow-secrets or after the
        # user confirms an interactive "send anyway".
        self.allow_secrets: bool = False
        # (non_doc, doc) file counts for the active generation, used by
        # ``_classification_instruction``. Set by ``generate`` /
        # ``generate_pr_description`` or by the squash caller.
        self._classification_counts: tuple[int, int] | None = None

        # Set by the provider methods around each HTTP call so
        # ``_log_token_usage`` can persist real latency data.
        # ``_last_event_id`` is the row id from the most recent
        # stats.record() — used by ``record_elapsed`` to patch in the
        # user-perceived elapsed time once the caller knows it.
        self._last_latency_ms: int | None = None
        self._last_event_id: int | None = None

        # Ollama lifecycle tracking (only used when provider == "ollama")
        self._ollama_proc: subprocess.Popen[str] | None = None
        self._ollama_started_by_us: bool = False

    def close(self) -> None:
        """Release resources started by this generator (best-effort)."""
        self._stop_ollama_server_if_started_by_us()

    def _timeout(self, provider: str) -> int:
        """Resolve the HTTP timeout (seconds) for a given provider.

        Per-provider override (e.g. `ollama.timeout: 300`) wins over the global
        `timeout` key. Falls back to 30s for remote providers and 300s for
        Ollama when nothing is configured.
        """
        provider_block = self.config.get(provider)
        if isinstance(provider_block, dict) and "timeout" in provider_block:
            return int(provider_block["timeout"])

        if "timeout" in self.config:
            return int(self.config["timeout"])

        return 300 if provider == "ollama" else 30

    _PROMPT_FILE_KEY_BY_KIND: Dict[str, str] = {
        "commit": "prompt_file",
        "amend": "prompt_file",
        "squash": "squash_prompt_file",
        "pr": "pr_prompt_file",
    }

    def _settings_snapshot(self, provider: str) -> Dict[str, Any]:
        """Snapshot of the user-visible generation settings for the
        active call. Empty/missing values become ``None`` so the stats
        row reflects "not set" rather than a default lie."""
        cfg = self.config

        emoji_raw = cfg.get("emoji")
        emoji_val: bool | None
        if emoji_raw is None:
            emoji_val = None
        else:
            emoji_val = bool(emoji_raw)

        temperature_val: float | None = None
        block = cfg.get(provider)
        if isinstance(block, dict):
            temp = block.get("temperature")
            if isinstance(temp, (int, float)):
                temperature_val = float(temp)

        # Full-files mode swaps the commit prompt file for a dedicated
        # one — surface that when active, regardless of kind.
        if self.kind in ("commit", "amend") and cfg.get("full_files"):
            prompt_key = "full_files_prompt_file"
        else:
            prompt_key = self._PROMPT_FILE_KEY_BY_KIND.get(self.kind, "prompt_file")
        prompt_file_raw = cfg.get(prompt_key)
        prompt_file_val: str | None = None
        if isinstance(prompt_file_raw, (str, Path)):
            text = str(prompt_file_raw).strip()
            prompt_file_val = text or None

        language_raw = cfg.get("language")
        language_val = str(language_raw) if language_raw else None

        style_raw = cfg.get("style")
        style_val = str(style_raw) if style_raw else None

        return {
            "language": language_val,
            "style": style_val,
            "emoji": emoji_val,
            "temperature": temperature_val,
            "prompt_file": prompt_file_val,
        }

    def _log_token_usage(
        self,
        provider: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> None:
        """Log token usage if token_logging is enabled, and record an
        analytics event if `stats: true` is set in config (FB.11)."""
        # Stats recording — best-effort, never raises. Routed before
        # token_logging short-circuit so analytics still capture even
        # when token_logging is off.
        try:
            from git_cai_cli.core import stats

            model = None
            block = self.config.get(provider)
            if isinstance(block, dict):
                model = block.get("model")
            self._last_event_id = stats.record(
                config=self.config,
                kind=self.kind,
                provider=provider,
                model=model,
                tokens_in=prompt_tokens,
                tokens_out=completion_tokens,
                latency_ms=self._last_latency_ms,
                repo=self.repo,
                **self._settings_snapshot(provider),
            )
        except (ImportError, AttributeError, TypeError, KeyError) as exc:
            log.debug("stats.record failed (non-fatal): %s", exc)

        if not self.config.get("token_logging", False):
            return
        if prompt_tokens is None and completion_tokens is None:
            log.debug(  # nosemgrep
                "Token usage not available for provider '%s'.", provider  # nosemgrep
            )  # nosemgrep
            return
        total = (prompt_tokens or 0) + (completion_tokens or 0)
        log.info(  # nosemgrep
            "Token usage [%s]: prompt=%s, completion=%s, total=%d",  # nosemgrep
            provider,  # nosemgrep
            prompt_tokens if prompt_tokens is not None else "n/a",  # nosemgrep
            completion_tokens if completion_tokens is not None else "n/a",  # nosemgrep
            total,  # nosemgrep
        )

    def record_elapsed(self, time_ms: int | None) -> None:
        """Patch the most recent stats event with the user-perceived
        elapsed time. Best-effort no-op when stats are disabled or no
        event has been recorded for this generator yet."""
        try:
            from git_cai_cli.core import stats

            stats.set_time_ms(self.config, self._last_event_id, time_ms)
        except (ImportError, AttributeError, TypeError, KeyError) as exc:
            log.debug("stats.set_time_ms failed (non-fatal): %s", exc)

    def set_changed_files(self, paths: list[str]) -> None:
        """Record changed paths so the mixed code/docs instruction uses real counts.

        Public so squash/PR callers (which know the changed file set from a commit
        range) can supply it without poking at internal state.
        """
        self._classification_counts = classify_changed_paths(paths)

    def _log_target(self) -> None:
        """Log the active provider and model once, up front.

        Call sites run this *before* starting the spinner so this routine
        config noise does not interleave with the spinner's live frames —
        interleaving would break the spinner line and make a single
        generation look like two. The per-provider methods log the same
        detail at DEBUG.
        """
        model = (self.config.get(self.default_model) or {}).get("model")
        log.info("Using provider '%s' (model '%s').", self.default_model, model)

    def send(self, content: str, system_prompt: str) -> str:
        """Run the secret scan and dispatch a prebuilt request to the LLM.

        This is the network-bound half of generation — the part worth
        wrapping in a spinner. Prompt building (and its logging) happens
        earlier in the matching ``build_*_request`` method.
        """
        return self._dispatch_generate(content=content, system_prompt=system_prompt)

    def build_commit_request(
        self,
        git_diff: str,
        context: str | None = None,
        previous_message: str | None = None,
    ) -> tuple[str, str]:
        """Build the ``(content, system_prompt)`` pair for a commit message.

        Split out from :meth:`generate` so prompt building runs before the
        spinner starts. ``previous_message`` is used in amend mode.
        """
        self._log_target()
        self.set_changed_files(paths_from_diff(git_diff))
        prompt = self._build_commit_prompt(previous_message=previous_message)
        log.debug("Commit system prompt preview: %r", prompt[:400])

        content = git_diff
        if context:
            content = (
                f"{git_diff}\n\n"
                f"--- Additional context from the author ---\n{context}"
            )
        return content, prompt

    def generate(
        self,
        git_diff: str,
        context: str | None = None,
        previous_message: str | None = None,
    ) -> str:
        """
        Generate a commit message from a diff.

        ``previous_message`` is used in amend mode so the model refines the
        existing message instead of regenerating from scratch.
        """
        content, prompt = self.build_commit_request(
            git_diff, context=context, previous_message=previous_message
        )
        return self.send(content, prompt)

    def build_squash_request(
        self, commit_messages: str, context: str | None = None
    ) -> tuple[str, str]:
        """Build the ``(content, system_prompt)`` pair for a squash summary."""
        self._log_target()
        prompt = self._build_squash_prompt()
        log.debug("Squash system prompt preview: %r", prompt[:400])

        content = commit_messages
        if context:
            content = (
                f"{commit_messages}\n\n"
                f"--- Additional context from the author ---\n{context}"
            )
        return content, prompt

    def summarize_commit_history(
        self, commit_messages: str, context: str | None = None
    ) -> str:
        """
        Summarize multiple commit messages into one high-level commit message.
        """
        content, prompt = self.build_squash_request(commit_messages, context=context)
        return self.send(content, prompt)

    def build_pr_request(
        self,
        commit_log: str,
        changed_files: str,
        context: str | None = None,
    ) -> tuple[str, str]:
        """Build the ``(content, system_prompt)`` pair for a PR description."""
        self._log_target()
        self.set_changed_files(changed_files.splitlines())
        prompt = self._build_pr_prompt()
        log.debug("PR system prompt preview: %r", prompt[:400])

        sections = [
            "--- Commit log ---",
            commit_log.strip() or "(no commits)",
            "",
            "--- Changed files ---",
            changed_files.strip() or "(no files)",
        ]
        content = "\n".join(sections)
        if context:
            content = (
                f"{content}\n\n"
                f"--- Additional context from the author ---\n{context}"
            )
        return content, prompt

    def generate_pr_description(
        self,
        commit_log: str,
        changed_files: str,
        context: str | None = None,
    ) -> str:
        """
        Generate a Markdown Pull Request description from the commit log and
        changed-files list of a feature branch.
        """
        content, prompt = self.build_pr_request(
            commit_log, changed_files, context=context
        )
        return self.send(content, prompt)

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
                "Use relevant emojis at the start of the headline and in bullet points "
                "where they add clarity. Keep emojis purposeful — one per bullet at most."
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

        return f"Write the commit message in the following tone style: {style}. Apply this tone to both the headline and the bullet points."

    def _conventional_instruction(self) -> str:
        """
        Returns a Conventional Commits instruction string if enabled, else empty.
        """
        if not self.config.get("conventional", False):
            return ""

        log.info("Conventional Commits format enabled.")
        return (
            "Follow the Conventional Commits specification. "
            "The headline MUST be structured as: <type>(<optional scope>): <description>. "
            "Allowed types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert. "
            "The scope is optional and describes the section of the codebase affected. "
            "Use a '!' after the type/scope for breaking changes (e.g., 'feat!: ...' or 'feat(api)!: ...'). "
            "The description must be a concise summary in imperative mood, lowercase, no trailing period. "
            "Additional details follow as bullet points in the body after a blank line. "
            "If every changed file in the diff is a documentation file "
            "(a `*.md` file or a file under `docs/`), the type MUST be `docs`."
        )

    def _branch_instruction(self) -> str:
        """
        Returns a branch context instruction string if enabled and branch name is available.
        """
        if not self.config.get("branch_context", False):
            return ""

        branch_name = self.branch_name or ""
        if not branch_name:
            return ""

        log.info("Branch context enabled: '%s'.", branch_name)
        return (
            f"The current Git branch is '{branch_name}'. "
            "Use the branch name as additional context to infer the intent "
            "and scope of the changes — but do not include the branch name in the message."
        )

    def _classification_instruction(self) -> str:
        """Guidance for mixed code+docs diffs so they are not labelled as docs.

        Emitted only for the genuinely mixed case (both code and doc files
        changed); docs-only relies on the existing hardcoded rule and code-only
        needs nothing. The live file counts cannot live in a static prompt, so
        this is injected at build time like the other instructions.
        """
        counts = self._classification_counts
        if not counts:
            return ""
        non_doc, doc = counts
        if non_doc > 0 and doc > 0:
            return (
                f"This change touches {non_doc} non-documentation file(s) and "
                f"{doc} documentation file(s). Classify by the functional change "
                "(feat/fix/refactor and similar), not the documentation. Lead the "
                "subject with the code change and mention documentation updates "
                "only secondarily in the body."
            )
        return ""

    def _amend_instruction(self, previous_message: str) -> str:
        """Instruct the model to refine the existing commit message, not replace it."""
        return (
            "An existing commit message is shown below. Improve its clarity and "
            "accuracy against the diff while preserving its original intent and any "
            "deliberate references (issue IDs, `Co-authored-by`, other trailers). "
            "Refine the wording; do not discard information.\n\n"
            "--- Existing commit message ---\n"
            f"{previous_message.strip()}"
        )

    def _config_instructions(self) -> str:
        """
        Build the config-driven instruction suffix (language, style, emoji, conventional).
        Only non-empty parts are included.
        """
        parts = [
            self._language_instruction(),
            self._style_instruction(),
            self._emoji_instruction(),
            self._conventional_instruction(),
            self._branch_instruction(),
            self._classification_instruction(),
        ]
        return " ".join(p for p in parts if p)

    # ---------------------------
    # PROMPTS
    # ---------------------------

    def _build_commit_prompt(self, previous_message: str | None = None) -> str:
        """
        Build the full commit prompt by loading the base prompt from file
        (with fallback) and appending config-driven instructions.

        When `full_files` is enabled in the config, the full-files prompt
        is used instead of the regular commit prompt so the LLM knows it
        receives complete file contents alongside the diff.

        In amend mode, ``previous_message`` is appended so the model refines
        the existing message rather than regenerating it.
        """
        if self.config.get("full_files", False):
            base = load_prompt_file(
                config_key="full_files_prompt_file",
                config=self.config,
                default_filename="full_files_prompt.md",
                hardcoded_fallback=HARDCODED_FULL_FILES_PROMPT,
            )
        else:
            base = load_prompt_file(
                config_key="prompt_file",
                config=self.config,
                default_filename="commit_prompt.md",
                hardcoded_fallback=HARDCODED_COMMIT_PROMPT,
            )

        parts = [base.rstrip()]
        suffix = self._config_instructions()
        if suffix:
            parts.append(suffix.lstrip())
        if self.kind == "amend" and previous_message and previous_message.strip():
            parts.append(self._amend_instruction(previous_message))
        prompt = "\n\n".join(parts)

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
            hardcoded_fallback=HARDCODED_SQUASH_PROMPT,
        )

        suffix = self._config_instructions()
        if suffix:
            prompt = "\n\n".join([base.rstrip(), suffix.lstrip()])
        else:
            prompt = base

        log.debug("Final squash prompt (%d characters).", len(prompt))
        return prompt

    def _build_pr_prompt(self) -> str:
        """
        Build the PR description prompt by loading the base prompt from file
        (with fallback) and appending universal style instructions.

        Only language/style/emoji are appended. `conventional` and
        `branch_context` are commit-message specific (no `feat(scope):`
        headline; branch intent is irrelevant to summarizing commits) and
        are deliberately excluded.
        """
        base = load_prompt_file(
            config_key="pr_prompt_file",
            config=self.config,
            default_filename="pr_prompt.md",
            hardcoded_fallback=HARDCODED_PR_PROMPT,
        )

        parts = [
            self._language_instruction(),
            self._style_instruction(),
            self._emoji_instruction(),
            self._classification_instruction(),
        ]
        suffix = " ".join(p for p in parts if p)
        prompt = "\n\n".join([base.rstrip(), suffix.lstrip()]) if suffix else base

        log.debug("Final PR prompt (%d characters).", len(prompt))
        return prompt

    # Keep old method names as aliases for backward compatibility in tests
    def _system_prompt(self, _language_name: str | None = None) -> str:
        """
        Legacy method — builds the commit prompt with config instructions.
        Kept for backward compatibility.
        """
        return self._build_commit_prompt()

    def _summary_prompt(self, _language_name: str | None = None) -> str:
        """
        Legacy method — builds the squash prompt with config instructions.
        Kept for backward compatibility.
        """
        return self._build_squash_prompt()

    # ---------------------------
    # DISPATCH
    # ---------------------------

    def _scan_for_secrets(self, content: str) -> None:
        """Block the send if the exact payload contains likely secrets.

        Skipped when the user bypassed (``--allow-secrets`` / confirmed), when
        scanning is disabled in config, or for tokenless providers where nothing
        leaves the machine.
        """
        if self.allow_secrets:
            return
        if not self.config.get("secret_scan", True):
            return
        from git_cai_cli.core.config import TOKENLESS_PROVIDERS

        if self.default_model in TOKENLESS_PROVIDERS:
            return

        from git_cai_cli.core.secrets import (
            SecretLeakError,
            drop_excluded,
            scan_for_secrets,
        )

        findings = scan_for_secrets(content)

        # Files listed in `secret_scan_exclude` stay part of the payload but
        # are exempt from the scan (false alarms the user already vetted).
        # Matched with gitignore semantics for parity with `.caiignore`.
        excludes = self.config.get("secret_scan_exclude") or []
        if findings and excludes:
            import pathspec

            spec = pathspec.GitIgnoreSpec.from_lines(excludes)
            findings = drop_excluded(findings, spec.match_file)

        if findings:
            raise SecretLeakError(findings)

    def _dispatch_generate(self, content: str, system_prompt: str) -> str:
        """
        Route to correct model with the right prompt. System prompt is
        _system_prompt or _summary_prompt depending on use case.
        Content is output of git diff.
        """
        self._scan_for_secrets(content)

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

        log.debug("Using provider '%s' for generation.", self.default_model)

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
        # ``max_output_tokens`` is the canonical config key (consistent
        # naming across providers); ``max_tokens`` is kept for backwards
        # compatibility with existing user configs.
        anthropic_cfg = self.config["anthropic"]
        max_tokens = int(
            anthropic_cfg.get("max_output_tokens")
            or anthropic_cfg.get("max_tokens", 32768)
        )

        log.debug("Using anthropic model '%s'.", model)

        # Anthropic Messages API expects system prompt via the top-level "system" field.
        messages = [{"role": "user", "content": content}]

        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }

        if system_prompt_override:
            request["system"] = system_prompt_override

        start = time.perf_counter()
        response = _http_post(  # nosec B113
            url, json=request, headers=headers, timeout=self._timeout("anthropic")
        )
        self._last_latency_ms = int((time.perf_counter() - start) * 1000)
        response.raise_for_status()

        data = response.json()

        usage = data.get("usage") or {}
        self._log_token_usage(
            "anthropic",
            usage.get("input_tokens"),
            usage.get("output_tokens"),
        )

        return data["content"][0]["text"].strip()

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

        log.debug("Using gemini model '%s'.", model)

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

        start = time.perf_counter()
        response = _http_post(  # nosec B113
            url, json=request, headers=headers, timeout=self._timeout("gemini")
        )
        self._last_latency_ms = int((time.perf_counter() - start) * 1000)
        response.raise_for_status()

        data = response.json()

        usage = data.get("usageMetadata") or {}
        self._log_token_usage(
            "gemini",
            usage.get("promptTokenCount"),
            usage.get("candidatesTokenCount"),
        )

        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

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

        log.debug("Using groq model '%s'.", model)

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

        start = time.perf_counter()
        response = _http_post(  # nosec B113
            url, json=request, headers=headers, timeout=self._timeout("groq")
        )
        self._last_latency_ms = int((time.perf_counter() - start) * 1000)
        response.raise_for_status()

        data = response.json()

        usage = data.get("usage") or {}
        self._log_token_usage(
            "groq",
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )

        return data["choices"][0]["message"]["content"].strip()

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

        log.debug("Using mistral model '%s'.", model)

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

        start = time.perf_counter()
        response = _http_post(  # nosec B113
            url, json=request, headers=headers, timeout=self._timeout("mistral")
        )
        self._last_latency_ms = int((time.perf_counter() - start) * 1000)
        response.raise_for_status()

        data = response.json()

        usage = data.get("usage") or {}
        self._log_token_usage(
            "mistral",
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )

        return data["choices"][0]["message"]["content"].strip()

    def _ollama_startup_timeout(self) -> float:
        """Seconds to wait for ``ollama serve`` to come up. Configurable
        per-user since first-load of large models can exceed the default."""
        ollama_cfg = self.config.get("ollama") or {}
        if isinstance(ollama_cfg, dict):
            value = ollama_cfg.get("startup_timeout")
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
        return 8.0

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
            popen_kwargs: Dict[str, Any] = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "text": True,
            }
            # ``start_new_session`` is POSIX-only; using it on Windows
            # raises ValueError. We need it on POSIX so we can later
            # killpg() the whole process group, but we have no equivalent
            # on Windows — fall back to per-process termination there.
            if sys.platform != "win32":
                popen_kwargs["start_new_session"] = True
            try:
                self._ollama_proc = (
                    subprocess.Popen(  # pylint: disable=consider-using-with
                        ["ollama", "serve"],
                        **popen_kwargs,
                    )
                )
            except OSError as exc:
                raise ValueError("Failed to start Ollama server.") from exc
            self._ollama_started_by_us = True

        startup_timeout = self._ollama_startup_timeout()
        deadline = time.time() + startup_timeout
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

        # POSIX: terminate the process group so child workers exit too.
        # Windows: no killpg, just terminate the parent process.
        posix = sys.platform != "win32"
        try:
            if posix:
                os.killpg(self._ollama_proc.pid, signal.SIGTERM)
            else:
                self._ollama_proc.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                self._ollama_proc.terminate()
            except (ProcessLookupError, OSError):
                return

        try:
            self._ollama_proc.wait(timeout=2)
            log.info("Ollama server stopped successfully.")
        except subprocess.TimeoutExpired:
            try:
                if posix:
                    os.killpg(self._ollama_proc.pid, signal.SIGKILL)
                else:
                    self._ollama_proc.kill()
                log.info("Ollama server killed successfully.")
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    self._ollama_proc.kill()
                    log.info("Ollama server killed successfully (fallback).")
                except (ProcessLookupError, OSError):
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

        log.debug("Using ollama model '%s'.", model)

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

        start = time.perf_counter()
        try:
            response = _http_post(  # nosec B113
                url, json=request, timeout=self._timeout("ollama")
            )
        except requests.RequestException as exc:
            raise ValueError(
                "Failed to reach Ollama. Ensure it is running (try: `ollama serve`)."
            ) from exc
        self._last_latency_ms = int((time.perf_counter() - start) * 1000)

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            # Try to surface Ollama's error message if possible.
            err = ""
            try:
                err = str(response.json().get("error", "")).strip()
            except ValueError:
                err = response.text.strip()
            suffix = f" ({err})" if err else ""
            raise ValueError(
                f"Ollama request failed with HTTP {response.status_code}{suffix}."
            ) from exc

        data = response.json()

        # Extract token usage from Ollama response
        self._log_token_usage(
            "ollama",
            data.get("prompt_eval_count") if isinstance(data, dict) else None,
            data.get("eval_count") if isinstance(data, dict) else None,
        )

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
        client_kwargs: dict[str, Any] = {"api_key": self.token}
        if base_url is not None:
            client_kwargs["base_url"] = base_url
        client_kwargs["timeout"] = self._timeout(provider_name)

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

        log.debug("Using %s model '%s'.", provider_name, model)

        messages = []

        if system_prompt_override:
            messages.append({"role": "system", "content": system_prompt_override})

        messages.append({"role": "user", "content": content})

        start = time.perf_counter()
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=False,
        )
        self._last_latency_ms = int((time.perf_counter() - start) * 1000)

        usage = completion.usage
        self._log_token_usage(
            provider_name,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )

        # Some models (e.g. reasoning models that hit a stop/refusal) return
        # ``None`` content; ``.strip()`` on that would raise AttributeError.
        # Surface a clean ValueError that ``_validate_llm_call`` can classify.
        content_out = completion.choices[0].message.content
        if not content_out:
            raise ValueError(f"{provider_name} returned an empty response.")

        return content_out.strip()

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

        log.debug("Using xai model '%s'.", model)

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
        start = time.perf_counter()
        response = _http_post(  # nosec B113
            url, json=request, headers=headers, timeout=self._timeout("xai")
        )
        self._last_latency_ms = int((time.perf_counter() - start) * 1000)
        response.raise_for_status()

        data = response.json()

        usage = data.get("usage") or {}
        self._log_token_usage(
            "xai",
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )

        return data["choices"][0]["message"]["content"].strip()

    # ---------------------------
    # LANGUAGE HELPER
    # ---------------------------

    def _language_name(self, lang_code: str, allowed_languages: dict[str, str]) -> str:
        return allowed_languages.get(lang_code, "English")
