#!/usr/bin/env python3
"""Deterministic local deployment engine for the PPU Bootstrap.

The engine owns transaction state, locking and evidence. The current
``ppu-z2-installer.py`` remains the authority for release verification,
immutable release staging, systemd activation, readiness and rollback.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import re
from contextlib import ExitStack, contextmanager
import importlib.util
import json
import os
import shutil
import stat
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence

SCHEMA_VERSION = 1
SAFE_RESTART_STATES = {"runtime_active", "engineering_active", "package_active", "bundle_installed", "asset_set_active", "rolled_back", "verify_failed", "fpga_loaded", "fpga_load_denied", "fpga_identity_failed"}
# B3 fpga_load: fixed protected Root Entry and its root-owned source pin.
# Neither path is ever taken from HTTP, the Bundle or the caller.
ROOT_ENTRY = Path("/usr/local/libexec/plasma/z2-path2-root-entry")
SYSTEMD_RUN = Path("/usr/bin/systemd-run")
ROOT_STAGED_ASSET_SETS = Path("/opt/plasma/assets/staged")
ROOT_BUNDLE_LOAD_TIMEOUT_S = 600
B3_RECEIPT_SCHEMA = "plasma.ppu.b3-deployment-receipt.v2"
_BUNDLE_LOAD_OUTCOMES = frozenset({
    "fpga_loaded", "fpga_load_denied", "recovery_required", "fpga_identity_failed",
})
_PATH2_DENIAL = re.compile(r"PATH2_[A-Z0-9_]{3,80}\Z")
ENGINEERING_MODULES = frozenset({"wordport", "openocd-integration", "abtest"})
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_API_TRANSACTION_ID = re.compile(r"[0-9a-f]{32}\Z")
QUALIFICATION_HEALTH_FAILURE = "qualification-injected post-activation health-check failure"


class DeploymentError(RuntimeError):
    """Raised when a bootstrap deployment transaction cannot complete safely."""


class BundleV3AdmissionVerificationDenied(DeploymentError):
    """Canonical Bundle v3 verification failed before B3 installation."""


class BundleV3AdmissionQualificationDenied(DeploymentError):
    """Trusted FPGA static qualification failed before B3 installation."""


@dataclass(frozen=True)
class DeploymentPaths:
    bootstrap_state_root: Path = Path("/var/lib/plasma-bootstrap")
    product_root: Path = Path("/opt/plasma")
    config_root: Path = Path("/etc/plasma")
    runtime_state_root: Path = Path("/var/lib/plasma")
    log_root: Path = Path("/var/log/plasma")
    systemd_root: Path = Path("/etc/systemd/system")

    @property
    def journal(self) -> Path:
        return self.bootstrap_state_root / "deployment.json"

    @property
    def lock(self) -> Path:
        return self.bootstrap_state_root / "deployment.lock"


@dataclass(frozen=True)
class DeploymentRequest:
    release_artifact: Path
    sidecar: Path
    plasma_python: Path
    gateway_host: str
    ppu_id: str
    facility_id: str
    display_name: str
    qualification_fail_health_check: bool = False
    api_transaction_id: str | None = None


@dataclass(frozen=True)
class EngineeringDeploymentRequest:
    """Internal host-only contract. Never construct this from raw HTTP claims."""

    release_artifact: Path
    module: str
    source_commit: str
    artifact_sha256: str


@dataclass(frozen=True)
class BundleV3InstallRequest:
    """Device-local B3 install, admitted by the existing Bootstrap API only.

    Exact archive digest and target are checked against device-local policy;
    HTTP can only refer to an already committed/admitted upload_id. Git
    provenance is never an admission or activation qualification.
    """

    archive: Path
    artifact_sha256: str
    target_profile: Mapping[str, str]
    api_transaction_id: str
    # Standard B3 selects the verified Set; stage_only is an explicit exception.
    mode: str = "activate"
    # Only a separately authorized, explicit request may load FPGA hardware.
    fpga_load: bool = False

@dataclass(frozen=True)
class HostOnlyPackageRequest:
    """Never built from HTTP; dry-run target identity comes from a test fixture."""

    archive: Path
    artifact_sha256: str
    target_profile: Mapping[str, str]


class EngineeringInstallRolledBack(RuntimeError):
    """The trusted installer proves it restored the complete prior state."""


@dataclass
class DeploymentRecord:
    schema_version: int
    transaction_id: str
    state: str
    sequence: int
    started_at_epoch_s: float
    updated_at_epoch_s: float
    release_artifact: str
    release_id: str | None = None
    artifact_sha256: str | None = None
    previous_release: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    kind: str = "ppu-runtime"
    module: str | None = None
    source_commit: str | None = None
    api_transaction_id: str | None = None
    package_kind: str | None = None
    asset_activation_previous: dict[str, Any] | None = None
    asset_activation_fpga: bool = False


class Journal:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self.path = path
        self.clock = clock

    def read(self) -> DeploymentRecord | None:
        if not self.path.exists():
            return None
        try:
            mode = self.path.stat().st_mode & 0o777
            if mode & 0o077:
                raise DeploymentError(
                    f"deployment journal permissions are too broad: {oct(mode)}"
                )
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise DeploymentError("deployment journal must contain a JSON object")
            record = DeploymentRecord(**payload)
        except DeploymentError:
            raise
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise DeploymentError(f"deployment journal is unreadable: {exc}") from exc
        if record.schema_version != SCHEMA_VERSION:
            raise DeploymentError(
                f"unsupported deployment journal schema: {record.schema_version}"
            )
        if not record.transaction_id or record.sequence < 1:
            raise DeploymentError("deployment journal identity/sequence is invalid")
        return record

    def write(self, record: DeploymentRecord, state: str, **updates: Any) -> None:
        record.sequence += 1
        record.state = state
        record.updated_at_epoch_s = self.clock()
        for key, value in updates.items():
            if not hasattr(record, key):
                raise DeploymentError(f"unknown deployment journal field: {key}")
            setattr(record, key, value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".new")
        payload = json.dumps(asdict(record), indent=2, sort_keys=True) + "\n"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(fd)
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)
        directory_fd = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


class _RuntimeQuiesceDenied(DeploymentError):
    """The running Runtime refused (or could not grant) its upgrade quiesce gate."""


RUNTIME_CONTROL_SOCKET = Path("/run/plasma-server/control.sock")
RUNTIME_RESTART_QUIESCE_TTL_S = 60


def quiesce_runtime_for_restart(
    socket_path: Path | None = None,
    ttl_s: int = RUNTIME_RESTART_QUIESCE_TTL_S,
) -> dict[str, Any]:
    """Acquire the running Runtime's bounded TTL quiesce before an upgrade restart.

    Self-contained on purpose: the Runtime upgrade runs this module from the
    Z2 PS kit ``scripts/`` directory, which ships no sibling helper modules.
    Same gate as the runtime-activation helper: refused while any execution
    lease exists; blocks new Job/Package admission until the TTL expires or
    the process restarts. It leaves no open connection, so it cannot stall the
    Runtime's graceful shutdown (Python >= 3.12.1 Server.wait_closed()).
    """
    path = RUNTIME_CONTROL_SOCKET if socket_path is None else socket_path
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or path.parent.is_symlink()):
        raise _RuntimeQuiesceDenied("RUNTIME_CONTROL_SOCKET_UNTRUSTED")
    try:
        node = path.stat()
        directory = path.parent.stat()
    except OSError as exc:
        raise _RuntimeQuiesceDenied("RUNTIME_CONTROL_SOCKET_UNAVAILABLE") from exc
    if (not stat.S_ISSOCK(node.st_mode) or node.st_mode & 0o077
            or not stat.S_ISDIR(directory.st_mode) or directory.st_mode & 0o022
            or node.st_uid != directory.st_uid):
        raise _RuntimeQuiesceDenied("RUNTIME_CONTROL_SOCKET_UNTRUSTED")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control:
        control.settimeout(5)
        try:
            control.connect(str(path))
            control.sendall(json.dumps({"operation": "quiesce", "ttl_s": ttl_s}).encode() + b"\n")
            buffer = bytearray()
            while b"\n" not in buffer:
                chunk = control.recv(4096)
                if not chunk or len(buffer) + len(chunk) > 8192:
                    raise _RuntimeQuiesceDenied("RUNTIME_RESTART_QUIESCE_REPLY_INVALID")
                buffer.extend(chunk)
            record = json.loads(bytes(buffer).split(b"\n", 1)[0])
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise _RuntimeQuiesceDenied("RUNTIME_RESTART_QUIESCE_TRANSPORT_UNAVAILABLE") from exc
    if (not isinstance(record, dict) or record.get("ok") is not True
            or not isinstance(record.get("result"), dict)
            or record["result"].get("ttl_s") != ttl_s
            or type(record["result"].get("token")) is not str):
        message = ""
        if isinstance(record, dict) and isinstance(record.get("error"), dict):
            message = str(record["error"].get("message") or "")[:200]
        raise _RuntimeQuiesceDenied("RUNTIME_RESTART_QUIESCE_NOT_GRANTED" + (f": {message}" if message else ""))
    return dict(record["result"])


class DeploymentCoordinator:
    def __init__(
        self,
        *,
        paths: DeploymentPaths,
        installer: ModuleType,
        clock: Callable[[], float] = time.time,
        transaction_id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        root_bundle_loader: Callable[[str], Mapping[str, Any]] | None = None,
        quiescence_lease: Callable[[], Any] | None = None,
        runtime_restart_quiesce: Callable[[], Any] | None = None,
    ) -> None:
        self.paths = paths
        self.installer = installer
        self.clock = clock
        self.transaction_id_factory = transaction_id_factory
        self.journal = Journal(paths.journal, clock)
        # Host-only tests inject fakes; production uses the fixed Root Entry
        # and the Runtime's connection-held Job quiesce lease.
        self.root_bundle_loader = root_bundle_loader
        self.quiescence_lease = quiescence_lease
        self.runtime_restart_quiesce = runtime_restart_quiesce

    @staticmethod
    def qualify_bundle_v3_admission(
        archive: Path, *, expected_sha256: str,
        target_profile: Mapping[str, str], contracts_path: Path,
    ) -> dict[str, Any]:
        """One read-only B2/B3 preflight for the canonical Bundle v3.

        The Bootstrap API owns upload transport and owner authorization; this
        Engine owns Bundle verification, static FPGA qualification and the
        canonical admission plan. This writes no journal or active pointer.
        B3 independently verifies the ZIP again *under* deployment.lock.
        """
        contract_path = Path(__file__).with_name("ppu_unified_deployment.py")
        spec = importlib.util.spec_from_file_location(
            "plasma_bundle_v3_engine_admission", contract_path,
        )
        if spec is None or spec.loader is None:
            raise BundleV3AdmissionVerificationDenied("BUNDLE_VERIFIER_UNAVAILABLE")
        contract = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = contract
        spec.loader.exec_module(contract)
        try:
            verified = contract.verify_host_only_artifact(
                archive, expected_sha256=expected_sha256,
                target_profile=target_profile,
            )
        except contract.UnifiedDeploymentError as exc:
            raise BundleV3AdmissionVerificationDenied(str(exc)) from exc
        if (not isinstance(verified, contract.VerifiedBundle)
                or verified.kind != "bundle" or verified.schema != contract.BUNDLE_SCHEMA):
            raise BundleV3AdmissionVerificationDenied("PACKAGE_KIND_MISMATCH")

        fpga_path = Path(__file__).with_name("ppu_fpga_qualification.py")
        fpga_spec = importlib.util.spec_from_file_location(
            "plasma_bundle_v3_engine_fpga_qualification", fpga_path,
        )
        if fpga_spec is None or fpga_spec.loader is None:
            raise BundleV3AdmissionQualificationDenied("FPGA_QUALIFIER_UNAVAILABLE")
        fpga = importlib.util.module_from_spec(fpga_spec)
        sys.modules[fpga_spec.name] = fpga
        fpga_spec.loader.exec_module(fpga)
        try:
            fpga_qualification = fpga.qualify_bundle_fpga(
                archive, verified, contracts_path=contracts_path,
                trusted_target=target_profile,
            )
        except fpga.FpgaQualificationDenied as exc:
            raise BundleV3AdmissionQualificationDenied(str(exc)) from exc

        return {
            "package": verified.name,
            "kind": verified.kind,
            "version": verified.version,
            "source_commit": verified.source_commit,
            "archive_sha256": verified.archive_sha256,
            "files": [dict(path=item.path, sha256=item.sha256, size=item.size,
                           executable=item.executable) for item in verified.files],
            "target": dict(verified.target),
            "requested_actions": list(verified.actions),
            "execution_permitted": False,
            "fpga_qualification": fpga_qualification,
            "purpose": verified.purpose,
            "packages": [
                {"id": package.id, "kind": package.kind, "version": package.version,
                 "requires": list(package.requires),
                 "files": [item.path for item in package.files]}
                for package in verified.packages
            ],
            "bundle_schema": verified.schema,
        }

    def _installer_paths(self):
        return self.installer.InstallPaths(
            product_root=self.paths.product_root,
            config_root=self.paths.config_root,
            state_root=self.paths.runtime_state_root,
            log_root=self.paths.log_root,
            systemd_root=self.paths.systemd_root,
        )

    def asset_status(self) -> dict[str, Any]:
        """Read-only identity plus the sole transaction journal's safety fence."""
        record = self.journal.read()
        current = self._asset_helper().read_active(self.paths.product_root)
        if record is not None and record.state in {
                "activating", "fpga_loading", "recovery_required", "fpga_identity_failed"}:
            current.update(state="RECOVERY_REQUIRED", ready=False,
                           coordinator_state=record.state)
        return current

    def _admit_previous_transaction(self, *, recover_assets: bool = False) -> None:
        previous = self.journal.read()
        if previous is None or previous.state in SAFE_RESTART_STATES:
            return
        if (previous.kind in {"bundle", "asset-set"}
                and previous.state in {"received", "verifying", "verified"}):
            # These phases precede staging, Root entry and pointer mutation.
            self.journal.write(previous, "verify_failed",
                               error_code="interrupted_before_asset_mutation")
            return
        # Only a pointer-only activation can be recovered without hardware
        # evidence. The snapshot is durable BEFORE publication; a PL write
        # (including a successful download with uncertain publication) must
        # remain fenced for guarded recovery.
        if (recover_assets and previous.asset_activation_previous is not None
                and previous.kind in {"bundle", "asset-set"}
                and previous.asset_activation_fpga is False
                and previous.state in {"activating", "recovery_required"}):
            helper = self._asset_helper()
            lease = self.quiescence_lease or helper.held_runtime_asset_lease
            try:
                with lease():
                    helper.restore_previous(
                        self.paths.product_root, previous.asset_activation_previous,
                        previous.artifact_sha256, runtime_quiesced=True,
                    )
                    self.journal.write(previous, "rolled_back",
                                       error_code="asset_activation_recovered",
                                       error_message=None)
            except Exception as exc:
                self.journal.write(previous, "recovery_required",
                                   error_code="asset_rollback_unproven",
                                   error_message=type(exc).__name__)
                raise DeploymentError("ASSET_SET_ROLLBACK_REQUIRES_RECOVERY") from exc
            return
        # "installed" is terminal for a verified B3 Host-only sandbox ONLY.
        # Do not admit this state for runtime/engineering/Bootstrap HTTP:
        # those paths have their own activation and recovery contract.
        if (previous.state == "installed" and previous.kind == "host-only-package"
                and self.paths.bootstrap_state_root != DeploymentPaths().bootstrap_state_root
                and self.paths.bootstrap_state_root.is_absolute()
                and not self.paths.bootstrap_state_root.is_symlink()
                and self.paths.bootstrap_state_root.resolve().is_relative_to(
                    Path(tempfile.gettempdir()).resolve())):
            return
        if previous.state == "recovery_required":
            raise DeploymentError(
                "previous deployment requires recovery before another transaction may start"
            )
        interrupted_state = previous.state
        self.journal.write(
            previous,
            "recovery_required",
            error_code="interrupted_transaction",
            error_message=(
                "previous deployment ended without a terminal result while in state "
                f"{interrupted_state}; inspect active release/service state before recovery"
            ),
        )
        raise DeploymentError(
            f"previous deployment transaction was interrupted in state {interrupted_state}; recovery is required"
        )

    @contextmanager
    def _deployment_lock(self, *, recover_assets: bool = False):
        """The *same* durable lock for PS Runtime and Engineering plans."""
        self.paths.bootstrap_state_root.mkdir(parents=True, exist_ok=True)
        with self.paths.lock.open("a+b") as lock_stream:
            os.chmod(self.paths.lock, 0o600)
            try:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DeploymentError("another PPU deployment transaction is active") from exc
            try:
                self._admit_previous_transaction(recover_assets=recover_assets)
                yield
            finally:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)

    def execute(self, request: DeploymentRequest) -> Mapping[str, Any]:
        # This is an audit correlation tag only, never a Root/Master grant.
        if request.api_transaction_id is not None and (
            not isinstance(request.api_transaction_id, str)
            or not _API_TRANSACTION_ID.fullmatch(request.api_transaction_id)
        ):
            raise DeploymentError("Bootstrap API transaction identity is invalid")
        with self._deployment_lock():
            if request.qualification_fail_health_check:
                previous = self.installer._previous_current(self._installer_paths().current)
                if previous is None:
                    raise DeploymentError(
                        "qualification health-check failure injection requires an existing previous release"
                    )
            return self._execute_locked(request)

    def execute_engineering(self, request: EngineeringDeploymentRequest) -> Mapping[str, Any]:
        """Host-only qualified-installer seam; not remotely callable or Root-enabled.

        This adds no second installer, process, socket, lock or journal.
        Existing deployed PS-only Installer exposes neither engineering method,
        and the Bootstrap HTTP API explicitly rejects engineering packages.
        The future reviewed Installer must verify publisher identity, exact
        file list, pinned Root source, quiescence, and durable rollback itself.
        """
        if not isinstance(request, EngineeringDeploymentRequest):
            raise DeploymentError("ENGINEERING_REQUEST_INVALID")
        if request.module not in ENGINEERING_MODULES:
            raise DeploymentError("ENGINEERING_MODULE_NOT_ALLOWED")
        if not _HEX40.fullmatch(request.source_commit) or not _HEX64.fullmatch(request.artifact_sha256):
            raise DeploymentError("ENGINEERING_PROVENANCE_FORMAT_INVALID")
        if not isinstance(request.release_artifact, Path) or request.release_artifact.is_symlink():
            raise DeploymentError("ENGINEERING_ARCHIVE_UNTRUSTED")
        with self._deployment_lock():
            # Fail before journal mutation if this is the real PS-only installer.
            verify = getattr(self.installer, "verify_engineering_package", None)
            install = getattr(self.installer, "install_engineering_package", None)
            if not callable(verify) or not callable(install):
                raise DeploymentError("ENGINEERING_INSTALL_NOT_QUALIFIED")
            record = DeploymentRecord(
                schema_version=SCHEMA_VERSION,
                transaction_id=self.transaction_id_factory(),
                state="received",
                sequence=0,
                started_at_epoch_s=self.clock(),
                updated_at_epoch_s=self.clock(),
                release_artifact=str(request.release_artifact),
                kind="engineering-module",
                module=request.module,
                source_commit=request.source_commit,
            )
            self.journal.write(record, "received")
            try:
                self.journal.write(record, "verifying")
                digest = hashlib.sha256()
                with request.release_artifact.open("rb") as file:
                    for block in iter(lambda: file.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != request.artifact_sha256:
                    raise DeploymentError("ENGINEERING_ARCHIVE_SHA256_MISMATCH")
                # Trusted installed verifier MUST independently re-check this
                # archive at installation; this check is not TOCTOU protection.
                verified = verify(
                    request.release_artifact, module=request.module,
                    source_commit=request.source_commit,
                    expected_sha256=request.artifact_sha256,
                )
            except Exception as exc:
                self.journal.write(
                    record, "verify_failed",
                    error_code="engineering_verification_failed", error_message=str(exc),
                )
                raise DeploymentError(f"engineering verification failed: {exc}") from exc
            self.journal.write(record, "verified", artifact_sha256=request.artifact_sha256)
            try:
                self.journal.write(record, "activating")
                evidence = install(verified, paths=self._installer_paths())
                if not isinstance(evidence, Mapping) or evidence.get("result") != "PASS":
                    raise DeploymentError("ENGINEERING_INSTALL_RECEIPT_INVALID")
            except EngineeringInstallRolledBack as exc:
                self.journal.write(
                    record, "rolled_back", error_code="engineering_rollback_completed",
                    error_message=str(exc),
                )
                raise DeploymentError(f"engineering installation rolled back: {exc}") from exc
            except Exception as exc:
                self.journal.write(
                    record, "recovery_required", error_code="engineering_outcome_unknown",
                    error_message=str(exc),
                )
                raise DeploymentError(f"engineering installation requires recovery: {exc}") from exc
            self.journal.write(record, "engineering_active")
            return {
                "schema_version": SCHEMA_VERSION,
                "result": "PASS",
                "transaction": asdict(record),
                "installer_evidence": dict(evidence),
                "not_claimed": [
                    "SWPC/Z2 atomic transaction",
                    "production authorization",
                    "hardware programming",
                ],
            }


    def execute_bundle_v3_install(
        self, request: BundleV3InstallRequest,
    ) -> Mapping[str, Any]:
        """Single locked B3 Install/Activate or explicit stage_only, no B4.

        This is NOT the Host-only simulator. A factory provisioned local policy
        and a matching B2 admission receipt must be checked by Bootstrap before
        invoking this path. The Installer independently verifies ZIP content.
        """
        if not isinstance(request, BundleV3InstallRequest):
            raise DeploymentError("B3_INSTALL_REQUEST_INVALID")
        if (not _HEX64.fullmatch(request.artifact_sha256)
                or not _API_TRANSACTION_ID.fullmatch(request.api_transaction_id)
                or not isinstance(request.archive, Path)
                or request.archive.is_symlink()
                or not request.archive.is_file()):
            raise DeploymentError("B3_INSTALL_PROVENANCE_INVALID")
        if (not isinstance(request.target_profile, Mapping)
                or set(request.target_profile) != {"platform", "board", "fpga_part"}):
            raise DeploymentError("B3_INSTALL_TARGET_INVALID")
        if type(request.fpga_load) is not bool:
            raise DeploymentError("B3_FPGA_LOAD_FLAG_INVALID")
        if type(request.mode) is not str or request.mode not in {"activate", "stage_only"}:
            raise DeploymentError("B3_MODE_INVALID")
        if request.mode == "stage_only" and request.fpga_load:
            raise DeploymentError("B3_STAGE_ONLY_FPGA_LOAD_DENIED")
        verify_contract = Path(__file__).with_name("ppu_unified_deployment.py")
        spec = importlib.util.spec_from_file_location("plasma_b3_device_contract", verify_contract)
        if spec is None or spec.loader is None:
            raise DeploymentError("B3_VERIFIER_UNAVAILABLE")
        contract = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = contract
        spec.loader.exec_module(contract)
        # Explicitly reuse the sole deployment lock and journal. Do not add
        # another lock, daemon, process supervisor or recovery mechanism.
        with self._deployment_lock(recover_assets=request.mode == "activate"):
            install = getattr(self.installer, "install_verified_bundle_v3", None)
            if not callable(install):
                raise DeploymentError("B3_DEVICE_INSTALLER_NOT_QUALIFIED")
            now = self.clock()
            record = DeploymentRecord(
                schema_version=SCHEMA_VERSION,
                transaction_id=self.transaction_id_factory(),
                state="received",
                sequence=0,
                started_at_epoch_s=now,
                updated_at_epoch_s=now,
                release_artifact=str(request.archive),
                api_transaction_id=request.api_transaction_id,
                artifact_sha256=request.artifact_sha256,
                kind="bundle",
                package_kind="bundle",
            )
            self.journal.write(record, "received")
            try:
                self.journal.write(record, "verifying")
                bundle = contract.verify_host_only_artifact(
                    request.archive, expected_sha256=request.artifact_sha256,
                    target_profile=request.target_profile,
                )
                if (not isinstance(bundle, contract.VerifiedBundle)
                        or bundle.schema != contract.BUNDLE_SCHEMA
                        or bundle.kind != "bundle"
                        or bundle.actions != ("install", "verify")
                        or not bundle.packages):
                    raise DeploymentError("B3_BUNDLE_INSTALL_CONTRACT_DENIED")
                # The canonical Bundle verifier already enforces Package IDs,
                # kinds, file constraints, target compatibility, SHA-256, and
                # closed acyclic dependency graph. Never special-case a named
                # fixture or treat its contents as execution authority.
                record.source_commit = bundle.source_commit
                record.module = bundle.name
                record.release_id = (bundle.version + "-" +
                                     bundle.archive_sha256[:16])
                has_fpga_image = any(
                    package.kind == "fpga-image" for package in bundle.packages)
                if request.fpga_load and not has_fpga_image:
                    raise DeploymentError("B3_FPGA_LOAD_REQUIRES_FPGA_IMAGE")
                if request.mode == "activate" and has_fpga_image and not request.fpga_load:
                    raise DeploymentError("B3_FPGA_ACTIVATION_REQUIRES_EXPLICIT_LOAD")
                self.journal.write(record, "verified")
            except Exception as exc:
                if str(exc) in {"B3_FPGA_LOAD_REQUIRES_FPGA_IMAGE",
                                "B3_FPGA_ACTIVATION_REQUIRES_EXPLICIT_LOAD"}:
                    self.journal.write(
                        record, "verify_failed",
                        error_code=("b3_fpga_load_requires_fpga_image"
                                    if request.fpga_load else "b3_fpga_activation_requires_explicit_load"),
                        error_message=type(exc).__name__,
                    )
                    raise
                self.journal.write(
                    record, "verify_failed",
                    error_code="b3_bundle_verification_failed",
                    error_message=type(exc).__name__,
                )
                raise DeploymentError("B3_BUNDLE_VERIFICATION_DENIED") from exc
            try:
                self.journal.write(record, "staging")
                evidence = install(
                    bundle, archive=request.archive, paths=self._installer_paths(),
                )
                if (not isinstance(evidence, Mapping)
                        or evidence.get("result") != "PASS"
                        or evidence.get("archive_sha256") != request.artifact_sha256
                        or evidence.get("bundle_name") != bundle.name):
                    raise DeploymentError("B3_DEVICE_INSTALL_RECEIPT_INVALID")
            except Exception as exc:
                self.journal.write(
                    record, "recovery_required",
                    error_code="b3_install_outcome_uncertain",
                    error_message=type(exc).__name__,
                )
                raise DeploymentError("B3_INSTALL_REQUIRES_RECOVERY") from exc
            self.journal.write(record, "bundle_installed")
            fpga_load: dict[str, Any] = {"requested": False, "result": "NOT_RUN"}
            active: Mapping[str, Any] | None = None
            if request.fpga_load:
                fpga_load, active = self._b3_fpga_load_locked(
                    record, request.artifact_sha256, Path(evidence["path"]),
                )
            elif request.mode == "activate":
                active = self._b3_activate_without_fpga_locked(
                    record, request.artifact_sha256,
                )
            return {
                "result": "PASS",
                "schema": B3_RECEIPT_SCHEMA,
                "stage": ("bundle_install_and_fpga_load" if request.fpga_load
                          else "bundle_install_and_activate" if request.mode == "activate"
                          else "bundle_staged_only"),
                "mode": request.mode,
                "ready": False,
                "transaction": asdict(record),
                "bundle_name": bundle.name,
                "archive_sha256": request.artifact_sha256,
                "source_commit": bundle.source_commit,
                "package_order": evidence["package_order"],
                "files_verified": evidence["files_verified"],
                "install_path": evidence["path"],
                "per_package_install_executed": True,
                "runtime_activation_executed": False,
                "fpga": "LOADED" if request.fpga_load else "NOT_RUN",
                "fpga_load": fpga_load,
                "active_asset_set": None if active is None else dict(active),
                # The Runtime's view of the PL is stale after a reload; Site
                # execution needs a fresh Site admission (not done in B3).
                "runtime_site_readmission": (
                    "REQUIRED" if request.fpga_load else "NOT_REQUIRED"),
                "dut": "NOT_RUN",
            }

    def _b3_activate_without_fpga_locked(
        self, record: DeploymentRecord, asset_set_sha256: str,
    ) -> Mapping[str, Any]:
        """Reuse the same Runtime lease and atomic Active Set publisher under deployment.lock."""
        helper = self._asset_helper()
        lease = self.quiescence_lease or helper.held_runtime_asset_lease
        try:
            hold = lease()
            with hold:
                self.journal.write(record, "activating",
                                   asset_activation_previous=helper.read_active(self.paths.product_root))
                try:
                    active = helper.activate_verified(
                        self.paths.product_root, asset_set_sha256, runtime_quiesced=True,
                    )
                    if (active.get("result") != "PASS"
                            or active.get("asset_set_sha256") != asset_set_sha256
                            or active.get("ready") is not False
                            or active.get("fpga") != "NOT_RUN"):
                        raise DeploymentError("B3_ACTIVE_SET_RECEIPT_INVALID")
                except Exception as exc:
                    self.journal.write(record, "recovery_required",
                                       error_code="b3_active_set_publish_uncertain",
                                       error_message=type(exc).__name__)
                    raise DeploymentError("B3_ACTIVE_SET_PUBLISH_REQUIRES_RECOVERY") from exc
                self.journal.write(record, "asset_set_active")
        except DeploymentError:
            raise
        except Exception as exc:
            if record.state == "bundle_installed":
                self.journal.write(record, "verify_failed",
                                   error_code="b3_runtime_quiesce_denied",
                                   error_message=type(exc).__name__)
                raise DeploymentError("B3_RUNTIME_QUIESCE_DENIED") from exc
            self.journal.write(record, "recovery_required",
                               error_code="b3_activation_outcome_uncertain",
                               error_message=type(exc).__name__)
            raise DeploymentError("B3_ACTIVATION_REQUIRES_RECOVERY") from exc
        return {"asset_set_sha256": active["asset_set_sha256"],
                "generation": active["generation"],
                "already_active": active["already_active"]}

    def _asset_helper(self) -> ModuleType:
        helper_path = Path(__file__).with_name("ppu_asset_set.py")
        spec = importlib.util.spec_from_file_location("plasma_ppu_active_asset_set", helper_path)
        if spec is None or spec.loader is None:
            raise DeploymentError("ASSET_SET_MANAGER_UNAVAILABLE")
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
        return helper

    def _b3_fpga_load_locked(
        self, record: DeploymentRecord, asset_set_sha256: str, install_path: Path,
    ) -> tuple[dict[str, Any], Mapping[str, Any]]:
        """B3 v2: Quiesce -> Root bundle-load -> publish active.json.

        Runs under the caller's deployment.lock. Journal outcomes:
        fpga_loaded | fpga_load_denied (PL untouched) | recovery_required |
        fpga_identity_failed (Image kept loaded, no automatic Golden Restore).
        active.json changes only after Root Identity PASS.
        """
        def deny(code: str, exc: BaseException | None = None) -> DeploymentError:
            self.journal.write(record, "fpga_load_denied", error_code=code,
                               error_message=type(exc).__name__ if exc else code)
            return DeploymentError("B3_FPGA_LOAD_DENIED:" + code)

        helper = self._asset_helper()
        loader = self.root_bundle_loader
        if loader is None:
            # The protected Root locates the Set under its fixed product root.
            if install_path != ROOT_STAGED_ASSET_SETS / asset_set_sha256:
                raise deny("b3_fpga_load_install_path_not_canonical")
            loader = run_root_bundle_load
        try:
            handoff = helper.resolve_staged_fpga_handoff(
                self.paths.product_root, asset_set_sha256)
        except Exception as exc:
            raise deny("b3_fpga_handoff_denied", exc) from exc
        lease = self.quiescence_lease or helper.held_runtime_asset_lease
        hold = ExitStack()
        try:
            # Connection-held for the whole load + active.json publish.
            hold.enter_context(lease())
        except Exception as exc:
            raise deny("b3_runtime_quiesce_denied", exc) from exc
        with hold:
            self.journal.write(record, "fpga_loading", asset_activation_fpga=True,
                               asset_activation_previous=helper.read_active(self.paths.product_root))
            try:
                outcome = dict(loader(asset_set_sha256))
            except Exception as exc:
                outcome = {"result": "recovery_required",
                           "code": "ROOT_ENTRY_OUTCOME_UNKNOWN:" + type(exc).__name__}
            result = outcome.get("result")
            code = outcome.get("code")
            code = code if isinstance(code, str) and code else str(result)
            if result not in _BUNDLE_LOAD_OUTCOMES:
                result, code = "recovery_required", "ROOT_ENTRY_OUTCOME_INVALID"
            if result == "fpga_loaded" and (
                    outcome.get("asset_set_sha256") != asset_set_sha256
                    or outcome.get("fpga_image_id") != handoff["fpga_image"]["image_id"]
                    or outcome.get("fpga_bin_sha256") != handoff["fpga_image"]["bin_sha256"]
                    or outcome.get("identity") != "IDENTITY_PASS"):
                # PL was written but the Root receipt does not match the Set.
                result, code = "recovery_required", "ROOT_RECEIPT_MISMATCH"
            if result == "fpga_load_denied":
                raise deny(code[:200])
            if result == "fpga_identity_failed":
                self.journal.write(record, "fpga_identity_failed",
                                   error_code="b3_fpga_identity_failed",
                                   error_message=code[:200])
                raise DeploymentError("B3_FPGA_IDENTITY_FAILED:" + code[:200])
            if result == "recovery_required":
                self.journal.write(record, "recovery_required",
                                   error_code="b3_fpga_download_outcome_uncertain",
                                   error_message=code[:200])
                raise DeploymentError("B3_FPGA_LOAD_REQUIRES_RECOVERY:" + code[:200])
            self.journal.write(record, "activating")
            try:
                active = helper.activate_verified(
                    self.paths.product_root, asset_set_sha256, runtime_quiesced=True,
                )
                if (active.get("result") != "PASS"
                        or active.get("asset_set_sha256") != asset_set_sha256):
                    raise DeploymentError("ASSET_SET_ACTIVATION_RECEIPT_INVALID")
            except Exception as exc:
                self.journal.write(record, "recovery_required",
                                   error_code="b3_active_set_publish_uncertain",
                                   error_message=type(exc).__name__)
                raise DeploymentError("B3_ACTIVE_SET_PUBLISH_REQUIRES_RECOVERY") from exc
            self.journal.write(record, "fpga_loaded")
        return ({
            "requested": True, "result": "fpga_loaded",
            "fpga_image_id": outcome["fpga_image_id"],
            "fpga_bin_sha256": outcome["fpga_bin_sha256"],
            "fpga_manifest_sha256": outcome.get("fpga_manifest_sha256"),
            "manifest_promoted": outcome.get("manifest_promoted"),
            "download_count": outcome.get("download_count"),
            "identity": outcome["identity"],
            "boot_id": outcome.get("boot_id"),
            "auto_restore": False,
            "programming_profile": handoff["programming_profile"],
        }, {
            "asset_set_sha256": active["asset_set_sha256"],
            "generation": active["generation"],
            "already_active": active["already_active"],
        })

    def activate_staged_asset_set(
        self, asset_set_sha256: str, *,
        quiescence_lease: Callable[[], Any] | None = None,
    ) -> Mapping[str, Any]:
        """P1 Host-only integration seam; never a Console-supplied idle bool.

        By default, the existing PPU Runtime's root-only Unix control
        socket grants a connection-held Job-admission quiesce lease. An
        absent Runtime, a busy/cancelling Site, or an untrusted socket fails
        closed. The existing Hardware Manager remains a separate P2 guard
        before any FPGA configuration or real IC programming.
        """
        if (type(asset_set_sha256) is not str
                or not _HEX64.fullmatch(asset_set_sha256)):
            raise DeploymentError("ASSET_SET_SHA_INVALID")
        # An omitted lease is NOT an idle authorization. It must use the
        # existing Runtime's private connection-held Job admission gate.
        # Host-only tests can inject an equivalent trusted lease explicitly.
        helper_path = Path(__file__).with_name("ppu_asset_set.py")
        spec = importlib.util.spec_from_file_location("plasma_ppu_active_asset_set", helper_path)
        if spec is None or spec.loader is None:
            raise DeploymentError("ASSET_SET_MANAGER_UNAVAILABLE")
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
        if quiescence_lease is None:
            quiescence_lease = helper.held_runtime_asset_lease
        with self._deployment_lock(recover_assets=True):
            now = self.clock()
            record = DeploymentRecord(
                schema_version=SCHEMA_VERSION,
                transaction_id=self.transaction_id_factory(),
                state="received", sequence=0,
                started_at_epoch_s=now, updated_at_epoch_s=now,
                release_artifact=str(self.paths.product_root / "assets" / "staged" / asset_set_sha256),
                artifact_sha256=asset_set_sha256,
                kind="asset-set",
            )
            self.journal.write(record, "received")
            try:
                self.journal.write(record, "verifying")
                helper.verify_staged(self.paths.product_root, asset_set_sha256)
                self.journal.write(record, "verified")
            except Exception as exc:
                self.journal.write(
                    record, "verify_failed", error_code="asset_set_verification_failed",
                    error_message=type(exc).__name__,
                )
                raise DeploymentError("ASSET_SET_NOT_VERIFIED") from exc
            try:
                with quiescence_lease():
                    self.journal.write(record, "activating",
                                       asset_activation_previous=helper.read_active(self.paths.product_root))
                    result = helper.activate_verified(
                        self.paths.product_root, asset_set_sha256,
                        runtime_quiesced=True,
                    )
                    if (result.get("result") != "PASS"
                            or result.get("asset_set_sha256") != asset_set_sha256
                            or result.get("ready") is not False
                            or result.get("fpga") != "NOT_RUN"):
                        raise DeploymentError("ASSET_SET_ACTIVATION_RECEIPT_INVALID")
            except Exception as exc:
                if record.state == "verified":
                    # Runtime refused the exclusive quiescence lease BEFORE
                    # any Active Set write: safe to retry after Jobs finish.
                    self.journal.write(
                        record, "verify_failed",
                        error_code="asset_set_quiescence_denied",
                        error_message=type(exc).__name__,
                    )
                    raise DeploymentError("ASSET_SET_QUIESCE_DENIED") from exc
                self.journal.write(
                    record, "recovery_required",
                    error_code="asset_set_activation_outcome_uncertain",
                    error_message=type(exc).__name__,
                )
                raise DeploymentError("ASSET_SET_ACTIVATION_REQUIRES_RECOVERY") from exc
            self.journal.write(record, "asset_set_active")
            return {
                "result": "PASS", "stage": "asset_set_active",
                "transaction": asdict(record), **dict(result),
                "runtime_activation_executed": False,
                "fpga": "NOT_RUN", "dut": "NOT_RUN",
            }

    def execute_authorized_bundle_host_only(
        self,
        request: HostOnlyPackageRequest,
        *,
        owner_authorization: Mapping[str, object],
        trusted_inventory: Mapping[str, Mapping[str, object]],
        inject_failure: str | None = None,
    ) -> Mapping[str, Any]:
        """PR3 policy/resolution -> the SAME Host-only Engine Lock/Journal.

        Test-fixture trust is never accepted from HTTP, never a real publisher
        signature or Master authorization. The only eventual writer is the
        existing execute_package_host_only() transaction.
        """
        if not isinstance(request, HostOnlyPackageRequest):
            raise DeploymentError("HOST_ONLY_PACKAGE_REQUEST_INVALID")
        # An independently qualified device installer is NOT connected here.
        contract_path = Path(__file__).with_name("ppu_unified_deployment.py")
        spec = importlib.util.spec_from_file_location("ppu_pr3_host_only_contract", contract_path)
        if spec is None or spec.loader is None:
            raise DeploymentError("HOST_ONLY_CONTRACT_UNAVAILABLE")
        contract = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = contract
        spec.loader.exec_module(contract)
        try:
            bundle = contract.verify_host_only_artifact(
                request.archive, expected_sha256=request.artifact_sha256,
                target_profile=request.target_profile,
            )
            if (not isinstance(bundle, contract.VerifiedBundle)
                    or bundle.schema != contract.BUNDLE_SCHEMA):
                raise contract.UnifiedDeploymentError("BUNDLE_V3_REQUIRED")
            authority = contract.evaluate_host_only_owner_authorization(
                bundle, owner_authorization=owner_authorization,
            )
            resolution = contract.resolve_host_only_bundle(
                bundle, trusted_inventory=trusted_inventory,
            )
        except contract.UnifiedDeploymentError as exc:
            raise DeploymentError(f"host-only Bundle authorization denied: {exc}") from exc
        receipt = dict(self.execute_package_host_only(
            request, inject_failure=inject_failure, install_only=True,
        ))
        receipt["authorization"] = authority
        receipt["resolution"] = resolution
        # The existing sandbox engine stages the verified archive and atomically
        # switches ONE bundle receipt. It does NOT install individual packages
        # or activate runtime services. Do not label the resolver's planned
        # package actions as completed B3/B4 operations.
        receipt["b3_install"] = {
            "status": "HOST_ONLY_VERIFIED",
            "archive_staged_host_only": True,
            "package_order_plan": resolution["package_order"],
            "package_stage_plan": resolution["stage"],
            "package_reuse_plan": resolution["reuse"],
            "per_package_install_executed": False,
            "per_package_host_only_staging_verified": True,
            "real_device_install_qualified": False,
        }
        receipt["b4_activate"] = {
            "status": "NOT_QUALIFIED",
            "bundle_receipt_switched_host_only": False,
            "runtime_activation_executed": False,
            "rollback_simulation_supported": True,
        }
        receipt["install_qualified"] = False
        return receipt

    def execute_package_host_only(
        self, request: HostOnlyPackageRequest, *, inject_failure: str | None = None,
        install_only: bool = False,
    ) -> Mapping[str, Any]:
        """One Lock/Journal/Engine; exercise package lifecycle in a sandbox ONLY.

        No installed Root path, service, hardware handler or HTTP request calls
        this method. The sandbox is under a non-production Bootstrap state root;
        payload files are never executed, imported or installed into product_root.
        """
        if not isinstance(request, HostOnlyPackageRequest):
            raise DeploymentError("HOST_ONLY_PACKAGE_REQUEST_INVALID")
        if self.paths.bootstrap_state_root == DeploymentPaths().bootstrap_state_root:
            raise DeploymentError("HOST_ONLY_PRODUCTION_STATE_ROOT_DENIED")
        if (not self.paths.bootstrap_state_root.is_absolute()
                or self.paths.bootstrap_state_root.is_symlink()):
            raise DeploymentError("HOST_ONLY_SANDBOX_ROOT_INVALID")
        temporary_root = Path(tempfile.gettempdir()).resolve()
        if not self.paths.bootstrap_state_root.resolve().is_relative_to(temporary_root):
            raise DeploymentError("HOST_ONLY_SANDBOX_MUST_BE_TEMPORARY")
        if inject_failure not in (None, "after_stage", "after_activate", "rollback_unknown"):
            raise DeploymentError("HOST_ONLY_FAILURE_SELECTOR_INVALID")
        if install_only and inject_failure in ("after_activate", "rollback_unknown"):
            raise DeploymentError("INSTALL_ONLY_ACTIVATION_FAILURE_SELECTOR_DENIED")
        if type(install_only) is not bool:
            raise DeploymentError("HOST_ONLY_FAILURE_SELECTOR_INVALID")

        # A data-only contract module, not an installer, adapter or new daemon.
        contract_path = Path(__file__).with_name("ppu_unified_deployment.py")
        spec = importlib.util.spec_from_file_location("ppu_host_only_package_contract", contract_path)
        if spec is None or spec.loader is None:
            raise DeploymentError("HOST_ONLY_CONTRACT_UNAVAILABLE")
        contract = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = contract
        spec.loader.exec_module(contract)

        with self._deployment_lock():
            now = self.clock()
            record = DeploymentRecord(
                schema_version=SCHEMA_VERSION,
                transaction_id=self.transaction_id_factory(),
                state="received", sequence=0, started_at_epoch_s=now,
                updated_at_epoch_s=now, release_artifact=str(request.archive),
                kind="host-only-package",
            )
            self.journal.write(record, "received")
            try:
                self.journal.write(record, "verifying")
                package = contract.verify_host_only_artifact(
                    request.archive, expected_sha256=request.artifact_sha256,
                    target_profile=request.target_profile,
                )
            except Exception as exc:
                self.journal.write(record, "verify_failed",
                                   error_code="package_verification_failed", error_message=str(exc))
                raise DeploymentError(f"host-only package verification failed: {exc}") from exc
            record.source_commit = package.source_commit
            record.module = package.name
            record.package_kind = package.kind
            record.artifact_sha256 = package.archive_sha256
            self.journal.write(record, "verified")
            # Resolve the canonical v3 DAG BEFORE mutating the sandbox.
            # The single existing transaction still activates the entire
            # bundle atomically; package binaries are never executed.
            resolution = contract.resolve_host_only_bundle(package, trusted_inventory={})
            package_by_id = {p.id: p for p in package.packages}
            ordered_members = []
            for package_id in resolution["package_order"]:
                component = package_by_id[package_id]
                prefix = f"payload/packages/{package_id}/"
                members = [entry for entry in component.files]
                for member in members:
                    if not member.path.startswith(prefix):
                        raise DeploymentError("HOST_ONLY_PACKAGE_FILE_SCOPE_INVALID")
                ordered_members.extend(members)
            if {m.path for m in ordered_members} != {m.path for m in package.files}:
                raise DeploymentError("HOST_ONLY_PACKAGE_FILE_COVERAGE_MISMATCH")

            # Only a non-production simulation store is mutated; the real
            # /opt/plasma, FPGA Manager and factory recovery are untouched.
            store = self.paths.bootstrap_state_root / "host-only-packages"
            release_id = (f"{package.version}-"
                          f"{package.archive_sha256[:16]}")
            release_root = store / "releases" / package.name / release_id
            active_path = store / "active" / f"{package.name}.json"
            record.release_id = release_id
            previous: bytes | None = None
            activated = False

            # Never follow an existing symlink in the simulated install tree.
            for boundary in (store, store / "releases", release_root.parent,
                             release_root, store / "active", active_path):
                if boundary.is_symlink():
                    self.journal.write(record, "verify_failed",
                                       error_code="host_only_store_symlink_denied")
                    raise DeploymentError("HOST_ONLY_SANDBOX_SYMLINK_DENIED")

            def verify_staged_files() -> None:
                allowed = {member.path for member in package.files}
                observed = set()
                for item in release_root.rglob("*"):
                    if item.is_symlink():
                        raise DeploymentError("HOST_ONLY_STAGED_SYMLINK_DENIED")
                    if item.is_dir():
                        continue
                    if not item.is_file():
                        raise DeploymentError("HOST_ONLY_STAGED_SPECIAL_FILE_DENIED")
                    relative = item.relative_to(release_root).as_posix()
                    if relative not in allowed:
                        raise DeploymentError("HOST_ONLY_STAGED_UNDECLARED_FILE")
                    observed.add(relative)
                if observed != allowed:
                    raise DeploymentError("HOST_ONLY_STAGED_FILE_MISSING")
                for member in package.files:
                    path = release_root / member.path
                    if not path.is_file() or path.is_symlink() or path.stat().st_size != member.size:
                        raise DeploymentError("HOST_ONLY_STAGED_FILE_MISSING")
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest != member.sha256:
                        raise DeploymentError("HOST_ONLY_STAGED_SHA256_MISMATCH")

            def save_active(contents: bytes | None) -> None:
                active_path.parent.mkdir(parents=True, exist_ok=True)
                if active_path.is_symlink():
                    raise DeploymentError("HOST_ONLY_ACTIVE_SYMLINK_DENIED")
                if contents is None:
                    active_path.unlink(missing_ok=True)
                else:
                    temporary = active_path.with_name(active_path.name + ".new")
                    if temporary.is_symlink():
                        raise DeploymentError("HOST_ONLY_ACTIVE_TEMP_SYMLINK_DENIED")
                    with temporary.open("wb") as stream:
                        stream.write(contents)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.chmod(temporary, 0o600)
                    os.replace(temporary, active_path)

            try:
                if active_path.is_symlink():
                    raise DeploymentError("HOST_ONLY_ACTIVE_SYMLINK_DENIED")
                if active_path.exists():
                    previous = active_path.read_bytes()
                    prior = json.loads(previous)
                    if (not isinstance(prior, dict) or prior.get("name") != package.name
                            or set(prior) != {"name", "kind", "release_id",
                                              "archive_sha256", "source_commit"}
                            or prior.get("kind") not in contract.PACKAGE_KINDS | {contract.BUNDLE_KIND}
                            or type(prior.get("release_id")) is not str
                            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", prior["release_id"])
                            or type(prior.get("archive_sha256")) is not str
                            or not _HEX64.fullmatch(prior["archive_sha256"])
                            or not prior["release_id"].endswith(prior["archive_sha256"][:16])):
                        raise DeploymentError("HOST_ONLY_PRIOR_RECEIPT_INVALID")
                    prior_root = store / "releases" / package.name / prior["release_id"]
                    if not prior_root.is_dir() or prior_root.is_symlink():
                        raise DeploymentError("HOST_ONLY_PRIOR_RELEASE_NOT_VERIFIED")
                    record.previous_release = prior["release_id"]
                self.journal.write(record, "staging")
                if not release_root.exists():
                    release_root.parent.mkdir(parents=True, exist_ok=True)
                    stage = Path(tempfile.mkdtemp(prefix=".host-only-", dir=release_root.parent))
                    try:
                        with zipfile.ZipFile(request.archive) as archive:
                            # Stage packages in dependency order, rather than
                            # iterating over ZIP/manifest declaration order.
                            for entry in ordered_members:
                                target = stage / entry.path
                                target.parent.mkdir(parents=True, exist_ok=True)
                                with archive.open(entry.path) as src, target.open("wb") as dest:
                                    shutil.copyfileobj(src, dest)
                                target.chmod(0o555 if entry.executable else 0o444)
                        os.replace(stage, release_root)
                    finally:
                        if stage.exists():
                            shutil.rmtree(stage)
                verify_staged_files()
                self.journal.write(record, "staged")
                if inject_failure == "after_stage":
                    raise DeploymentError("HOST_ONLY_INJECTED_STAGE_FAILURE")
                if install_only:
                    self.journal.write(record, "installed")
                    return {
                        "result": "PASS", "transaction": asdict(record),
                        "operation": "install_only", "host_only": True,
                        "release_id": release_id,
                        "package_order": resolution["package_order"],
                        "active_pointer_unchanged": True,
                        "runtime_activation_executed": False,
                        "install_qualified": False,
                        "not_claimed": ["real Z2 install", "FPGA load", "DUT operation"],
                    }
                self.journal.write(record, "activating")
                receipt = json.dumps({
                    "name": package.name, "kind": package.kind, "release_id": release_id,
                    "archive_sha256": package.archive_sha256,
                    "source_commit": package.source_commit,
                }, sort_keys=True).encode()
                save_active(receipt)
                activated = True
                if inject_failure in ("after_activate", "rollback_unknown"):
                    raise DeploymentError("HOST_ONLY_INJECTED_ACTIVATION_FAILURE")
                self.journal.write(record, "health_check")
                verify_staged_files()
                if active_path.read_bytes() != receipt:
                    raise DeploymentError("HOST_ONLY_ACTIVATION_RECEIPT_MISMATCH")
            except Exception as exc:
                try:
                    if inject_failure == "rollback_unknown":
                        raise DeploymentError("HOST_ONLY_INJECTED_ROLLBACK_UNCERTAIN")
                    if activated:
                        save_active(previous)
                        if previous is None:
                            if active_path.exists():
                                raise DeploymentError("HOST_ONLY_ROLLBACK_NOT_VERIFIED")
                        elif active_path.read_bytes() != previous:
                            raise DeploymentError("HOST_ONLY_ROLLBACK_NOT_VERIFIED")
                    self.journal.write(record, "rolled_back",
                                       error_code="host_only_install_rolled_back", error_message=str(exc))
                except Exception as rollback_exc:
                    self.journal.write(record, "recovery_required",
                                       error_code="host_only_rollback_unknown",
                                       error_message=str(rollback_exc))
                raise DeploymentError(f"host-only package transaction failed: {exc}") from exc

            self.journal.write(record, "package_active")
            return {
                "result": "PASS", "transaction": asdict(record),
                **{("bundle" if getattr(package, "schema", None) == contract.BUNDLE_SCHEMA
                    else "package"): {"name": package.name, "kind": package.kind,
                            "version": package.version, "sha256": package.archive_sha256,
                            "purpose": getattr(package, "purpose", None),
                            **({("packages" if package.schema ==
                                 "plasma.ppu.bundle.v3" else "components"): [
                                dict(id=p.id, kind=p.kind, version=p.version,
                                     requires=list(p.requires))
                                for p in package.packages
                            ]} if hasattr(package, "packages") else {"components": []})}},
                "host_only": True, "install_qualified": False,
                "not_claimed": ["real engineering deployment", "FPGA load", "SWPC/Z2 rollout"],
            }

    def _execute_locked(self, request: DeploymentRequest) -> Mapping[str, Any]:
        now = self.clock()
        record = DeploymentRecord(
            schema_version=SCHEMA_VERSION,
            transaction_id=self.transaction_id_factory(),
            state="received",
            sequence=0,
            started_at_epoch_s=now,
            updated_at_epoch_s=now,
            release_artifact=str(request.release_artifact),
            api_transaction_id=request.api_transaction_id,
        )
        self.journal.write(record, "received")

        with tempfile.TemporaryDirectory(prefix="plasma-bootstrap-deploy-") as temporary:
            self.journal.write(record, "verifying")
            try:
                verified = self.installer.verify_release(
                    request.release_artifact,
                    sidecar=request.sidecar,
                    extract_to=Path(temporary) / "verified",
                )
                python_runtime = self.installer.validate_plasma_python(
                    request.plasma_python,
                    product_root=self.paths.product_root,
                )
            except Exception as exc:
                self.journal.write(
                    record,
                    "verify_failed",
                    error_code="verification_failed",
                    error_message=str(exc),
                )
                raise DeploymentError(f"release verification failed: {exc}") from exc

            self.journal.write(
                record,
                "verified",
                release_id=verified.release_id,
                artifact_sha256=verified.archive_sha256,
            )
            installer_paths = self._installer_paths()
            try:
                self.installer._require_target_baseline()
                previous = self.installer._previous_current(installer_paths.current)
                self.journal.write(
                    record,
                    "staging",
                    previous_release=str(previous) if previous is not None else None,
                )
                target = installer_paths.releases_root / verified.release_id
                installer_paths.releases_root.mkdir(parents=True, exist_ok=True)
                self.installer._copy_release(verified, target)
                self.journal.write(record, "staged")

                def health_check(host: str):
                    self.journal.write(record, "health_check")
                    if request.qualification_fail_health_check:
                        raise RuntimeError(QUALIFICATION_HEALTH_FAILURE)
                    return self.installer._health_ready(host)

                if previous is not None:
                    # The upgrade restarts the running Runtime: take its bounded
                    # quiesce (refused while any Site executes) right before
                    # activation so no Job/Package is admitted and then killed.
                    try:
                        (self.runtime_restart_quiesce or quiesce_runtime_for_restart)()
                    except Exception as exc:
                        raise _RuntimeQuiesceDenied(str(exc)) from exc
                self.journal.write(record, "activating")
                evidence = self.installer.install_release(
                    verified,
                    python_runtime=python_runtime,
                    gateway_host=request.gateway_host,
                    paths=installer_paths,
                    ppu_id=request.ppu_id,
                    facility_id=request.facility_id,
                    display_name=request.display_name,
                    health_check=health_check,
                )
            except _RuntimeQuiesceDenied as exc:
                self.journal.write(
                    record, "verify_failed", error_code="runtime_quiesce_denied", error_message=str(exc),
                )
                raise DeploymentError(f"runtime upgrade quiesce denied: {exc}") from exc
            except Exception as exc:
                message = str(exc)
                if "rollback also failed" in message:
                    state = "recovery_required"
                    code = "rollback_failed"
                elif "restored" in message:
                    state = "rolled_back"
                    code = "activation_failed_rolled_back"
                else:
                    state = "recovery_required"
                    code = "deployment_failed"
                self.journal.write(record, state, error_code=code, error_message=message)
                raise DeploymentError(f"deployment failed: {message}") from exc

        self.journal.write(record, "runtime_active")
        return {
            "schema_version": SCHEMA_VERSION,
            "result": "PASS",
            "transaction": asdict(record),
            "installer_evidence": dict(evidence),
            "capabilities": {"fpga_update": False},
            "not_claimed": [
                "FPGA bitstream deployment",
                "PS-to-PL qualification",
                "Site I/O",
                "target power",
                "real IC programming",
                "physical multi-Site concurrency",
            ],
        }


def run_root_bundle_load(asset_set_sha256: str) -> Mapping[str, Any]:
    """Invoke the fixed protected Root Entry: bundle-load <set sha>.

    The Bootstrap service runs with ProtectHome, so the Root Entry and its
    /root tree are invisible here. systemd-run starts the Root Entry as a
    transient root unit outside this sandbox; it receives only the Set SHA.
    Anything that cannot be proven to have stopped before the PL write is
    ``recovery_required``.
    """
    if not _HEX64.fullmatch(asset_set_sha256):
        return {"result": "fpga_load_denied", "code": "ASSET_SET_SHA_INVALID"}
    try:
        entry = ROOT_ENTRY.lstat()
        runner = SYSTEMD_RUN.lstat()
    except OSError:
        return {"result": "fpga_load_denied", "code": "ROOT_ENTRY_NOT_INSTALLED"}
    if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != 0 or entry.st_mode & 0o022
            or not stat.S_ISREG(runner.st_mode) or runner.st_uid != 0):
        return {"result": "fpga_load_denied", "code": "ROOT_ENTRY_NOT_INSTALLED"}
    try:
        completed = subprocess.run(
            root_bundle_load_argv(asset_set_sha256),
            check=False, capture_output=True, text=True,
            timeout=ROOT_BUNDLE_LOAD_TIMEOUT_S + 60,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
        )
    except subprocess.TimeoutExpired:
        return {"result": "recovery_required", "code": "ROOT_ENTRY_TIMEOUT"}
    except OSError as exc:
        return {"result": "fpga_load_denied", "code": "ROOT_ENTRY_EXEC_FAILED:" + type(exc).__name__}
    return classify_root_bundle_load(completed.returncode, completed.stdout, completed.stderr)


