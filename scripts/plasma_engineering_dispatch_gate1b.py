#!/usr/bin/env python3
"""Gate 1B: non-deployed GitHub engineering-dispatch ADAPTER contracts.

No CLI or GitHub workflow uses this module to dispatch jobs. Functions are
pure or dependency-injected, so hosted CI can validate a future exact-owner
work-order -> immutable claim -> software-only execution plan safely.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable
import urllib.error
import urllib.request

import plasma_engineering_dispatch_v1 as core

API = "https://api.github.com/repos/physicslu/plasma/git/refs"
CLAIM_PREFIX = "refs/heads/plasma-engineering-claims"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
CI_NO_RUNTIME = "GATE1B_NOT_ACTIVE_NO_ISSUE_DISPATCH"
DEV_NULL = frozenset({"usb", "z2", "fpga", "mmio", "dut", "hub-power",
                      "network-instrument", "host-root"})
ALLOWED_WORKER = "software-isolated"
REF_PATTERN = re.compile(
    r"refs/heads/plasma-engineering-claims/[1-9][0-9]*/"
    r"[a-z0-9][a-z0-9-]{2,63}-r[1-9][0-9]*\Z"
)


def refuse(code: str) -> None:
    raise core.ContractDenied(code)


@dataclass(frozen=True)
class ClaimRequest:
    path: str
    ref: str
    sha: str

    def json_payload(self) -> dict[str, str]:
        return {"ref": self.ref, "sha": self.sha}


def claim_request(order: dict, plan: dict, policy: dict) -> ClaimRequest:
    """Build canonical immutable ref create. Never lookup-then-create.

    POST /git/refs uniquely creates a Git ref or fails with conflict. Git
    branches survive individual Actions runners, job retries and redeploys.
    There is NO automatic expiry, overwrite or deletion of claim refs.
    """
    rule = core.validate_work_order(order, policy)
    if (rule["worker_class"] != ALLOWED_WORKER
            or order["capability"] != "software-pr"
            or order["authorization_kind"] != "gate1-implementation"):
        refuse("SOFTWARE_ONLY_CAPABILITY_REQUIRED")
    if (type(plan) is not dict
            or plan.get("status") != "AUTH_CONTRACT_PASS_NO_DISPATCH"
            or plan.get("runtime_enabled") is not False
            or plan.get("worker_class") != ALLOWED_WORKER
            or plan.get("work_order_sha256") != core.digest(order)
            or plan.get("issue_number") != order["issue_number"]
            or plan.get("work_order_id") != order["work_order_id"]
            or plan.get("revision") != order["revision"]
            or plan.get("authorization_kind") != order["authorization_kind"]):
        refuse("CLAIM_PLAN_MISMATCH")
    issue = order["issue_number"]
    work_id = order["work_order_id"]
    rev = order["revision"]
    ref = f"{CLAIM_PREFIX}/{issue}/{work_id}-r{rev}"
    if not SHA40.fullmatch(order["reviewed_main_sha"]):
        refuse("CLAIM_PIN_INVALID")
    return ClaimRequest(API, ref, order["reviewed_main_sha"])


def accept_claim_response(request: ClaimRequest, status: int, data: object) -> str:
    """201+exact echo only; any ambiguous response is NO-GO and NOT retried."""
    if status == 422:
        refuse("WORK_ORDER_ALREADY_CLAIMED_OR_REF_INVALID")
    if status != 201:
        refuse("GITHUB_CLAIM_NOT_CONFIRMED")
    if (type(data) is not dict or data.get("ref") != request.ref
            or type(data.get("object")) is not dict
            or data["object"].get("sha") != request.sha):
        refuse("GITHUB_CLAIM_RECEIPT_MISMATCH")
    return "CLAIMED_ONCE_GITHUB_REF_CREATE_CONFIRMED"


def claim_with_transport(request: ClaimRequest,
                         transport: Callable[[str, dict[str, str]], tuple[int, object]]) -> str:
    """Atomic transport call, no race-prone GET/existence check beforehand."""
    try:
        status, body = transport(request.path, request.json_payload())
    except (OSError, ValueError, TypeError) as exc:
        raise core.ContractDenied("GITHUB_CLAIM_TRANSPORT_FAILED_CLOSED") from exc
    return accept_claim_response(request, status, body)


def github_ref_transport(token: str) -> Callable[[str, dict[str, str]], tuple[int, object]]:
    """Future GitHub token adapter (not called from any Gate 1B workflow).

    The token must be a trusted GitHub Actions 'contents:write' credential
    isolated from Codex and destroyed after claiming. No Work Order/prose
    may control the target URL, requested ref prefix, or method.
    """
    if not token or not isinstance(token, str) or len(token) < 16:
        refuse("GITHUB_CLAIM_TOKEN_MISSING")
    def post(endpoint: str, payload: dict[str, str]) -> tuple[int, object]:
        if endpoint != API or not isinstance(payload, dict) or set(payload) != {"ref", "sha"}:
            refuse("GITHUB_CLAIM_ENDPOINT_INVALID")
        if not (isinstance(payload["ref"], str)
                and REF_PATTERN.fullmatch(payload["ref"])
                and isinstance(payload["sha"], str)
                and SHA40.fullmatch(payload["sha"])):
            refuse("GITHUB_CLAIM_PAYLOAD_INVALID")
        request = urllib.request.Request(
            API,
            data=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status != 201:
                    return response.status, {}
                return response.status, json.loads(response.read(8192))
        except urllib.error.HTTPError as err:
            return err.code, {}
        except (OSError, ValueError) as err:
            raise core.ContractDenied("GITHUB_CLAIM_TRANSPORT_FAILED_CLOSED") from err
    return post


def event_context_from_env(environ: dict[str, str], reviewed_git_sha: str) -> dict:
    """Trusted GitHub env -> core context; never read context from Issue text."""
    def number(key: str) -> int:
        v = environ.get(key, "")
        if not re.fullmatch(r"[1-9][0-9]{0,18}", v):
            refuse("GITHUB_CONTEXT_NUMBER_INVALID")
        return int(v)
    if not SHA40.fullmatch(reviewed_git_sha):
        refuse("REVIEWED_GIT_SHA_INVALID")
    return {
        "event_name": environ.get("GITHUB_EVENT_NAME", ""),
        "actor": environ.get("GITHUB_ACTOR", ""),
        "repository": environ.get("GITHUB_REPOSITORY", ""),
        "ref": environ.get("GITHUB_REF", ""),
        "checked_out_sha": reviewed_git_sha,
        "run_id": number("GITHUB_RUN_ID"),
        "run_attempt": number("GITHUB_RUN_ATTEMPT"),
    }


def authorize_from_event(event: dict, environ: dict[str, str], order: dict,
                         policy: dict, reviewed_git_sha: str) -> tuple[dict, ClaimRequest]:
    """Returns an OFFLINE plan, never schedules a job."""
    ctx = event_context_from_env(environ, reviewed_git_sha)
    plan = core.authorize(event, ctx, order, policy)
    claim = claim_request(order, plan, policy)
    return plan, claim


def software_only_command(order: dict, workspace: Path, codex: Path) -> list[str]:
    """Construct a future Codex argv, NOT EXECUTED by the Gate1B CLI.

    Workspace-write sandbox is NOT a substitute for OS-enforced device
    isolation. Production must run on ephemeral GitHub-hosted runner and
    must provide credentials without exposing a GitHub write token to Codex.
    """
    if order["capability"] != "software-pr":
        refuse("CODEX_SOFTWARE_ONLY_REQUIRED")
    if not isinstance(workspace, Path) or not workspace.is_absolute():
        refuse("CODEX_WORKSPACE_INVALID")
    if not isinstance(codex, Path) or not codex.is_absolute():
        refuse("CODEX_BINARY_INVALID")
    return [str(codex), "--ask-for-approval", "never", "exec",
            "--sandbox", "workspace-write",
            "--cd", str(workspace), "-"]


def offline_mock_codex_acceptance(order: dict, policy: dict,
                                   scratch: Path, mock_codex: Path) -> dict:
    """Gate 1B fake-Codex contract (not live model execution).

    The fixture runs a deterministic untrusted-like executable in a fresh
    CI temporary dir. No GitHub auth or hardware mounts are supplied.
    Does not claim that arbitrary executable code is intrinsically sandboxed.
    """
    rule = core.validate_work_order(order, policy)
    if (order["capability"] != "software-pr"
            or rule["worker_class"] != ALLOWED_WORKER
            or order["authorization_kind"] != "gate1-implementation"
            or not DEV_NULL.issubset(set(order["scope"]["deny_resources"]))):
        refuse("OFFLINE_SOFTWARE_SCOPE_DENIED")
    if not isinstance(scratch, Path) or scratch.is_symlink() or not scratch.is_dir():
        refuse("OFFLINE_SCRATCH_INVALID")
    if not isinstance(mock_codex, Path) or not mock_codex.is_absolute() or not mock_codex.is_file():
        refuse("OFFLINE_MOCK_CODEX_REQUIRED")
    repo_paths = order["scope"]["allow_repo_paths"]
    if not all(p.startswith("docs/") or p == "scripts/tests" or p.startswith("scripts/tests/") for p in repo_paths):
        refuse("SOFTWARE_SMOKE_REPO_SCOPE_INVALID")
    # Fake executable is a trusted CI fixture; no actual Codex auth, repo
    # token, network grant or hardware device access.
    command = [str(mock_codex), "--simulate-codex-v1", str(scratch)]
    allow_env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG")
                 if k in os.environ}
    try:
        result = subprocess.run(
            command, input="PLASMA offline software-only fake Codex acceptance\n",
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=allow_env,
            timeout=min(order["timeout_seconds"], 20), check=False,
            cwd=scratch,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise core.ContractDenied("OFFLINE_MOCK_CODEX_NOT_COMPLETED") from exc
    if result.returncode != 0:
        refuse("OFFLINE_MOCK_CODEX_FAILED")
    receipt = scratch / "result.txt"
    if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 1024:
        refuse("OFFLINE_MOCK_CODEX_EVIDENCE_MISSING")
    if receipt.read_text() != "GATE1B_FAKE_CODEX_PASS\n":
        refuse("OFFLINE_MOCK_CODEX_EVIDENCE_INVALID")
    return {
        "status": "OFFLINE_FAKE_CODEX_CONTRACT_PASS_NOT_REAL_CODEX",
        "work_order_sha256": core.digest(order),
        "evidence_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        "runtime_enabled": False,
        "software_only": True,
        "hardware_access_verified": False,
        "codex_model_access_verified": False,
    }


def main() -> int:
    """No CLI for GitHub claims or model execution until next approved gate."""
    print(json.dumps({"status": CI_NO_RUNTIME, "runtime_enabled": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
