#!/usr/bin/env python3
"""Path 2 staged Development Mode: three separate triggers, never a chain.

Existing Vivado Engine is the BUILD implementation. DOWNLOAD and TESTING
are independent commands which MUST NOT touch hardware until separately
reviewed live adapters and durable safety/restore ownership exist. All tests
here inject offline callbacks: this module opens no devices or network.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Callable

STAGE_TASKS = {
    "fixed-site1-vivado-host-build": "BUILD",
    "z2-path2-download": "DOWNLOAD",
    "z2-path2-testing": "TESTING",
}
CAPABILITIES = {"BUILD": "vivado-host-build",
                "DOWNLOAD": "z2-development-cycle",
                "TESTING": "z2-development-cycle"}
BUILD_PASS = "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED"
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class StageDenied(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise StageDenied(reason)


def check_approval(task_id: str, approval: dict) -> str:
    """Existing trusted Dispatcher authenticates owner, SHA, PR and runner."""
    stage = STAGE_TASKS.get(task_id)
    require(stage is not None and type(approval) is dict
            and approval.get("task_id") == task_id
            and approval.get("execution_path") == "path2-cli"
            and approval.get("execution_capability") == CAPABILITIES[stage],
            "STAGE_APPROVAL_DENIED")
    source, trusted, pr = (approval.get("pinned_sha"),
                           approval.get("trusted_sha"),
                           approval.get("pr_number"))
    require(type(source) is str and SHA40.fullmatch(source) is not None
            and type(trusted) is str and SHA40.fullmatch(trusted) is not None
            and type(pr) is int and
            ((pr == 0 and source == trusted)
             or (pr > 0 and source != trusted)),
            "STAGE_SOURCE_IDENTITY_DENIED")
    return stage


def check_build_evidence(receipt: dict, source: str) -> dict:
    """A hosted CI PASS alone is not real Vivado artifact evidence."""
    require(type(receipt) is dict
            and receipt.get("status") == BUILD_PASS
            and receipt.get("source_sha") == source
            and receipt.get("physical_load") == "NOT_RUN"
            and receipt.get("z2_hil") == "NOT_RUN"
            and type(receipt.get("bit_sha256")) is str
            and SHA256.fullmatch(receipt["bit_sha256"]) is not None
            and type(receipt.get("hwh_sha256")) is str
            and SHA256.fullmatch(receipt["hwh_sha256"]) is not None,
            "STAGE_BUILD_EVIDENCE_DENIED")
    return receipt


def check_download_evidence(receipt: dict, source: str) -> dict:
    """Only actual runtime collector can create a trusted session receipt.

    This validates structural continuity for OFFLINE testing; it does not
    authenticate a caller-provided JSON or grant physical FPGA access.
    """
    require(type(receipt) is dict
            and receipt.get("stage") == "DOWNLOAD"
            and receipt.get("source_sha") == source
            and receipt.get("outcome") == "PASS"
            and type(receipt.get("session_id")) is str
            and bool(receipt["session_id"])
            and type(receipt.get("boot_id")) is str
            and bool(receipt["boot_id"])
            and receipt.get("restore_lease_active") is True
            and receipt.get("candidate_image_verified") is True,
            "STAGE_DOWNLOAD_EVIDENCE_DENIED")
    return receipt


def run_stage(*, task_id: str, approval: dict, evidence_dir: Path,
              build: Callable[[], dict] | None = None,
              download: Callable[[], dict] | None = None,
              testing: Callable[[], dict] | None = None,
              previous: dict | None = None,
              hardware_authorized: bool = False) -> dict:
    """Execute exactly ONE requested stage; never trigger a successor.

    Injected DOWNLOAD/TESTING callbacks are for offline contract tests only.
    A real adapter requires independent trusted runtime approval, root route,
    source/hash/current-boot checks, AXI isolation, exclusive hardware owner,
    durable recovery intent and a working restore lease/watchdog. None is
    provided by this library or the GitHub Dispatcher in this PR.
    """
    stage = check_approval(task_id, approval)
    require(type(evidence_dir) is Path and evidence_dir.is_dir()
            and not evidence_dir.is_symlink(), "STAGE_EVIDENCE_DIR_DENIED")
    output = evidence_dir / ("plasma-path2-" + stage.lower() + ".json")
    require(not output.exists(), "STAGE_EVIDENCE_EXISTS")
    source = approval["pinned_sha"]
    report = {"schema": "plasma.path2.staged.v1", "stage": stage,
              "source_sha": source, "outcome": "NOT_RUN",
              "next_stage_triggered": False, "physical_execution": "NOT_RUN"}
    # All prerequisites must be established before attempting a hardware step.
    if stage == "BUILD":
        require(build is not None, "STAGE_BUILD_ENGINE_MISSING")
        actual = check_build_evidence(build(), source)
        report["outcome"] = "PASS"
        report["bit_sha256"] = actual["bit_sha256"]
        report["hwh_sha256"] = actual["hwh_sha256"]
    elif stage == "DOWNLOAD":
        require(previous is not None, "STAGE_BUILD_EVIDENCE_REQUIRED")
        check_build_evidence(previous, source)
        require(hardware_authorized is True and download is not None,
                "STAGE_LIVE_DOWNLOAD_BACKEND_UNAVAILABLE")
        # Hardware adapter must persist a bounded recovery lease BEFORE load.
        result = download()
        require(type(result) is dict and result.get("outcome") == "PASS"
                and result.get("restore_lease_active") is True
                and result.get("candidate_image_verified") is True
                and type(result.get("session_id")) is str
                and bool(result["session_id"])
                and type(result.get("boot_id")) is str
                and bool(result["boot_id"]),
                "STAGE_DOWNLOAD_RESULT_UNKNOWN")
        report.update({k: result[k] for k in
                       ("outcome", "restore_lease_active",
                        "candidate_image_verified", "session_id", "boot_id")})
        report["physical_execution"] = "ATTEMPTED"
    else:
        require(previous is not None, "STAGE_DOWNLOAD_EVIDENCE_REQUIRED")
        check_download_evidence(previous, source)
        require(hardware_authorized is True and testing is not None,
                "STAGE_LIVE_TEST_BACKEND_UNAVAILABLE")
        # Test adapter must reverify current boot/FPGA/ownership before MMIO;
        # restore original base.bin and independently verify it before PASS.
        result = testing()
        require(type(result) is dict and result.get("identity") == "PASS"
                and result.get("restore") == "PASS"
                and result.get("restoration_verified") == "PASS",
                "STAGE_TEST_OR_RESTORE_UNKNOWN")
        report["outcome"] = "PASS"
        report["physical_execution"] = "ATTEMPTED"
        report["restoration_verified"] = True
    # Each invocation writes only its own stage report. Never call another.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return report
