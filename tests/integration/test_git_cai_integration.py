import os
import subprocess


def test_git_cai_creates_commit_with_fake_llm(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=repo, check=True)

    # Create and stage a file
    (repo / "file.txt").write_text("hello")
    subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True)

    env = {
        **os.environ,

        # Fake LLM
        "CAI_FAKE_LLM": "1",

        # Disable all user/system git config
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",

        # Explicit identity (no user credentials)
        "GIT_AUTHOR_NAME": "CI",
        "GIT_AUTHOR_EMAIL": "ci@example.com",
        "GIT_COMMITTER_NAME": "CI",
        "GIT_COMMITTER_EMAIL": "ci@example.com",

        # Deterministic timestamps
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",

        # Disable editor and prompts
        "GIT_EDITOR": "true",
        "GIT_TERMINAL_PROMPT": "0",

        # Disable GPG signing
        "GIT_COMMIT_GPGSIGN": "false",
    }

    # Run git cai
    result = subprocess.run(
        ["git", "cai", "--crazy"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr

    # Verify commit message
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )

    # Verify commit message exists and is non-empty
    assert log.stdout.strip()
    assert "file.txt" in log.stdout

