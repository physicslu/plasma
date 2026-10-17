#!/usr/bin/env python3
"""PLASMA Engineering Dispatch v1: OFFLINE contract only, no executor.

No dynamic command execution, hardware access, GitHub API mutation or workflow
trigger is implemented here. Future adapters MUST separately enforce trusted
GitHub event provenance, globally durable idempotency, worker isolation and
fresh Gate 2/one-shot physical authorizations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

REPO = "physicslu/plasma"
OWNER = "physicslu"
SCHEMA_VERSION = "plasma.engineering.work_order.v1"
POLICY_VERSION = "plasma.engineering.capabilities.v1"
NO_RUNTIME = "CONTRACT_ONLY_NO_RUNTIME_DISPATCH"
CAPABILITIES = frozenset({
    "software-readonly", "software-pr", "la2016-loopback",
    "z2-readonly", "z2-privileged",
})
PERMISSIONS = frozenset({
    "repo:read", "repo:write-branch", "usb:la2016",
    "ssh:z2-readonly", "z2:hardware-owner",
})
RESOURCES = frozenset({
    "usb", "z2", "fpga", "mmio", "dut", "hub-power",
    "network-instrument", "repository-write", "host-root",
})
EVIDENCE = frozenset({
    "sanitized-receipt", "ci-checks", "pr-url", "sha256-manifest",
    "sr-waveform", "readonly-inventory", "offline-test-report",
})
ORDER_KEYS = frozenset({
    "schema_version", "work_order_id", "revision", "repository",
    "issue_number", "requested_by", "reviewed_main_sha",
    "authorization_kind", "objective", "capability", "entrypoint",
    "scope", "timeout_seconds", "acceptance", "evidence",
})
SCOPE_KEYS = frozenset({"allow_repo_paths", "deny_resources", "required_permissions"})
REQUIRED_CONTEXT = frozenset({
    "event_name", "actor", "repository", "ref",
    "checked_out_sha", "run_id", "run_attempt",
})
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
WORK_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")
PATH_CHARS = re.compile(r"[a-zA-Z0-9._/-]{1,160}\Z")


class ContractDenied(ValueError):
    """Fixed public reason-code only; never include untrusted input in output."""


def deny(code: str) -> None:
    raise ContractDenied(code)


def exact_keys(value: object, expected: frozenset[str], reason: str) -> dict:
    if type(value) is not dict or set(value) != expected:
        deny(reason)
    return value


def positive_int(value: object, maximum: int, code: str) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        deny(code)
    return value


def safe_path(value: object) -> bool:
    if type(value) is not str or not PATH_CHARS.fullmatch(value):
        return False
    if value.startswith(("/", "-")) or "//" in value or ".." in value or "\\" in value:
        return False
    parts = PurePosixPath(value).parts
    return bool(parts) and all(p not in {".", ".."} for p in value.split("/"))


def strings(value: object, *, allowed: frozenset[str] | None = None,
            min_count: int = 1, max_count: int = 32, min_chars: int = 0,
            max_chars: int = 256, reason: str) -> list[str]:
    if (type(value) is not list or not min_count <= len(value) <= max_count
            or any(type(v) is not str or not min_chars <= len(v) <= max_chars
                   for v in value)):
        deny(reason)
    if len(set(value)) != len(value):
        deny(reason)
    if allowed is not None and any(v not in allowed for v in value):
        deny(reason)
    return value


def validate_work_order(order: object, policy: object) -> dict:
    order = exact_keys(order, ORDER_KEYS, "WORK_ORDER_FIELDS_INVALID")
    if order["schema_version"] != SCHEMA_VERSION:
        deny("WORK_ORDER_VERSION_DENIED")
    if (type(order["work_order_id"]) is not str
            or not WORK_ID.fullmatch(order["work_order_id"])):
        deny("WORK_ORDER_ID_INVALID")
    positive_int(order["revision"], 2**31 - 1, "WORK_ORDER_REVISION_INVALID")
    positive_int(order["issue_number"], 2**31 - 1, "WORK_ORDER_ISSUE_INVALID")
    if order["repository"] != REPO or order["requested_by"] != OWNER:
        deny("WORK_ORDER_OWNER_DENIED")
    if type(order["reviewed_main_sha"]) is not str or not HEX40.fullmatch(order["reviewed_main_sha"]):
        deny("WORK_ORDER_PIN_INVALID")
    if order["authorization_kind"] not in {
        "gate1-implementation", "hardware-one-shot",
    }:
        deny("WORK_ORDER_AUTHORIZATION_KIND_INVALID")
    if (type(order["objective"]) is not str
            or not 10 <= len(order["objective"]) <= 2048
            or any(ch in order["objective"] for ch in ("\x00", "\r"))):
        deny("WORK_ORDER_OBJECTIVE_INVALID")
    positive_int(order["timeout_seconds"], 3600, "WORK_ORDER_TIMEOUT_INVALID")
    capability = order["capability"]
    if type(capability) is not str or capability not in CAPABILITIES:
        deny("CAPABILITY_UNKNOWN")
    scope = exact_keys(order["scope"], SCOPE_KEYS, "WORK_ORDER_SCOPE_INVALID")
    paths = strings(scope["allow_repo_paths"], min_chars=1, max_chars=160,
                    max_count=32, reason="WORK_ORDER_PATHS_INVALID")
    if any(not safe_path(p) for p in paths):
        deny("WORK_ORDER_PATHS_INVALID")
    denied = strings(scope["deny_resources"], allowed=RESOURCES,
                     max_count=12, reason="WORK_ORDER_DENY_INVALID")
    required = strings(scope["required_permissions"], allowed=PERMISSIONS,
                       max_count=12, reason="WORK_ORDER_PERMISSIONS_INVALID")
    strings(order["acceptance"], min_chars=5, max_chars=256, max_count=16,
            reason="WORK_ORDER_ACCEPTANCE_INVALID")
    strings(order["evidence"], allowed=EVIDENCE, max_count=16,
            reason="WORK_ORDER_EVIDENCE_INVALID")

    policy = exact_keys(policy, frozenset({"schema_version", "status", "capabilities"}),
                        "CAPABILITY_POLICY_FIELDS_INVALID")
    if policy["schema_version"] != POLICY_VERSION or policy["status"] != NO_RUNTIME:
        deny("CAPABILITY_POLICY_VERSION_DENIED")
    all_caps = policy["capabilities"]
    if type(all_caps) is not dict or set(all_caps) != CAPABILITIES:
        deny("CAPABILITY_POLICY_INCOMPLETE")
    for name, rule in all_caps.items():
        exact_keys(rule, frozenset({
            "entrypoint", "worker_class", "runtime_enabled", "permissions",
            "max_timeout_seconds", "hardware_authorization", "must_deny",
        }), "CAPABILITY_RULE_INVALID")
        if type(rule["runtime_enabled"]) is not bool or rule["runtime_enabled"]:
            deny("RUNTIME_DISPATCH_FORBIDDEN_GATE1A")
        if type(rule["worker_class"]) is not str or not re.fullmatch(r"[a-z0-9-]{5,64}", rule["worker_class"]):
            deny("CAPABILITY_WORKER_INVALID")
        strings(rule["permissions"], allowed=PERMISSIONS,
                reason="CAPABILITY_PERMISSIONS_INVALID")
        strings(rule["must_deny"], allowed=RESOURCES,
                reason="CAPABILITY_DENY_INVALID")
        positive_int(rule["max_timeout_seconds"], 3600, "CAPABILITY_TIMEOUT_INVALID")
        if type(rule["hardware_authorization"]) is not bool:
            deny("CAPABILITY_HARDWARE_FLAG_INVALID")
        if type(rule["entrypoint"]) is not str:
            deny("CAPABILITY_ENTRYPOINT_INVALID")
    rule = all_caps[capability]
    if order["entrypoint"] != rule["entrypoint"]:
        deny("CAPABILITY_ENTRYPOINT_MISMATCH")
    if set(required) != set(rule["permissions"]):
        deny("CAPABILITY_PERMISSIONS_MISMATCH")
    if not set(rule["must_deny"]).issubset(denied):
        deny("CAPABILITY_NEGATIVE_SCOPE_MISSING")
    if order["timeout_seconds"] > rule["max_timeout_seconds"]:
        deny("CAPABILITY_TIMEOUT_EXCEEDED")
    if rule["hardware_authorization"] and order["authorization_kind"] != "hardware-one-shot":
        deny("HARDWARE_ONE_SHOT_APPROVAL_REQUIRED")
    if (not rule["hardware_authorization"]
            and order["authorization_kind"] != "gate1-implementation"):
        deny("SOFTWARE_GATE1_APPROVAL_REQUIRED")
    # A capability may never request permissions that its negative scope forbids.
    conflicts = {
        "usb": "usb:la2016", "z2": "ssh:z2-readonly",
        "repository-write": "repo:write-branch",
    }
    if any(r in denied and p in required for r, p in conflicts.items()):
        deny("CAPABILITY_ALLOW_DENY_CONFLICT")
    return rule


def canonical_bytes(order: dict) -> bytes:
    return json.dumps(order, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def digest(order: dict) -> str:
    return hashlib.sha256(canonical_bytes(order)).hexdigest()


def approval_command(order: dict) -> str:
    # No execution semantics; exact string to be manually reviewed.
    return ("/plasma-dispatch approve " + order["work_order_id"]
            + " rev=" + str(order["revision"])
            + " sha256=" + digest(order)
            + " kind=" + order["authorization_kind"])


def authorize(event: object, context: object, order: dict, policy: dict) -> dict:
    rule = validate_work_order(order, policy)
    context = exact_keys(context, REQUIRED_CONTEXT, "GITHUB_CONTEXT_INVALID")
    if (context["event_name"] != "issue_comment"
            or context["actor"] != OWNER
            or context["repository"] != REPO
            or context["ref"] != "refs/heads/main"):
        deny("GITHUB_CONTEXT_DENIED")
    if (type(context["checked_out_sha"]) is not str
            or context["checked_out_sha"] != order["reviewed_main_sha"]):
        deny("REVIEWED_SHA_CHANGED")
    positive_int(context["run_id"], 2**63-1, "GITHUB_RUN_ID_INVALID")
    positive_int(context["run_attempt"], 2**31-1, "GITHUB_RUN_ATTEMPT_INVALID")
    if type(event) is not dict or event.get("action") != "created":
        deny("EVENT_ACTION_DENIED")
    issue = event.get("issue")
    comment = event.get("comment")
    sender = event.get("sender")
    repository = event.get("repository")
    if any(type(x) is not dict for x in (issue, comment, sender, repository)):
        deny("EVENT_METADATA_INVALID")
    if (issue.get("number") != order["issue_number"]
            or "pull_request" in issue):
        deny("EVENT_ISSUE_DENIED")
    if (repository.get("full_name") != REPO
            or sender.get("login") != OWNER
            or type(comment.get("user")) is not dict
            or comment["user"].get("login") != OWNER):
        deny("EVENT_OWNER_DENIED")
    positive_int(comment.get("id"), 2**63-1, "EVENT_COMMENT_ID_INVALID")
    if comment.get("body") != approval_command(order):
        deny("APPROVAL_DIGEST_OR_BODY_MISMATCH")
    # A passing auth CONTRACT is not a runtime execution permit.
    return {
        "status": "AUTH_CONTRACT_PASS_NO_DISPATCH",
        "work_order_id": order["work_order_id"],
        "revision": order["revision"],
        "work_order_sha256": digest(order),
        "issue_number": order["issue_number"],
        "comment_id": comment["id"],
        "run_id": context["run_id"],
        "worker_class": rule["worker_class"],
        "runtime_enabled": False,
        "authorization_kind": order["authorization_kind"],
    }


def replay_key(plan: dict) -> str:
    # Same work-order revision cannot be re-approved by a new comment/run.
    return (str(plan["issue_number"]) + "--" + plan["work_order_id"]
            + "--r" + str(plan["revision"]))


def claim_offline(plan: dict, directory: Path) -> Path:
    """Atomic local receipt for contract tests, NOT cross-run GitHub storage.

    A production adapter needs a GitHub/concurrency-backed *global* durable
    ledger and must block hardware access if it cannot atomically claim.
    """
    if plan.get("status") != "AUTH_CONTRACT_PASS_NO_DISPATCH":
        deny("REPLAY_PLAN_UNAUTHORIZED")
    if directory.is_symlink():
        deny("REPLAY_DIRECTORY_SYMLINK_DENIED")
    st = directory.stat(follow_symlinks=False)
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
            or (st.st_mode & 0o077) != 0):
        deny("REPLAY_DIRECTORY_NOT_PRIVATE")
    key = replay_key(plan)
    if not re.fullmatch(r"[0-9]+--[a-z0-9-]+--r[1-9][0-9]*", key):
        deny("REPLAY_KEY_INVALID")
    path = directory / (key + ".json")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as exc:
        raise ContractDenied("WORK_ORDER_REVISION_ALREADY_CLAIMED") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(json.dumps(plan, sort_keys=True) + "\n")
        out.flush()
        os.fsync(out.fileno())
    return path


def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            deny("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def load_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        deny("JSON_FILE_DENIED")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _: deny("JSON_CONSTANT_DENIED"),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractDenied("JSON_PARSE_DENIED") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline-only engineering-dispatch v1 contract")
    parser.add_argument("operation", choices=("validate", "authorize"))
    parser.add_argument("--work-order", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--context", type=Path)
    args = parser.parse_args()
    try:
        order = load_json(args.work_order)
        policy = load_json(args.policy)
        validate_work_order(order, policy)
        if args.operation == "authorize":
            if args.event is None or args.context is None:
                deny("GITHUB_CONTEXT_REQUIRED")
            out = authorize(load_json(args.event), load_json(args.context), order, policy)
        else:
            if args.event is not None or args.context is not None:
                deny("VALIDATE_HAS_UNEXPECTED_INPUT")
            out = {"status": "VALIDATED_OFFLINE_ONLY_NO_DISPATCH",
                   "work_order_sha256": digest(order),
                   "reviewed_main_sha": order["reviewed_main_sha"],
                   "approval_command": approval_command(order),
                   "runtime_enabled": False}
        print(json.dumps(out, sort_keys=True))
        return 0
    except ContractDenied as exc:
        print(json.dumps({"status": "DENIED", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
