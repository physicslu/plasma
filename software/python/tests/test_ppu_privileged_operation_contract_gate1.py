"""Host-only PPU Master non-root operation planning tests — no device/root calls."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ppu_privilege_policy import PPUAction, PPURole
from plasma_core.ppu_privileged_operation_contract import (
    AdmissionFacts,
    PrivilegedRequest,
    PrivilegedRoute,
    RecoveryState,
    inspect_staged_artifact,
    plan_privileged_operation,
)


def good_master(**overrides: object) -> AdmissionFacts:
    defaults = {
        "role": PPURole.MASTER,
        "authenticated": True,
        "registered_master": True,
        "master_generation": 12,
        "session_generation": 12,
        "site_count": 8,
        "site_idle": True,
        "all_sites_quiescent": True,
        "recovery": RecoveryState.KNOWN_SAFE,
        "protected_source_verified": True,
        "target_or_image_qualified": True,
    }
    defaults.update(overrides)
    return AdmissionFacts(**defaults)


def good_engineer(**overrides: object) -> AdmissionFacts:
    defaults = {"role": PPURole.ENGINEER, "authenticated": True, "engineer_local_maintenance": True}
    defaults.update(overrides)
    return AdmissionFacts(**defaults)


def assert_denied(request: PrivilegedRequest, facts: AdmissionFacts, code: ErrorCode) -> None:
    with pytest.raises(PlasmaError) as exc:
        plan_privileged_operation(request, facts)
    assert exc.value.code == code


@pytest.mark.parametrize("action", [
    PPUAction.TARGET_ERASE,
    PPUAction.TARGET_PROGRAM,
    PPUAction.TARGET_VERIFY,
    PPUAction.TARGET_READ,
])
def test_master_site_programming_is_a_non_root_job_route(action: PPUAction) -> None:
    plan = plan_privileged_operation(PrivilegedRequest(action, site_id=3), good_master())
    assert plan.route is PrivilegedRoute.EXISTING_WORDPORT_JOB
    assert plan.site_id == 3
    assert plan.staged_artifact is None


@pytest.mark.parametrize("action", [PPUAction.JOB_START, PPUAction.JOB_CANCEL])
def test_existing_job_manager_reused(action: PPUAction) -> None:
    assert plan_privileged_operation(PrivilegedRequest(action), good_master()).route is PrivilegedRoute.EXISTING_JOB_MANAGER


@pytest.mark.parametrize("action", [
    PPUAction.PROGRAMMING_SETTINGS_WRITE,
    PPUAction.PROGRAMMING_READBACK_EXPORT,
])
def test_existing_gateway_reused(action: PPUAction) -> None:
    assert plan_privileged_operation(PrivilegedRequest(action), good_master()).route is PrivilegedRoute.EXISTING_GATEWAY


def staged(root: Path, *, relative: str = "assets/ppu-release.tar.gz", data: bytes = b"release") -> tuple[str, str]:
    path = root / relative
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o600)
    return relative, hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("action", [
    PPUAction.PROGRAMMING_ASSET_DEPLOY,
    PPUAction.PROGRAMMING_ENGINE_DEPLOY,
    PPUAction.PROGRAMMING_SCRIPT_DEPLOY,
    PPUAction.PROGRAMMING_PROFILE_DEPLOY,
    PPUAction.PROGRAMMING_DOCUMENT_DEPLOY,
])
def test_master_programming_asset_deployment_routes_existing_installer_not_root_script(
    tmp_path: Path, action: PPUAction
) -> None:
    path, digest = staged(tmp_path)
    request = PrivilegedRequest(action, staged_relative_path=path, expected_sha256=digest)
    plan = plan_privileged_operation(request, good_master(), trusted_staging_root=tmp_path)
    assert plan.route is PrivilegedRoute.EXISTING_PPU_RELEASE
    assert plan.staged_artifact.sha256 == digest
    assert plan.staged_artifact.size == len(b"release")
    assert not hasattr(plan, "command")
    assert not hasattr(plan, "argv")
    assert not hasattr(plan, "sudo")


def test_master_fpga_image_install_is_unavailable_until_unified_deployer_exists(
    tmp_path: Path,
) -> None:
    path, digest = staged(tmp_path, relative="images/fpga.bin", data=b"new FPGA image")
    with pytest.raises(PlasmaError, match="FPGA Image installation is not implemented") as exc:
        plan_privileged_operation(
            PrivilegedRequest(PPUAction.FPGA_IMAGE_DEPLOY, staged_relative_path=path, expected_sha256=digest),
            good_master(),
            trusted_staging_root=tmp_path,
        )
    assert exc.value.code is ErrorCode.OPERATION_UNSUPPORTED


def test_master_fpga_reload_requires_no_caller_selected_command() -> None:
    plan = plan_privileged_operation(
        PrivilegedRequest(PPUAction.FPGA_IMAGE_RELOAD),
        good_master(),
    )
    assert plan.route is PrivilegedRoute.EXISTING_FPGA_ROOT
    assert plan.staged_artifact is None


@pytest.mark.parametrize("action", [
    PPUAction.PROTECTED_ROOT_REPLACE,
    PPUAction.LINUX_SYSTEM_MAINTAIN,
    PPUAction.LINUX_ACCOUNT_MANAGE,
    PPUAction.ROOT_SHELL_OPEN,
])
def test_master_never_gets_engineer_or_root(action: PPUAction) -> None:
    assert_denied(PrivilegedRequest(action), good_master(), ErrorCode.AUTHORIZATION_DENIED)
    plan = plan_privileged_operation(PrivilegedRequest(action), good_engineer())
    assert plan.route is PrivilegedRoute.ENGINEER_MAINTENANCE
    assert not hasattr(plan, "command")


@pytest.mark.parametrize("action", [
    PPUAction.TARGET_PROGRAM,
    PPUAction.PROGRAMMING_SCRIPT_DEPLOY,
    PPUAction.FPGA_IMAGE_RELOAD,
    PPUAction.ROOT_SHELL_OPEN,
])
def test_monitor_denied_even_when_valid_master_fields_are_forged(action: PPUAction) -> None:
    assert_denied(
        PrivilegedRequest(action, site_id=1 if action is PPUAction.TARGET_PROGRAM else None),
        good_master(role=PPURole.MONITOR),
        ErrorCode.AUTHORIZATION_DENIED,
    )


@pytest.mark.parametrize("role", ["master", "engineer", "root", None])
def test_caller_supplied_role_strings_are_not_trusted(role: object) -> None:
    assert_denied(
        PrivilegedRequest(PPUAction.TARGET_PROGRAM, site_id=1),
        good_master(role=role),
        ErrorCode.AUTHORIZATION_DENIED,
    )


@pytest.mark.parametrize("action", ["target.program", "sudo", None])
def test_unknown_action_denied(action: object) -> None:
    assert_denied(PrivilegedRequest(action, site_id=1), good_master(), ErrorCode.AUTHORIZATION_DENIED)


def test_unauthenticated_request_denied() -> None:
    assert_denied(
        PrivilegedRequest(PPUAction.JOB_START),
        good_master(authenticated=False),
        ErrorCode.AUTHENTICATION_REQUIRED,
    )


@pytest.mark.parametrize("override", [
    {"registered_master": False},
    {"master_generation": 12, "session_generation": 11},
    {"master_generation": 12, "session_generation": None},
    {"master_generation": 0, "session_generation": 0},
    {"master_generation": True, "session_generation": True},
])
def test_stale_master_or_revoked_generation_denied(override: dict) -> None:
    assert_denied(
        PrivilegedRequest(PPUAction.JOB_START),
        good_master(**override),
        ErrorCode.AUTHORIZATION_DENIED,
    )


def test_engineer_role_label_cannot_enable_local_root_mode() -> None:
    assert_denied(
        PrivilegedRequest(PPUAction.LINUX_SYSTEM_MAINTAIN),
        good_engineer(engineer_local_maintenance=False),
        ErrorCode.AUTHORIZATION_DENIED,
    )


@pytest.mark.parametrize("site", [-1, 0, 9, True, 1.0, "1", None])
def test_invalid_or_unqualified_site_rejected(site: object) -> None:
    assert_denied(
        PrivilegedRequest(PPUAction.TARGET_PROGRAM, site_id=site),
        good_master(),
        ErrorCode.SITE_INVALID,
    )


def test_busy_site_denied_without_global_single_site_serialization() -> None:
    assert_denied(
        PrivilegedRequest(PPUAction.TARGET_PROGRAM, site_id=3),
        good_master(site_idle=False),
        ErrorCode.SITE_BUSY,
    )
    assert plan_privileged_operation(
        PrivilegedRequest(PPUAction.TARGET_PROGRAM, site_id=4),
        good_master(site_idle=True, all_sites_quiescent=False),
    ).route is PrivilegedRoute.EXISTING_WORDPORT_JOB


@pytest.mark.parametrize("state", [RecoveryState.UNKNOWN, RecoveryState.RECOVERY_REQUIRED, "known_safe"])
def test_unsafe_or_untrusted_recovery_state_denied(state: object) -> None:
    assert_denied(
        PrivilegedRequest(PPUAction.TARGET_ERASE, site_id=1),
        good_master(recovery=state),
        ErrorCode.AUTHORIZATION_DENIED,
    )


def test_fpga_reload_blocked_by_any_active_site() -> None:
    assert_denied(
        PrivilegedRequest(PPUAction.FPGA_IMAGE_RELOAD),
        good_master(all_sites_quiescent=False),
        ErrorCode.PPU_BUSY,
    )


@pytest.mark.parametrize("action", [PPUAction.TARGET_PROGRAM, PPUAction.FPGA_IMAGE_RELOAD])
@pytest.mark.parametrize("override", [
    {"protected_source_verified": False},
    {"target_or_image_qualified": False},
])
def test_wordport_and_fpga_require_existing_hardware_root_guard_evidence(
    action: PPUAction, override: dict
) -> None:
    assert_denied(
        PrivilegedRequest(action, site_id=1 if action is PPUAction.TARGET_PROGRAM else None),
        good_master(**override),
        ErrorCode.AUTHORIZATION_DENIED,
    )


@pytest.mark.parametrize("path", [
    "/etc/sudoers", "../escape.tar.gz", "a/../escape.tar.gz",
    "a/./file.tar.gz", "a//file.tar.gz", "a\\file.tar.gz",
    ".", "", "foo/with space.tar.gz", "a\nfile.tar.gz",
])
def test_path_traversal_absolute_and_unexpected_paths_rejected(tmp_path: Path, path: str) -> None:
    with pytest.raises(PlasmaError) as exc:
        inspect_staged_artifact(tmp_path, path, "0" * 64)
    assert exc.value.code in (ErrorCode.INVALID_ARGUMENT, ErrorCode.AUTHORIZATION_DENIED)


@pytest.mark.parametrize("digest", ["", "abcd", "F" * 64, "g" * 64])
def test_digest_format_fail_closed(tmp_path: Path, digest: str) -> None:
    with pytest.raises(PlasmaError):
        inspect_staged_artifact(tmp_path, "assets/release.tar.gz", digest)


def test_symlink_file_and_ancestor_denied(tmp_path: Path) -> None:
    path, digest = staged(tmp_path)
    link = tmp_path / "assets" / "shadow.tar.gz"
    link.symlink_to(tmp_path / path)
    with pytest.raises(PlasmaError, match="unsafe or unavailable"):
        inspect_staged_artifact(tmp_path, "assets/shadow.tar.gz", digest)

    shadow_dir = tmp_path / "shadow"
    shadow_dir.symlink_to(tmp_path / "assets", target_is_directory=True)
    with pytest.raises(PlasmaError, match="unsafe or unavailable"):
        inspect_staged_artifact(tmp_path, "shadow/ppu-release.tar.gz", digest)

    root_link = tmp_path / "root-link"
    root_link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PlasmaError, match="unsafe or unavailable"):
        inspect_staged_artifact(root_link, path, digest)


def test_changed_script_denied_instead_of_running_as_root(tmp_path: Path) -> None:
    path, digest = staged(tmp_path, relative="scripts/wordport.py", data=b"trusted script")
    assert inspect_staged_artifact(tmp_path, path, digest).sha256 == digest
    (tmp_path / path).write_bytes(b"new unapproved script")
    with pytest.raises(PlasmaError, match="digest mismatch"):
        inspect_staged_artifact(tmp_path, path, digest)


def test_group_writable_artifact_and_fifo_denied(tmp_path: Path) -> None:
    path, digest = staged(tmp_path)
    (tmp_path / path).chmod(0o660)
    with pytest.raises(PlasmaError, match="regular non-group-writable"):
        inspect_staged_artifact(tmp_path, path, digest)
    fifo = tmp_path / "assets" / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(PlasmaError, match="regular non-group-writable"):
        inspect_staged_artifact(tmp_path, "assets/pipe", digest)


def test_untrusted_or_missing_artifact_and_unexpected_artifact_denied(tmp_path: Path) -> None:
    for request in (
        PrivilegedRequest(PPUAction.PROGRAMMING_SCRIPT_DEPLOY),
        PrivilegedRequest(PPUAction.PROGRAMMING_SCRIPT_DEPLOY, staged_relative_path="assets/a.py", expected_sha256="0"*64),
    ):
        with pytest.raises(PlasmaError):
            plan_privileged_operation(request, good_master(), trusted_staging_root=tmp_path)
    assert_denied(
        PrivilegedRequest(PPUAction.TARGET_PROGRAM, site_id=1, staged_relative_path="scripts/a.py"),
        good_master(),
        ErrorCode.INVALID_ARGUMENT,
    )


def test_no_flexible_argv_command_or_root_override_in_request() -> None:
    with pytest.raises(TypeError):
        PrivilegedRequest(PPUAction.TARGET_PROGRAM, argv=["sh", "-c", "id"])  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        PrivilegedRequest(PPUAction.TARGET_PROGRAM, run_as_root=True)  # type: ignore[call-arg]


def test_existing_install_root_code_unchanged_and_requires_hashes_and_rollback() -> None:
    repository = Path(__file__).resolve().parents[3]
    deployment = (repository / "scripts/ppu-bootstrap-deployment.py").read_text()
    installer = (repository / "scripts/ppu-z2-installer-core.py").read_text()
    protected = (repository / "scripts/z2/plasma-path2-root-entry").read_text()
    wordport = (repository / "scripts/plasma_wordport_program.py").read_text()
    assert "self.installer.verify_release(" in deployment
    assert "self.installer.install_release(" in deployment
    assert "recovery_required" in deployment and "rolled_back" in deployment
    assert "sha256" in installer and "rollback" in installer
    assert "download|test|restore" in protected
    assert "PATH2_ROOT_REQUIRED" in protected
    assert 'os.geteuid() != 0' in wordport
