#!/usr/bin/env python3
"""Trusted Path 2/3 integration with shared trusted-main stage transport."""
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
import plasma_path2_stage_orchestrator as coordinator
import plasma_path2_f1b_adapters as f1b
import plasma_path2_build_qualification as qualifier


class RuntimeDenied(ValueError):
    """Fail closed before expensive or privileged operations."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise RuntimeDenied(code)


def host_build(task: dict, *, workspace: Path, approval: dict,
               evidence_dir: Path, executor=None,
               build_driver=None, qualify=None) -> dict:
    """One reviewed host-side Vivado build, then real file qualification.

    Host-side Build is not a global Path 2 Host-only restriction, and does
    not itself confer FPGA programming or any target-device authority.
    The optional injected hooks exist solely for offline test coverage;
    the trusted Dispatcher calls with no hooks and no device backend.
    """
    require(type(approval) is dict
            and approval.get("task_id") == "z2-path2-build"
            and approval.get("execution_capability") == "vivado-host-build"
            and approval.get("execution_path") == "path2-cli"
            and coordinator._sha(approval.get("pinned_sha"), 40)
            and coordinator._sha(approval.get("trusted_sha"), 40)
            and type(approval.get("pr_number")) is int
            and ((approval["pr_number"] == 0 and approval["pinned_sha"] ==
                  approval["trusted_sha"]) or
                 (approval["pr_number"] > 0 and approval["pinned_sha"] !=
                  approval["trusted_sha"])), "PATH2_BUILD_APPROVAL_DENIED")
    require(type(task) is dict
            and task.get("capability") == "vivado-host-build"
            and task.get("project") == "pl/projects/z2-fixed-unified-site1",
            "PATH2_BUILD_TASK_DENIED")
    # One stage's per-request option never elevates hardware privileges.
    # Reject any route requiring Download BEFORE running Vivado.
    auto_download = approval.get("auto_download_after_build_success", False)
    auto_testing = approval.get("auto_test_after_download_success", False)
    require(type(auto_download) is bool and type(auto_testing) is bool,
            "PATH2_BUILD_OPTION_TYPE_DENIED")
    require(not auto_download, "PATH2_LIVE_DOWNLOAD_PROVIDER_NOT_REGISTERED")
    require(evidence_dir is not None and evidence_dir.is_dir()
            and not evidence_dir.is_symlink(), "PATH2_EVIDENCE_DIR_DENIED")

    def perform(context: dict) -> dict:
        if build_driver is not None:
            return build_driver(context)
        kwargs = dict(task=task, workspace=workspace, approval=approval,
                      evidence_dir=evidence_dir)
        if executor is not None:
            kwargs["executor"] = executor
        return f1b.existing_host_build(**kwargs)

    def qualify_result(raw: dict) -> dict:
        if qualify is not None:
            return qualify(raw)
        return qualifier.qualify_host_build(
            raw, workspace=workspace, pinned_sha=approval["pinned_sha"])

    handlers = f1b.bind_f1b_adapters(
        build_driver=perform, build_qualification=qualify_result)
    request = {
        "stage": "build", "source_sha": approval["pinned_sha"],
        "profile_id": f1b.PROFILE_ID, "target_id": "z2-development",
        "options": {"auto_download_after_build_success": auto_download,
                    "auto_test_after_download_success": auto_testing}
    }
    result = coordinator.run(request, adapters=handlers)
    require(result["status"] == "RECEIPTS_VALIDATED"
            and result["completed"] == ["build"],
            "PATH2_BUILD_STAGE_NOT_QUALIFIED")
    return result


STAGE_TASKS = {
    "z2-path2-download": "download",
    "z2-path2-testing": "test",
    "z2-path2-restore": "restore",
}


def stage_contract(task: dict, approval: dict) -> str:
    """Owner/pin identity is already authenticated by trusted Dispatcher."""
    require(type(approval) is dict
            and approval.get("execution_path") == "path2-cli"
            and approval.get("execution_capability") == "path2-stage-contract"
            and coordinator._sha(approval.get("pinned_sha"), 40)
            and coordinator._sha(approval.get("trusted_sha"), 40)
            and type(approval.get("pr_number")) is int
            and ((approval["pr_number"] == 0 and
                  approval["pinned_sha"] == approval["trusted_sha"]) or
                 (approval["pr_number"] > 0 and
                  approval["pinned_sha"] != approval["trusted_sha"])),
            "PATH2_STAGE_APPROVAL_DENIED")
    stage = STAGE_TASKS.get(approval.get("task_id"))
    if approval.get("task_id") == "path2-work-order":
        # Only the owner-pinned, single-stage generic route; no full-HIL
        # transition or arbitrary shell. Use only the trusted-main adapter.
        stage = task.get("stage") if type(task) is dict else None
        require(stage in ("download", "test", "restore") and
                approval.get("authorized_stage") == stage and
                type(approval.get("work_order_sha256")) is str and
                approval["work_order_sha256"] == task.get("work_order_sha256"),
                "PATH2_STAGE_WORK_ORDER_DENIED")
    require(stage is not None and type(task) is dict
            and task.get("capability") == "path2-stage-contract"
            and task.get("stage") == stage
            and type(task.get("project")) is str
            and re.fullmatch(r"pl/projects/[a-z0-9][a-z0-9-]{2,69}",
                             task["project"]) is not None,
            "PATH2_STAGE_TASK_DENIED")
    # A single-stage adapter never consumes automation options. Exact stage
    # authorization above bounds the only physical call for both Paths.
    return stage


def registered_hardware_stage(task: dict, approval: dict) -> dict:
    """Register fixed Task -> trusted-main transport, not a generic shell/SSH API.

    Returns actual sanitized target evidence only after trusted transport
    executes. No implicit Build->Download or Download->Test progression.
    """
    stage = stage_contract(task, approval)
    try:
        payload = transport.execute(stage, approval["pinned_sha"],
                                    task["project"])
    except transport.Blocked as exc:
        raise RuntimeDenied(transport.failure_code(exc)) from None
    except (OSError, ValueError, subprocess.SubprocessError):
        raise RuntimeDenied("UNKNOWN") from None
    require(type(payload) is dict and
            payload.get("stage") == stage and
            payload.get("source_sha") == approval["pinned_sha"] and
            payload.get("project") == task["project"] and
            payload.get("real_z2") is True and
            type(payload.get("boot_id")) is str and
            len(payload["boot_id"]) >= 8 and
            payload.get("result") in ({
                "download": {"LOADED_AND_HELD"},
                "test": {"IDENTITY_PASS", "DPIDR_PASS"},
                "restore": {"RESTORED_VERIFIED", "ALREADY_RESTORED"},
            }[stage]),
            # Historical failure code retained for callers; the required
            # evidence now comes from the protected Z2 root Stage Transport,
            # not an installed SWPC Bridge.
            "PATH2_BRIDGE_RECEIPT_NOT_REAL_Z2")
    return {
        "status": "REAL_Z2_STAGE_EVIDENCE_REVIEW_REQUIRED",
        "stage": stage,
        "source_sha": approval["pinned_sha"],
        "project": task["project"],
        "boot_id": payload["boot_id"],
        "result": payload["result"],
        "real_z2": True,
        "auto_next_stage": False,
    }



def full_hil_sequence(task: dict, approval: dict) -> dict:
    """Explicit opt-in: one SWPC trigger performs three real *separate* stages.

    Reuses the same fixed trusted adapter used by individual tasks. A
    failed or uncertain stage stops; never blindly launch the next stage.
    Neither Build nor any stage other than F1-B Download/Test/Restore is run.
    """
    require(type(approval) is dict
            and approval.get("task_id") == "z2-path2-full-hil"
            and type(task) is dict
            and set(task) == {"execution_path", "capability", "project", "stage"}
            and task.get("execution_path") == "path2-cli"
            and task.get("capability") == "path2-stage-contract"
            and task.get("project") == "pl/projects/z2-fixed-unified-site1"
            and task.get("stage") == "full",
            "PATH2_FULL_TASK_DENIED")
    # Each shared stage_contract enforces transition scope before transport.
    # These are three normal calls to the trusted provider, but the owner
    # explicitly selected full-hil. Normal task triggers never auto-chain.
    stages = (("z2-path2-download", "download"),
              ("z2-path2-testing", "test"),
              ("z2-path2-restore", "restore"))
    results = []
    boot_id = None
    for task_id, stage in stages:
        stage_task = {"execution_path": "path2-cli",
                      "capability": "path2-stage-contract",
                      "project": "pl/projects/z2-fixed-unified-site1",
                      "stage": stage}
        stage_approval = {**approval, "task_id": task_id}
        observed = registered_hardware_stage(
            stage_task, stage_approval)
        # The shared adapter already validates stage and real root receipt.
        require(boot_id is None or boot_id == observed["boot_id"],
                "PATH2_FULL_BOOT_OR_STAGE_CHANGED")
        boot_id = observed["boot_id"]
        results.append({"stage": stage, "result": observed["result"]})
    # Each stage's result was already validated by registered_hardware_stage.
    return {"status": "REAL_Z2_FULL_HIL_EVIDENCE_REVIEW_REQUIRED",
            "real_z2": True,
            "mode": "full-hil",
            "source_sha": approval["pinned_sha"],
            "boot_id": boot_id, "completed": results,
            "auto_next_stage": True,
            "build_stage": "REUSED_PREVIOUS_PINNED_IMAGE_NOT_REBUILT"}


def disabled_hardware_stage(task: dict, approval: dict) -> dict:
    """Disabled compatibility API; cannot replace trusted Stage Transport.

    Retain the historical Bridge-named failure code for negative-test callers.
    """
    stage_contract(task, approval)
    raise RuntimeDenied("PATH2_TRUSTED_BRIDGE_NOT_INSTALLED")


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
            coordinator._sha(approval.get("pinned_sha"), 40) and
            coordinator._sha(approval.get("trusted_sha"), 40) and
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
