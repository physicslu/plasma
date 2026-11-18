#!/usr/bin/env python3
"""Owner-only Z2 SSH/UART login dispatch contract; no hardware in this test."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/plasma-codex-z2-login.yml"
SCRIPT = ROOT / "scripts/plasma-codex-z2-login.py"
WRAPPER = ROOT / "scripts/plasma-codex-z2-login.sh"
INNER = ROOT / "scripts/plasma-codex-z2-login-inner.sh"
REPO = "physicslu/plasma"
OWNER = "physicslu"
ISSUE = 981
COMMAND = "/plasma-codex z2-login 981"


def authorized(event: dict, actor: str, repository: str, ref: str) -> bool:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    sender = event.get("sender") or {}
    repo = event.get("repository") or {}
    return (
        event.get("action") == "created"
        and repository == REPO and repo.get("full_name") == REPO
        and ref == "refs/heads/main" and actor == OWNER
        and sender.get("login") == OWNER
        and comment.get("user", {}).get("login") == OWNER
        and issue.get("number") == ISSUE
        and not issue.get("pull_request")
        and comment.get("body") == COMMAND
    )


def sample() -> dict:
    return {
        "action": "created", "issue": {"number": ISSUE},
        "comment": {"body": COMMAND, "user": {"login": OWNER}},
        "sender": {"login": OWNER},
        "repository": {"full_name": REPO},
    }


def check() -> None:
    good = sample()
    assert authorized(good, OWNER, REPO, "refs/heads/main")
    for args in (
        ("rogue", REPO, "refs/heads/main"),
        (OWNER, "rogue/repo", "refs/heads/main"),
        (OWNER, REPO, "refs/heads/other"),
    ):
        assert not authorized(good, *args)
    for key, value in (
        ("action", "edited"), ("issue.number", 982),
        ("issue.pull_request", {"url": "https://example.com/pr"}),
        ("comment.body", COMMAND + "\n"),
        ("comment.body", COMMAND + " && bash"),
        ("comment.user.login", "rogue"),
        ("sender.login", "rogue"),
        ("repository.full_name", "rogue/repo"),
    ):
        bad = copy.deepcopy(good)
        obj = bad
        bits = key.split(".")
        for bit in bits[:-1]:
            obj = obj[bit]
        obj[bits[-1]] = value
        assert not authorized(bad, OWNER, REPO, "refs/heads/main"), key

    wf = WORKFLOW.read_text()
    assert "\n  issue_comment:\n" not in wf, "RETIRED_ISSUE_DISPATCH_REENABLED"
    src = SCRIPT.read_text()
    outer = WRAPPER.read_text()
    inner = INNER.read_text()
    for required in (
        "pull_request:", "github.actor == 'physicslu'",
        "github.event.issue.number == 981",
        "github.event.comment.body == '/plasma-codex z2-login 981'",
        "needs.authorize.outputs.reviewed_sha",
        "runs-on: [self-hosted, linux, x64, plasma-codex]",
        "persist-credentials: false", "contents: read",
        "bash scripts/plasma-codex-z2-login.sh",
    ):
        assert required in wf, required
    for required in (
        "StrictHostKeyChecking=yes", "UserKnownHostsFile",
        "TIOCEXCL", "fuser", "ssh_password", "PRIVATE_FILE_MODE",
        "PLASMA_Z2_UART_USER=", "PLASMA_Z2_SSH_USER=", "getpass",
        "BLOCKED_PRIVATE_CREDENTIAL", "GITHUB_ACTIONS",
        "O_NOCTTY",
    ):
        assert required in src, required
    for required in (
        "attach-session -r", "chmod 0660", "plasma-monitor",
        "tmux -S",
    ):
        assert required in outer, required
    assert "python3 scripts/plasma-codex-z2-login.py --run" in inner
    for bad in (
        "pull_request_target:", "permissions: write-all",
        "sudo ", "uhubctl -a", "power_off(", "power_on(",
        "docker.sock", "GITHUB_TOKEN: ",
    ):
        assert bad not in wf + outer + inner, bad
    print("PLASMA Z2 SSH/UART login authorized owner and tmux contracts PASS")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "check":
        check()
        return
    if len(sys.argv) == 3 and sys.argv[1] == "event":
        event = json.loads(Path(sys.argv[2]).read_text())
        if not authorized(event, os.environ.get("GITHUB_ACTOR", ""),
                          os.environ.get("GITHUB_REPOSITORY", ""),
                          os.environ.get("GITHUB_REF", "")):
            raise SystemExit("Z2 login smoke dispatch DENIED")
        print("Z2 login smoke owner dispatch PASS")
        return
    raise SystemExit("Usage: contract.py check | event PATH")


if __name__ == "__main__":
    main()
