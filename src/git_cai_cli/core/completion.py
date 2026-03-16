"""
Shell completion for git-cai.

Generates and installs completion scripts that work for both
`git-cai` (direct) and `git cai` (as a git subcommand).
"""

import logging
import os
from pathlib import Path

import typer

log = logging.getLogger(__name__)

# Zsh completion script.
# Placed in fpath as _git-cai, zsh's git completion auto-discovers it
# for `git cai <TAB>`. Also registers via compdef for `git-cai <TAB>`.
_ZSH_SCRIPT = """\
#compdef git-cai

_git-cai() {
  local -a options
  options=(
    '(-h --help)'{-h,--help}'[Show help]'
    '(-v --version)'{-v,--version}'[Show version]'
    '(-a --all)'{-a,--all}'[Stage all tracked files]'
    '(-c --crazy)'{-c,--crazy}'[Commit immediately without editor]'
    '(-d --debug)'{-d,--debug}'[Enable debug logging]'
    '(-g --generate-config)'{-g,--generate-config}'[Generate default config]'
    '(-i --install-completion)'{-i,--install-completion}'[Install shell completion]'
    '(-l --list)'{-l,--list}'[List information]'
    '(-m --model)'{-m,--model}'[Override model (requires --provider)]:model:'
    '(-p --generate-prompts)'{-p,--generate-prompts}'[Generate default prompts]'
    '(-s --squash)'{-s,--squash}'[Squash commits on this branch]'
    '(-t --time)'{-t,--time}'[Measure generation time]'
    '(-u --update)'{-u,--update}'[Check for updates]'
    '(-P --provider)'{-P,--provider}'[Override LLM provider]:provider:(anthropic deepseek gemini groq mistral ollama openai xai)'
  )
  _arguments -s -S $options
}

_git-cai "$@"
"""

# Bash completion script.
_BASH_SCRIPT = """\
_git_cai_completion() {
    local cur opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    opts="-h --help -v --version -a --all -c --crazy -d --debug \\
          -g --generate-config -i --install-completion -l --list \\
          -m --model -p --generate-prompts -s --squash -t --time \\
          -u --update -P --provider"

    if [[ "${COMP_WORDS[COMP_CWORD-1]}" == "--provider" || \\
          "${COMP_WORDS[COMP_CWORD-1]}" == "-P" ]]; then
        local providers="anthropic deepseek gemini groq mistral ollama openai xai"
        COMPREPLY=( $(compgen -W "$providers" -- "$cur") )
        return 0
    fi

    COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
    return 0
}

complete -o default -F _git_cai_completion git-cai

# Also register for 'git cai' via git's bash completion mechanism
__git_cai() {
    _git_cai_completion
}
"""

# Fish completion script.
_FISH_SCRIPT = """\
# Completions for git-cai / git cai
complete -c git-cai -s h -l help -d 'Show help'
complete -c git-cai -s v -l version -d 'Show version'
complete -c git-cai -s a -l all -d 'Stage all tracked files'
complete -c git-cai -s c -l crazy -d 'Commit immediately without editor'
complete -c git-cai -s d -l debug -d 'Enable debug logging'
complete -c git-cai -s g -l generate-config -d 'Generate default config'
complete -c git-cai -s i -l install-completion -d 'Install shell completion'
complete -c git-cai -s l -l list -d 'List information'
complete -c git-cai -s m -l model -d 'Override model' -r
complete -c git-cai -s p -l generate-prompts -d 'Generate default prompts'
complete -c git-cai -s s -l squash -d 'Squash commits on this branch'
complete -c git-cai -s t -l time -d 'Measure generation time'
complete -c git-cai -s u -l update -d 'Check for updates'
complete -c git-cai -s P -l provider -d 'Override LLM provider' -r -a 'anthropic deepseek gemini groq mistral ollama openai xai'
"""


def _detect_shell() -> str:
    """Detect the current shell."""
    shell = os.environ.get("SHELL", "")
    return os.path.basename(shell) if shell else "bash"


def install_completion() -> None:
    """Install shell completion for git-cai."""
    shell = _detect_shell()

    if shell == "zsh":
        _install_zsh()
    elif shell == "bash":
        _install_bash()
    elif shell == "fish":
        _install_fish()
    else:
        typer.echo(
            f"Unsupported shell '{shell}'. Supported: bash, zsh, fish.", err=True
        )
        raise typer.Exit(code=1)


def _install_zsh() -> None:
    """Install zsh completion."""
    # Determine the target directory
    zfunc_dir = Path.home() / ".zfunc"
    zfunc_dir.mkdir(parents=True, exist_ok=True)

    target = zfunc_dir / "_git-cai"
    target.write_text(_ZSH_SCRIPT, encoding="utf-8")

    # Check if ~/.zfunc is in fpath via .zshrc
    zshrc = Path.home() / ".zshrc"
    fpath_line = "fpath=(~/.zfunc $fpath)"

    needs_fpath = True
    if zshrc.exists():
        content = zshrc.read_text(encoding="utf-8")
        if ".zfunc" in content:
            needs_fpath = False

    if needs_fpath:
        with zshrc.open("a", encoding="utf-8") as f:
            f.write(
                f"\n# git-cai completion\n{fpath_line}\nautoload -Uz compinit && compinit\n"
            )
        typer.echo(f"Added {fpath_line} to {zshrc}")

    typer.echo(f"zsh completion installed in {target}.")
    typer.echo("Restart your terminal or run: source ~/.zshrc")


def _install_bash() -> None:
    """Install bash completion."""
    # Try system completions dir first, fall back to user dir
    comp_dir = Path.home() / ".local" / "share" / "bash-completion" / "completions"
    comp_dir.mkdir(parents=True, exist_ok=True)

    target = comp_dir / "git-cai"
    target.write_text(_BASH_SCRIPT, encoding="utf-8")

    # Check if the completion dir is sourced
    bashrc = Path.home() / ".bashrc"
    source_line = f"[ -f {target} ] && source {target}"

    needs_source = True
    if bashrc.exists():
        content = bashrc.read_text(encoding="utf-8")
        if "git-cai" in content or str(comp_dir) in content:
            needs_source = False

    if needs_source:
        with bashrc.open("a", encoding="utf-8") as f:
            f.write(f"\n# git-cai completion\n{source_line}\n")
        typer.echo(f"Added sourcing line to {bashrc}")

    typer.echo(f"bash completion installed in {target}.")
    typer.echo("Restart your terminal or run: source ~/.bashrc")


def _install_fish() -> None:
    """Install fish completion."""
    comp_dir = Path.home() / ".config" / "fish" / "completions"
    comp_dir.mkdir(parents=True, exist_ok=True)

    target = comp_dir / "git-cai.fish"
    target.write_text(_FISH_SCRIPT, encoding="utf-8")

    typer.echo(f"fish completion installed in {target}.")
    typer.echo("Restart your terminal for completions to take effect.")
