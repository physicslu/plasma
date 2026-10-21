#!/usr/bin/env python3
"""Trusted Path 2/3 integration with shared trusted-main stage transport."""
from __future__ import annotations

from pathlib import Path
import os
import json
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
    """One reviewed Host-only Vivado invocation, then real file qualification.

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
            and task.get("project") == "pl/projects/z2-fixed-unified-site1",
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
        payload = transport.execute(stage, approval["pinned_sha"])
    except transport.Blocked as exc:
        raise RuntimeDenied(transport.failure_code(exc)) from None
    except (OSError, ValueError, subprocess.SubprocessError):
        raise RuntimeDenied("UNKNOWN") from None
    require(type(payload) is dict and
            payload.get("stage") == stage and
            payload.get("source_sha") == approval["pinned_sha"] and
            payload.get("real_z2") is True and
            type(payload.get("boot_id")) is str and
            len(payload["boot_id"]) >= 8 and
            payload.get("result") in ({
                "download": {"LOADED_AND_HELD"},
                "test": {"IDENTITY_PASS"},
                "restore": {"RESTORED_VERIFIED", "ALREADY_RESTORED"},
            }[stage]),
            "PATH2_BRIDGE_RECEIPT_NOT_REAL_Z2")
    return {
        "status": "REAL_Z2_STAGE_EVIDENCE_REVIEW_REQUIRED",
        "stage": stage,
        "source_sha": approval["pinned_sha"],
        "boot_id": payload["boot_id"],
        "result": payload["result"],
        "real_z2": True,
        "auto_next_stage": False,
    }



def path3_shared_hardware_stages(task: dict, approval: dict) -> dict:
    """Path 3 delegates authorized physical stages to the SAME Path 2 adapter.

    Executed by the existing trusted SWPC development-execute job, never
    inside Codex. No new hardware driver, runner, privilege or service.
    """
    require(type(task) is dict and type(approval) is dict and
            approval.get("task_id") == "path3-work-order" and
            approval.get("execution_path") == "path3-codex" and
            approval.get("execution_capability") == "codex-guarded-hardware" and
            task.get("execution_path") == "path3-codex" and
            task.get("capability") == "codex-workspace" and
            task.get("work_order_scope") == "guarded-hardware" and
            approval.get("work_order_sha256") == task.get("work_order_sha256") and
            type(task.get("work_order_sha256")) is str and
            len(task["work_order_sha256"]) == 64 and
            coordinator._sha(approval.get("pinned_sha"), 40) and
            coordinator._sha(approval.get("trusted_sha"), 40),
            "PATH3_SHARED_BRIDGE_APPROVAL_DENIED")
    require("swpc_bridge_deployment" not in task,
            "PATH2_OBSOLETE_DEPLOYMENT_FLAG")
    stages = task.get("hardware_stages")
    require(type(stages) is list and 1 <= len(stages) <= 3 and
            all(type(stage) is str and
                stage in ("download", "test", "restore") for stage in stages)
            and len(stages) == len(set(stages)),
            "PATH3_SHARED_STAGE_LIST_DENIED")
    # The common stage_contract enforces auto-transition scope before the
    # first trusted adapter invocation for both Paths.
    observed = []
    boot_id = None
    for stage in stages:
        stage_task = {"execution_path": "path2-cli",
                      "capability": "path2-stage-contract",
                      "project": "pl/projects/z2-fixed-unified-site1",
                      "stage": stage,
                      "work_order_sha256": task["work_order_sha256"]}
        stage_approval = {**approval,
                          "task_id": "path2-work-order",
                          "execution_path": "path2-cli",
                          "execution_capability": "path2-stage-contract",
                          "authorized_stage": stage}
        receipt = registered_hardware_stage(stage_task, stage_approval)
        require(boot_id is None or receipt["boot_id"] == boot_id,
                "PATH3_SHARED_BOOT_CHANGED")
        boot_id = receipt["boot_id"]
        observed.append({"stage": stage, "result": receipt["result"]})
    return {"status": "REAL_Z2_PATH3_SHARED_BRIDGE_EVIDENCE_REVIEW_REQUIRED",
            "execution_path": "path3-codex",
            "delegate": "shared-trusted-main-stage-transport",
            "source_sha": approval["pinned_sha"],
            "real_z2": True, "boot_id": boot_id,
            "completed": observed, "auto_next_stage": False}


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
    """Compatibility negative test: never bypass authorization via this API."""
    stage_contract(task, approval)
    raise RuntimeDenied("PATH2_TRUSTED_BRIDGE_NOT_INSTALLED")