def root_bundle_load_argv(asset_set_sha256: str) -> list[str]:
    return [
        str(SYSTEMD_RUN), "--wait", "--pipe", "--collect", "--quiet",
        "--service-type=exec",
        "--property=RuntimeMaxSec=%d" % ROOT_BUNDLE_LOAD_TIMEOUT_S,
        str(ROOT_ENTRY), "bundle-load", asset_set_sha256,
    ]


def classify_root_bundle_load(returncode: int, stdout: str, stderr: str) -> Mapping[str, Any]:
    """Map Root Entry output to a B3 outcome; unknown is never 'denied'."""
    receipts = [line[len("PLASMA_BUNDLE_LOAD="):] for line in stdout.splitlines()
                if line.startswith("PLASMA_BUNDLE_LOAD=")]
    if len(receipts) == 1:
        try:
            outcome = json.loads(receipts[0])
        except ValueError:
            outcome = None
        if (isinstance(outcome, dict)
                and outcome.get("result") in _BUNDLE_LOAD_OUTCOMES
                and (returncode == 0) == (outcome["result"] == "fpga_loaded")
                and returncode in (0, 3)):
            return outcome
        return {"result": "recovery_required", "code": "ROOT_ENTRY_RECEIPT_INVALID"}
    lines = stderr.strip().splitlines()
    if (not receipts and returncode == 2 and lines
            and _PATH2_DENIAL.fullmatch(lines[-1].strip())):
        # The shell Root Entry refused before starting Python: no PL access.
        return {"result": "fpga_load_denied", "code": lines[-1].strip()}
    return {"result": "recovery_required", "code": "ROOT_ENTRY_OUTCOME_UNKNOWN"}


