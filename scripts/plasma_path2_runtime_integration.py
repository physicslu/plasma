#!/usr/bin/env python3
"""Trusted Path 2 Stage Gate 1 wiring: existing Build only, no live device provider.

No generic callbacks supplied by an Issue payload. Host-only Build may run only
via the existing reviewed vivado-host-build capability and pinned SHA.
Download and Testing remain independently addressable but NOT RUN.
"""
from __future__ import annotations

from pathlib import Path
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


def disabled_hardware_stage(task: dict, approval: dict) -> dict:
    """Registered task identity is NOT a registered privileged provider."""
    require(type(approval) is dict
            and approval.get("execution_path") == "path2-cli"
            and approval.get("execution_capability") == "path2-stage-contract"
            and coordinator._sha(approval.get("pinned_sha"), 40)
            and coordinator._sha(approval.get("trusted_sha"), 40)
            and type(approval.get("pr_number")) is int
            and ((approval["pr_number"] == 0 and approval["pinned_sha"] ==
                  approval["trusted_sha"]) or
                 (approval["pr_number"] > 0 and approval["pinned_sha"] !=
                  approval["trusted_sha"])), "PATH2_STAGE_APPROVAL_DENIED")
    names = {"z2-path2-download": "download", "z2-path2-testing": "test"}
    stage = names.get(approval.get("task_id"))
    require(stage is not None and type(task) is dict
            and task.get("stage") == stage
            and task.get("project") == "pl/projects/z2-fixed-unified-site1",
            "PATH2_STAGE_TASK_DENIED")
    require(approval.get("auto_download_after_build_success", False) is False,
            "PATH2_STAGE_AUTO_DOWNLOAD_DENIED")
    require(type(approval.get("auto_test_after_download_success", False)) is bool,
            "PATH2_STAGE_AUTO_TEST_TYPE_DENIED")
    # Zero side effects and no fake callback. Preserve absence of fresh
    # target facts, current-boot AXI admission and real lease providers.
    raise RuntimeDenied("PATH2_LIVE_PROVIDER_NOT_REGISTERED")
