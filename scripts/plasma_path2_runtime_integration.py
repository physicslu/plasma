#!/usr/bin/env python3
"""Trusted Path 2 direct Root operations and reviewed host build."""
from __future__ import annotations

from pathlib import Path
import os
import json
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import plasma_development_stage_transport as transport
import plasma_path2_build_qualification as qualifier


class RuntimeDenied(ValueError):
    """Fail closed before expensive or privileged operations."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise RuntimeDenied(code)


def _sha(value: object, length: int) -> bool:
    return (type(value) is str and len(value) == length and
            re.fullmatch("[0-9a-f]+", value) is not None)


def host_build(task: dict, *, workspace: Path, approval: dict,
               evidence_dir: Path, executor=None,
               build_driver=None, qualify=None) -> dict:
    """Reviewed host build -> qualification. No Stage, Profile or Z2 Root call."""
    require(type(approval) is dict
            and approval.get("task_id") == "z2-path2-build"
            and approval.get("execution_capability") == "vivado-host-build"
            and approval.get("execution_path") == "path2-cli"
            and _sha(approval.get("pinned_sha"), 40)
            and _sha(approval.get("trusted_sha"), 40)
            and type(approval.get("pr_number")) is int
            and ((approval["pr_number"] == 0 and approval["pinned_sha"] ==
                  approval["trusted_sha"]) or
                 (approval["pr_number"] > 0 and approval["pinned_sha"] !=
                  approval["trusted_sha"])), "PATH2_BUILD_APPROVAL_DENIED")
    require(type(task) is dict
            and task.get("capability") == "vivado-host-build"
            and task.get("project") == "pl/projects/z2-fixed-unified-site1",
            "PATH2_BUILD_TASK_DENIED")
    auto_download = approval.get("auto_download_after_build_success", False)
    auto_testing = approval.get("auto_test_after_download_success", False)
    require(type(auto_download) is bool and type(auto_testing) is bool,
            "PATH2_BUILD_OPTION_TYPE_DENIED")
    require(not auto_download, "PATH2_LIVE_DOWNLOAD_PROVIDER_NOT_REGISTERED")
    require(evidence_dir is not None and evidence_dir.is_dir()
            and not evidence_dir.is_symlink(), "PATH2_EVIDENCE_DIR_DENIED")
    if build_driver is not None:
        raw = build_driver({"source_sha": approval["pinned_sha"]})
    else:
        kwargs = dict(task=task, workspace=workspace, approval=approval,
                      evidence_dir=evidence_dir)
        if executor is not None:
            kwargs["executor"] = executor
        import plasma_vivado_host_build as build
        raw = build.run(**kwargs)
    require(type(raw) is dict and
            raw.get("status") == "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED" and
            raw.get("execution_capability") == "vivado-host-build" and
            raw.get("source_sha") == approval["pinned_sha"] and
            raw.get("physical_load") == "NOT_RUN" and
            raw.get("z2_hil") == "NOT_RUN" and
            raw.get("m1") == "NO_GO" and
            _sha(raw.get("bit_sha256"), 64) and
            _sha(raw.get("hwh_sha256"), 64) and
            type(raw.get("report_sha256")) is dict and
            bool(raw["report_sha256"]) and
            all(_sha(x, 64) for x in raw["report_sha256"].values()),
            "VIVADO_BUILD_EVIDENCE_NOT_QUALIFIED")
    decision = (qualify(raw) if qualify is not None else
                qualifier.qualify_host_build(
                    raw, workspace=workspace,
                    pinned_sha=approval["pinned_sha"]))
    require(type(decision) is dict and set(decision) == {
                "decision", "source_sha", "bit_sha256", "hwh_sha256",
                "qualification_evidence_sha256"} and
            decision["decision"] == "APPROVED" and
            decision["source_sha"] == approval["pinned_sha"] and
            decision["bit_sha256"] == raw["bit_sha256"] and
            decision["hwh_sha256"] == raw["hwh_sha256"] and
            _sha(decision["qualification_evidence_sha256"], 64),
            "BUILD_QUALIFICATION_REQUIRED")
    return {
        "status": "HOST_BUILD_QUALIFIED_NO_HARDWARE",
        "source_sha": approval["pinned_sha"],
        "bit_sha256": raw["bit_sha256"],
        "hwh_sha256": raw["hwh_sha256"],
        "qualification_evidence_sha256":
            decision["qualification_evidence_sha256"],
        "physical_load": "NOT_RUN", "z2_hil": "NOT_RUN",
        "auto_download": False, "auto_test": False,
    }




def direct_root_operation(task: dict, approval: dict) -> dict:
    """Path 2 direct CLI-to-existing-Root; bypass legacy Stage/Profile gates.

    Only authenticated, digest-pinned owner Work Orders reach this code.
    Hardware evidence still comes solely from the protected Root transport.
    """
    require(type(task) is dict and type(approval) is dict and
            set(task) >= {"execution_path", "capability", "objective",
                          "acceptance", "work_order_sha256",
                          "work_order_scope", "operation"} and
            set(task) <= {"execution_path", "capability", "objective",
                          "acceptance", "work_order_sha256",
                          "work_order_scope", "operation", "monitor_summary"} and
            task["execution_path"] == "path2-cli" and
            task["capability"] == "z2-root-operation" and
            task["work_order_scope"] == "guarded-hardware" and
            task["operation"] in ("download", "test", "restore") and
            type(task["work_order_sha256"]) is str and
            re.fullmatch("[0-9a-f]{64}", task["work_order_sha256"]) is not None,
            "PATH2_ROOT_OPERATION_TASK_DENIED")
    operation = task["operation"]
    require(approval.get("task_id") == "path2-work-order" and
            approval.get("execution_path") == "path2-cli" and
            approval.get("execution_capability") == "z2-root-operation" and
            approval.get("authorized_operation") == operation and
            approval.get("work_order_sha256") == task["work_order_sha256"] and
            _sha(approval.get("pinned_sha"), 40) and
            _sha(approval.get("trusted_sha"), 40) and
            type(approval.get("pr_number")) is int and
            ((approval["pr_number"] == 0 and
              approval["pinned_sha"] == approval["trusted_sha"]) or
             (approval["pr_number"] > 0 and
              approval["pinned_sha"] != approval["trusted_sha"])) and
            approval.get("auto_download_after_build_success") is False and
            approval.get("auto_test_after_download_success") is False,
            "PATH2_ROOT_OPERATION_APPROVAL_DENIED")
    try:
        receipt = transport.execute_operation(operation, approval["pinned_sha"])
    except transport.Blocked as exc:
        raise RuntimeDenied(transport.failure_code(exc)) from None
    except (OSError, ValueError, subprocess.SubprocessError):
        raise RuntimeDenied("UNKNOWN") from None
    require(type(receipt) is dict and
            receipt.get("stage") == operation and
            receipt.get("source_sha") == approval["pinned_sha"] and
            receipt.get("project") == "pl/projects/z2-fixed-unified-site1" and
            receipt.get("real_z2") is True and
            type(receipt.get("boot_id")) is str and
            len(receipt["boot_id"]) >= 8 and
            receipt.get("result") in {
                "download": {"LOADED_AND_HELD"},
                "test": {"IDENTITY_PASS", "DPIDR_PASS"},
                "restore": {"RESTORED_VERIFIED", "ALREADY_RESTORED"},
            }[operation],
            "PATH2_ROOT_OPERATION_RECEIPT_DENIED")
    return {
        "status": "REAL_Z2_ROOT_OPERATION_EVIDENCE_REVIEW_REQUIRED",
        "operation": operation, "source_sha": approval["pinned_sha"],
        "boot_id": receipt["boot_id"], "result": receipt["result"],
        "real_z2": True, "auto_next_operation": False,
    }
