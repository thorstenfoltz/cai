import pytest
import typer
from git_cai_cli.cli import modes
from git_cai_cli.cli.modes import Mode

# ----------------------
# Tests for resolve_mode
# ----------------------


def test_resolve_mode_commit_by_default():
    """No flags should return COMMIT mode."""
    mode = modes.resolve_mode(
        amend=False, list_flag=False, pr=False, squash=False, update=False
    )
    assert mode == Mode.COMMIT


def test_resolve_mode_list_flag():
    """--list flag should return LIST mode."""
    mode = modes.resolve_mode(
        amend=False, list_flag=True, pr=False, squash=False, update=False
    )
    assert mode == Mode.LIST


def test_resolve_mode_squash_flag():
    """--squash flag should return SQUASH mode."""
    mode = modes.resolve_mode(
        amend=False, list_flag=False, pr=False, squash=True, update=False
    )
    assert mode == Mode.SQUASH


def test_resolve_mode_pr_flag():
    """--PR flag should return PR mode."""
    mode = modes.resolve_mode(
        amend=False, list_flag=False, pr=True, squash=False, update=False
    )
    assert mode == Mode.PR


def test_resolve_mode_update_flag():
    """--update flag should return UPDATE mode."""
    mode = modes.resolve_mode(
        amend=False, list_flag=False, pr=False, squash=False, update=True
    )
    assert mode == Mode.UPDATE


def test_resolve_mode_multiple_flags(capsys):
    """Using more than one of --list, --PR, --squash, --update raises typer.Exit."""
    with pytest.raises(typer.Exit) as exc:
        modes.resolve_mode(
            amend=False, list_flag=True, pr=False, squash=True, update=False
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used together" in captured.out
        or "cannot be used together" in captured.err
    )
    assert exc.value.exit_code == 1


def test_resolve_mode_pr_with_squash_rejected(capsys):
    """--PR cannot be used with --squash."""
    with pytest.raises(typer.Exit) as exc:
        modes.resolve_mode(
            amend=False, list_flag=False, pr=True, squash=True, update=False
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used together" in captured.out
        or "cannot be used together" in captured.err
    )
    assert exc.value.exit_code == 1


# -------------------------
# Tests for validate_options
# -------------------------


def test_validate_options_debug_with_help(capsys):
    """--debug cannot be used with --help."""
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.COMMIT,
            stage_tracked=False,
            enable_debug=True,
            help_flag=True,
            version_flag=False,
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used with --help or --version" in captured.out
        or "cannot be used with --help or --version" in captured.err
    )
    assert exc.value.exit_code == 1


def test_validate_options_debug_with_version(capsys):
    """--debug cannot be used with --version."""
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.COMMIT,
            stage_tracked=False,
            enable_debug=True,
            help_flag=False,
            version_flag=True,
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used with --help or --version" in captured.out
        or "cannot be used with --help or --version" in captured.err
    )
    assert exc.value.exit_code == 1


def test_validate_options_stage_tracked_with_non_commit(capsys):
    """--all cannot be used with non-COMMIT mode."""
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.LIST,
            stage_tracked=True,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
        )
    captured = capsys.readouterr()
    assert (
        "--all can only be used in COMMIT or AMEND mode." in captured.out
        or "--all can only be used in COMMIT or AMEND mode." in captured.err
    )
    assert exc.value.exit_code == 1


def test_validate_options_valid_combination():
    """A valid combination should not raise."""
    modes.validate_options(
        mode=Mode.COMMIT,
        stage_tracked=True,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
    )

    modes.validate_options(
        mode=Mode.COMMIT,
        stage_tracked=False,
        enable_debug=True,
        help_flag=False,
        version_flag=False,
    )


# -----------------------------------------------
# Tests for --provider / --model option validation
# -----------------------------------------------


def test_provider_rejected_with_list_mode(capsys):
    """--provider cannot be used with --list."""
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.LIST,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            provider_override="openai",
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used with --init, --list, or --update" in captured.out
        or "cannot be used with --init, --list, or --update" in captured.err
    )
    assert exc.value.exit_code == 1


def test_provider_rejected_with_update_mode(capsys):
    """--provider cannot be used with --update."""
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.UPDATE,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            provider_override="openai",
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used with --init, --list, or --update" in captured.out
        or "cannot be used with --init, --list, or --update" in captured.err
    )
    assert exc.value.exit_code == 1


def test_provider_allowed_with_commit_mode():
    """--provider is allowed with COMMIT mode."""
    modes.validate_options(
        mode=Mode.COMMIT,
        stage_tracked=False,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
        provider_override="openai",
    )


