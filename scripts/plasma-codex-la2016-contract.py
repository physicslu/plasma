#!/usr/bin/env python3
"""Issue #981: owner-only, exact Codex LA2016 capability dispatch."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = "physicslu/plasma"
OWNER = "physicslu"
CMD = "/plasma-codex la2016 981"

def authorized(event: dict, actor: str, repo: str, ref: str) -> bool:
    issue, comment, sender, origin = (
        event.get("issue") or {}, event.get("comment") or {},
        event.get("sender") or {}, event.get("repository") or {}
    )
    return (
        event.get("action") == "created"
        and repo == REPO and origin.get("full_name") == REPO
        and actor == OWNER and sender.get("login") == OWNER
        and comment.get("user", {}).get("login") == OWNER
        and ref == "refs/heads/main"
        and issue.get("number") == 981
        and not issue.get("pull_request")
        and comment.get("body") == CMD
    )

def sample() -> dict:
    return {"action": "created", "issue": {"number": 981},
            "comment": {"user": {"login": OWNER}, "body": CMD},
            "sender": {"login": OWNER}, "repository": {"full_name": REPO}}

def check() -> None:
    good = sample()
    assert authorized(good, OWNER, REPO, "refs/heads/main")
    for a, r, branch in (
        ("fake", REPO, "refs/heads/main"),
        (OWNER, "fake/plasma", "refs/heads/main"),
        (OWNER, REPO, "refs/heads/untrusted"),
    ):
        assert not authorized(good, a, r, branch)
    for path, val in (
        ("action", "edited"), ("issue.number", 1000),
        ("issue.pull_request", {"url": "pr"}),
        ("comment.body", CMD + "\n"), ("comment.body", CMD + "; echo unsafe"),
        ("comment.user.login", "fake"), ("sender.login", "fake"),
        ("repository.full_name", "fake/plasma"),
    ):
        bad = copy.deepcopy(good)
        obj = bad
        pieces = path.split(".")
        for key in pieces[:-1]:
            obj = obj[key]
        obj[pieces[-1]] = val
        assert not authorized(bad, OWNER, REPO, "refs/heads/main"), path

    wf = (ROOT / ".github/workflows/plasma-codex-la2016.yml").read_text()
    assert "\n  issue_comment:\n" not in wf, "RETIRED_ISSUE_DISPATCH_REENABLED"
    src = (ROOT / "scripts/plasma-codex-la2016.py").read_text()
    sh = (ROOT / "scripts/plasma-codex-la2016.sh").read_text()
    inner = (ROOT / "scripts/plasma-codex-la2016-inner.sh").read_text()
    for required in (
        "pull_request:", "github.actor == 'physicslu'",
        "github.event.issue.number == 981",
        "github.event.comment.body == '/plasma-codex la2016 981'",
        "needs.authorize.outputs.reviewed_sha",
        "runs-on: [self-hosted, linux, x64, plasma-codex]",
        "persist-credentials: false", "contents: read",
        "bash scripts/plasma-codex-la2016.sh",
    ):
        assert required in wf, required
    for required in (
        "bwrap", '"--dev", "/dev"', "codex", '"read-only"',
        '"never"', "validate_agent_request", "KINGST_PWM1_TO_SAME_KINGST_CH0",
        "flock", "kingst-la2016:conn=", "turn_off",
        "watchdog", "off_low", "EXPECTED_IMAGE_HASH",
        "pwm-off-confirmed", "agent-request.json",
    ):
        assert required in src, required
    assert '"--bind", str(output / "agent"), str(output / "agent")' in src
    assert '"--bind", str(output), str(output)' not in src
    for required in ("tmux -S", "chmod 0660", "sha256sum -c SHA256SUMS",
                     "PLASMA_LA2016_OUT"):
        assert required in sh, required
    assert "timeout --signal=TERM --kill-after=7s 245s" in inner
    for bad in ("pull_request_target:", "permissions: write-all",
                "--dangerously-bypass-approvals-and-sandbox",
                "sudo ", "uhubctl -a", "docker.sock", "GITHUB_TOKEN:"):
        assert bad not in wf + sh + inner, bad
    print("Codex -> LA2016 owner dispatch, namespace and evidence contracts PASS")

def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "check":
        check()
    elif len(sys.argv) == 3 and sys.argv[1] == "event":
        evt = json.loads(Path(sys.argv[2]).read_text())
        if not authorized(evt, os.environ.get("GITHUB_ACTOR", ""),
                          os.environ.get("GITHUB_REPOSITORY", ""),
                          os.environ.get("GITHUB_REF", "")):
            raise SystemExit("LA2016 dispatch DENIED")
        print("Owner LA2016 dispatch PASS")
    else:
        raise SystemExit("Usage: ... check | event PATH")

if __name__ == "__main__":
    main()
