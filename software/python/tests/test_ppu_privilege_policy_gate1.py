"""Host-only PPU privilege contract and protected Root negative tests.

No Root escalation, device files, FPGA Manager, SWPC, Z2 or DUT I/O.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ppu_privilege_policy import (
    PPUAction,
    PPUBoundary,
    PPURole,
    ROLE_ACTIONS,
    execution_boundary,
    require_role_capability,
    role_permits,
)


@pytest.mark.parametrize("action", [
    PPUAction.STATUS_VIEW,
    PPUAction.JOB_PROGRESS_VIEW,
    PPUAction.PUBLIC_LOG_VIEW,
    PPUAction.JOB_RESULT_VIEW,
    PPUAction.CONFIG_VIEW,
])
def test_monitor_can_observe_non_sensitive_information(action: PPUAction) -> None:
    assert role_permits(PPURole.MONITOR, action)
    assert execution_boundary(action) == PPUBoundary.INFORMATION_ONLY


@pytest.mark.parametrize("action", [
    PPUAction.TARGET_ERASE, PPUAction.TARGET_PROGRAM,
    PPUAction.TARGET_VERIFY, PPUAction.TARGET_READ,
    PPUAction.JOB_START, PPUAction.JOB_CANCEL,
    PPUAction.PROGRAMMING_READBACK_EXPORT,
    PPUAction.PROGRAMMING_ASSET_DEPLOY,
    PPUAction.PROGRAMMING_ENGINE_DEPLOY,
    PPUAction.PROGRAMMING_SCRIPT_DEPLOY,
    PPUAction.PROGRAMMING_PROFILE_DEPLOY,
    PPUAction.PROGRAMMING_DOCUMENT_DEPLOY,
    PPUAction.PROGRAMMING_SETTINGS_WRITE,
    PPUAction.FPGA_IMAGE_DEPLOY, PPUAction.FPGA_IMAGE_RELOAD,
])
def test_monitor_denied_all_mutations_and_physical_target_reads(action: PPUAction) -> None:
    assert not role_permits(PPURole.MONITOR, action)
    with pytest.raises(PlasmaError) as exc:
        require_role_capability(PPURole.MONITOR, action)
    assert exc.value.code is ErrorCode.AUTHORIZATION_DENIED


@pytest.mark.parametrize("action", [
    PPUAction.TARGET_ERASE, PPUAction.TARGET_PROGRAM,
    PPUAction.TARGET_VERIFY, PPUAction.TARGET_READ,
    PPUAction.PROGRAMMING_ENGINE_DEPLOY,
    PPUAction.PROGRAMMING_SCRIPT_DEPLOY,
    PPUAction.PROGRAMMING_PROFILE_DEPLOY,
    PPUAction.PROGRAMMING_DOCUMENT_DEPLOY,
    PPUAction.FPGA_IMAGE_DEPLOY, PPUAction.FPGA_IMAGE_RELOAD,
])
def test_master_may_request_all_programming_work_but_not_root(action: PPUAction) -> None:
    assert role_permits(PPURole.MASTER, action)


@pytest.mark.parametrize("action", [
    PPUAction.PROTECTED_ROOT_REPLACE, PPUAction.LINUX_SYSTEM_MAINTAIN,
    PPUAction.LINUX_ACCOUNT_MANAGE, PPUAction.ROOT_SHELL_OPEN,
])
def test_system_repairs_require_engineer_mode_not_master(action: PPUAction) -> None:
    assert not role_permits(PPURole.MONITOR, action)
    assert not role_permits(PPURole.MASTER, action)
    assert role_permits(PPURole.ENGINEER, action)
    assert execution_boundary(action) is PPUBoundary.ENGINEER_ROOT_MAINTENANCE


@pytest.mark.parametrize("action", [
    PPUAction.FPGA_IMAGE_DEPLOY, PPUAction.FPGA_IMAGE_RELOAD,
])
def test_master_image_work_requires_reviewed_privileged_bridge(action: PPUAction) -> None:
    assert role_permits(PPURole.MASTER, action)
    assert execution_boundary(action) is PPUBoundary.REVIEWED_PRIVILEGED_BRIDGE


@pytest.mark.parametrize("role,action", [
    ("master", PPUAction.TARGET_PROGRAM),
    ("root", PPUAction.LINUX_SYSTEM_MAINTAIN),
    ("monitor", PPUAction.STATUS_VIEW),
    (PPURole.MASTER, "target.program"),
    (PPURole.MASTER, "root_shell.open"),
    (None, PPUAction.STATUS_VIEW),
    (PPURole.MASTER, None),
    (PPURole.ENGINEER, "linux.root_shell.open"),
])
def test_unknown_or_untrusted_strings_fail_closed(role: object, action: object) -> None:
    assert not role_permits(role, action)
    with pytest.raises(PlasmaError) as exc:
        require_role_capability(role, action)
    assert exc.value.code is ErrorCode.AUTHORIZATION_DENIED


def test_all_actions_exactly_classified_and_inheritance_is_monotone() -> None:
    all_actions = set(PPUAction)
    assert ROLE_ACTIONS[PPURole.MONITOR] < ROLE_ACTIONS[PPURole.MASTER]
    assert ROLE_ACTIONS[PPURole.MASTER] < ROLE_ACTIONS[PPURole.ENGINEER]
    assert ROLE_ACTIONS[PPURole.ENGINEER] == all_actions
    for action in all_actions:
        assert isinstance(execution_boundary(action), PPUBoundary)
    with pytest.raises(PlasmaError) as exc:
        execution_boundary("linux.system.maintain")  # type: ignore[arg-type]
    assert exc.value.code is ErrorCode.AUTHORIZATION_DENIED


def test_policy_is_not_identity_or_linux_privilege_issuer() -> None:
    # The role matrix deliberately does not supply a Console ID, token,
    # root credential, sudoers rule, file deployment, or direct hardware I/O.
    assert not hasattr(PPURole, "ROOT")
    assert not hasattr(PPUBoundary, "ROOT_GRANTED")
    assert role_permits(PPURole.ENGINEER, PPUAction.ROOT_SHELL_OPEN)
    assert execution_boundary(PPUAction.ROOT_SHELL_OPEN) is PPUBoundary.ENGINEER_ROOT_MAINTENANCE


def test_protected_root_rejects_unknown_operation_before_any_hardware() -> None:
    from pl.hil.fpga_image_root import ImageDeploymentDenied, run

    with pytest.raises(ImageDeploymentDenied, match="OPERATION_NOT_ALLOWLISTED"):
        run("arbitrary-command")


def test_root_guard_rejects_non_root_before_device_access(monkeypatch: pytest.MonkeyPatch) -> None:
    from pl.hil import fpga_image_guard as guard
    from pl.hil import fpga_image_root as root

    monkeypatch.setattr(root.os, "geteuid", lambda: 1000)
    with pytest.raises(root.ImageDeploymentDenied, match="ROOT_REQUIRED"):
        root.trusted_local()

    with pytest.raises(guard.TargetSafetyDenied, match="Z2_ROOT_REQUIRED"):
        with guard.RootZ2TargetPort(release=object()).exclusive():
            pytest.fail("Non-root must not enter protected image owner lock")


def test_existing_root_entry_remains_narrow_source_pinned() -> None:
    # Static regression on unchanged protected script; this test does not run it.
    repo_root = Path(__file__).resolve().parents[3]
    root_entry = (repo_root / "scripts/z2/plasma-path2-root-entry").read_text()
    assert 'download|test|restore' in root_entry
    assert "PATH2_ROOT_REQUIRED" in root_entry
    assert "PATH2_REQUEST_NOT_PINNED" in root_entry
    assert "sha256sum --check --status" in root_entry


def test_runtime_program_session_does_not_use_global_proc_census() -> None:
    # Verify the existing separation; do not change Root executable bytes.
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "pl/hil/fpga_image_guard.py").read_text()
    root_source = (repo_root / "pl/hil/fpga_image_root.py").read_text()
    assert "if runtime_program_session:" in source
    assert '"NOT_RUN_PROGRAM_SESSION"' in source
    assert "scan_proc_consumers(" in source  # still kept for maintenance.
    assert "def live_program_session_report(" in root_source
    assert "runtime_program_session=True" in root_source
