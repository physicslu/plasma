#!/usr/bin/env python3
"""Minimal Path 2 development cycle: Build -> FPGA Download -> Testing -> Restore.

This is an orchestration contract, NOT a hardware backend. It never opens
/dev/mem, contacts Z2, loads FPGA Manager or escalates privileges. The trusted
dispatcher must supply a separately reviewed, explicitly approved live
transaction adapter; the default is deliberately NOT_RUN. The transaction
must own atomic intent-before-load, current-boot admission and safe restore.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Callable

from pl.hil import f1b

TASK_ID = "z2-path2-development-cycle"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
BUILD_PASS = "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED"
HIL_PASS = "PASS_DEVELOPMENT_INTERNAL_FIXTURE"
STAGES = ("BUILD", "DOWNLOAD", "TESTING", "RESTORE")


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def validate_authorization(approval: dict) -> None:
    """Keep existing owner/PR/SHA/runner checks in trusted dispatcher."""
    require(type(approval) is dict
            and approval.get("task_id") == TASK_ID
            and approval.get("execution_path") == "path2-cli"
            and approval.get("execution_capability") == "z2-development-cycle",
            "CYCLE_APPROVAL_DENIED")
    sha = approval.get("pinned_sha")
    trusted = approval.get("trusted_sha")
    pr = approval.get("pr_number")
    require(type(sha) is str and SHA40.fullmatch(sha) is not None
            and type(trusted) is str and SHA40.fullmatch(trusted) is not None
            and type(pr) is int
            and ((pr == 0 and sha == trusted)
                 or (pr > 0 and sha != trusted)),
            "CYCLE_SOURCE_DENIED")


def f1b_transaction(*, lock_path: Path, observe: Callable,
                    record_intent: Callable, load: Callable,
                    identity: Callable, restore: Callable,
                    verify_restore: Callable) -> dict:
    """Reuse the existing F1-B safety guards, not SWD04's four-aperture test.

    observe MUST collect fresh process/VMA/fd, kernel-owner/AXI-idle, root,
    recovery and current-boot evidence. identity MUST execute in a supervised,
    bounded and reaped child and use f1b.read_identity's native aligned u32
    whitelist. Callers must not implement speculative driver unbind/reloads.
    """
    return f1b.supervised_sequence(
        lock_path=lock_path, observe=observe, record_intent=record_intent,
        load=load, identity=identity, restore=restore,
        verify_restore=verify_restore)


def run_cycle(*, approval: dict, build: Callable[[], dict],
              evidence_dir: Path, transaction: Callable[[], dict] | None = None,
              live_hardware_approved: bool = False) -> dict:
    """One call for all three stages, with no per-stage human gate.

    Trusted dispatcher passes the reviewed Vivado Build Engine as build().
    Without BOTH explicit trusted live admission and a real safe adapter,
    only Build runs. Offline tests inject synthetic functions, not devices.
    """
    validate_authorization(approval)
    require(type(evidence_dir) is Path and evidence_dir.is_dir()
            and not evidence_dir.is_symlink(), "CYCLE_EVIDENCE_DIR_DENIED")
    require(not (evidence_dir / "plasma-path2-cycle.json").exists(),
            "CYCLE_REPORT_ALREADY_EXISTS")
    stages = {name: "NOT_RUN" for name in STAGES}
    result = {"schema": "plasma.path2.development_cycle.v1",
              "source_sha": approval["pinned_sha"],
              "stages": stages, "overall": "NO_GO",
              "physical_execution": "NOT_RUN",
              "failure": None}
    try:
        receipt = build()
        require(type(receipt) is dict and receipt.get("status") == BUILD_PASS
                and receipt.get("physical_load") == "NOT_RUN"
                and receipt.get("z2_hil") == "NOT_RUN",
                "CYCLE_BUILD_NOT_QUALIFIED")
        stages["BUILD"] = "PASS"
    except Exception:
        stages["BUILD"] = "FAIL"
        result["failure"] = "BUILD_FAILED"
    else:
        if live_hardware_approved is not True or transaction is None:
            result["failure"] = "HARDWARE_BACKEND_NOT_AUTHORIZED"
        else:
            # No automatic retry and no second bitstream load on error.
            result["physical_execution"] = "ATTEMPTED"
            try:
                outcome = transaction()
                require(type(outcome) is dict
                        and set(("preflight", "candidate_load", "hil01",
                                 "hil02", "restore", "restoration_verified",
                                 "overall")) <= set(outcome),
                        "CYCLE_HIL_RECEIPT_INVALID")
                stages["DOWNLOAD"] = (
                    "PASS" if outcome["candidate_load"] == "PASS"
                    else "FAIL" if outcome["preflight"] == "PASS"
                    else "NOT_RUN")
                stages["TESTING"] = (
                    "PASS" if outcome["hil01"] == "PASS"
                    and outcome["hil02"] == "PASS"
                    else "FAIL" if stages["DOWNLOAD"] == "PASS"
                    else "NOT_RUN")
                stages["RESTORE"] = (
                    "PASS" if outcome["restore"] == "PASS"
                    and outcome["restoration_verified"] == "PASS"
                    else "NOT_RUN" if outcome["restore"] == "NOT_RUN"
                    else "UNKNOWN")
                if (outcome["overall"] == HIL_PASS
                        and all(stages[key] == "PASS"
                                for key in STAGES)):
                    result["overall"] = "PASS"
                else:
                    result["failure"] = "HIL_FAIL_OR_UNKNOWN"
            except Exception:
                # A crashed / unreaped worker or unverified restore is UNKNOWN.
                # Never invoke a second FPGA write from this coordinator.
                stages["RESTORE"] = "UNKNOWN"
                result["failure"] = "HIL_RESULT_UNKNOWN"
    report = evidence_dir / "plasma-path2-cycle.json"
    with report.open("x", encoding="utf-8") as out:
        json.dump(result, out, sort_keys=True, indent=2)
        out.write("\n")
    return result
