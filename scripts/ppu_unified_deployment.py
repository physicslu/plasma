"""Host-only single PPU deployment entry planning; never performs installation.

Both Console and SWPC must target the EXISTING Bootstrap deployment endpoint
and deployment lock/journal. The installed Bootstrap currently only supports
PS runtime: engineering modules and FPGA Image installation are intentionally
NOT_QUALIFIED, not dynamically dispatched or privileged here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

DEPLOYMENT_API = "/v1/deployments"
DEPLOYMENT_LOCK = "/var/lib/plasma-bootstrap/deployment.lock"
DEPLOYMENT_JOURNAL = "/var/lib/plasma-bootstrap/deployment.json"
ENGINEERING_MODULES = ("wordport", "openocd-integration", "abtest")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")


class UnifiedDeploymentError(ValueError):
    pass


class DeploymentKind(StrEnum):
    PPU_RUNTIME = "ppu-runtime"
    ENGINEERING_MODULE = "engineering-module"
    FPGA_IMAGE = "fpga-image"


class IntegrationState(StrEnum):
    EXISTING_RUNTIME = "existing-runtime"
    BLOCKED_NOT_QUALIFIED = "blocked-not-qualified"


@dataclass(frozen=True)
class UnifiedDeploymentIntent:
    kind: DeploymentKind
    module: str | None
    source_commit: str
    artifact_sha256: str
    state: IntegrationState
    api_path: str = DEPLOYMENT_API
    shared_lock: str = DEPLOYMENT_LOCK
    shared_journal: str = DEPLOYMENT_JOURNAL

    def to_descriptor(self) -> dict[str, str | None]:
        return {
            "kind": self.kind.value,
            "module": self.module,
            "source_commit": self.source_commit,
            "artifact_sha256": self.artifact_sha256,
            "integration_state": self.state.value,
            "api_path": self.api_path,
            "shared_lock": self.shared_lock,
            "shared_journal": self.shared_journal,
            "no_deployment": True,
        }


def plan_unified_deployment(
    kind: DeploymentKind,
    *,
    source_commit: str,
    artifact_sha256: str,
    module: str | None = None,
) -> UnifiedDeploymentIntent:
    """Construct a typed plan. Not an authorization token or deploy request.

    Actual authentication must be device-derived, bound to the active Master
    generation and checked at dispatch. A verified checksum is not a publisher
    signature; Master-controlled Python must never execute as Root.
    """
    if not isinstance(kind, DeploymentKind):
        raise UnifiedDeploymentError("UNKNOWN_DEPLOYMENT_KIND")
    if not isinstance(source_commit, str) or not SHA40.fullmatch(source_commit):
        raise UnifiedDeploymentError("SOURCE_COMMIT_REQUIRED")
    if not isinstance(artifact_sha256, str) or not SHA64.fullmatch(artifact_sha256):
        raise UnifiedDeploymentError("ARTIFACT_SHA256_REQUIRED")
    if kind is DeploymentKind.ENGINEERING_MODULE:
        if type(module) is not str or module not in ENGINEERING_MODULES:
            raise UnifiedDeploymentError("UNAPPROVED_ENGINEERING_MODULE")
        state = IntegrationState.BLOCKED_NOT_QUALIFIED
    elif kind is DeploymentKind.PPU_RUNTIME:
        if module is not None:
            raise UnifiedDeploymentError("RUNTIME_MODULE_SELECTOR_DENIED")
        state = IntegrationState.EXISTING_RUNTIME
    else:
        if module is not None:
            raise UnifiedDeploymentError("FPGA_MODULE_SELECTOR_DENIED")
        state = IntegrationState.BLOCKED_NOT_QUALIFIED
    return UnifiedDeploymentIntent(kind, module, source_commit, artifact_sha256, state)


def admit_existing_bootstrap_request(body: Mapping[str, object]) -> dict[str, str]:
    """Fail-closed admission BEFORE the existing Bootstrap runtime request.

    Only PPU_RUNTIME is deployed by today's Bootstrap Coordinator/Installer.
    Engineers can package all three modules, but must not send them into
    the PS-only Release Installer until a qualified unified Z2 target adapter
    exists, with Source Pin, immutable release and hardware quiescence checks.
    """
    if not isinstance(body, Mapping):
        raise UnifiedDeploymentError("INVALID_DEPLOYMENT_REQUEST")
    kind = body.get("kind", DeploymentKind.PPU_RUNTIME.value)
    if kind != DeploymentKind.PPU_RUNTIME.value:
        if kind == DeploymentKind.ENGINEERING_MODULE.value:
            raise UnifiedDeploymentError("ENGINEERING_INSTALL_NOT_QUALIFIED")
        if kind == DeploymentKind.FPGA_IMAGE.value:
            raise UnifiedDeploymentError("FPGA_IMAGE_INSTALL_NOT_QUALIFIED")
        raise UnifiedDeploymentError("UNKNOWN_DEPLOYMENT_KIND")
    if "module" in body:
        raise UnifiedDeploymentError("MODULE_NOT_ALLOWED_IN_RUNTIME_INSTALL")
    if "source_commit" in body or "artifact_sha256" in body:
        # The runtime upload ID points to a committed archive + sidecar;
        # provenance must be checked by the installed coordinator/installer.
        raise UnifiedDeploymentError("CALLER_PROVIDED_PROVENANCE_DENIED")
    # Strip only one explicitly admitted discriminator, preserving the
    # existing exact field-set validation performed by Bootstrap.
    return {k: v for k, v in body.items() if k != "kind"}
