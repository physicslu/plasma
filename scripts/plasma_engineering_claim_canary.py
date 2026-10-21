#!/usr/bin/env python3
"""Owner-gated, one-shot real GitHub claim Ruleset CANARY. No Codex/hardware.

OFFLINE by default: the network path is reachable only through the CLI 'run'
after an exact GitHub issue-comment event, trusted Actions actor/environment,
pinned main checkout and protected Ruleset readback. Never retry writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

import plasma_engineering_dispatch_gate1d as gate

REPO = "physicslu/plasma"
OWNER = "physicslu"
ISSUE = 981
COMMAND = "/plasma-dispatch claim-canary 981"
RULESET_ID = 25329605
REF = gate.CANARY_REF
SHORT_REF = REF.removeprefix("refs/")
API = "https://api.github.com/repos/physicslu/plasma"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
STEPS = gate.CANARY_TYPES
EXPECTED_REJECTIONS = frozenset({403, 422})


class Stop(ValueError):
    """Only fixed public reason codes, never request/secret material."""


def deny(code: str) -> None:
    raise Stop(code)


def require_event(event: object, env: dict[str, str], checkout_sha: str) -> dict:
    """Return a sanitized immutable dispatch receipt; do NOT trust Issue body."""
    if (env.get("GITHUB_EVENT_NAME") != "issue_comment"
            or env.get("GITHUB_ACTOR") != OWNER
            or env.get("GITHUB_REPOSITORY") != REPO
            or env.get("GITHUB_REF") != "refs/heads/main"
            or env.get("GITHUB_SHA") != checkout_sha
            or not SHA40.fullmatch(checkout_sha)):
        deny("CANARY_GITHUB_CONTEXT_DENIED")
    if (type(event) is not dict or event.get("action") != "created"
            or type(event.get("issue")) is not dict
            or type(event.get("comment")) is not dict
            or type(event.get("sender")) is not dict
            or type(event.get("repository")) is not dict):
        deny("CANARY_EVENT_SHAPE_DENIED")
    issue, comment = event["issue"], event["comment"]
    if (issue.get("number") != ISSUE or "pull_request" in issue
            or comment.get("body") != COMMAND
            or type(comment.get("user")) is not dict
            or comment["user"].get("login") != OWNER
            or event["sender"].get("login") != OWNER
            or event["repository"].get("full_name") != REPO):
        deny("CANARY_EXACT_OWNER_COMMAND_DENIED")
    if (type(comment.get("id")) is not int or comment["id"] <= 0):
        deny("CANARY_COMMENT_ID_DENIED")
    if (not re.fullmatch(r"[1-9][0-9]{0,18}", env.get("GITHUB_RUN_ID", ""))
            or not re.fullmatch(r"[1-9][0-9]{0,9}", env.get("GITHUB_RUN_ATTEMPT", ""))):
        deny("CANARY_RUN_ID_DENIED")
    # Every run attempt is subject to the permanent unique claim. Never
    # re-run an unknown/maybe-successful 201 after a lost response.
    return {
        "comment_id": comment["id"],
        "run_id": int(env["GITHUB_RUN_ID"]),
        "run_attempt": int(env["GITHUB_RUN_ATTEMPT"]),
        "reviewed_sha": checkout_sha,
        "ref": REF,
    }


def confirmed_rulesets(rulesets: object, proposal: dict) -> dict:
    result = gate.exact_live_ruleset(rulesets, proposal)
    if (result.get("status") != "RULESET_READBACK_MATCH_NOT_LIVE_CANARY"
            or result.get("ruleset_id") != RULESET_ID
            or result.get("matching_claim_rulesets") != 1):
        deny("CANARY_RULESET_PRECHECK_DENIED")
    return result


def request(token: str, method: str, endpoint: str,
            payload: dict | None = None) -> tuple[int, object]:
    """Strict fixed API calls; no URL from Issue text or Work Order."""
    allowed = {
        ("GET", "/rulesets?includes_parents=true"),
        ("GET", f"/rulesets/{RULESET_ID}"),
        ("GET", f"/git/ref/{SHORT_REF}"),
        ("POST", "/git/refs"),
        ("PATCH", f"/git/refs/{SHORT_REF}"),
        ("DELETE", f"/git/refs/{SHORT_REF}"),
    }
    if (method, endpoint) not in allowed:
        deny("CANARY_API_ENDPOINT_DENIED")
    if not isinstance(token, str) or len(token) < 16:
        deny("CANARY_TOKEN_MISSING")
    body = None
    if payload is not None:
        if method == "POST" and set(payload) == {"ref", "sha"}:
            if payload["ref"] != REF or not SHA40.fullmatch(payload["sha"]):
                deny("CANARY_CREATE_PAYLOAD_DENIED")
        elif method == "PATCH" and set(payload) == {"sha", "force"}:
            if not SHA40.fullmatch(payload["sha"]) or type(payload["force"]) is not bool:
                deny("CANARY_UPDATE_PAYLOAD_DENIED")
        else:
            deny("CANARY_API_PAYLOAD_DENIED")
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    req = urllib.request.Request(
        API + endpoint, data=body, method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read(1024 * 1024)
            return response.status, json.loads(data) if data else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (OSError, ValueError, UnicodeError) as exc:
        raise Stop("CANARY_TRANSPORT_UNCERTAIN_FAIL_CLOSED") from exc


def ref_readback(transport, expected: str) -> None:
    status, data = transport("GET", f"/git/ref/{SHORT_REF}", None)
    if (status != 200 or type(data) is not dict
            or data.get("ref") != REF
            or type(data.get("object")) is not dict
            or data["object"].get("sha") != expected):
        deny("CANARY_REF_READBACK_MISMATCH")


def run_probes(transport, head: str, other: str, observer=None) -> dict:
    """One non-repeatable create then negatives. Abort on any ambiguity.

    'other' MUST be another existing commit SHA. An unexpected successful
    update/delete is a security incident and stops immediately.
    """
    if (not SHA40.fullmatch(head) or not SHA40.fullmatch(other)
            or head == other):
        deny("CANARY_DISTINCT_COMMIT_REQUIRED")
    events = []

    def record(step: str, http: int) -> None:
        events.append({"step": step, "http_status": http, "ref": REF,
                       "result": "OBSERVED"})
        if observer is not None:
            observer(list(events))

    # Informational preflight; POST itself is the atomic one-shot claim.
    pre_status, _ = transport("GET", f"/git/ref/{SHORT_REF}", None)
    if pre_status != 404:
        deny("CANARY_REF_ALREADY_PRESENT_OR_UNKNOWN")
    status, obj = transport("POST", "/git/refs", {"ref": REF, "sha": head})
    if (status != 201 or type(obj) is not dict or obj.get("ref") != REF
            or type(obj.get("object")) is not dict
            or obj["object"].get("sha") != head):
        deny("CANARY_CREATE_NOT_CONFIRMED_NO_RETRY")
    record(STEPS[0], status)
    ref_readback(transport, head)

    status, _ = transport("POST", "/git/refs", {"ref": REF, "sha": head})
    if status != 422:
        deny("CANARY_DUPLICATE_CREATE_NOT_REJECTED")
    record(STEPS[1], status)
    ref_readback(transport, head)

    for step, forced in ((STEPS[2], False), (STEPS[3], True)):
        status, _ = transport("PATCH", f"/git/refs/{SHORT_REF}",
                              {"sha": other, "force": forced})
        if status not in EXPECTED_REJECTIONS:
            deny("CANARY_UPDATE_PROTECTION_NOT_PROVEN")
        record(step, status)
        ref_readback(transport, head)

    status, _ = transport("DELETE", f"/git/refs/{SHORT_REF}", None)
    if status not in EXPECTED_REJECTIONS:
        deny("CANARY_DELETE_PROTECTION_NOT_PROVEN")
    record(STEPS[4], status)
    ref_readback(transport, head)
    record(STEPS[5], 200)
    return {
        "status": "LIVE_CANARY_SEQUENCE_OBSERVED_NO_RUNTIME_ACTIVATION",
        "ref": REF, "head_sha": head,
        "step_count": len(events), "observations": events,
        "runtime_enabled": False, "codex_executed": False,
        "hardware_verified": False, "claim_ref_retained": True,
        "workflow_trigger_effects_audited": False,
        "token_identity_fully_qualified": False,
    }


def live_ruleset_preflight(transport, proposal: dict) -> None:
    status, records = transport("GET", "/rulesets?includes_parents=true", None)
    if status != 200 or type(records) is not list or len(records) > 100:
        deny("CANARY_RULESET_LIST_UNVERIFIED")
    full = []
    for summary in records:
        if type(summary) is not dict or type(summary.get("id")) is not int:
            deny("CANARY_RULESET_LIST_MALFORMED")
        # The known repository has two rulesets. Any additional ruleset
        # needs a reviewed release of this canary, not silent acceptance.
        if summary["id"] not in {RULESET_ID, 20964250}:
            deny("CANARY_UNKNOWN_RULESET_REQUIRES_REVIEW")
        # Only the dedicated ruleset needs exact origin/schema readback.
        if summary["id"] == RULESET_ID:
            code, detailed = transport("GET", f"/rulesets/{RULESET_ID}", None)
            if code != 200 or type(detailed) is not dict:
                deny("CANARY_RULESET_DETAIL_UNVERIFIED")
            full.append(detailed)
    if len(records) != 2 or len(full) != 1:
        deny("CANARY_RULESET_SET_DRIFT")
    confirmed_rulesets(full, proposal)


def safe_report(output: Path, event: dict, probes: list[dict] | None,
                status: str) -> None:
    if output.is_symlink() or (output.exists() and not output.is_file()):
        deny("CANARY_REPORT_PATH_INVALID")
    report = {
        "schema": "plasma.engineering.claim-canary.v1",
        "status": status,
        "dispatch": event,
        "observations": probes or [],
        "runtime_enabled": False,
        "codex_executed": False,
        "hardware_verified": False,
    }
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="One-shot Claim Ruleset canary; NOT model dispatch")
    p.add_argument("mode", choices=("authorize", "run"))
    p.add_argument("--event", type=Path, required=True)
    p.add_argument("--proposal", type=Path)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    try:
        if args.event.is_symlink() or not args.event.is_file():
            deny("CANARY_EVENT_FILE_UNTRUSTED")
        event = gate.read_json(args.event)
        checkout_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip()
        receipt = require_event(event, os.environ, checkout_sha)
        if args.mode == "authorize":
            if args.proposal is not None or args.report is not None:
                deny("CANARY_AUTHORIZE_UNEXPECTED_ARGS")
            print("CANARY_OWNER_AUTHORIZATION_PASS_NO_MUTATION")
            return 0
        if args.proposal is None or args.report is None:
            deny("CANARY_RUN_ARGS_MISSING")
        proposal = gate.read_json(args.proposal)
        token = os.environ.get("GH_TOKEN", "")
        if not token or len(token) < 16:
            deny("CANARY_TOKEN_MISSING")
        def transport(method, path, payload):
            return request(token, method, path, payload)
        live_ruleset_preflight(transport, proposal)
        other = subprocess.check_output(
            ["git", "rev-parse", "HEAD^"], text=True).strip()
        observations = []
        def capture(items):
            nonlocal observations
            observations = items
            safe_report(args.report, receipt, observations, "CANARY_PARTIAL_FAIL_CLOSED")
        result = run_probes(transport, checkout_sha, other, capture)
        safe_report(args.report, receipt, observations, result["status"])
        print(json.dumps({"status": result["status"], "run_id": receipt["run_id"],
                          "step_count": result["step_count"],
                          "runtime_enabled": False}, sort_keys=True))
        return 0
    except (gate.Denied, Stop, OSError, subprocess.CalledProcessError) as exc:
        code = str(exc) if isinstance(exc, (gate.Denied, Stop)) else "CANARY_INPUT_OR_GIT_FAILURE"
        # Do not print HTTP bodies, exception messages, secrets or untrusted text.
        print(json.dumps({"status": "NO_GO_CANARY",
                          "reason": code, "runtime_enabled": False},
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
