import pytest
import typer
from git_cai_cli.cli import modes
from git_cai_cli.cli.modes import Mode

# -----------------------------
# Integration test for modes.py
# -----------------------------


@pytest.mark.parametrize(
    "flags,expected_mode",
    [
        ({"list_flag": False, "squash": False, "update": False}, Mode.COMMIT),
        ({"list_flag": True, "squash": False, "update": False}, Mode.LIST),
        ({"list_flag": False, "squash": True, "update": False}, Mode.SQUASH),
        ({"list_flag": False, "squash": False, "update": True}, Mode.UPDATE),
    ],
)
def test_resolve_mode_integration(flags, expected_mode):
    """
    Test that resolve_mode returns correct Mode in normal scenarios.
    """
    mode = modes.resolve_mode(**flags)
    assert mode == expected_mode


def test_resolve_mode_conflict_raises(capsys):
    """
    Test that resolve_mode raises typer.Exit if multiple flags are used together.
    """
    with pytest.raises(typer.Exit) as exc:
        modes.resolve_mode(list_flag=True, squash=True, update=False)
    captured = capsys.readouterr()
    assert (
        "cannot be used together" in captured.out
        or "cannot be used together" in captured.err
    )
    assert exc.value.exit_code == 1


@pytest.mark.parametrize(
    "mode,stage_tracked,enable_debug,help_flag,version_flag,error_message",
    [
        (
            Mode.LIST,
            True,
            False,
            False,
            False,
            "Error: --all cannot be used with --list, --update, or --squash.",
        ),
        (
            Mode.COMMIT,
            False,
            True,
            True,
            False,
            "Error: --debug cannot be used with --help or --version.",
        ),
        (
            Mode.COMMIT,
            False,
            True,
            False,
            True,
            "Error: --debug cannot be used with --help or --version.",
        ),
    ],
)
def test_validate_options_integration(
    mode, stage_tracked, enable_debug, help_flag, version_flag, error_message, capsys
):
    """
    Test that validate_options raises typer.Exit for invalid combinations.
    """
    import typer
    from git_cai_cli.cli import modes

    with pytest.raises(typer.Exit) as exc:
        modes.validate_options(
            mode=mode,
            stage_tracked=stage_tracked,
            enable_debug=enable_debug,
            help_flag=help_flag,
            version_flag=version_flag,
        )
    captured = capsys.readouterr()
    # Check that the full message appears in stderr
    assert error_message in captured.err
    assert exc.value.exit_code == 1


def test_validate_options_valid_combinations():
    """
    Test that validate_options allows valid combinations without raising.
    """
    # COMMIT mode, stage_tracked=True, debug off
    modes.validate_options(
        mode=Mode.COMMIT,
        stage_tracked=True,
        enable_debug=False,
        help_flag=False,
        version_flag=False,
    )

    # COMMIT mode, debug=True, no help/version
    modes.validate_options(
        mode=Mode.COMMIT,
        stage_tracked=False,
        enable_debug=True,
        help_flag=False,
        version_flag=False,
    )
