"""PPU product capability contract — Host-only, not runtime authorization.

This module intentionally has no device I/O, credentials, sudo or role lookup.
The trusted PPU ingress must *authenticate* a Console, check active Master
generation and run real hardware/OS safety admission before dispatching work.
Never use this enum/table as proof of a Linux UID, maintenance activation,
FPGA readiness, or an existing deployed security boundary.
"""
from __future__ import annotations

from enum import StrEnum

from .errors import ErrorCode, PlasmaError


class PPURole(StrEnum):
    MONITOR = "monitor"
    MASTER = "master"
    ENGINEER = "engineer"


class PPUAction(StrEnum):
    STATUS_VIEW = "status.view"
    JOB_PROGRESS_VIEW = "job.progress.view"
    PUBLIC_LOG_VIEW = "log.public.view"
    JOB_RESULT_VIEW = "job.result.view"
    CONFIG_VIEW = "config.view"

    JOB_START = "job.start"
    JOB_CANCEL = "job.cancel"
    TARGET_ERASE = "target.erase"
    TARGET_PROGRAM = "target.program"
    TARGET_VERIFY = "target.verify"
    TARGET_READ = "target.read"  # Physical IC read, NOT a monitor/status read.
    PROGRAMMING_READBACK_EXPORT = "programming.readback.export"
    PROGRAMMING_ASSET_DEPLOY = "programming.asset.deploy"
    PROGRAMMING_ENGINE_DEPLOY = "programming.engine.deploy"
    PROGRAMMING_SCRIPT_DEPLOY = "programming.script.deploy"
    PROGRAMMING_PROFILE_DEPLOY = "programming.profile.deploy"
    PROGRAMMING_DOCUMENT_DEPLOY = "programming.document.deploy"
    PROGRAMMING_SETTINGS_WRITE = "programming.settings.write"
    FPGA_IMAGE_DEPLOY = "fpga.image.deploy"
    FPGA_IMAGE_RELOAD = "fpga.image.reload"

    PROTECTED_ROOT_REPLACE = "protected_root.replace"
    LINUX_SYSTEM_MAINTAIN = "linux.system.maintain"
    LINUX_ACCOUNT_MANAGE = "linux.account.manage"
    ROOT_SHELL_OPEN = "linux.root_shell.open"


class PPUBoundary(StrEnum):
    """What runtime authority the action needs in addition to product role."""

    INFORMATION_ONLY = "information_only"
    PROGRAMMING_SERVICE = "programming_service"
    REVIEWED_PRIVILEGED_BRIDGE = "reviewed_privileged_bridge"
    ENGINEER_ROOT_MAINTENANCE = "engineer_root_maintenance"


# Exact allowlist: new/unknown actions are denied until separately classified.
_MONITOR = frozenset({
    PPUAction.STATUS_VIEW, PPUAction.JOB_PROGRESS_VIEW,
    PPUAction.PUBLIC_LOG_VIEW, PPUAction.JOB_RESULT_VIEW,
    PPUAction.CONFIG_VIEW,
})
_PROGRAMMING = frozenset({
    PPUAction.JOB_START, PPUAction.JOB_CANCEL,
    PPUAction.TARGET_ERASE, PPUAction.TARGET_PROGRAM,
    PPUAction.TARGET_VERIFY, PPUAction.TARGET_READ,
    PPUAction.PROGRAMMING_READBACK_EXPORT,
    PPUAction.PROGRAMMING_ASSET_DEPLOY,
    PPUAction.PROGRAMMING_ENGINE_DEPLOY,
    PPUAction.PROGRAMMING_SCRIPT_DEPLOY,
    PPUAction.PROGRAMMING_PROFILE_DEPLOY,
    PPUAction.PROGRAMMING_DOCUMENT_DEPLOY,
    PPUAction.PROGRAMMING_SETTINGS_WRITE,
    PPUAction.FPGA_IMAGE_DEPLOY, PPUAction.FPGA_IMAGE_RELOAD,
})
_ENGINEER_ONLY = frozenset({
    PPUAction.PROTECTED_ROOT_REPLACE, PPUAction.LINUX_SYSTEM_MAINTAIN,
    PPUAction.LINUX_ACCOUNT_MANAGE, PPUAction.ROOT_SHELL_OPEN,
})
_PRIVELEGED = frozenset({PPUAction.FPGA_IMAGE_DEPLOY, PPUAction.FPGA_IMAGE_RELOAD})

ROLE_ACTIONS: dict[PPURole, frozenset[PPUAction]] = {
    PPURole.MONITOR: _MONITOR,
    PPURole.MASTER: _MONITOR | _PROGRAMMING,
    PPURole.ENGINEER: _MONITOR | _PROGRAMMING | _ENGINEER_ONLY,
}


def role_permits(role: object, action: object) -> bool:
    """Classify trusted roles only. This does not authorize a live request."""
    return (
        isinstance(role, PPURole)
        and isinstance(action, PPUAction)
        and action in ROLE_ACTIONS[role]
    )


def require_role_capability(role: object, action: object) -> None:
    """Fail closed on unknown roles/actions; does NOT grant Linux privileges."""
    if not role_permits(role, action):
        raise PlasmaError(
            ErrorCode.AUTHORIZATION_DENIED,
            "PPU product role does not permit the requested capability",
        )


def execution_boundary(action: PPUAction) -> PPUBoundary:
    """Declare additional execution boundary without claiming it is active."""
    if not isinstance(action, PPUAction):
        raise PlasmaError(ErrorCode.AUTHORIZATION_DENIED, "unknown PPU capability")
    if action in _ENGINEER_ONLY:
        return PPUBoundary.ENGINEER_ROOT_MAINTENANCE
    if action in _PRIVELEGED:
        return PPUBoundary.REVIEWED_PRIVILEGED_BRIDGE
    if action in _PROGRAMMING:
        return PPUBoundary.PROGRAMMING_SERVICE
    if action in _MONITOR:
        return PPUBoundary.INFORMATION_ONLY
    raise PlasmaError(ErrorCode.AUTHORIZATION_DENIED, "unclassified PPU capability")
