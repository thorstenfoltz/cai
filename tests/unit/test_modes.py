import pytest
import typer
from git_cai_cli.cli import modes
from git_cai_cli.cli.modes import Mode

# ----------------------
# Tests for resolve_mode
# ----------------------


def test_resolve_mode_commit_by_default():
    """No flags should return COMMIT mode."""
    mode = modes.resolve_mode(list_flag=False, squash=False, update=False)
    assert mode == Mode.COMMIT


def test_resolve_mode_list_flag():
    """--list flag should return LIST mode."""
    mode = modes.resolve_mode(list_flag=True, squash=False, update=False)
    assert mode == Mode.LIST


def test_resolve_mode_squash_flag():
    """--squash flag should return SQUASH mode."""
    mode = modes.resolve_mode(list_flag=False, squash=True, update=False)
    assert mode == Mode.SQUASH


def test_resolve_mode_update_flag():
    """--update flag should return UPDATE mode."""
    mode = modes.resolve_mode(list_flag=False, squash=False, update=True)
    assert mode == Mode.UPDATE


def test_resolve_mode_multiple_flags(capsys):
    """Using more than one of --list, --squash, --update raises typer.Exit."""
    with pytest.raises(typer.Exit) as exc:
        modes.resolve_mode(list_flag=True, squash=True, update=False)
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
        "cannot be used with --list, --update, or --squash" in captured.out
        or "cannot be used with --list, --update, or --squash" in captured.err
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
