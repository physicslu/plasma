#!/usr/bin/env python3
"""Deterministic local deployment engine for the PPU Bootstrap.

This is the Phase-2 mutation engine.  It is intentionally local-only: no HTTP
mutation endpoint is exposed here.  The later Manager/Console transport must
authenticate and authorize before invoking this engine.

The engine owns transaction state, locking and evidence.  Existing
``ppu-z2-installer.py`` remains the authority for release verification,
immutable release staging, systemd activation, readiness and rollback.
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence

SCHEMA_VERSION = 1
TERMINAL_STATES = {"runtime_active", "rolled_back", "recovery_required", "verify_failed"}


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


class Journal:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self.path = path
        self.clock = clock

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
        temporary.write_text(json.dumps(asdict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, self.path)


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

    def execute(self, request: DeploymentRequest) -> Mapping[str, Any]:
        self.paths.bootstrap_state_root.mkdir(parents=True, exist_ok=True)
        with self.paths.lock.open("a+b") as lock_stream:
            try:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DeploymentError("another PPU deployment transaction is active") from exc
            return self._execute_locked(request)

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
                    # Failure before installer-owned activation rollback can still
                    # leave only an immutable staged release, never a committed
                    # active runtime.  Classify it explicitly rather than claiming
                    # rollback occurred.
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
                "8-Site physical concurrency",
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
    deploy.add_argument("--sidecar", type=Path, required=True)
    deploy.add_argument("--plasma-python", type=Path, required=True)
    deploy.add_argument("--gateway-host", required=True)
    deploy.add_argument("--ppu-id", required=True)
    deploy.add_argument("--facility-id", required=True)
    deploy.add_argument("--display-name", default="Plasma PPU")
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
    request = DeploymentRequest(
        release_artifact=args.release_artifact.resolve(),
        sidecar=args.sidecar.resolve(),
        plasma_python=args.plasma_python.resolve(),
        gateway_host=args.gateway_host,
        ppu_id=args.ppu_id,
        facility_id=args.facility_id,
        display_name=args.display_name,
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
