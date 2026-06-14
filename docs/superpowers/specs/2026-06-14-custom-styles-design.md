# Custom styles + richer built-in style guidance — Design

**Date:** 2026-06-14
**Branch:** `fix/style-option`
**Status:** Approved

## Goal

Extend the commit-message `style` option in two ways:

- **A — User-defined custom styles:** let users define their own styles in
  `cai_config.yml` via a `custom_styles` map, so individuals and teams can add
  tones beyond the shipped set without code changes.
- **C — Richer built-in style guidance:** replace the single generic style
  instruction with a per-style prompt fragment, so each style (built-in or
  custom) contributes real tone guidance to the prompt.
- **E — Single registry (cleanup):** consolidate the built-in style data, which
  today is split between the allowlist in `validate.py` and the
  descriptions/examples in `options.py::styles()`, into one source of truth.
- **F — Override flag ergonomics:** give the invocation-override options short
  flags and make them visible in `git cai -h`. Today `--style`, `--language`,
  `--emoji`, and `--temperature` are long-only **and** absent from the
  hand-maintained help text (`cli/helptext.py`).

## Background (current behaviour)

- `_validate_style()` (`core/validate.py`) checks a hardcoded allowlist:
  `professional, neutral, friendly, funny, excited, sarcastic, apologetic,
  academic`, plus `none` (disables the style instruction).
- `_style_instruction()` (`core/llm.py`) emits one generic line for every
  style: *"Write the commit message in the following tone style: {style}.
  Apply this tone to both the headline and the bullet points."*
- `options.py::styles()` holds per-style `description` and `example` used by
  `git cai -l style`, hand-synced with the allowlist.

## Decisions

1. **Custom style entry shape (Option 3 — hybrid):** `instruction` is required;
   `description` and `example` are optional.
2. **Built-in names are protected (Option 2):** a `custom_styles` key that
   collides with a built-in name or with `none` is a config validation error.
3. **Prompt assembly (Option 3):** the style's `instruction` leads, followed by
   a fixed suffix: `"{instruction} Apply this tone to both the headline and the
   bullet points."`
4. **Listing (Option 1 — merged + marker):** `git cai -l style` shows built-in
   and custom styles in one list; custom entries are tagged `name (custom)`.
5. **Override short flags (F):** the invocation-override options get short flags
   and are added to the help text — `-y/--style`, `-e/--emoji`, `-L/--language`,
   `-E/--temperature`. `--temperature` previously used `-e`; it moves to `-E` so
   `--emoji` can take the mnemonic `-e`. `-L` and `-E` each differ from an
   existing flag (`-l/--list`, `-e`) only by case, which Typer/Click handle.

## Components

### 1. `core/styles.py` (new — single registry)

Dependency-free module (same rationale as `prompts_fallback.py`: importable by
`config`, `validate`, `llm`, `options` without creating import cycles). Single
source of truth for built-in styles, each carrying all three fields:

```python
BUILTIN_STYLES: dict[str, dict[str, str]] = {
    "professional": {
        "instruction": "Write in a clear, concise, and formal tone.",
        "description": "Clear, concise, and formal. Default style.",
        "example": "...",
    },
    # neutral, friendly, funny, excited, sarcastic, apologetic, academic
}

RESERVED_STYLE_NAMES = set(BUILTIN_STYLES) | {"none"}
```

Replaces the allowlist in `validate.py` and the inline descriptions/examples in
`options.py::styles()`.

### 2. Config — `custom_styles` key

- New top-level key in `DEFAULT_CONFIG`, default `{}`; documented in
  `cai_config.yml`.
- Repo config remains authoritative (per `CLAUDE.md`), so a repo can ship a
  house style set.
- Entry shape: `instruction` required; `description`, `example` optional.

Example:

```yaml
custom_styles:
  sardonic:
    instruction: "Use dry, ironic understatement; keep the subject imperative."
    description: "Dry, ironic tone."   # optional
    example: "Heroically fixed the bug we wrote yesterday."  # optional
```

### 3. Validation (`core/validate.py`)

