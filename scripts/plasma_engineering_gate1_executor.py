#!/usr/bin/env python3
"""Gate 1 executor choice: OFFLINE routing proposal; never an executor.

A ChatGPT/Codex choice is selected at Gate 1, not inferred from capability.
Capability independently determines permitted hardware resources. Hardware
may use an explicitly authorized SWPC execution lane, never an unrestricted
model shell. This module does NOT authorize, dispatch, run or merge anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import plasma_engineering_dispatch_v1 as core

EXECUTORS = frozenset({"chatgpt", "codex"})
NO_RUNTIME_STATUS = "GATE1_EXECUTOR_CHOICE_CONTRACT_ONLY_NO_DISPATCH"
CHOICE_KEYS = frozenset({"executor", "work_order_sha256"})


def plan_route(order: object, policy: object, choice: object) -> dict:
    rule = core.validate_work_order(order, policy)
    choice = core.exact_keys(choice, CHOICE_KEYS, "GATE1_EXECUTOR_CHOICE_INVALID")
    executor = choice["executor"]
    if type(executor) is not str or executor not in EXECUTORS:
        core.deny("GATE1_EXECUTOR_UNKNOWN")
    if (type(choice["work_order_sha256"]) is not str
            or choice["work_order_sha256"] != core.digest(order)):
        core.deny("GATE1_EXECUTOR_WORK_ORDER_DIGEST_MISMATCH")

    hardware = rule["hardware_authorization"]
    # Execution actor and capability are orthogonal. ChatGPT cannot directly
    # drive physical devices from an arbitrary cloud tool or OS shell.
    lane = ("swpc-controlled-hardware" if hardware else
            ("chatgpt-direct-github" if executor == "chatgpt" else
             "hosted-software-codex"))
    intent = {
        "work_order_sha256": choice["work_order_sha256"],
        "executor": executor,
        "capability": order["capability"],
        "authorization_kind": order["authorization_kind"],
        "reviewed_main_sha": order["reviewed_main_sha"],
        "lane": lane,
    }
    selection_sha256 = hashlib.sha256(core.canonical_bytes(intent)).hexdigest()
    return {
        "status": NO_RUNTIME_STATUS,
        "work_order_id": order["work_order_id"],
        "revision": order["revision"],
        "executor": executor,
        "capability": order["capability"],
        "lane": lane,
        "selection_sha256": selection_sha256,
        "hardware": hardware,
        "required_permissions": list(rule["permissions"]),
        "must_deny": list(rule["must_deny"]),
        "hardware_one_shot_required": hardware,
        "github_owner_approval_verified": False,
        "hardware_permission_granted": False,
        "qualified_runtime_path": False,
        "runtime_enabled": False,
        "gate2_merge_requires_separate_approval": True,
        "automatic_fallback_or_executor_switch": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Gate 1 executor choice planner")
    parser.add_argument("--work-order", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--executor", choices=sorted(EXECUTORS), required=True)
    args = parser.parse_args()
    try:
        order = core.load_json(args.work_order)
        policy = core.load_json(args.policy)
        choice = {"executor": args.executor, "work_order_sha256": core.digest(order)}
        print(json.dumps(plan_route(order, policy, choice), sort_keys=True))
        return 0
    except (core.ContractDenied, OSError) as exc:
        # Do not print file paths or sensitive untrusted Work Order content.
        code = str(exc) if isinstance(exc, core.ContractDenied) else "GATE1_INPUT_IO_DENIED"
        print(json.dumps({"status": "DENIED", "reason": code, "runtime_enabled": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
