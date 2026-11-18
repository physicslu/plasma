#!/usr/bin/env python3
"""PLASMA reusable Path 2/3 dispatcher candidate.

Qualification-only adapter to the immutable Gate 1A contract; runtime defaults
OFF. This is not the active Development Mode Path 3 dispatcher; its restrictive
software-pr isolation profile must not be interpreted as a blanket Path 3
Host-only policy. No runtime capability or permission is enabled here.
Never invokes GitHub APIs or creates a claim. GitHub's trusted hosted job
must authorize, atomically create the protected one-shot claim, and only
then release a job to a separately provisioned isolated worker.
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

import plasma_engineering_dispatch_v1 as contract

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_VERSION = "plasma.engineering.runtime_request.v1"
DENIED = "NO_GO_RUNTIME_DISPATCH"
# Qualification-only, disabled-by-default capability mapping. Development
# Mode Path 3 uses the separate owner-approved codex-workspace Work Order.
PATHS = {"path2-cli": "software-readonly", "path3-codex": "software-pr"}
TASK_FIELDS = frozenset({"kind", "script", "argv", "prompt"})
BUNDLE_FIELDS = frozenset({
    "schema_version", "execution_path", "work_order", "work_order_sha256",
    "task", "isolation_profile",
})
REQUIRED_DENIALS = frozenset({
    "usb", "z2", "fpga", "mmio", "dut", "hub-power",
    "network-instrument", "host-root",
})
ISOLATION_PATH = Path("/etc/plasma/engineering-dispatch/isolation-v1.json")
EXPECTED_RUNNER = "SWPC-plasma-dispatch-isolated"


def refuse(code: str) -> None:
    raise contract.ContractDenied(code)


def digest(value: dict) -> str:
    return hashlib.sha256(contract.canonical_bytes(value)).hexdigest()


def verify_bundle(bundle: object, legacy_policy: dict) -> dict:
    """Strict schema, existing capability contract and safe command profiles."""
    bundle = contract.exact_keys(bundle, BUNDLE_FIELDS, "RUNTIME_BUNDLE_FIELDS_INVALID")
    if bundle["schema_version"] != RUNTIME_VERSION:
        refuse("RUNTIME_BUNDLE_VERSION_DENIED")
    path = bundle["execution_path"]
    if type(path) is not str or path not in PATHS:
        refuse("RUNTIME_PATH_DENIED")
    order = bundle["work_order"]
    # Gate 1A still validates every field and keeps all runtime flags FALSE.
    contract.validate_work_order(order, legacy_policy)
    if order["capability"] != PATHS[path]:
        refuse("RUNTIME_CAPABILITY_PATH_MISMATCH")
    if bundle["work_order_sha256"] != contract.digest(order):
        refuse("RUNTIME_WORK_ORDER_DIGEST_MISMATCH")
    if bundle["isolation_profile"] != "swpc-no-hardware-v1":
        refuse("RUNTIME_ISOLATION_PROFILE_DENIED")
    if not REQUIRED_DENIALS.issubset(set(order["scope"]["deny_resources"])):
        refuse("RUNTIME_HARDWARE_SCOPE_DENIED")
    task = contract.exact_keys(bundle["task"], TASK_FIELDS, "RUNTIME_TASK_FIELDS_INVALID")
    script, argv, prompt = task["script"], task["argv"], task["prompt"]
    if type(argv) is not list or len(argv) > 12 or any(
        type(a) is not str or not re.fullmatch(r"[a-zA-Z0-9._=@/:-]{1,120}", a)
        or a.startswith("-") or ".." in a for a in argv
    ):
        refuse("RUNTIME_TASK_ARGV_DENIED")
    if path == "path2-cli":
        if task["kind"] != "checked-in-python" or prompt is not None:
            refuse("RUNTIME_CLI_TASK_DENIED")
        if (type(script) is not str or not contract.safe_path(script)
                or not script.startswith("scripts/experiments/")
                or not script.endswith(".py")
                or script not in order["scope"]["allow_repo_paths"]):
            refuse("RUNTIME_CLI_SCRIPT_DENIED")
    else:
        if task["kind"] != "codex-workspace" or script is not None or argv:
            refuse("RUNTIME_CODEX_TASK_DENIED")
        if (type(prompt) is not str or not 20 <= len(prompt) <= 3000
                or any(c in prompt for c in ("\\x00", "\\r"))):
            refuse("RUNTIME_CODEX_PROMPT_DENIED")
    return {
        "status": "RUNTIME_BUNDLE_VALIDATED_NO_EXECUTION",
        "execution_path": path,
        "work_order_id": order["work_order_id"],
        "revision": order["revision"],
        "reviewed_main_sha": order["reviewed_main_sha"],
        "work_order_sha256": contract.digest(order),
        "bundle_sha256": digest(bundle),
        "capability": order["capability"],
        "timeout_seconds": order["timeout_seconds"],
    }


def authorize_dispatch(event: object, context: object, bundle: dict,
                       legacy_policy: dict) -> dict:
    plan = verify_bundle(bundle, legacy_policy)
    context = contract.exact_keys(context, frozenset({
        "event_name", "actor", "repository", "ref", "checked_out_sha",
        "run_id", "run_attempt",
    }), "RUNTIME_CONTEXT_INVALID")
    if (context["event_name"] != "workflow_dispatch"
            or context["actor"] != contract.OWNER
            or context["repository"] != contract.REPO
            or context["ref"] != "refs/heads/main"):
        refuse("RUNTIME_EVENT_OR_OWNER_DENIED")
    if context["checked_out_sha"] != plan["reviewed_main_sha"]:
        refuse("RUNTIME_PINNED_MAIN_SHA_MISMATCH")
    contract.positive_int(context["run_id"], 2**63 - 1, "RUNTIME_RUN_ID_DENIED")
    if context["run_attempt"] != 1 or type(context["run_attempt"]) is not int:
        refuse("RUNTIME_RERUN_DENIED")
    if type(event) is not dict or event.get("ref") not in ("refs/heads/main", "main"):
        refuse("RUNTIME_EVENT_METADATA_DENIED")
    sender = event.get("sender")
    repo = event.get("repository")
    inputs = event.get("inputs")
    if (type(sender) is not dict or sender.get("login") != contract.OWNER
            or type(repo) is not dict or repo.get("full_name") != contract.REPO
            or type(inputs) is not dict
            or set(inputs) != {"work_order_id", "bundle_sha256"}):
        refuse("RUNTIME_EVENT_INPUTS_DENIED")
    if (inputs["work_order_id"] != plan["work_order_id"]
            or inputs["bundle_sha256"] != plan["bundle_sha256"]):
        refuse("RUNTIME_DISPATCH_SHA_MISMATCH")
    # Protected Git ref creation is the actual claim; this is only a proposal.
    claim = ("refs/heads/plasma-engineering-claims/"
             + plan["work_order_id"] + "/r" + str(plan["revision"]))
    return {**plan, "status": "AUTHORIZED_PENDING_ATOMIC_CLAIM",
            "claim_ref": claim, "run_id": context["run_id"]}


def isolation_check(marker: Path = ISOLATION_PATH) -> dict:
    """External root-owned OS isolation is mandatory; no prompt-only bypass."""
    if (os.geteuid() == 0 or os.environ.get("RUNNER_NAME") != EXPECTED_RUNNER
            or os.environ.get("RUNNER_ENVIRONMENT") != "self-hosted"
            or os.environ.get("GITHUB_REPOSITORY") != contract.REPO):
        refuse("RUNTIME_WORKER_IDENTITY_DENIED")
    try:
        if marker.is_symlink():
            refuse("RUNTIME_ISOLATION_SYMLINK_DENIED")
        st = marker.stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            refuse("RUNTIME_ISOLATION_PROVENANCE_DENIED")
        data = contract.load_json(marker)
    except (OSError, ValueError) as exc:
        refuse("RUNTIME_ISOLATION_EVIDENCE_MISSING")
    if (type(data) is not dict or set(data) != {
        "schema_version", "runner", "os_isolated", "no_hardware_devices",
        "lab_network_blocked", "provisioner",
    } or data["schema_version"] != "plasma.dispatch.isolation.v1"
            or data["runner"] != EXPECTED_RUNNER or data["os_isolated"] is not True
            or data["no_hardware_devices"] is not True
            or data["lab_network_blocked"] is not True
            or data["provisioner"] != "root"):
        refuse("RUNTIME_ISOLATION_ATTESTATION_DENIED")
    return data


def run_worker(bundle: dict, policy: dict, expected_digest: str,
               *, executor=subprocess.run) -> dict:
    """Only reachable from an independently isolated, claimed worker.

    No shell, sudo, SSH, hardware, git push or GH token is passed to tasks.
    """
    plan = verify_bundle(bundle, policy)
    if plan["bundle_sha256"] != expected_digest:
        refuse("RUNTIME_WORKER_SHA_MISMATCH")
    isolation_check()
    order = bundle["work_order"]
    task = bundle["task"]
    if plan["execution_path"] == "path2-cli":
        script = REPO_ROOT / task["script"]
        if script.is_symlink() or not script.is_file():
            refuse("RUNTIME_SCRIPT_MISSING")
        command = [sys.executable, str(script), *task["argv"]]
        task_input = None
    else:
        # This legacy worker retains its attested OS isolation, without
        # overriding the operator's Codex CLI policy.
        command = ["codex", "exec", "-"]
        task_input = (
            task["prompt"] + "\\n\\nOnly modify these reviewed repository paths: "
            + ", ".join(order["scope"]["allow_repo_paths"])
            + "\\nNever access devices, privileged APIs, local lab networks, "
            "or publish/merge a PR. Produce test evidence.\\n"
        ).encode("utf-8")
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    result = executor(
        command, input=task_input, cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=min(order["timeout_seconds"], 900), check=False,
    )
    if len(result.stdout) > 65536 or len(result.stderr) > 65536:
        refuse("RUNTIME_OUTPUT_TOO_LARGE")
    return {
        "status": "WORKER_PASS" if result.returncode == 0 else "WORKER_FAIL",
        "exit_code": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "bundle_sha256": expected_digest,
        "execution_path": plan["execution_path"],
    }


ACTIVATION_PATH = REPO_ROOT / "specs/engineering-dispatch/runtime-activation-v1.json"


def require_reviewed_activation(path: str, activation: object) -> None:
    """Repository-pinned second interlock, never inferred from Actions vars."""
    activation = contract.exact_keys(
        activation, frozenset({"schema_version", "status", "paths", "notes"}),
        "RUNTIME_ACTIVATION_POLICY_INVALID",
    )
    paths = contract.exact_keys(
        activation["paths"], frozenset(PATHS), "RUNTIME_ACTIVATION_PATHS_INVALID",
    )
    if (activation["schema_version"] != "plasma.engineering.runtime_activation.v1"
            or activation["status"] != "ENABLED_BY_SEPARATE_APPROVAL"
            or any(type(flag) is not bool for flag in paths.values())
            or paths[path] is not True):
        refuse("RUNTIME_ACTIVATION_NOT_APPROVED")


def load_bundle(path: Path, policy_path: Path) -> tuple[dict, dict]:
    raw = contract.load_json(path)
    policy = contract.load_json(policy_path)
    verify_bundle(raw, policy)
    return raw, policy


def main() -> int:
    parser = argparse.ArgumentParser(description="Reusable Engineering Runtime candidate")
    parser.add_argument("mode", choices=("validate", "authorize", "worker"))
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--event", type=Path)
    args = parser.parse_args()
    try:
        bundle, policy = load_bundle(args.bundle, args.policy)
        if args.mode != "validate":
            require_reviewed_activation(
                bundle["execution_path"], contract.load_json(ACTIVATION_PATH),
            )
        if args.mode == "validate":
            result = verify_bundle(bundle, policy)
        elif args.mode == "authorize":
            if args.event is None or args.expected_sha256 is None:
                refuse("RUNTIME_ARGUMENTS_MISSING")
            event = contract.load_json(args.event)
            context = {
                "event_name": os.environ.get("GITHUB_EVENT_NAME"),
                "actor": os.environ.get("GITHUB_ACTOR"),
                "repository": os.environ.get("GITHUB_REPOSITORY"),
                "ref": os.environ.get("GITHUB_REF"),
                "checked_out_sha": os.environ.get("GITHUB_SHA"),
                "run_id": int(os.environ.get("GITHUB_RUN_ID", "0")),
                "run_attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
            }
            result = authorize_dispatch(event, context, bundle, policy)
            if result["bundle_sha256"] != args.expected_sha256:
                refuse("RUNTIME_DISPATCH_SHA_MISMATCH")
        else:
            if args.expected_sha256 is None:
                refuse("RUNTIME_ARGUMENTS_MISSING")
            result = run_worker(bundle, policy, args.expected_sha256)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("status") != "WORKER_FAIL" else 2
    except (contract.ContractDenied, OSError, subprocess.TimeoutExpired,
            subprocess.SubprocessError, ValueError) as exc:
        code = str(exc) if isinstance(exc, contract.ContractDenied) else "RUNTIME_FAILURE"
        print(json.dumps({"status": DENIED, "reason": code}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
