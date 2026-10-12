#!/usr/bin/env python3
"""Fail-closed contract checks for the PLASMA GitHub Actions control bridge."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".github" / "plasma-actions-control.json"
WORKFLOW = ROOT / ".github" / "workflows" / "plasma-actions-control-bridge.yml"

EXPECTED_ISSUE = 814
EXPECTED_ACTORS = ["physicslu"]
EXPECTED_REF = "main"


def main() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["control_issue"] == EXPECTED_ISSUE
    assert cfg["allowed_actors"] == EXPECTED_ACTORS
    assert cfg["dispatch_ref"] == EXPECTED_REF

    workflows = cfg["allowed_workflows"]
    assert workflows
    assert len(workflows) == len(set(workflows))
    for workflow in workflows:
        assert re.fullmatch(r"[A-Za-z0-9._-]+\.ya?ml", workflow), workflow
        assert "/" not in workflow
        assert (ROOT / ".github" / "workflows" / workflow).is_file(), workflow

    text = WORKFLOW.read_text(encoding="utf-8")
    required_fragments = [
        "issue_comment:",
        "github.event.issue.number == 814",
        "github.actor == 'physicslu'",
        "actions: write",
        "contents: read",
        "ref: main",
        "actions/github-script@f28e40c7f34bde8b3046d885e986cb6290c5673b",
        "createWorkflowDispatch",
        "cancelWorkflowRun",
        "reRunWorkflow",
        "run.head_branch !== cfg.dispatch_ref",
        "requireAllowedWorkflow(workflow)",
    ]
    for fragment in required_fragments:
        assert fragment in text, fragment

    forbidden_fragments = [
        "pull_request_target:",
        "permissions: write-all",
        "secrets: inherit",
        "force-push",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in text, fragment

    print(
        f"PLASMA Actions control bridge contract PASS: "
        f"{len(workflows)} allowlisted workflows, issue #{EXPECTED_ISSUE}, "
        f"actor {EXPECTED_ACTORS[0]}, ref {EXPECTED_REF}"
    )


if __name__ == "__main__":
    main()
