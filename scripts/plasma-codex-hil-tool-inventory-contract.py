#!/usr/bin/env python3
"""Owner-only Issue #981 passive SWPC HIL inventory dispatch contract."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/plasma-codex-hil-tool-inventory.yml"
SCRIPT = ROOT / "scripts/plasma-codex-hil-tool-inventory.py"
REPO = "physicslu/plasma"
OWNER = "physicslu"
ISSUE = 981
COMMAND = "/plasma-codex hil-tools 981"


def authorized(event: dict, actor: str, repository: str, ref: str) -> bool:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    sender = event.get("sender") or {}
    repo = event.get("repository") or {}
    return (
        event.get("action") == "created"
        and repository == REPO
        and repo.get("full_name") == REPO
        and ref == "refs/heads/main"
        and actor == OWNER
        and sender.get("login") == OWNER
        and comment.get("user", {}).get("login") == OWNER
        and issue.get("number") == ISSUE
        and not issue.get("pull_request")
        and comment.get("body") == COMMAND
    )


def sample() -> dict:
    return {
        "action": "created",
        "issue": {"number": ISSUE},
        "comment": {"body": COMMAND, "user": {"login": OWNER}},
        "sender": {"login": OWNER},
        "repository": {"full_name": REPO},
    }


def check() -> None:
    event = sample()
    assert authorized(event, OWNER, REPO, "refs/heads/main")
    for override in (
        {"actor": "malicious"},
        {"repository": "malicious/plasma"},
        {"ref": "refs/heads/untrusted"},
    ):
        args = {"actor": OWNER, "repository": REPO, "ref": "refs/heads/main"}
        args.update(override)
        assert not authorized(event, **args), override
    for key, bad in (
        ("action", "edited"), ("issue.number", 982),
        ("issue.pull_request", {"url": "https://example.test/pr"}),
        ("comment.body", COMMAND + "\n"), ("comment.body", COMMAND + " && exit"),
        ("comment.user.login", "malicious"), ("sender.login", "malicious"),
        ("repository.full_name", "malicious/plasma"),
    ):
        altered = copy.deepcopy(event)
        cursor = altered
        chain = key.split(".")
        for name in chain[:-1]:
            cursor = cursor[name]
        cursor[chain[-1]] = bad
        assert not authorized(altered, OWNER, REPO, "refs/heads/main"), key

    workflow = WF.read_text(encoding="utf-8")
    assert "\n  issue_comment:\n" not in workflow, "RETIRED_ISSUE_DISPATCH_REENABLED"
    checker = SCRIPT.read_text(encoding="utf-8")
    for required in (
        "pull_request:", "github.actor == 'physicslu'",
        "github.event.issue.number == 981",
        "github.event.comment.body == '/plasma-codex hil-tools 981'",
        "needs: authorize", "needs.authorize.outputs.reviewed_sha",
        "runs-on: [self-hosted, linux, x64, plasma-codex]",
        "test \"$(id -un)\" = plasma-codex",
        "test \"$RUNNER_NAME\" = SWPC-plasma-codex",
        "persist-credentials: false", "contents: read",
        "python3 scripts/plasma-codex-hil-tool-inventory.py --json",
        "sha256sum",
    ):
        assert required in workflow, f"missing workflow invariant: {required}"
    for required in (
        "sys/bus/usb/devices", "device_access", "shutil.which",
        "PLASMA_HIL_LA_CLI", "hardware_access_qualified",
        "NOT_RUN", "NOT_CHECKED",
    ):
        assert required in checker, f"missing passive probe invariant: {required}"
    for prohibited in (
        "pull_request_target:", "permissions: write-all",
        "sudo ", "uhubctl -a", "power_off(", "power_on(",
        "os.system(", "subprocess.", "eval(", "exec(",
        "ssh -", "openocd -f", "chmod 666", "docker.sock",
    ):
        assert prohibited not in workflow + checker, f"prohibited command: {prohibited}"
    print("PLASMA Issue #981 passive HIL tool dispatch contract PASS")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "check":
        check()
    elif len(sys.argv) == 3 and sys.argv[1] == "event":
        event = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        if not authorized(event, os.environ.get("GITHUB_ACTOR", ""),
                          os.environ.get("GITHUB_REPOSITORY", ""),
                          os.environ.get("GITHUB_REF", "")):
            raise SystemExit("PLASMA Issue #981 HIL tool dispatch DENIED")
        print("PLASMA Issue #981 HIL tool dispatch authorization PASS")
    else:
        raise SystemExit("Usage: plasma-codex-hil-tool-inventory-contract.py check | event EVENT_JSON")


if __name__ == "__main__":
    main()
