#!/usr/bin/env python3
"""Trusted Path 2 integration: existing Build and installed root bridge stages.

The *task registry* maps Download, Testing and Restore to a fixed, root-owned
SWPC stage bridge. An uninstalled bridge fails closed, never substitutes a PR
checkout as a privileged runner or issues an SSH command from this module.
"""
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


ROOT_STAGE_BRIDGE = Path("/usr/local/libexec/plasma/z2-path2-f1b-bridge")
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
        # transition or arbitrary shell. Continue using the installed Bridge.
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
    # A single-stage bridge never consumes automation options. Exact stage
    # authorization above bounds the only physical call for both Paths.
    return stage


def _trusted_root_bridge(path: Path) -> None:
    """Fixed local bridge installed by SWPC admin, never from PR checkout."""
    require(path == ROOT_STAGE_BRIDGE, "PATH2_BRIDGE_PATH_NOT_FIXED")
    require(path.is_file() and not path.is_symlink(),
            "PATH2_TRUSTED_BRIDGE_NOT_INSTALLED")
    metadata = path.stat()
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0 and
            metadata.st_nlink == 1 and metadata.st_mode & 0o022 == 0 and
            metadata.st_mode & 0o111 != 0,
            "PATH2_TRUSTED_BRIDGE_NOT_PROTECTED")
    # A root-owned file under an untrusted parent is not a trust root.
    for parent in (path.parent, path.parent.parent):
        require(parent.is_dir() and not parent.is_symlink()
                and parent.stat().st_uid == 0 and
                parent.stat().st_mode & 0o022 == 0,
                "PATH2_BRIDGE_PARENT_NOT_PROTECTED")


def registered_hardware_stage(task: dict, approval: dict, *,
                              executor=subprocess.run) -> dict:
    """Register fixed Task -> SWPC root bridge, not a generic shell/SSH API.

    Returns actual sanitized target evidence only after installed bridge
    executes. No implicit Build->Download or Download->Test progression.
    """
    stage = stage_contract(task, approval)
    _trusted_root_bridge(ROOT_STAGE_BRIDGE)
    command = [str(ROOT_STAGE_BRIDGE), stage, approval["pinned_sha"]]
    try:
        result = executor(command, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=120,
                          check=False, env={"PATH": "/usr/bin:/bin"})
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeDenied("PATH2_BRIDGE_EXECUTION_UNCERTAIN") from None
    require(result.returncode == 0 and len(result.stdout) <= 8192,
            "PATH2_BRIDGE_STAGE_FAILED_OR_UNKNOWN")
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeError, ValueError, AttributeError):
        raise RuntimeDenied("PATH2_BRIDGE_RECEIPT_INVALID") from None
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



def path3_shared_hardware_stages(task: dict, approval: dict, *,
                                 executor=subprocess.run) -> dict:
    """Path 3 delegates authorized physical stages to the SAME Path 2 Bridge.

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
    # Enrollment supplies a stage transport, not a callable admin installer.
    # Neither the owner request nor candidate checkout may rewrite the root
    # PIN. Keep this denial until an existing authenticated admin entrypoint
    # (including independently verified source/digests and atomic install)
    # can actually be bound here. Never fall back to stage Bridge or sudo.
    deployment = task.get("swpc_bridge_deployment", False)
    require(type(deployment) is bool,
            "PATH3_SHARED_BRIDGE_DEPLOYMENT_REQUEST_INVALID")
    require(not deployment,
            "PATH3_SHARED_BRIDGE_DEPLOYMENT_NOT_INSTALLED: "
            "SWPC_ADMIN_DEPLOYMENT_ENTRYPOINT_NOT_REGISTERED")
    stages = task.get("hardware_stages")
    require(type(stages) is list and 1 <= len(stages) <= 3 and
            all(type(stage) is str and
                stage in ("download", "test", "restore") for stage in stages)
            and len(stages) == len(set(stages)),
            "PATH3_SHARED_STAGE_LIST_DENIED")
    # The common stage_contract enforces auto-transition scope before the
    # first trusted Bridge invocation for both Paths.
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
        receipt = registered_hardware_stage(stage_task, stage_approval,
                                            executor=executor)
        require(boot_id is None or receipt["boot_id"] == boot_id,
                "PATH3_SHARED_BOOT_CHANGED")
        boot_id = receipt["boot_id"]
        observed.append({"stage": stage, "result": receipt["result"]})
    return {"status": "REAL_Z2_PATH3_SHARED_BRIDGE_EVIDENCE_REVIEW_REQUIRED",
            "execution_path": "path3-codex",
            "delegate": "existing-path2-trusted-bridge",
            "source_sha": approval["pinned_sha"],
            "real_z2": True, "boot_id": boot_id,
            "completed": observed, "auto_next_stage": False}


def full_hil_sequence(task: dict, approval: dict, *,
                      executor=subprocess.run) -> dict:
    """Explicit opt-in: one SWPC trigger performs three real *separate* stages.

    Reuses the same fixed installed Bridge used by individual tasks. A
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
    # Each shared stage_contract enforces transition scope before Bridge.
    # These are three normal calls to the installed provider, but the owner
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
            stage_task, stage_approval, executor=executor)
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
    """Compatibility negative test: never bypass installation via this API."""
    stage_contract(task, approval)
    raise RuntimeDenied("PATH2_TRUSTED_BRIDGE_NOT_INSTALLED")
