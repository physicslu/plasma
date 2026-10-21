#!/usr/bin/env python3
"""Exact owner-only SSH Z2 SWD05 dispatch contract (Issue #981)."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = "physicslu/plasma"
OWNER = "physicslu"
COMMAND = "/plasma-codex z2-swd05 981"
WF = ROOT / ".github/workflows/plasma-codex-z2-swd05.yml"


def allowed(event: dict, actor: str, repo: str, ref: str) -> bool:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    sender = event.get("sender") or {}
    origin = event.get("repository") or {}
    return (
        event.get("action") == "created"
        and actor == OWNER and repo == REPO and origin.get("full_name") == REPO
        and ref == "refs/heads/main"
        and sender.get("login") == OWNER
        and comment.get("user", {}).get("login") == OWNER
        and issue.get("number") == 981
        and not issue.get("pull_request")
        and comment.get("body") == COMMAND
    )


def event() -> dict:
    return {
        "action": "created", "issue": {"number": 981},
        "comment": {"user": {"login": OWNER}, "body": COMMAND},
        "sender": {"login": OWNER}, "repository": {"full_name": REPO},
    }


def check() -> None:
    e = event()
    assert allowed(e, OWNER, REPO, "refs/heads/main")
    for args in (("someone", REPO, "refs/heads/main"),
                 (OWNER, "someone/repo", "refs/heads/main"),
                 (OWNER, REPO, "refs/heads/feature")):
        assert not allowed(e, *args)
    for path, alternative in (
        ("action", "edited"),
        ("issue.number", 982),
        ("issue.pull_request", {"url": "pr"}),
        ("comment.body", COMMAND + " "),
        ("comment.body", "/plasma-codex z2-login 981"),
        ("comment.user.login", "someone"),
        ("sender.login", "someone"),
        ("repository.full_name", "someone/repo"),
    ):
        altered = copy.deepcopy(e)
        obj = altered
        parts = path.split(".")
        for part in parts[:-1]:
            obj = obj[part]
        obj[parts[-1]] = alternative
        assert not allowed(altered, OWNER, REPO, "refs/heads/main"), path

    wf = WF.read_text()
    py = (ROOT / "scripts/plasma-codex-z2-swd05.py").read_text()
    sh = (ROOT / "scripts/plasma-codex-z2-swd05.sh").read_text()
    inner = (ROOT / "scripts/plasma-codex-z2-swd05-inner.sh").read_text()
    for term in (
        "issue_comment:", "github.actor == 'physicslu'",
        "github.event.issue.number == 981",
        "github.event.comment.body == '/plasma-codex z2-swd05 981'",
        "needs.authorize.outputs.reviewed_sha",
        "runs-on: [self-hosted, linux, x64, plasma-codex]",
        "persist-credentials: false", "contents: read",
        "bash scripts/plasma-codex-z2-swd05.sh",
    ):
        assert term in wf, term
    for term in ("StrictHostKeyChecking=yes", "UserKnownHostsFile=",
                 "LOGIN.creds()", "fixed_remote_cmd", "sanitize_report",
                 "PRIVATE_ROUTE_NOT_READY", "sudo", "PLASMA_SWD05_OUT"):
        assert term in py, term
    for term in ("tmux -S", "attach-session -r", "chmod 0660",
                 "plasma-monitor", "PLASMA_SWD05_OUT"):
        assert term in sh, term
    assert "python3 scripts/plasma-codex-z2-swd05.py --run" in inner
    assert "PLASMA_SWD05_OUT" in inner
    for forbidden in ("pull_request_target:", "permissions: write-all",
                      "uhubctl -a", "docker.sock", "GITHUB_TOKEN:"):
        assert forbidden not in wf + sh + inner, forbidden
    print("SSH-only Z2 SWD05 owner dispatch and execution contracts PASS")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "check":
        check()
    elif len(sys.argv) == 3 and sys.argv[1] == "event":
        e = json.loads(Path(sys.argv[2]).read_text())
        if not allowed(e, os.environ.get("GITHUB_ACTOR", ""),
                       os.environ.get("GITHUB_REPOSITORY", ""),
                       os.environ.get("GITHUB_REF", "")):
            raise SystemExit("Z2 SWD05 dispatch DENIED")
        print("Z2 SSH-only readiness owner dispatch PASS")
    else:
        raise SystemExit("Usage: readiness-contract.py check | event PATH")
