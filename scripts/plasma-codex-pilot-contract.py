#!/usr/bin/env python3
"""Fail-closed bootstrap contract for PLASMA Issue #981 (no external deps)."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/plasma-codex-pilot.yml"
OUTER = ROOT / "scripts/plasma-codex-pilot.sh"
INNER = ROOT / "scripts/plasma-codex-pilot-inner.sh"

REPO = "physicslu/plasma"
ACTOR = "physicslu"
ISSUE = 981
COMMAND = "/plasma-codex pilot 981"


def authorize(event: dict, actor: str, repository: str, ref: str) -> bool:
    """All inputs here are GitHub-supplied event metadata, never Issue text code."""
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    sender = event.get("sender") or {}
    source_repo = event.get("repository") or {}
    return (
        event.get("action") == "created"
        and repository == REPO
        and source_repo.get("full_name") == REPO
        and ref == "refs/heads/main"
        and actor == ACTOR
        and sender.get("login") == ACTOR
        and comment.get("user", {}).get("login") == ACTOR
        and issue.get("number") == ISSUE
        and not issue.get("pull_request")
        and comment.get("body") == COMMAND
    )


def example_event() -> dict:
    return {
        "action": "created",
        "issue": {"number": ISSUE},
        "comment": {"body": COMMAND, "user": {"login": ACTOR}},
        "sender": {"login": ACTOR},
        "repository": {"full_name": REPO},
    }


def check() -> None:
    event = example_event()
    assert authorize(event, ACTOR, REPO, "refs/heads/main")
    negative_cases = [
        ("actor", "mallory"),
        ("repository", "mallory/plasma"),
        ("ref", "refs/heads/feature"),
    ]
    for key, bad in negative_cases:
        opts = {"actor": ACTOR, "repository": REPO, "ref": "refs/heads/main"}
        opts[key] = bad
        assert not authorize(event, **opts), key
    for key, value in (
        ("action", "edited"),
        ("issue.number", 980),
        ("issue.pull_request", {"url": "https://example.test/pr"}),
        ("comment.body", COMMAND + " ; echo injected"),
        ("comment.body", COMMAND + "\n"),
        ("comment.user.login", "mallory"),
        ("sender.login", "mallory"),
        ("repository.full_name", "mallory/plasma"),
    ):
        altered = copy.deepcopy(event)
        cursor = altered
        segments = key.split(".")
        for segment in segments[:-1]:
            cursor = cursor[segment]
        cursor[segments[-1]] = value
        assert not authorize(altered, ACTOR, REPO, "refs/heads/main"), key

    workflow = WORKFLOW.read_text(encoding="utf-8")
    shell = OUTER.read_text(encoding="utf-8")
    inner = INNER.read_text(encoding="utf-8")
    needed_workflow = [
        "issue_comment:",
        "pull_request:",
        "github.actor == 'physicslu'",
        "github.event.issue.number == 981",
        "github.event.comment.body == '/plasma-codex pilot 981'",
        "needs: authorize",
        "runs-on: [self-hosted, linux, x64, plasma-codex]",
        "test \"$(id -un)\" = plasma-codex",
        "test \"$RUNNER_NAME\" = SWPC-plasma-codex",
        "persist-credentials: false",
        "ref: main",
        "python3 scripts/plasma-codex-pilot-contract.py event",
        "python3 scripts/plasma-codex-pilot-contract.py check",
        "bash scripts/plasma-codex-pilot.sh",
        "timeout-minutes: 20",
        "permissions:",
        "contents: read",
    ]
    for piece in needed_workflow:
        assert piece in workflow, f"missing workflow contract: {piece}"
    for piece in (
        "tmux -S \"$socket\"",
        "trap cleanup EXIT INT TERM",
        "chmod 0660 \"$socket\"",
        "test -f \"$out/complete\"",
        "sha256sum -c SHA256SUMS",
    ):
        assert piece in shell, f"missing monitor contract: {piece}"
    for piece in (
        "--sandbox read-only",
        "--ask-for-approval never",
        "timeout --signal=TERM --kill-after=10s 900s",
        "codex exec",
        'rc="${PIPESTATUS[0]}"',
    ):
        assert piece in inner, f"missing bounded Codex contract: {piece}"
    for prohibited in (
        "pull_request_target:",
        "permissions: write-all",
        "secrets: inherit",
        "sudo -S",
        "--dangerously-bypass-approvals-and-sandbox",
        "docker.sock",
    ):
        assert prohibited not in workflow + shell + inner, prohibited
    print("PLASMA Issue #981 pilot contract PASS (owner-only, fixed command, non-hardware runner)")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "check":
        check()
    elif len(sys.argv) == 3 and sys.argv[1] == "event":
        event = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        if not authorize(
            event,
            os.environ.get("GITHUB_ACTOR", ""),
            os.environ.get("GITHUB_REPOSITORY", ""),
            os.environ.get("GITHUB_REF", ""),
        ):
            raise SystemExit("PLASMA Codex pilot dispatcher authorization DENIED")
        print("PLASMA Codex pilot dispatcher authorization PASS")
    else:
        raise SystemExit("Usage: plasma-codex-pilot-contract.py check | event EVENT_JSON")


if __name__ == "__main__":
    main()