- **`_validate_custom_styles(custom_styles)`** (new): for each entry —
  - key is a non-empty string and **not** in `RESERVED_STYLE_NAMES`
    (collision → `ValueError`);
  - value has a non-empty `instruction`;
  - `description` / `example`, if present, are strings.
  Called during config load; fails fast with a message naming the offending key
  and the problem.
- **`_validate_style(style, custom_names)`**: signature gains the set of
  configured custom style names. Accepts built-ins, `none`, or any custom name;
  otherwise raises with the merged allowed list. Call sites in `config.py`
  (default load and `--style` override) already have `custom_styles` available
  and pass the names through.

### 4. Prompt assembly (`core/llm.py::_style_instruction`)

Look up the active style in `BUILTIN_STYLES` merged with config `custom_styles`,
then:

```python
return f"{entry['instruction']} Apply this tone to both the headline and the bullet points."
```

`none` / `None` → `""` (unchanged). The old generic hardcoded line is removed;
every style now contributes its own flavor plus the fixed suffix.

### 5. Listing (`core/options.py::styles`)

Build the returned dict from `BUILTIN_STYLES` + config `custom_styles`. Custom
entries are tagged `name (custom)`. When `description` is absent, fall back to
the `instruction` text; when `example` is absent, omit the example line.

### 6. CLI short flags + help visibility (`cli/cli.py`, `cli/helptext.py`)

- Update the override `typer.Option` definitions in `cli.py`:
  - `--style` → add `"-y"`
  - `--emoji` → add `"-e"`
  - `--language` → add `"-L"`
  - `--temperature` → change its existing `"-e"` to `"-E"` (freeing `-e` for
    emoji)
- Add the four flags to the hand-maintained `HELP_TEXT` in `helptext.py`, in
  the alphabetical position used by the existing list, e.g.:

  ```text
  -E, --temperature FLOAT  Override the active provider's sampling temperature for this invocation
  -e, --emoji              Toggle emoji prefixes (use --no-emoji to disable)
  -L, --language CODE      Override the commit message language (e.g. de, fr, none)
  -y, --style NAME         Override the commit message style (e.g. funny, neutral, none)
  ```

  The `-l, --list` line already documents `style` as a list type and stays as
  is.

## Data flow

```text
cai_config.yml (custom_styles)
        │
        ▼
config load ──► _validate_custom_styles()         (structure + collisions)
        │
        ├──► _validate_style(style, custom_names)  (default + --style override)
        │
        ▼
config["style"], config["custom_styles"]
        │
        ├──► llm._style_instruction()  → "{instruction} <suffix>"  (BUILTIN_STYLES ∪ custom)
        │
        └──► options.styles()          → merged list with (custom) markers
```

## Error handling

An invalid `custom_styles` block fails fast at config load with a clear message
(which key, what is wrong), consistent with how `_validate_style` already
reports invalid styles. An unknown `--style` value raises with the merged
allowed list (built-ins + `none` + configured custom names).

## Testing

All mocked — no real API/HTTP calls (CI has no creds; tokens cost money):

- `_validate_custom_styles`: happy path; missing/empty `instruction`;
  collision with a built-in name; collision with `none`; non-string optional
  fields.
- `_validate_style`: accepts a configured custom name; rejects an unknown name
  with the merged allowed list in the message.
- `_style_instruction`: builds `"{instruction} <suffix>"` for a built-in, for a
  custom style, and returns `""` for `none` / `None`.
- `options.styles()`: merges built-ins + custom; applies `(custom)` marker;
  falls back `description → instruction`; omits `example` when absent.
- CLI short flags: invoking with `-y`, `-e`, `-L`, `-E` is parsed equivalently
  to the long form (via Typer's `CliRunner`, no network), and `git cai -h`
  output contains all four override flags.

## Documentation

Update **`docs/git-cai.txt` only** (per standing preference — do not touch
`docs/man/git-cai.1`, `README.md`, or `CLAUDE.md` unless asked): document the
`custom_styles` key and entry shape, and the new `-y/-e/-L/-E` override short
flags.

## Out of scope (YAGNI)

- Overriding/retuning built-in styles via config (built-ins are protected).
- Free-form passthrough of arbitrary style strings (rejected in favor of an
  explicit custom registry).
- `random`/surprise style selection.