def _load_installer(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("plasma_ppu_z2_installer_for_bootstrap", path)
    if spec is None or spec.loader is None:
        raise DeploymentError(f"cannot load PPU installer: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plasma PPU Bootstrap local deployment engine")
    parser.add_argument(
        "--installer",
        type=Path,
        default=Path(__file__).with_name("ppu-z2-installer.py"),
    )
    parser.add_argument("--bootstrap-state-root", type=Path, default=Path("/var/lib/plasma-bootstrap"))
    parser.add_argument("--product-root", type=Path, default=Path("/opt/plasma"))
    parser.add_argument("--config-root", type=Path, default=Path("/etc/plasma"))
    parser.add_argument("--runtime-state-root", type=Path, default=Path("/var/lib/plasma"))
    parser.add_argument("--log-root", type=Path, default=Path("/var/log/plasma"))
    parser.add_argument("--systemd-root", type=Path, default=Path("/etc/systemd/system"))
    sub = parser.add_subparsers(dest="command", required=True)

    deploy = sub.add_parser("deploy", help="verify, stage, activate and health-check one PPU release")
    deploy.add_argument("--release-artifact", type=Path, required=True)
    deploy.add_argument("--sidecar", type=Path)
    deploy.add_argument("--plasma-python", type=Path, required=True)
    deploy.add_argument("--gateway-host", required=True)
    deploy.add_argument("--ppu-id", required=True)
    deploy.add_argument("--facility-id", required=True)
    deploy.add_argument("--display-name", default="Plasma PPU")
    deploy.add_argument("--api-transaction-id", help="optional Bootstrap API correlation ID; not authority")
    b3 = sub.add_parser("install-bundle", help="B3 canonical v3 Install/Activate or explicit stage_only")
    b3.add_argument("--release-artifact", type=Path, required=True)
    b3.add_argument("--artifact-sha256", required=True)
    b3.add_argument("--platform", required=True)
    b3.add_argument("--board", required=True)
    b3.add_argument("--fpga-part", required=True)
    b3.add_argument("--api-transaction-id", required=True)
    b3.add_argument("--mode", required=True, choices=("activate", "stage_only"))
    b3.add_argument("--fpga-load", action="store_true",
                    help="also load the Bundle's FPGA Image via the protected Root Entry")

    deploy.add_argument(
        "--qualification-fail-health-check",
        action="store_true",
        help=(
            "HIL only: fail the post-activation health check so the real installer must restore "
            "an existing previous release"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = DeploymentPaths(
        bootstrap_state_root=args.bootstrap_state_root,
        product_root=args.product_root,
        config_root=args.config_root,
        runtime_state_root=args.runtime_state_root,
        log_root=args.log_root,
        systemd_root=args.systemd_root,
    )
    installer = _load_installer(args.installer)
    if args.command == "install-bundle":
        request = BundleV3InstallRequest(
            archive=args.release_artifact,
            artifact_sha256=args.artifact_sha256,
            target_profile={
                "platform": args.platform, "board": args.board,
                "fpga_part": args.fpga_part,
            },
            api_transaction_id=args.api_transaction_id,
            mode=args.mode, fpga_load=bool(args.fpga_load),
        )
        try:
            result = DeploymentCoordinator(paths=paths, installer=installer).execute_bundle_v3_install(request)
        except DeploymentError as exc:
            print("ppu-bootstrap-deployment: B3 install denied: " + str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    release_artifact = args.release_artifact.resolve()
    sidecar = (args.sidecar or Path(str(release_artifact) + ".sha256")).resolve()
    request = DeploymentRequest(
        release_artifact=release_artifact,
        sidecar=sidecar,
        plasma_python=args.plasma_python.resolve(),
        gateway_host=args.gateway_host,
        ppu_id=args.ppu_id,
        facility_id=args.facility_id,
        display_name=args.display_name,
        qualification_fail_health_check=bool(args.qualification_fail_health_check),
        api_transaction_id=args.api_transaction_id,
    )
    try:
        result = DeploymentCoordinator(paths=paths, installer=installer).execute(request)
    except DeploymentError as exc:
        print(f"ppu-bootstrap-deployment: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
