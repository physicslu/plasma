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
from contextlib import contextmanager
import importlib.util
import json
import os
import shutil
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
SAFE_RESTART_STATES = {"runtime_active", "engineering_active", "package_active", "rolled_back", "verify_failed"}
ENGINEERING_MODULES = frozenset({"wordport", "openocd-integration", "abtest"})
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_API_TRANSACTION_ID = re.compile(r"[0-9a-f]{32}\Z")
QUALIFICATION_HEALTH_FAILURE = "qualification-injected post-activation health-check failure"


class DeploymentError(RuntimeError):
    """Raised when a bootstrap deployment transaction cannot complete safely."""


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
class HostOnlyPackageRequest:
    """Never built from HTTP; dry-run target identity comes from a test fixture."""

    archive: Path
    source_commit: str
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


class DeploymentCoordinator:
    def __init__(
        self,
        *,
        paths: DeploymentPaths,
        installer: ModuleType,
        clock: Callable[[], float] = time.time,
        transaction_id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.paths = paths
        self.installer = installer
        self.clock = clock
        self.transaction_id_factory = transaction_id_factory
        self.journal = Journal(paths.journal, clock)

    def _installer_paths(self):
        return self.installer.InstallPaths(
            product_root=self.paths.product_root,
            config_root=self.paths.config_root,
            state_root=self.paths.runtime_state_root,
            log_root=self.paths.log_root,
            systemd_root=self.paths.systemd_root,
        )

    def _admit_previous_transaction(self) -> None:
        previous = self.journal.read()
        if previous is None or previous.state in SAFE_RESTART_STATES:
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
    def _deployment_lock(self):
        """The *same* durable lock for PS Runtime and Engineering plans."""
        self.paths.bootstrap_state_root.mkdir(parents=True, exist_ok=True)
        with self.paths.lock.open("a+b") as lock_stream:
            os.chmod(self.paths.lock, 0o600)
            try:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DeploymentError("another PPU deployment transaction is active") from exc
            try:
                self._admit_previous_transaction()
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

    def execute_authorized_bundle_host_only(
        self,
        request: HostOnlyPackageRequest,
        *,
        trusted_policy: Mapping[str, object],
        trusted_inventory: Mapping[str, Mapping[str, object]],
        now_epoch_s: int,
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
                source_commit=request.source_commit,
                target_profile=request.target_profile,
            )
            if not isinstance(bundle, contract.VerifiedBundle):
                raise contract.UnifiedDeploymentError("BUNDLE_V2_REQUIRED")
            authority = contract.evaluate_host_only_bundle_authority(
                bundle, trusted_policy=trusted_policy, now_epoch_s=now_epoch_s,
            )
            resolution = contract.resolve_host_only_bundle(
                bundle, trusted_inventory=trusted_inventory,
            )
        except contract.UnifiedDeploymentError as exc:
            raise DeploymentError(f"host-only Bundle authorization denied: {exc}") from exc
        receipt = dict(self.execute_package_host_only(
            request, inject_failure=inject_failure,
        ))
        receipt["authorization"] = authority
        receipt["resolution"] = resolution
        receipt["install_qualified"] = False
        return receipt

    def execute_package_host_only(
        self, request: HostOnlyPackageRequest, *, inject_failure: str | None = None,
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
                source_commit=request.source_commit, kind="host-only-package",
            )
            self.journal.write(record, "received")
            try:
                self.journal.write(record, "verifying")
                package = contract.verify_host_only_artifact(
                    request.archive, expected_sha256=request.artifact_sha256,
                    source_commit=request.source_commit, target_profile=request.target_profile,
                )
            except Exception as exc:
                self.journal.write(record, "verify_failed",
                                   error_code="package_verification_failed", error_message=str(exc))
                raise DeploymentError(f"host-only package verification failed: {exc}") from exc
            record.module = package.name
            record.package_kind = package.kind
            record.artifact_sha256 = package.archive_sha256
            self.journal.write(record, "verified")

            # Only a non-production simulation store is mutated; the real
            # /opt/plasma, FPGA Manager and factory recovery are untouched.
            store = self.paths.bootstrap_state_root / "host-only-packages"
            release_id = (f"{package.version}-{package.source_commit[:12]}-"
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
                            or type(prior.get("source_commit")) is not str
                            or not _HEX40.fullmatch(prior["source_commit"])
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
                            for entry in package.files:
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
                "package": {"name": package.name, "kind": package.kind,
                            "version": package.version, "sha256": package.archive_sha256,
                            "purpose": getattr(package, "purpose", None),
                            **({("packages" if package.schema ==
                                 "plasma.ppu.bundle.v3" else "components"): [
                                dict(id=p.id, kind=p.kind, version=p.version,
                                     requires=list(p.requires))
                                for p in package.packages
                            ]} if hasattr(package, "packages") else {"components": []})},
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
