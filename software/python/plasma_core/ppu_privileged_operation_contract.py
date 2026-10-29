"""Host-only PPU privilege *planning* contract, not an authorization bridge.

This code does not authenticate callers, execute subprocesses, install assets,
grant sudo, access devices or write protected files. Every admission input is
a **test-supplied fact**, not a verified credential. A production service must
derive role, live Master generation and device facts independently and retain
the existing OS privilege, Installer/Bootstrap, Job and Root Guard boundaries.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from .errors import ErrorCode, PlasmaError
from .ppu_privilege_policy import PPUAction, PPURole, require_role_capability

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SEGMENT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*\Z")


class PrivilegedRoute(StrEnum):
    EXISTING_PPU_RELEASE = "existing_ppu_bootstrap_deployment"
    EXISTING_WORDPORT_JOB = "existing_z2_ps_wordport_job"
    EXISTING_FPGA_ROOT = "existing_protected_fpga_root"
    EXISTING_JOB_MANAGER = "existing_ppu_job_manager"
    EXISTING_GATEWAY = "existing_authenticated_gateway"
    ENGINEER_MAINTENANCE = "separate_engineer_root_maintenance"


class RecoveryState(StrEnum):
    KNOWN_SAFE = "known_safe"
    UNKNOWN = "unknown"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass(frozen=True)
class PrivilegedRequest:
    action: PPUAction
    site_id: int | None = None
    staged_relative_path: str | None = None
    expected_sha256: str | None = None


@dataclass(frozen=True)
class AdmissionFacts:
    """Fake/trusted-by-test facts; must NOT originate as JSON caller claims."""

    role: PPURole
    authenticated: bool = False
    registered_master: bool = False
    master_generation: int | None = None
    session_generation: int | None = None
    engineer_local_maintenance: bool = False
    site_count: int = 0
    site_idle: bool = False
    all_sites_quiescent: bool = False
    recovery: RecoveryState = RecoveryState.UNKNOWN
    protected_source_verified: bool = False
    target_or_image_qualified: bool = False


@dataclass(frozen=True)
class StagedArtifactInspection:
    sha256: str
    size: int
    # Descriptive receipt only; not an immutable capability or atomic install.
    inode: int


@dataclass(frozen=True)
class PrivilegedPlan:
    action: PPUAction
    route: PrivilegedRoute
    site_id: int | None
    staged_artifact: StagedArtifactInspection | None
    # No command, executable, script path, root credential or OS operation.


_RELEASE_ACTIONS = frozenset({
    PPUAction.PROGRAMMING_ASSET_DEPLOY,
    PPUAction.PROGRAMMING_ENGINE_DEPLOY,
    PPUAction.PROGRAMMING_SCRIPT_DEPLOY,
    PPUAction.PROGRAMMING_PROFILE_DEPLOY,
    PPUAction.PROGRAMMING_DOCUMENT_DEPLOY,
})
_FPGA_ACTIONS = frozenset({PPUAction.FPGA_IMAGE_DEPLOY, PPUAction.FPGA_IMAGE_RELOAD})
_SITE_ACTIONS = frozenset({
    PPUAction.TARGET_ERASE, PPUAction.TARGET_PROGRAM,
    PPUAction.TARGET_VERIFY, PPUAction.TARGET_READ,
})
_ENGINEER_ACTIONS = frozenset({
    PPUAction.PROTECTED_ROOT_REPLACE, PPUAction.LINUX_SYSTEM_MAINTAIN,
    PPUAction.LINUX_ACCOUNT_MANAGE, PPUAction.ROOT_SHELL_OPEN,
})
_JOB_ACTIONS = frozenset({PPUAction.JOB_START, PPUAction.JOB_CANCEL})
_GATEWAY_ACTIONS = frozenset({
    PPUAction.PROGRAMMING_SETTINGS_WRITE, PPUAction.PROGRAMMING_READBACK_EXPORT,
})


def _reject(message: str, code: ErrorCode = ErrorCode.AUTHORIZATION_DENIED) -> None:
    raise PlasmaError(code, message)


def _relative_parts(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or len(value) > 240:
        _reject("staged artifact requires a bounded relative path", ErrorCode.INVALID_ARGUMENT)
    path = PurePosixPath(value)
    parts = tuple(value.split("/"))
    if (
        path.is_absolute()
        or "\\" in value
        or any(part in ("", ".", "..") or not _SEGMENT.fullmatch(part) for part in parts)
    ):
        _reject("unsafe staged artifact path", ErrorCode.INVALID_ARGUMENT)
    return parts


def inspect_staged_artifact(
    trusted_staging_root: Path,
    relative_path: str,
    expected_sha256: str,
) -> StagedArtifactInspection:
    """Verify a test artifact using O_NOFOLLOW for *every* path component.

    The returned receipt does not pin future file content after fd closure.
    Existing Release Installer/Bootstrap must independently authenticate,
    verify and atomically install its archive at the actual execution boundary.
    No caller-provided staging root may be accepted by a production bridge.
    """
    parts = _relative_parts(relative_path)
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        _reject("invalid expected artifact SHA256", ErrorCode.INVALID_ARGUMENT)
    if not isinstance(trusted_staging_root, Path):
        _reject("trusted staging root is not a Path", ErrorCode.INVALID_ARGUMENT)

    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    root_fd = -1
    opened: list[int] = []
    try:
        root_fd = os.open(trusted_staging_root, flags | os.O_DIRECTORY)
        directory_fd = root_fd
        for component in parts[:-1]:
            directory_fd = os.open(component, flags | os.O_DIRECTORY, dir_fd=directory_fd)
            opened.append(directory_fd)
        file_fd = os.open(parts[-1], flags | os.O_NONBLOCK, dir_fd=directory_fd)
        opened.append(file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_mode & 0o022:
            _reject("staged artifact must be a regular non-group-writable file")
        digest = hashlib.sha256()
        total = 0
        while block := os.read(file_fd, 1024 * 1024):
            total += len(block)
            digest.update(block)
        after = os.fstat(file_fd)
        if (
            total != before.st_size
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            _reject("staged artifact changed during verification")
        if digest.hexdigest() != expected_sha256:
            _reject("staged artifact digest mismatch")
        return StagedArtifactInspection(expected_sha256, total, before.st_ino)
    except (OSError, ValueError) as exc:
        _reject(f"unsafe or unavailable staged artifact: {type(exc).__name__}")
    finally:
        for fd in reversed(opened):
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)


def plan_privileged_operation(
    request: PrivilegedRequest,
    facts: AdmissionFacts,
    *,
    trusted_staging_root: Path | None = None,
) -> PrivilegedPlan:
    """Return only a route recommendation. **Never** dispatch this plan as root.

    Production must authenticate independently; verify ownership on dispatch
    (including revocation), use scoped hardware admission, and hand artifacts
    to an existing verified installer/Root guard without caller-supplied argv.
    """
    if not isinstance(request, PrivilegedRequest) or not isinstance(facts, AdmissionFacts):
        _reject("unknown PPU privilege request/facts")
    action = request.action
    if not isinstance(action, PPUAction) or not isinstance(facts.role, PPURole):
        _reject("unknown PPU action or role")
    if facts.authenticated is not True:
        _reject("PPU requester authentication required", ErrorCode.AUTHENTICATION_REQUIRED)
    require_role_capability(facts.role, action)
    if facts.role is PPURole.MASTER:
        if not (
            facts.registered_master is True
            and type(facts.master_generation) is int
            and facts.master_generation >= 1
            and type(facts.session_generation) is int
            and facts.session_generation == facts.master_generation
        ):
            _reject("Master ownership absent or generation revoked")
    if facts.role is PPURole.ENGINEER and facts.engineer_local_maintenance is not True:
        _reject("Engineer maintenance must be independently authorized")

    if action in _ENGINEER_ACTIONS:
        # Engineer still needs real Linux UID 0 and a separate local maintenance route.
        route = PrivilegedRoute.ENGINEER_MAINTENANCE
    elif action in _RELEASE_ACTIONS:
        route = PrivilegedRoute.EXISTING_PPU_RELEASE
    elif action in _FPGA_ACTIONS:
        route = PrivilegedRoute.EXISTING_FPGA_ROOT
    elif action in _SITE_ACTIONS:
        route = PrivilegedRoute.EXISTING_WORDPORT_JOB
    elif action in _JOB_ACTIONS:
        route = PrivilegedRoute.EXISTING_JOB_MANAGER
    elif action in _GATEWAY_ACTIONS:
        route = PrivilegedRoute.EXISTING_GATEWAY
    else:
        _reject("action cannot be dispatched by a privileged operation planner")

    if action in _SITE_ACTIONS:
        if (
            type(request.site_id) is not int
            or type(facts.site_count) is not int
            or not 1 <= request.site_id <= facts.site_count
        ):
            _reject("invalid/unqualified Site", ErrorCode.SITE_INVALID)
        if facts.site_idle is not True:
            _reject("Site is busy", ErrorCode.SITE_BUSY)
    elif request.site_id is not None:
        _reject("unnecessary Site selector on non-Site action", ErrorCode.INVALID_ARGUMENT)

    if action not in _ENGINEER_ACTIONS and facts.recovery is not RecoveryState.KNOWN_SAFE:
        _reject("unknown or unsafe PPU recovery state")
    if action in (_RELEASE_ACTIONS | _FPGA_ACTIONS) and facts.all_sites_quiescent is not True:
        _reject("active Site blocks deployment/reload", ErrorCode.PPU_BUSY)
    if action in (_SITE_ACTIONS | _FPGA_ACTIONS):
        if facts.protected_source_verified is not True or facts.target_or_image_qualified is not True:
            _reject("Root source/image/target qualification not established")

    required_artifact = action in _RELEASE_ACTIONS or action is PPUAction.FPGA_IMAGE_DEPLOY
    inspection = None
    if required_artifact:
        if trusted_staging_root is None:
            _reject("trusted staging location required")
        inspection = inspect_staged_artifact(
            trusted_staging_root, request.staged_relative_path, request.expected_sha256
        )
    elif request.staged_relative_path is not None or request.expected_sha256 is not None:
        _reject("unexpected artifact or digest for operation", ErrorCode.INVALID_ARGUMENT)

    return PrivilegedPlan(action=action, route=route, site_id=request.site_id, staged_artifact=inspection)
