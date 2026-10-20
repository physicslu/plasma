#!/usr/bin/env python3
"""Path 2: independent BUILD, DOWNLOAD, TESTING triggers and optional chaining.

Each successor requires an explicit owner-selected flag in the SAME trusted
request; both flags default false. This module provides neither privileged
access nor a live FPGA adapter. Real DOWNLOAD/TESTING remain unavailable
until independent target authorization, current-state checks and recovery
ownership are implemented. These APIs accept fakes ONLY for offline tests.
"""
from __future__ import annotations

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


def check_approval(task_id: str, approval: dict) -> tuple[str, bool, bool]:
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
            and type(pr) is int
            and ((pr == 0 and source == trusted)
                 or (pr > 0 and source != trusted)),
            "STAGE_SOURCE_IDENTITY_DENIED")
    auto_download = approval.get("auto_download", False)
    auto_testing = approval.get("auto_testing", False)
    require(type(auto_download) is bool and type(auto_testing) is bool,
            "STAGE_OPTION_TYPE_DENIED")
    require((not auto_download or stage == "BUILD")
            and (not auto_testing or stage in ("BUILD", "DOWNLOAD"))
            and (not (stage == "BUILD" and auto_testing) or auto_download),
            "STAGE_OPTION_SCOPE_DENIED")
    return stage, auto_download, auto_testing


def check_build_evidence(receipt: dict, source: str) -> dict:
    """CI PASS is not SWPC Vivado evidence; prove hashes/source/stage."""
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
    """Structure only. Authentic current-boot evidence needs a live collector."""
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
    """Run requested stage, optionally follow the TWO independent switches.

    Unchecked CLI flags and user-supplied JSON are NEVER hardware admission.
    A trusted backend must still supply validated build/download receipts,
    root-route and current-boot checks, AXI/driver ownership, timeout/reaping,
    persistent recovery lease and verified base.bin restore. No live adapter
    exists in this revision; the trusted dispatcher supplies none.

    On hardware exception, callback owns its safe recovery/UNKNOWN receipt.
    This coordinator NEVER retries a failed FPGA write.
    """
    stage, auto_download, auto_testing = check_approval(task_id, approval)
    require(isinstance(evidence_dir, Path) and evidence_dir.is_dir()
            and not evidence_dir.is_symlink(), "STAGE_EVIDENCE_DIR_DENIED")
    output = evidence_dir / ("plasma-path2-" + stage.lower() + ".json")
    require(not output.exists(), "STAGE_EVIDENCE_EXISTS")
    source = approval["pinned_sha"]
    do_download = stage == "DOWNLOAD" or auto_download
    do_testing = stage == "TESTING" or auto_testing
    # Validate permissions and adapters BEFORE invoking Build or hardware.
    if do_download:
        require(hardware_authorized is True and download is not None,
                "STAGE_LIVE_DOWNLOAD_BACKEND_UNAVAILABLE")
    if do_testing:
        require(hardware_authorized is True and testing is not None,
                "STAGE_LIVE_TEST_BACKEND_UNAVAILABLE")
    report = {"schema": "plasma.path2.staged.v1", "stage": stage,
              "source_sha": source, "outcome": "NOT_RUN",
              "auto_download": auto_download, "auto_testing": auto_testing,
              "next_stage_triggered": False, "physical_execution": "NOT_RUN",
              "completed_stages": {}}
    if stage == "BUILD":
        require(build is not None, "STAGE_BUILD_ENGINE_MISSING")
        build_receipt = check_build_evidence(build(), source)
        report["completed_stages"]["BUILD"] = "PASS"
        report["bit_sha256"] = build_receipt["bit_sha256"]
        report["hwh_sha256"] = build_receipt["hwh_sha256"]
    elif stage == "DOWNLOAD":
        require(previous is not None, "STAGE_BUILD_EVIDENCE_REQUIRED")
        build_receipt = check_build_evidence(previous, source)
    else:
        require(previous is not None, "STAGE_DOWNLOAD_EVIDENCE_REQUIRED")
        download_receipt = check_download_evidence(previous, source)

    if do_download:
        # A downloaded image may remain active between separate triggers:
        # the adapter must have already committed an independent restore
        # lease / watchdog before changing FPGA state.
        result = download()
        require(type(result) is dict, "STAGE_DOWNLOAD_RESULT_UNKNOWN")
        download_receipt = check_download_evidence(result, source)
        report["completed_stages"]["DOWNLOAD"] = "PASS"
        report["session_id"] = download_receipt["session_id"]
        report["boot_id"] = download_receipt["boot_id"]
        report["restore_lease_active"] = True
        report["candidate_image_verified"] = True
        report["physical_execution"] = "ATTEMPTED"
        if stage == "BUILD":
            report["next_stage_triggered"] = True

    if do_testing:
        # Trust in prior receipt alone is insufficient for live execution.
        # Target-side adapter MUST revalidate FPGA, boot, ownership and
        # perform a bounded MMIO read + verified restore before PASS.
        result = testing()
        require(type(result) is dict
                and result.get("identity") == "PASS"
                and result.get("restore") == "PASS"
                and result.get("restoration_verified") == "PASS",
                "STAGE_TEST_OR_RESTORE_UNKNOWN")
        report["completed_stages"]["TESTING"] = "PASS"
        report["restoration_verified"] = True
        report["physical_execution"] = "ATTEMPTED"
        if stage == "DOWNLOAD" or do_download:
            report["next_stage_triggered"] = True

    report["outcome"] = "PASS"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return report