def test_provider_allowed_with_squash_mode():
    """--provider is allowed with SQUASH mode."""
    modes.validate_options(
        mode=Mode.SQUASH,
        stage_tracked=False,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
        provider_override="openai",
        model_override="gpt-4o",
    )


# ----------------------------------
# Tests for --time option validation
# ----------------------------------


def test_time_flag_rejected_with_list_mode(capsys):
    """--time cannot be used with --list."""
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.LIST,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            time_flag=True,
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used with --init, --list, or --update" in captured.out
        or "cannot be used with --init, --list, or --update" in captured.err
    )
    assert exc.value.exit_code == 1


def test_time_flag_rejected_with_update_mode(capsys):
    """--time cannot be used with --update."""
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.UPDATE,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            time_flag=True,
        )
    captured = capsys.readouterr()
    assert (
        "cannot be used with --init, --list, or --update" in captured.out
        or "cannot be used with --init, --list, or --update" in captured.err
    )
    assert exc.value.exit_code == 1


def test_time_flag_allowed_with_squash_mode():
    """--time is allowed with SQUASH mode."""
    modes.validate_options(
        mode=Mode.SQUASH,
        stage_tracked=False,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
        time_flag=True,
    )


# ------------------------------------
# Tests for --context option validation
# ------------------------------------


def test_context_rejected_with_list_mode(capsys):
    """--context cannot be used with --list."""
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.LIST,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            context="some context",
        )
    captured = capsys.readouterr()
    assert (
        "--context cannot be used with this mode." in captured.out
        or "--context cannot be used with this mode." in captured.err
    )
    assert exc.value.exit_code == 1


def test_context_rejected_with_update_mode(capsys):
    """--context cannot be used with --update."""
    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=Mode.UPDATE,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            context="some context",
        )
    captured = capsys.readouterr()
    assert (
        "--context cannot be used with this mode." in captured.out
        or "--context cannot be used with this mode." in captured.err
    )
    assert exc.value.exit_code == 1


def test_context_allowed_with_squash_mode():
    """--context is allowed with SQUASH mode."""
    modes.validate_options(
        mode=Mode.SQUASH,
        stage_tracked=False,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
        context="Closes #42",
    )


def test_context_allowed_with_commit_mode():
    """--context is allowed with COMMIT mode."""
    modes.validate_options(
        mode=Mode.COMMIT,
        stage_tracked=False,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
        context="Fixes JIRA-1234",
    )


def test_context_allowed_with_amend_mode():
    """--context is allowed with AMEND mode."""
    modes.validate_options(
        mode=Mode.AMEND,
        stage_tracked=False,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
        context="Reword after review",
    )


def test_context_none_allowed_with_any_mode():
    """context=None should be accepted for all modes."""
    for mode in Mode:
        modes.validate_options(
            mode=mode,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            context=None,
        )


# ------------------------------------------------------------------
# Read-only generator modes (explain / split / changelog / tag)
# ------------------------------------------------------------------


def _base_kwargs():
    return dict(
        amend=False,
        check=False,
        init=False,
        list_flag=False,
        pr=False,
        squash=False,
        stats=False,
        update=False,
    )


def test_resolve_mode_explain():
    assert modes.resolve_mode(**_base_kwargs(), explain=True) is Mode.EXPLAIN


def test_resolve_mode_split():
    assert modes.resolve_mode(**_base_kwargs(), split=True) is Mode.SPLIT


def test_resolve_mode_changelog():
    assert modes.resolve_mode(**_base_kwargs(), changelog=True) is Mode.CHANGELOG


def test_resolve_mode_release():
    assert modes.resolve_mode(**_base_kwargs(), release=True) is Mode.RELEASE


def test_resolve_mode_rejects_two_new_modes(capsys):
    with pytest.raises(typer.Exit):
        modes.resolve_mode(**_base_kwargs(), explain=True, release=True)
    assert "cannot be used together" in capsys.readouterr().err


def test_resolve_mode_rejects_new_mode_with_squash(capsys):
    kwargs = _base_kwargs()
    kwargs["squash"] = True
    with pytest.raises(typer.Exit):
        modes.resolve_mode(**kwargs, split=True)


def test_context_allowed_in_new_modes():
    for mode in (Mode.EXPLAIN, Mode.SPLIT, Mode.CHANGELOG, Mode.RELEASE):
        modes.validate_options(
            mode=mode,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            context="ticket-1",
        )


def test_print_rejected_in_new_modes(capsys):
    with pytest.raises(typer.Exit):
        modes.validate_options(
            mode=Mode.EXPLAIN,
            stage_tracked=False,
            enable_debug=False,
            help_flag=False,
            version_flag=False,
            print_only=True,
        )
