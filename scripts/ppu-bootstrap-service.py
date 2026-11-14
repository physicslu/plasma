#!/usr/bin/env python3
"""Authenticated PPU Bootstrap service for Console-managed runtime deployment.

The service is intentionally independent from Plasma Server/Gateway. Read-only
health/status remain available when the product runtime is absent or broken.
All mutation endpoints require mutual request authentication
(``ppu_bootstrap_request_auth.py``) under the CURRENT controller credential of
``ppu_controller.py`` (LOM-P2A-2 local enrollment: PS-GPIO button, Engineering
CLI or SD rescue ticket); the credential itself never crosses the wire. The
same process serves the Gateway controller admission socket (G13). Release transport is chunked and bounded so the Manager
never needs a single multi-hundred-megabyte request.

Request/response MACs give integrity and mutual credential proof but NOT
confidentiality; plain HTTP remains acceptable only on the explicitly
controlled lab/private commissioning link. Production transport
confidentiality and publisher authenticity are not claimed by this service. Durable deployment API
state fails closed after a service restart so an interrupted deployment cannot
be silently overwritten by a later request.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import hashlib
import hmac
import http.client
import importlib.util
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

API_VERSION = "1"
DEFAULT_PORT = 18081
MAX_JSON_BODY = 2 * 1024 * 1024
MAX_CHUNK_BYTES = 1024 * 1024
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
DEPLOYMENT_API_IN_FLIGHT_STATES = {"queued", "running"}
# ``reconciled``: a ``coordinator_result_unreconciled`` Runtime transaction closed by
# the explicit P0 reconciliation; the original error stays in the record.
DEPLOYMENT_API_TERMINAL_STATES = {"succeeded", "admitted", "failed", "recovery_required",
                                  "reconciled"}
COORDINATOR_SAFE_RESTART_STATES = {
    "runtime_active", "engineering_active", "package_active",
    "bundle_installed", "asset_set_active", "rolled_back", "verify_failed",
    "fpga_loaded", "fpga_load_denied", "fpga_identity_failed",
}
# Coordinator B3 terminal states that are a *known* failure, not uncertainty.
B3_KNOWN_FAILURE_STATES = {"verify_failed", "fpga_load_denied", "fpga_identity_failed"}
MAX_COORDINATOR_JOURNAL_BYTES = 1024 * 1024
# A B2 admission is a short-lived, device-clock transaction. B3 must name the
# CURRENT admission and start within this window; otherwise re-run B2.
B2_ADMISSION_TTL_S = 3600


class BootstrapServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServicePaths:
    product_root: Path = Path("/opt/plasma")
    state_root: Path = Path("/var/lib/plasma-bootstrap")
    machine_id_path: Path = Path("/etc/machine-id")
    bootstrap_script: Path = Path("/opt/plasma/bootstrap/ppu-bootstrap.py")
    kit_tool: Path = Path("/opt/plasma/bootstrap/ppu-bootstrap-kit.py")
    package_target_file: Path = Path("/etc/plasma/ppu-package-target.json")
    # Root-provisioned lab installation capability, independent of any
    # Bundle name, file SHA or test fixture; NEVER writable via HTTP.
    bundle_install_policy: Path = Path("/opt/plasma/bootstrap/ppu-bundle-install-policy.json")
    deployment_engine_script: Path = Path("/opt/plasma/bootstrap/ppu-bootstrap-deployment.py")
    z2_installer_script: Path = Path("/opt/plasma/bootstrap/ppu-z2-installer.py")
    # LOM-P2A-2 controller authority and its read-only safety observation.
    button_profile: Path = Path("/etc/plasma/ppu-enrollment-button.json")
    admission_socket: Path = Path("/run/plasma-bootstrap/controller-admission.sock")
    seal_dir: Path = Path("/var/lib/plasma-site-worker/seals")
    runtime_control_socket: Path = Path("/run/plasma-server/control.sock")
    reload_fence: Path = Path("/run/lock/plasma-mmio.lock")
    site_recovery_script: Path = Path("/opt/plasma/bootstrap/ppu_site_recovery.py")
    # The Runtime Gateway port observed by the P0 reconciliation (read-only).
    gateway_port: int = 18080

    @property
    def uploads_root(self) -> Path:
        return self.state_root / "uploads"

    @property
    def deployment_record(self) -> Path:
        return self.state_root / "deployment-api.json"

    @property
    def coordinator_journal(self) -> Path:
        return self.state_root / "deployment.json"

    @property
    def coordinator_lock(self) -> Path:
        # The SAME flock the Coordinator holds for every transaction.
        return self.state_root / "deployment.lock"

    @property
    def reconciliation_root(self) -> Path:
        return self.state_root / "deployment-reconciliations"


@dataclass(frozen=True)
class UploadPaths:
    meta: Path
    partial: Path
    committed: Path
    sidecar: Path


def _load_script(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise BootstrapServiceError(f"cannot load bootstrap module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _atomic_json(path: Path, payload: Mapping[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapServiceError(f"cannot read bootstrap state {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BootstrapServiceError(f"bootstrap state must be a JSON object: {path}")
    return payload


def _read_private_json(path: Path) -> dict[str, Any]:
    try:
        metadata = path.stat()
    except OSError as exc:
        raise BootstrapServiceError(f"cannot stat bootstrap state {path}: {exc}") from exc
    if metadata.st_mode & 0o077:
        raise BootstrapServiceError(f"bootstrap state permissions are too broad: {path}")
    return _read_json(path)


def _deployment_api_record(paths: ServicePaths) -> dict[str, Any] | None:
    if not paths.deployment_record.exists():
        return None
    record = _read_private_json(paths.deployment_record)
    if record.get("schema_version") != 1:
        raise BootstrapServiceError("deployment API state schema is unsupported")
    transaction_id = record.get("transaction_id")
    upload_id = record.get("upload_id")
    state = record.get("state")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise BootstrapServiceError("deployment API transaction_id is invalid")
    if not isinstance(upload_id, str) or not UPLOAD_ID_RE.fullmatch(upload_id):
        raise BootstrapServiceError("deployment API upload_id is invalid")
    if state not in DEPLOYMENT_API_IN_FLIGHT_STATES | DEPLOYMENT_API_TERMINAL_STATES:
        raise BootstrapServiceError(f"deployment API state is invalid: {state!r}")
    return record


def _read_coordinator_journal(paths: ServicePaths) -> dict[str, Any] | None:
    """Bounded, non-following read of the existing Coordinator's private journal."""
    path = paths.coordinator_journal
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None  # First deployment: the Coordinator has no journal yet.
    except OSError as exc:
        raise BootstrapServiceError("deployment Coordinator journal is unavailable") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                raise BootstrapServiceError("deployment Coordinator journal is not a private regular file")
            try:
                raw = stream.read(MAX_COORDINATOR_JOURNAL_BYTES + 1)
                if len(raw) > MAX_COORDINATOR_JOURNAL_BYTES:
                    raise BootstrapServiceError("deployment Coordinator journal is oversized")
                record = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise BootstrapServiceError("deployment Coordinator journal is unreadable") from exc
    except OSError as exc:
        raise BootstrapServiceError("deployment Coordinator journal is unreadable") from exc
    if (
        not isinstance(record, dict)
        or type(record.get("schema_version")) is not int
        or record["schema_version"] != 1
        or not isinstance(record.get("transaction_id"), str)
        or not record["transaction_id"]
        or type(record.get("sequence")) is not int
        or record["sequence"] < 1
    ):
        raise BootstrapServiceError("deployment Coordinator journal identity is invalid")
    return record


def _admit_coordinator_journal(paths: ServicePaths) -> dict[str, Any] | None:
    """Fail closed before queueing when the *shared* Coordinator is unsafe.

    This is a read-only early rejection, not an API/Coordinator transaction-ID
    reconciliation or a replacement for the Coordinator's exclusive flock.
    The Coordinator independently rechecks the journal under its own lock.
    """
    record = _read_coordinator_journal(paths)
    if record is None:
        return None
    if (
        not isinstance(record.get("state"), str)
        or record["state"] not in COORDINATOR_SAFE_RESTART_STATES
    ):
        raise BootstrapServiceError(
            "previous Coordinator deployment is active, unknown or requires recovery"
        )
    return record


def _reconcile_runtime_result(
    paths: ServicePaths,
    *,
    api_transaction_id: str,
    previous_coordinator_id: str | None,
    runner_result: Mapping[str, Any],
) -> dict[str, str]:
    """Bind an API result to the exact Coordinator transaction under its journal.

    The API ID is written by the existing Coordinator while holding its flock.
    It is only a correlation field, never a Master/Root authorization token.
    """
    if not isinstance(api_transaction_id, str) or not UPLOAD_ID_RE.fullmatch(api_transaction_id):
        raise BootstrapServiceError("deployment API transaction identity is invalid")
    if not isinstance(runner_result, Mapping) or runner_result.get("result") != "PASS":
        raise BootstrapServiceError("deployment runner did not prove success")
    expected_release = runner_result.get("kit_release_id")
    if not isinstance(expected_release, str) or not expected_release:
        raise BootstrapServiceError("deployment runner release identity is missing")
    journal = _read_coordinator_journal(paths)
    if journal is None:
        raise BootstrapServiceError("deployment Coordinator receipt is missing")
    if (
        journal.get("state") != "runtime_active"
        or journal.get("kind") != "ppu-runtime"
        or journal.get("api_transaction_id") != api_transaction_id
        or not isinstance(journal.get("release_id"), str)
        or journal["release_id"] != expected_release
        or journal["transaction_id"] == previous_coordinator_id
    ):
        raise BootstrapServiceError("deployment API and Coordinator result are not reconciled")
    return {
        "api_transaction_id": api_transaction_id,
        "coordinator_transaction_id": journal["transaction_id"],
        "coordinator_release_id": journal["release_id"],
        "coordinator_state": journal["state"],
    }


def _recover_interrupted_api_deployment(paths: ServicePaths) -> dict[str, Any] | None:
    record = _deployment_api_record(paths)
    if record is not None and record.get("state") in DEPLOYMENT_API_IN_FLIGHT_STATES | {"recovery_required"}:
        journal = _read_coordinator_journal(paths)
        if (journal is not None and journal.get("kind") == "bundle"
                and journal.get("api_transaction_id") == record.get("transaction_id")
                and journal.get("asset_activation_previous") is not None
                and journal.get("asset_activation_fpga") is False
                and journal.get("state") in {"activating", "recovery_required", "rolled_back"}):
            # Resume only the already authorized pointer-only transaction.
            # The sole Coordinator rechecks under its lock and Runtime lease;
            # failed or unavailable recovery leaves the API fenced.
            engine = _load_script(Path(__file__).with_name("ppu-bootstrap-deployment.py"),
                                  "plasma_ppu_api_recovery_engine")
            coordinator = engine.DeploymentCoordinator(
                paths=engine.DeploymentPaths(product_root=paths.product_root,
                                             bootstrap_state_root=paths.state_root),
                installer=object(),
            )
            try:
                with coordinator._deployment_lock(recover_assets=True):
                    recovered = coordinator.journal.read()
                    if recovered.state != "rolled_back":
                        raise BootstrapServiceError("ASSET_SET_RECOVERY_NOT_CONFIRMED")
            except Exception:
                pass  # Existing interrupted-service reconciliation below fences it.
            else:
                record.update(state="failed", updated_at_epoch_s=time.time(),
                              error_code="asset_activation_rolled_back",
                              error="Previous Asset Set restored; activation did not succeed",
                              result=None)
                _atomic_json(paths.deployment_record, record)
                return record
    if record is None or record["state"] not in DEPLOYMENT_API_IN_FLIGHT_STATES:
        return record
    interrupted_state = record["state"]
    record["state"] = "recovery_required"
    record["updated_at_epoch_s"] = time.time()
    record["error_code"] = "interrupted_service_restart"
    record["error"] = (
        "PPU Bootstrap restarted while deployment API transaction was "
        f"{interrupted_state}; explicit recovery is required before another deployment"
    )
    record["result"] = None
    _atomic_json(paths.deployment_record, record)
    return record


def _controller_module() -> ModuleType:
    return _load_script(Path(__file__).with_name("ppu_controller.py"), "plasma_ppu_controller")


def current_controller_credential(paths: ServicePaths) -> str:
    """The current controller credential (root-private record), or fail closed.

    Used for the Owner Operation Authorization key; request authentication goes
    through ``EnrollmentEngine`` so mode/generation/rollback are enforced.
    """
    controller = _controller_module()
    store = controller.ControllerStore(paths.state_root)
    try:
        record = store.controller()
        high_water = store.ledger()["high_water"]
    except controller.ControllerError as exc:
        raise BootstrapServiceError(exc.code) from exc
    if record is None:
        raise BootstrapServiceError("CONTROLLER_NOT_ENROLLED")
    if record["generation"] < high_water:
        raise BootstrapServiceError("CONTROLLER_STATE_ROLLBACK")
    return record["credential"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _upload_paths(paths: ServicePaths, upload_id: str) -> UploadPaths:
    if not UPLOAD_ID_RE.fullmatch(upload_id):
        raise BootstrapServiceError("upload_id is invalid")
    root = paths.uploads_root
    committed = root / f"{upload_id}.tar.gz"
    return UploadPaths(
        meta=root / f"{upload_id}.json",
        partial=root / f"{upload_id}.part",
        committed=committed,
        sidecar=Path(str(committed) + ".sha256"),
    )


def create_upload(paths: ServicePaths, *, size: object, sha256: object) -> dict[str, Any]:
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_UPLOAD_BYTES:
        raise BootstrapServiceError(f"size must be an integer in range 1..{MAX_UPLOAD_BYTES}")
    if not isinstance(sha256, str) or not HEX64_RE.fullmatch(sha256.lower()):
        raise BootstrapServiceError("sha256 must be a 64-character hexadecimal digest")
    upload_id = uuid.uuid4().hex
    upload = _upload_paths(paths, upload_id)
    paths.uploads_root.mkdir(parents=True, exist_ok=True)
    fd = os.open(upload.partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    payload = {
        "schema_version": 1,
        "upload_id": upload_id,
        "state": "receiving",
        "size": size,
        "sha256": sha256.lower(),
        "received_bytes": 0,
    }
    _atomic_json(upload.meta, payload)
    return payload


def append_chunk(
    paths: ServicePaths,
    upload_id: str,
    *,
    offset: object,
    data_base64: object,
    sha256: object,
) -> dict[str, Any]:
    upload = _upload_paths(paths, upload_id)
    meta = _read_json(upload.meta)
    if meta.get("state") != "receiving":
        raise BootstrapServiceError("upload is not accepting chunks")
    received = meta.get("received_bytes")
    total = meta.get("size")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset != received:
        raise BootstrapServiceError(f"chunk offset must equal current received_bytes={received}")
    if not isinstance(data_base64, str):
        raise BootstrapServiceError("data_base64 must be a string")
    try:
        data = base64.b64decode(data_base64.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise BootstrapServiceError("chunk data_base64 is invalid") from exc
    if not data or len(data) > MAX_CHUNK_BYTES:
        raise BootstrapServiceError(f"decoded chunk size must be 1..{MAX_CHUNK_BYTES} bytes")
    if not isinstance(sha256, str) or not HEX64_RE.fullmatch(sha256.lower()):
        raise BootstrapServiceError("chunk sha256 is invalid")
    actual = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(actual, sha256.lower()):
        raise BootstrapServiceError("chunk SHA-256 mismatch")
    if not isinstance(total, int) or not isinstance(received, int) or received + len(data) > total:
        raise BootstrapServiceError("chunk exceeds declared upload size")
    with upload.partial.open("ab") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    meta["received_bytes"] = received + len(data)
    _atomic_json(upload.meta, meta)
    return meta


def commit_upload(paths: ServicePaths, upload_id: str) -> dict[str, Any]:
    upload = _upload_paths(paths, upload_id)
    meta = _read_json(upload.meta)
    if meta.get("state") != "receiving":
        raise BootstrapServiceError("upload is not in receiving state")
    if meta.get("received_bytes") != meta.get("size"):
        raise BootstrapServiceError("upload is incomplete")
    expected = meta.get("sha256")
    actual = _sha256(upload.partial)
    if not isinstance(expected, str) or not hmac.compare_digest(actual, expected):
        raise BootstrapServiceError("complete upload SHA-256 mismatch")
    os.replace(upload.partial, upload.committed)
    upload.committed.chmod(0o400)
    upload.sidecar.write_text(f"{actual}  {upload.committed.name}\n", encoding="utf-8")
    upload.sidecar.chmod(0o400)
    meta["state"] = "committed"
    meta["artifact"] = str(upload.committed)
    _atomic_json(upload.meta, meta)
    return meta


def run_deployment_subprocess(
    paths: ServicePaths,
    upload_id: str,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    api_transaction_id = request.get("api_transaction_id")
    if not isinstance(api_transaction_id, str) or not UPLOAD_ID_RE.fullmatch(api_transaction_id):
        raise BootstrapServiceError("internal Bootstrap API transaction identity is missing")
    upload = _upload_paths(paths, upload_id)
    meta = _read_json(upload.meta)
    if meta.get("state") != "committed" or not upload.committed.is_file() or not upload.sidecar.is_file():
        raise BootstrapServiceError("deployment upload is not committed")
    if not paths.kit_tool.is_file():
        raise BootstrapServiceError("PPU bootstrap kit deployment tool is unavailable")
    argv = [
        sys.executable,
        str(paths.kit_tool),
        "deploy",
        str(upload.committed),
        "--sidecar",
        str(upload.sidecar),
        "--gateway-host",
        str(request["gateway_host"]),
        "--ppu-id",
        str(request["ppu_id"]),
        "--facility-id",
        str(request["facility_id"]),
        "--display-name",
        str(request["display_name"]),
        "--product-root",
        str(paths.product_root),
        "--api-transaction-id",
        api_transaction_id,
    ]
    completed = subprocess.run(
        argv,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=1200,
    )
    if completed.returncode != 0:
        tail = completed.stdout[-8000:] if completed.stdout else ""
        raise BootstrapServiceError(f"deployment engine failed with exit {completed.returncode}: {tail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise BootstrapServiceError("deployment engine returned invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("result") != "PASS":
        raise BootstrapServiceError("deployment engine did not return PASS evidence")
    return payload


def _deployment_request(body: Mapping[str, Any]) -> dict[str, str]:
    # Unified API is PS-only until the exact engineering-module adapter is
    # qualified against Bootstrap's single deployment lock/journal, and FPGA
    # Image + Manifest installation is implemented. The current Bootstrap
    # must not feed either type to the PS-only installer.
    kind = body.get("kind", "ppu-runtime")
    if kind == "engineering-module":
        raise BootstrapServiceError("ENGINEERING_INSTALL_NOT_QUALIFIED")
    if kind == "fpga-image":
        raise BootstrapServiceError("FPGA_IMAGE_INSTALL_NOT_QUALIFIED")
    if kind != "ppu-runtime":
        raise BootstrapServiceError("UNKNOWN_DEPLOYMENT_KIND")
    allowed = {"kind", "upload_id", "gateway_host", "ppu_id", "facility_id", "display_name"}
    unexpected = set(body) - allowed
    if unexpected:
        raise BootstrapServiceError(f"unsupported deployment fields: {', '.join(sorted(unexpected))}")
    upload_id = body.get("upload_id")
    if not isinstance(upload_id, str) or not UPLOAD_ID_RE.fullmatch(upload_id):
        raise BootstrapServiceError("deployment upload_id is invalid")
    normalized: dict[str, str] = {"upload_id": upload_id}
    for field in ("gateway_host", "ppu_id", "facility_id", "display_name"):
        value = body.get(field)
        if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
            raise BootstrapServiceError(f"deployment {field} must be a non-empty single-line string")
        normalized[field] = value
    return normalized



def _owner_operation(
    paths: ServicePaths, authorization: object, *, action: str,
    subject_sha256: str, transaction_id: str,
) -> dict[str, Any]:
    """Verify ONE explicit owner operation against device-derived facts.

    The paired credential, device identity, archive SHA256 and transaction
    are all read from this PPU, never from the request carrying the
    authorization. There is no per-Bundle allowlist.
    """
    module = _load_script(
        Path(__file__).with_name("ppu_owner_authorization.py"),
        "plasma_ppu_owner_authorization",
    )
    identity = _load_script(
        Path(__file__).with_name("ppu-bootstrap.py"),
        "plasma_ppu_bootstrap_device_identity",
    )
    try:
        device_id = identity._machine_device_id(paths.machine_id_path)
    except Exception as exc:
        raise BootstrapServiceError("OWNER_AUTHORIZATION_DEVICE_IDENTITY_UNAVAILABLE") from exc
    credential = current_controller_credential(paths)
    try:
        return module.verify(
            authorization, credential=credential, action=action,
            device_id=device_id, subject_sha256=subject_sha256,
            transaction_id=transaction_id,
        )
    except module.OwnerAuthorizationDenied as exc:
        raise BootstrapServiceError(str(exc)) from exc


def _trusted_package_target(paths: ServicePaths) -> dict[str, str]:
    """Local PPU target identity, not data accepted from the uploaded manifest."""
    path = paths.package_target_file
    if path.is_symlink():
        raise BootstrapServiceError("PACKAGE_TARGET_PROFILE_UNTRUSTED")
    try:
        info = path.stat()
    except OSError as exc:
        raise BootstrapServiceError("PACKAGE_TARGET_PROFILE_UNAVAILABLE") from exc
    if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
            or info.st_uid != os.geteuid()):
        raise BootstrapServiceError("PACKAGE_TARGET_PROFILE_UNTRUSTED")
    profile = _read_private_json(path)
    if (set(profile) != {"platform", "board", "fpga_part"}
            or any(type(value) is not str for value in profile.values())):
        raise BootstrapServiceError("PACKAGE_TARGET_PROFILE_INVALID")
    return profile



def _trusted_b3_install_policy(paths: ServicePaths) -> dict[str, Any]:
    """Device-local generic B3 enablement, not publisher authentication.

    Generic, Bundle-independent device capability (no per-Bundle SHA list).
    Each B3 additionally needs a fresh mode-specific owner ``bundle.install`` /
    ``bundle.activate`` / ``bundle.activate-fpga-load`` authorization for
    the exact admitted Bundle. B3 never permits Package execution or DUT
    operation; FPGA load still passes the protected Root Entry.
    """
    path = paths.bundle_install_policy
    if path.is_symlink():
        raise BootstrapServiceError("B3_INSTALL_POLICY_UNTRUSTED")
    try:
        info = path.stat()
    except OSError as exc:
        raise BootstrapServiceError("B3_INSTALL_POLICY_NOT_INSTALLED") from exc
    if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
            or info.st_uid != os.geteuid()):
        raise BootstrapServiceError("B3_INSTALL_POLICY_UNTRUSTED")
    policy = _read_private_json(path)
    if (set(policy) != {"schema", "mode", "modes", "actions"}
            or policy.get("schema") != "plasma.ppu.b3-install-policy.v2"
            or policy.get("mode") != "development"
            or policy.get("modes") != ["activate", "stage_only"]
            or policy.get("actions") != ["install", "verify"]):
        raise BootstrapServiceError("B3_INSTALL_POLICY_INVALID")
    return policy


def run_bundle_install_subprocess(
    paths: ServicePaths,
    upload_id: str,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Same existing Deployment Engine CLI, no second writer or daemon."""
    identity = request.get("api_transaction_id")
    if type(identity) is not str or not UPLOAD_ID_RE.fullmatch(identity):
        raise BootstrapServiceError("B3_CORRELATION_ID_INVALID")
    upload = _upload_paths(paths, upload_id)
    for script in (paths.deployment_engine_script, paths.z2_installer_script):
        if script.is_symlink() or not script.is_file():
            raise BootstrapServiceError("B3_INSTALLED_ENGINE_NOT_QUALIFIED")
    _trusted_b3_install_policy(paths)
    if (set(request) != {"api_transaction_id", "archive_sha256",
                         "target", "mode", "fpga_load"}
            or request.get("mode") not in ("activate", "stage_only")
            or type(request.get("mode")) is not str
            or (request["mode"] == "stage_only" and request["fpga_load"])
            or type(request.get("fpga_load")) is not bool
            or type(request.get("archive_sha256")) is not str
            or not HEX64_RE.fullmatch(request["archive_sha256"])
            or type(request.get("target")) is not dict
            or request["target"] != _trusted_package_target(paths)):
        raise BootstrapServiceError("B3_INTERNAL_ADMISSION_IDENTITY_DENIED")
    argv = [
        sys.executable, str(paths.deployment_engine_script),
        "--installer", str(paths.z2_installer_script),
        "--bootstrap-state-root", str(paths.state_root),
        "--product-root", str(paths.product_root),
        "install-bundle", "--release-artifact", str(upload.committed),
        "--artifact-sha256", request["archive_sha256"],
        "--platform", request["target"]["platform"],
        "--board", request["target"]["board"],
        "--fpga-part", request["target"]["fpga_part"],
        "--api-transaction-id", identity,
        "--mode", request["mode"],
    ]
    if request["fpga_load"]:
        argv.append("--fpga-load")
    completed = subprocess.run(
        argv, check=False, capture_output=True, text=True,
        # Root bundle-load has its own bounded timeout inside the Coordinator.
        timeout=900 if request["fpga_load"] else 120,
    )
    if completed.returncode != 0:
        # Do not include external process output or raw secrets in API errors.
        raise BootstrapServiceError("B3_DEVICE_INSTALL_SUBPROCESS_FAILED")
    try:
        result = json.loads(completed.stdout)
    except (ValueError, TypeError) as exc:
        raise BootstrapServiceError("B3_DEVICE_INSTALL_RECEIPT_INVALID") from exc
    stage = ("bundle_staged_only" if request["mode"] == "stage_only"
             else "bundle_install_and_fpga_load" if request["fpga_load"]
             else "bundle_install_and_activate")
    active = result.get("active_asset_set") if isinstance(result, dict) else None
    if (type(result) is not dict or result.get("result") != "PASS"
            or result.get("schema") != "plasma.ppu.b3-deployment-receipt.v2"
            or result.get("mode") != request["mode"]
            or result.get("stage") != stage
            or result.get("ready") is not False
            or (active is not None if request["mode"] == "stage_only"
                else not isinstance(active, dict) or active.get("asset_set_sha256") != request["archive_sha256"])
            or result.get("archive_sha256") != request["archive_sha256"]):
        raise BootstrapServiceError("B3_DEVICE_INSTALL_RECEIPT_INVALID")
    return result


def _reconcile_b3_install_result(
    paths: ServicePaths,
    *,
    api_transaction_id: str,
    previous_coordinator_id: str | None,
    runner_result: Mapping[str, Any],
    fpga_load: bool,
    mode: str,
) -> dict[str, str]:
    if (type(api_transaction_id) is not str
            or not UPLOAD_ID_RE.fullmatch(api_transaction_id)
            or mode not in {"activate", "stage_only"}
            or runner_result.get("result") != "PASS"):
        raise BootstrapServiceError("B3_API_CORRELATION_INVALID")
    expected_stage = ("bundle_staged_only" if mode == "stage_only"
                      else "bundle_install_and_fpga_load" if fpga_load
                      else "bundle_install_and_activate")
    active = runner_result.get("active_asset_set")
    if (runner_result.get("mode") != mode
            or runner_result.get("stage") != expected_stage
            or runner_result.get("ready") is not False
            or (active is not None if mode == "stage_only"
                else not isinstance(active, Mapping)
                or active.get("asset_set_sha256") != runner_result.get("archive_sha256"))):
        raise BootstrapServiceError("B3_API_RECEIPT_MODE_MISMATCH")
    record = _read_coordinator_journal(paths)
    digest = runner_result.get("archive_sha256")
    if (record is None
            or record.get("state") != ("bundle_installed" if mode == "stage_only" else
                                       "fpga_loaded" if fpga_load else "asset_set_active")
            or record.get("kind") != "bundle"
            or record.get("artifact_sha256") != digest
            or record.get("api_transaction_id") != api_transaction_id
            or record.get("transaction_id") == previous_coordinator_id
            or record.get("transaction_id") != runner_result.get("transaction", {}).get("transaction_id")):
        raise BootstrapServiceError("B3_COORDINATOR_RECEIPT_UNRECONCILED")
    return {
        "api_transaction_id": api_transaction_id,
        "coordinator_transaction_id": record["transaction_id"],
        "coordinator_release_id": record["release_id"],
        "coordinator_state": record["state"],
    }


def _b3_known_failure(
    paths: ServicePaths, *, api_transaction_id: str,
    previous_coordinator_id: str | None,
) -> dict[str, str] | None:
    """A B3 failure the Coordinator journal proves was a known terminal state.

    fpga_load_denied: PL and Active Set unchanged. fpga_identity_failed: the
    Image stays loaded (no automatic Golden Restore). Anything else remains
    recovery_required.
    """
    try:
        record = _read_coordinator_journal(paths)
    except BootstrapServiceError:
        return None
    if (record is None
            or record.get("kind") != "bundle"
            or record.get("api_transaction_id") != api_transaction_id
            or record.get("transaction_id") == previous_coordinator_id
            or record.get("state") not in B3_KNOWN_FAILURE_STATES):
        return None
    code = record.get("error_code")
    return {
        "coordinator_transaction_id": record["transaction_id"],
        "coordinator_state": record["state"],
        "error_code": code if isinstance(code, str) and code else record["state"],
    }


class BootstrapHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        paths: ServicePaths,
        base_module: ModuleType,
        deployment_runner: Callable[[ServicePaths, str, Mapping[str, Any]], Mapping[str, Any]] = run_deployment_subprocess,
        boot_id: str | None = None,
    ) -> None:
        self.bootstrap_paths = paths
        self.base_module = base_module
        self.deployment_runner = deployment_runner
        self.mutation_lock = threading.RLock()
        self.deployment_thread: threading.Thread | None = None
        self.recovered_deployment = _recover_interrupted_api_deployment(paths)
        self.controller_module = _controller_module()
        self.request_auth = self.controller_module.request_auth
        store = self.controller_module.ControllerStore(paths.state_root)
        store.migrate_legacy_token()      # P2A-1 control-token -> generation 1 (once)
        self.engine = self.controller_module.EnrollmentEngine(
            store, self._safety_probe(), device_id=self._local_device_id(),
            boot_id=self.controller_module.boot_id() if boot_id is None else boot_id,
            log=lambda line: sys.stderr.write(line + "\n"))
        self.nonces = self.engine.request_nonces
        self.button_watcher = None
        self.admission_server = None
        self.reconcile_crash_at: str | None = None   # Host-test crash injection only
        super().__init__(address, BootstrapHandler)

    def _reconcile_point(self, name: str) -> None:
        if name not in RECONCILE_CRASH_POINTS:
            raise ValueError(name)
        if self.reconcile_crash_at == name:
            raise RuntimeError("injected crash at " + name)

    # -- LOM-P2A-2 safety observation (read-only; never modifies records)
    def _safety_probe(self) -> Any:
        paths = self.bootstrap_paths
        return self.controller_module.PPUSafetyProbe(
            seal_dir=paths.seal_dir, runtime_control_socket=paths.runtime_control_socket,
            reload_fence=paths.reload_fence, bootstrap_active=self._bootstrap_active,
            bootstrap_unknown=self._bootstrap_unknown,
            bootstrap_recovery_required=self._bootstrap_recovery_required,
            site_recovery_script=paths.site_recovery_script)

    def _bootstrap_active(self) -> list[str]:
        ops = []
        thread_alive = self.deployment_thread is not None and self.deployment_thread.is_alive()
        try:
            record = _deployment_api_record(self.bootstrap_paths)
        except BootstrapServiceError:
            record = None
        if thread_alive or (record is not None and record["state"] in DEPLOYMENT_API_IN_FLIGHT_STATES):
            ops.append("bootstrap-deployment:" + (record["transaction_id"] if record else "unknown"))
        return ops

    def _bootstrap_unknown(self) -> list[str]:
        try:
            record = _deployment_api_record(self.bootstrap_paths)
        except BootstrapServiceError:
            return ["bootstrap-deployment:record-unreadable"]
        if record is not None and record["state"] == "recovery_required":
            return ["bootstrap-deployment:" + record["transaction_id"]]
        return []

    def _bootstrap_recovery_required(self) -> bool:
        if self.deployment_thread is not None and self.deployment_thread.is_alive():
            return False      # an active deployment defers takeover instead
        try:
            journal = _read_coordinator_journal(self.bootstrap_paths)
        except BootstrapServiceError:
            return True
        return journal is not None and journal.get("state") not in COORDINATOR_SAFE_RESTART_STATES

    def start_controller_services(self) -> None:
        """Admission socket for the Gateway (G13) and, when the board profile
        enables it, the PS-GPIO enrollment button watcher."""
        module = self.controller_module
        try:
            self.admission_server = module.AdmissionServer(self.bootstrap_paths.admission_socket,
                                                           self.engine)
        except OSError as exc:
            # Gateway writes then fail closed (503); Bootstrap recovery stays reachable.
            sys.stderr.write(f"plasma-controller admission socket unavailable: {exc}\n")
        else:
            threading.Thread(target=self.admission_server.serve_forever,
                             name="plasma-controller-admission", daemon=True).start()
        profile_path = self.bootstrap_paths.button_profile
        if not profile_path.exists():
            return
        try:
            profile = module.ButtonProfile.load(profile_path)
            if not profile.enabled:
                sys.stderr.write("plasma-enrollment button disabled: "
                                 f"{profile.disabled_reason or 'board profile'}\n")
                return
            line = module.SysfsGpioInput(profile)
        except Exception as exc:  # never arm on an untrusted/absent profile or line
            sys.stderr.write(f"plasma-enrollment button unavailable: {type(exc).__name__}: {exc}\n")
            return
        self.engine.button_enabled = True
        self.button_watcher = module.ButtonWatcher(self.engine, line, profile)
        self.button_watcher.start()

    def server_close(self) -> None:
        if self.admission_server is not None:
            self.admission_server.shutdown()
            self.admission_server.server_close()
        if self.button_watcher is not None:
            self.button_watcher.stopped.set()
        super().server_close()

    def _local_device_id(self) -> str:
        """Device identity from the sibling factory script (never request data)."""
        identity = _load_script(Path(__file__).with_name("ppu-bootstrap.py"),
                                "plasma_ppu_bootstrap_device_identity")
        try:
            return identity._machine_device_id(self.bootstrap_paths.machine_id_path)
        except Exception as exc:
            raise BootstrapServiceError("bootstrap device identity is unavailable") from exc

    def device_id(self) -> str:
        try:
            return self.base_module._machine_device_id(self.bootstrap_paths.machine_id_path)
        except Exception as exc:
            raise BootstrapServiceError("bootstrap device identity is unavailable") from exc

    def admit_package(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Receive -> verify -> plan only. NEVER dispatch the runtime Installer.

        Requires an explicit owner ``bundle.admit`` authorization bound to
        this device, the committed upload and its exact SHA256.
        """
        if set(body) != {"kind", "upload_id", "authorization"}:
            raise BootstrapServiceError("PACKAGE_REQUEST_FIELDS_DENIED")
        kind, upload_id = body["kind"], body["upload_id"]
        if type(kind) is not str or kind != "bundle":
            raise BootstrapServiceError("PACKAGE_KIND_DENIED")
        if type(upload_id) is not str or not UPLOAD_ID_RE.fullmatch(upload_id):
            raise BootstrapServiceError("PACKAGE_UPLOAD_ID_DENIED")
        with self.mutation_lock:
            if self.deployment_thread is not None and self.deployment_thread.is_alive():
                raise BootstrapServiceError("another deployment is already running")
            previous = _deployment_api_record(self.bootstrap_paths)
            if previous is not None and previous["state"] in DEPLOYMENT_API_IN_FLIGHT_STATES | {"recovery_required"}:
                raise BootstrapServiceError("previous deployment not safe for package admission")
            _admit_coordinator_journal(self.bootstrap_paths)
            upload = _upload_paths(self.bootstrap_paths, upload_id)
            meta = _read_json(upload.meta)
            if (meta.get("state") != "committed"
                    or meta.get("upload_id") != upload_id
                    or type(meta.get("sha256")) is not str
                    or not HEX64_RE.fullmatch(meta["sha256"])):
                raise BootstrapServiceError("PACKAGE_UPLOAD_NOT_COMMITTED")
            owner = _owner_operation(
                self.bootstrap_paths, body["authorization"], action="bundle.admit",
                subject_sha256=meta["sha256"], transaction_id=upload_id,
            )
            target = _trusted_package_target(self.bootstrap_paths)
            # Bundle v3 verification and qualification have ONE domain
            # owner. The API only supplies trusted upload/owner context.
            deployment = _load_script(
                Path(__file__).with_name("ppu-bootstrap-deployment.py"),
                "plasma_ppu_b2_deployment_engine",
            )
            try:
                plan = deployment.DeploymentCoordinator.qualify_bundle_v3_admission(
                    upload.committed, expected_sha256=meta["sha256"],
                    target_profile=target,
                )
            except (deployment.BundleV3AdmissionVerificationDenied,
                    deployment.BundleV3AdmissionQualificationDenied) as exc:
                raise BootstrapServiceError(str(exc)) from exc
            fpga_qualification = plan["fpga_qualification"]
            if plan["archive_sha256"] != owner["subject_sha256"]:
                raise BootstrapServiceError("OWNER_AUTHORIZATION_SUBJECT_MISMATCH")
            plan["owner_authorization"] = owner
            transaction_id = uuid.uuid4().hex
            now = time.time()
            record = {
                "schema_version": 1,
                "transaction_id": transaction_id,
                "state": "admitted",
                "upload_id": upload_id,
                "started_at_epoch_s": now,
                "updated_at_epoch_s": now,
                "error_code": None,
                "error": None,
                "result": {
                    "result": "PASS",
                    "stage": "package_admission_only",
                    "owner_authorized": True,
                    "fpga_static_qualification": (
                        "NOT_APPLICABLE" if fpga_qualification is None
                        else fpga_qualification["result"]),
                    # B2 PASS is NOT execution, FPGA load or Identity readback.
                    "fpga_loaded": False,
                    "identity_readback": "NOT_RUN",
                    "install_qualified": False,
                    "plan": plan,
                },
            }
            _atomic_json(self.bootstrap_paths.deployment_record, record)
            return record

    def start_bundle_install(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """B3 only for the CURRENT B2 admission and a fresh owner install action."""
        if (type(body) is not dict
                or set(body) != {"kind", "upload_id", "mode", "fpga_load", "authorization"}
                or body["kind"] != "bundle" or type(body["fpga_load"]) is not bool
                or type(body["mode"]) is not str or body["mode"] not in {"activate", "stage_only"}
                or (body["mode"] == "stage_only" and body["fpga_load"])):
            raise BootstrapServiceError("B3_INSTALL_REQUEST_FIELDS_DENIED")
        fpga_load = body["fpga_load"]
        mode = body["mode"]
        upload_id = body["upload_id"]
        if type(upload_id) is not str or not UPLOAD_ID_RE.fullmatch(upload_id):
            raise BootstrapServiceError("B3_UPLOAD_ID_INVALID")
        with self.mutation_lock:
            if self.deployment_thread is not None and self.deployment_thread.is_alive():
                raise BootstrapServiceError("B3_DEPLOYMENT_ALREADY_RUNNING")
            earlier = _deployment_api_record(self.bootstrap_paths)
            if (earlier is None or earlier.get("state") != "admitted"
                    or earlier.get("upload_id") != upload_id):
                raise BootstrapServiceError("B3_MATCHING_B2_ADMISSION_REQUIRED")
            admitted_at = earlier.get("started_at_epoch_s")
            age = time.time() - admitted_at if type(admitted_at) in (int, float) else -1
            if not 0 <= age <= B2_ADMISSION_TTL_S:
                raise BootstrapServiceError("B3_B2_ADMISSION_EXPIRED")
            result = earlier.get("result")
            plan = result.get("plan") if type(result) is dict else None
            policy = _trusted_b3_install_policy(self.bootstrap_paths)
            trusted_target = _trusted_package_target(self.bootstrap_paths)
            if (type(plan) is not dict
                    or result.get("stage") != "package_admission_only"
                    or plan.get("bundle_schema") != "plasma.ppu.bundle.v3"
                    or plan.get("kind") != "bundle"
                    or type(plan.get("archive_sha256")) is not str
                    or not HEX64_RE.fullmatch(plan["archive_sha256"])
                    or type(plan.get("packages")) is not list
                    or not plan["packages"]
                    or plan.get("target") != trusted_target
                    or plan.get("requested_actions") != policy["actions"]
                    or result.get("owner_authorized") is not True
                    or type(plan.get("owner_authorization")) is not dict
                    or plan["owner_authorization"].get("subject_sha256") != plan["archive_sha256"]):
                raise BootstrapServiceError("B3_ADMISSION_NOT_QUALIFIED")
            upload = _upload_paths(self.bootstrap_paths, upload_id)
            metadata = _read_json(upload.meta)
            if (metadata.get("state") != "committed"
                    or metadata.get("upload_id") != upload_id
                    or metadata.get("sha256") != plan["archive_sha256"]
                    or not upload.committed.is_file()
                    or upload.committed.is_symlink()
                    or _sha256(upload.committed) != plan["archive_sha256"]):
                raise BootstrapServiceError("B3_UPLOADED_ARCHIVE_CHANGED")
            # A fresh, B3-specific owner authorization bound to THIS device,
            # these exact bytes and the CURRENT B2 transaction. The B2 receipt
            # is never accepted as install authority.
            owner = _owner_operation(
                self.bootstrap_paths, body["authorization"],
                action=("bundle.activate-fpga-load" if fpga_load else
                        "bundle.activate" if mode == "activate" else "bundle.install"),
                subject_sha256=plan["archive_sha256"],
                transaction_id=earlier["transaction_id"],
            )
            deployment = _load_script(
                Path(__file__).with_name("ppu-bootstrap-deployment.py"),
                "plasma_ppu_b3_deployment_engine",
            )
            try:
                reverified_plan = deployment.DeploymentCoordinator.qualify_bundle_v3_admission(
                    upload.committed, expected_sha256=plan["archive_sha256"],
                    target_profile=trusted_target,
                )
            except deployment.BundleV3AdmissionVerificationDenied as exc:
                raise BootstrapServiceError("B3_BUNDLE_REVERIFY_DENIED") from exc
            except deployment.BundleV3AdmissionQualificationDenied as exc:
                raise BootstrapServiceError("B3_FPGA_QUALIFICATION_DENIED") from exc
            # Re-qualification must match B2 for the exact uploaded archive.
            if ("fpga_qualification" not in plan or
                    plan["fpga_qualification"] != reverified_plan["fpga_qualification"]):
                raise BootstrapServiceError("B3_FPGA_QUALIFICATION_CHANGED")
            has_fpga_image = any(
                type(item) is dict and item.get("kind") == "fpga-image"
                for item in plan["packages"])
            if fpga_load and not has_fpga_image:
                raise BootstrapServiceError("B3_FPGA_LOAD_REQUIRES_FPGA_IMAGE")
            if mode == "activate" and has_fpga_image and not fpga_load:
                raise BootstrapServiceError("B3_FPGA_ACTIVATION_REQUIRES_EXPLICIT_LOAD")
            if mode not in policy["modes"]:
                raise BootstrapServiceError("B3_MODE_POLICY_DENIED")
            previous_coordinator = _admit_coordinator_journal(self.bootstrap_paths)
            transaction_id = uuid.uuid4().hex
            record = {
                "schema_version": 1, "transaction_id": transaction_id,
                "state": "queued", "upload_id": upload_id,
                "started_at_epoch_s": time.time(),
                "updated_at_epoch_s": time.time(),
                "error_code": None, "error": None, "result": None,
                "mode": mode, "fpga_load": fpga_load,
                "admission_transaction_id": earlier["transaction_id"],
                "owner_authorization": owner,
            }
            _atomic_json(self.bootstrap_paths.deployment_record, record)
            previous_id = previous_coordinator["transaction_id"] if previous_coordinator else None

            def worker() -> None:
                record["state"] = "running"
                record["updated_at_epoch_s"] = time.time()
                _atomic_json(self.bootstrap_paths.deployment_record, record)
                try:
                    runner = getattr(self, "bundle_install_runner", run_bundle_install_subprocess)
                    evidence = dict(runner(
                        self.bootstrap_paths, upload_id,
                        {"api_transaction_id": transaction_id,
                         "archive_sha256": plan["archive_sha256"],
                         "target": dict(trusted_target),
                         "mode": mode, "fpga_load": fpga_load},
                    ))
                    correlation = _reconcile_b3_install_result(
                        self.bootstrap_paths, api_transaction_id=transaction_id,
                        previous_coordinator_id=previous_id,
                        runner_result=evidence, fpga_load=fpga_load,
                        mode=mode,
                    )
                except Exception as exc:
                    known = _b3_known_failure(
                        self.bootstrap_paths, api_transaction_id=transaction_id,
                        previous_coordinator_id=previous_id,
                    )
                    if known is not None:
                        record["state"] = "failed"
                        record["error_code"] = known["error_code"]
                        record["error"] = known["coordinator_state"]
                        record["result"] = {"result": "FAIL", "coordinator_receipt": known}
                    else:
                        record["state"] = "recovery_required"
                        record["error_code"] = "b3_install_outcome_unreconciled"
                        record["error"] = type(exc).__name__
                        record["result"] = None
                else:
                    record["state"] = "succeeded"
                    record["result"] = {**evidence, "coordinator_receipt": correlation}
                record["updated_at_epoch_s"] = time.time()
                _atomic_json(self.bootstrap_paths.deployment_record, record)

            self.deployment_thread = threading.Thread(
                target=worker, name="plasma-bootstrap-deploy", daemon=True,
            )
            self.deployment_thread.start()
            return record

    def start_deployment(self, body: Mapping[str, Any]) -> dict[str, Any]:
        if type(body) is dict and body.get("kind") == "bundle":
            if "fpga_load" in body or "mode" in body:
                return self.start_bundle_install(body)
            return self.admit_package(body)
        request = _deployment_request(body)
        upload_id = request["upload_id"]
        upload = _upload_paths(self.bootstrap_paths, upload_id)
        meta = _read_json(upload.meta)
        if meta.get("state") != "committed":
            raise BootstrapServiceError("deployment upload is not committed")
        with self.mutation_lock:
            if self.deployment_thread is not None and self.deployment_thread.is_alive():
                raise BootstrapServiceError("another deployment is already running")
            existing = _deployment_api_record(self.bootstrap_paths)
            if existing is not None and existing["state"] in DEPLOYMENT_API_IN_FLIGHT_STATES:
                existing = _recover_interrupted_api_deployment(self.bootstrap_paths)
            if existing is not None and existing["state"] == "recovery_required":
                raise BootstrapServiceError(
                    "previous deployment requires explicit recovery before another deployment"
                )
            previous_coordinator = _admit_coordinator_journal(self.bootstrap_paths)
            transaction_id = uuid.uuid4().hex
            record = {
                "schema_version": 1,
                "transaction_id": transaction_id,
                "state": "queued",
                "upload_id": upload_id,
                "started_at_epoch_s": time.time(),
                "updated_at_epoch_s": time.time(),
                "error_code": None,
                "error": None,
                "result": None,
            }
            _atomic_json(self.bootstrap_paths.deployment_record, record)

            def worker() -> None:
                record["state"] = "running"
                record["updated_at_epoch_s"] = time.time()
                _atomic_json(self.bootstrap_paths.deployment_record, record)
                try:
                    # The public request is strictly normalized before this
                    # internal correlation ID is added; clients cannot choose it.
                    internal_request = {**request, "api_transaction_id": transaction_id}
                    result = dict(self.deployment_runner(self.bootstrap_paths, upload_id, internal_request))
                    receipt = _reconcile_runtime_result(
                        self.bootstrap_paths,
                        api_transaction_id=transaction_id,
                        previous_coordinator_id=(
                            previous_coordinator["transaction_id"] if previous_coordinator else None
                        ),
                        runner_result=result,
                    )
                except Exception as exc:
                    # A failed/ambiguous runner may already have activated a
                    # release. Do not make this transaction retryable without
                    # an authoritative matching Coordinator receipt.
                    record["state"] = "recovery_required"
                    record["error_code"] = "coordinator_result_unreconciled"
                    record["error"] = str(exc)
                    record["result"] = None
                else:
                    record["state"] = "succeeded"
                    record["result"] = {**result, "coordinator_receipt": receipt}
                record["updated_at_epoch_s"] = time.time()
                _atomic_json(self.bootstrap_paths.deployment_record, record)

            self.deployment_thread = threading.Thread(target=worker, name="plasma-bootstrap-deploy", daemon=True)
            self.deployment_thread.start()
            return record


# --- P0: explicit reconciliation of a Runtime deployment that DID activate ----
#
# ``coordinator_result_unreconciled`` means the API worker could not bind the
# runner result to the Coordinator receipt. The release may already be active.
# This operation never re-runs, re-sends or rolls back anything. It re-proves,
# under the API mutation lock AND the Coordinator's own flock, that the exact
# transaction activated and that the Runtime answers a G13-admitted request,
# then appends an evidence record and marks the API record ``reconciled``. The
# original error, the Coordinator journal and every receipt stay untouched.

RECONCILE_ACTION = "runtime.activation.reconcile"
RECONCILE_SCHEMA = "plasma.ppu.deployment-reconciliation.v1"
RECONCILE_ERROR_CODE = "coordinator_result_unreconciled"
RECONCILE_LOOPBACK_TARGET = "/api/engineering/diagnostics/loopback"
RECONCILE_LOOPBACK_MAX_AGE_S = 300.0
MAX_RECONCILE_LOOPBACK_BYTES = 64 * 1024
_GATEWAY_HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\Z")
_COORDINATOR_TX_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_RELEASE_ID_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,127}\Z")
RECONCILE_CRASH_POINTS = ("reconcile.after_evidence_record", "reconcile.after_api_record")


class ReconciliationDenied(BootstrapServiceError):
    """A reconciliation precondition failed. Nothing was written."""

    def __init__(self, code: str, detail: Any = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def _deny(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise ReconciliationDenied(code, detail)


def _file_sha256(path: Path) -> str | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        return hashlib.sha256(stream.read(MAX_COORDINATOR_JOURNAL_BYTES + 1)).hexdigest()


def _gateway_get(host: str, port: int, path: str, timeout_s: float = 5.0) -> tuple[int, Any]:
    connection = http.client.HTTPConnection(host, port, timeout=timeout_s)
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        raw = response.read(65537)
        status = response.status
    finally:
        connection.close()
    if len(raw) > 65536:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return status, None


def _validated_reconcile_request(body: Mapping[str, Any]) -> dict[str, Any]:
    _deny(set(body) == {"action", "transaction_id", "expected", "ps_loopback", "explicit_request"},
          "RECONCILE_REQUEST_FIELDS_DENIED")
    _deny(body["action"] == RECONCILE_ACTION, "RECONCILE_ACTION_DENIED")
    _deny(body["explicit_request"] is True, "RECOVERY_ACTION_NOT_REQUESTED")
    tx = body["transaction_id"]
    _deny(type(tx) is str and UPLOAD_ID_RE.fullmatch(tx) is not None, "RECONCILE_TRANSACTION_INVALID")
    expected = body["expected"]
    _deny(isinstance(expected, dict)
          and set(expected) == {"coordinator_transaction_id", "release_id", "artifact_sha256"},
          "RECONCILE_EXPECTED_FIELDS_DENIED")
    _deny(type(expected["coordinator_transaction_id"]) is str
          and _COORDINATOR_TX_RE.fullmatch(expected["coordinator_transaction_id"]) is not None
          and type(expected["release_id"]) is str
          and _RELEASE_ID_RE.fullmatch(expected["release_id"]) is not None
          and type(expected["artifact_sha256"]) is str
          and HEX64_RE.fullmatch(expected["artifact_sha256"]) is not None,
          "RECONCILE_EXPECTED_INVALID")
    proof = body["ps_loopback"]
    _deny(isinstance(proof, dict) and set(proof) == {"target", "response_base64"}
          and proof["target"] == RECONCILE_LOOPBACK_TARGET
          and type(proof["response_base64"]) is str,
          "RECONCILE_LOOPBACK_PROOF_INVALID")
    try:
        response = base64.b64decode(proof["response_base64"], validate=True)
    except (ValueError, binascii.Error):
        raise ReconciliationDenied("RECONCILE_LOOPBACK_PROOF_INVALID") from None
    _deny(0 < len(response) <= MAX_RECONCILE_LOOPBACK_BYTES, "RECONCILE_LOOPBACK_PROOF_INVALID")
    try:
        payload = json.loads(response.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ReconciliationDenied("RECONCILE_LOOPBACK_PROOF_INVALID") from None
    loopback = payload.get("loopback") if isinstance(payload, dict) else None
    _deny(isinstance(loopback, dict) and payload.get("ok") is True
          and loopback.get("endpoint") == "ps" and loopback.get("source") == "ps"
          and type(loopback.get("tx_crc32")) is str
          and loopback.get("tx_crc32") == loopback.get("rx_crc32"),
          "RECONCILE_LOOPBACK_NOT_PASS")
    return {"transaction_id": tx, "expected": dict(expected), "loopback_response": response}


def reconcile_runtime_activation(server: Any, body: Mapping[str, Any]) -> dict[str, Any]:
    """Close ONE ``coordinator_result_unreconciled`` Runtime transaction.

    Every check below must pass while both locks are held; otherwise a typed
    ``ReconciliationDenied`` is raised and nothing is written.
    """
    request = _validated_reconcile_request(body)
    tx, expected = request["transaction_id"], request["expected"]
    paths: ServicePaths = server.bootstrap_paths
    engine = server.engine
    with server.mutation_lock:
        _deny(server.deployment_thread is None or not server.deployment_thread.is_alive(),
              "RECONCILE_DEPLOYMENT_ACTIVE")
        paths.state_root.mkdir(parents=True, exist_ok=True)
        with paths.coordinator_lock.open("a+b") as lock_stream:
            try:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ReconciliationDenied("RECONCILE_COORDINATOR_ACTIVE") from None
            try:
                return _reconcile_locked(server, paths, engine, tx, expected,
                                         request["loopback_response"])
            finally:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)


def _reconcile_locked(server: Any, paths: ServicePaths, engine: Any, tx: str,
                      expected: Mapping[str, str], loopback_response: bytes) -> dict[str, Any]:
    record_sha = _file_sha256(paths.deployment_record)
    journal_sha = _file_sha256(paths.coordinator_journal)
    # 1. The API record is exactly the unreconciled transaction named.
    try:
        record = _deployment_api_record(paths)
    except BootstrapServiceError as exc:
        raise ReconciliationDenied("RECONCILE_API_RECORD_UNREADABLE") from exc
    _deny(record is not None and record["transaction_id"] == tx, "RECONCILE_TRANSACTION_MISMATCH")
    _deny(record["state"] == "recovery_required" and record.get("error_code") == RECONCILE_ERROR_CODE,
          "RECONCILE_STATE_NOT_ELIGIBLE", {"state": record["state"],
                                           "error_code": record.get("error_code")})
    # 2. The Coordinator receipt names this API transaction and the expected identity.
    try:
        journal = _read_coordinator_journal(paths)
    except BootstrapServiceError as exc:
        raise ReconciliationDenied("RECONCILE_COORDINATOR_JOURNAL_UNREADABLE") from exc
    _deny(journal is not None, "RECONCILE_COORDINATOR_RECEIPT_MISSING")
    _deny(journal.get("api_transaction_id") == tx, "RECONCILE_COORDINATOR_TRANSACTION_MISMATCH")
    _deny(journal.get("kind") == "ppu-runtime" and journal.get("state") == "runtime_active",
          "RECONCILE_COORDINATOR_NOT_RUNTIME_ACTIVE",
          {"kind": journal.get("kind"), "state": journal.get("state")})
    _deny(journal["transaction_id"] == expected["coordinator_transaction_id"]
          and journal.get("release_id") == expected["release_id"]
          and journal.get("artifact_sha256") == expected["artifact_sha256"],
          "RECONCILE_COORDINATOR_IDENTITY_MISMATCH")
    activated_at = journal.get("updated_at_epoch_s")
    _deny(type(activated_at) in (int, float), "RECONCILE_COORDINATOR_RECEIPT_INVALID")
    # 3. The active release and its installer evidence are this release.
    product = paths.product_root
    release_root = product / "releases" / expected["release_id"]
    try:
        current = (product / "current").resolve(strict=True)
        expected_root = release_root.resolve(strict=True)
    except OSError:
        raise ReconciliationDenied("RECONCILE_CURRENT_RELEASE_MISMATCH") from None
    _deny((product / "current").is_symlink() and current == expected_root and current.is_dir(),
          "RECONCILE_CURRENT_RELEASE_MISMATCH")
    try:
        evidence = _read_json(product / "install" / "last-install.json")
    except BootstrapServiceError:
        raise ReconciliationDenied("RECONCILE_INSTALL_EVIDENCE_UNREADABLE") from None
    _deny(evidence.get("result") == "PASS" and evidence.get("release_id") == expected["release_id"]
          and evidence.get("archive_sha256") == expected["artifact_sha256"],
          "RECONCILE_INSTALL_EVIDENCE_MISMATCH")
    gateway_host = evidence.get("gateway_host")
    _deny(type(gateway_host) is str and _GATEWAY_HOST_RE.fullmatch(gateway_host) is not None,
          "RECONCILE_INSTALL_EVIDENCE_MISMATCH")
    # 6. Nothing is running, sealed or otherwise unknown (besides THIS tx).
    probe = engine.probe
    _deny(probe.active_operations() == [], "RECONCILE_ACTIVE_OPERATION", probe.active_operations())
    _deny(probe.seals() == [], "RECONCILE_SITE_SEALED", probe.seals())
    _deny(probe.extra_blockers() == [], "RECONCILE_STATE_UNOBSERVABLE", probe.extra_blockers())
    _deny(probe.unknown_outcomes() == ["bootstrap-deployment:" + tx],
          "RECONCILE_OTHER_UNKNOWN_OUTCOME", probe.unknown_outcomes())
    _deny(not probe.active_set_recovery_required(), "RECONCILE_COORDINATOR_UNSAFE")
    # 4. Bootstrap admission socket, Server (lease) and Gateway are serving, and
    #    the Gateway is bound to THIS controller through the admission socket.
    try:
        socket_ok = stat.S_ISSOCK(os.lstat(paths.admission_socket).st_mode)
    except OSError:
        socket_ok = False
    _deny(server.admission_server is not None and socket_ok, "RECONCILE_ADMISSION_SOCKET_UNAVAILABLE")
    _deny(probe._runtime_lease() == "idle", "RECONCILE_SERVER_NOT_IDLE")
    record_now = engine.controller()
    _deny(record_now is not None, "CONTROLLER_NOT_ENROLLED")
    generation = record_now["generation"]
    try:
        ready_status, ready = _gateway_get(gateway_host, paths.gateway_port, "/api/health/ready")
        challenge_status, challenge = _gateway_get(gateway_host, paths.gateway_port,
                                                   "/api/auth/challenge")
    except OSError:
        raise ReconciliationDenied("RECONCILE_GATEWAY_UNREACHABLE") from None
    _deny(ready_status == 200 and isinstance(ready, dict) and ready.get("gateway") == "alive"
          and ready.get("execution") == "ready", "RECONCILE_GATEWAY_NOT_READY")
    _deny(challenge_status == 200 and isinstance(challenge, dict)
          and challenge.get("device_id") == engine.device_id
          and challenge.get("controller_generation") == generation,
          "RECONCILE_GATEWAY_NOT_BOUND_TO_CONTROLLER")
    # 5. A fresh, PPU-admitted, PPU-MACed PS loopback after the activation.
    response_sha = hashlib.sha256(loopback_response).hexdigest()
    receipt = engine.find_gateway_receipt(
        method="POST", target=RECONCILE_LOOPBACK_TARGET, status=200, body_sha256=response_sha,
        generation=generation, not_before_epoch_s=float(activated_at),
        max_age_s=RECONCILE_LOOPBACK_MAX_AGE_S)
    _deny(receipt is not None, "RECONCILE_LOOPBACK_NOT_ADMITTED")
    # 7. Nothing changed the transaction state while we were checking.
    _deny(_file_sha256(paths.deployment_record) == record_sha
          and _file_sha256(paths.coordinator_journal) == journal_sha,
          "RECONCILE_STATE_CHANGED")
    now = time.time()
    evidence_record = {
        "schema": RECONCILE_SCHEMA,
        "decision": "CONFIRMED_EXECUTED_VERIFIED",
        "api_transaction_id": tx,
        "original_api_record": record,
        "original_api_record_sha256": record_sha,
        "coordinator_journal_sha256": journal_sha,
        "coordinator": {key: journal.get(key) for key in (
            "transaction_id", "kind", "state", "release_id", "artifact_sha256",
            "api_transaction_id", "sequence", "updated_at_epoch_s")},
        "verified": {
            "current_release": str(current), "install_evidence_release_id": evidence["release_id"],
            "install_evidence_archive_sha256": evidence["archive_sha256"],
            "gateway": {"host": gateway_host, "port": paths.gateway_port,
                        "ready": {"gateway": "alive", "execution": "ready"},
                        "challenge_device_id": challenge["device_id"],
                        "challenge_controller_generation": generation},
            "admission_socket": str(paths.admission_socket), "runtime_lease": "idle",
            "active_operations": [], "seals": [],
            "ps_loopback": {"target": RECONCILE_LOOPBACK_TARGET, "status": 200,
                            "response_sha256": response_sha,
                            "admitted_generation": receipt["generation"],
                            "admitted_at_epoch_s": receipt["recorded_at_epoch_s"]},
        },
        "controller_generation": generation,
        "reconciled_at_epoch_s": now,
        "boot_id": engine.boot_id,
    }
    evidence_path = paths.reconciliation_root / f"{tx}.json"
    paths.reconciliation_root.mkdir(mode=0o700, exist_ok=True)
    try:
        existing = _read_private_json(evidence_path) if evidence_path.exists() else None
    except BootstrapServiceError:
        raise ReconciliationDenied("RECONCILE_EVIDENCE_RECORD_UNREADABLE") from None
    if existing is not None:
        # Only a crash after the evidence write may leave one; it must name the
        # same untouched original record. Append-only: never overwritten.
        _deny(existing.get("api_transaction_id") == tx
              and existing.get("original_api_record_sha256") == record_sha,
              "RECONCILE_EVIDENCE_RECORD_CONFLICT")
        evidence_record = existing
    else:
        _atomic_json(evidence_path, evidence_record)
    server._reconcile_point("reconcile.after_evidence_record")
    evidence_sha = _file_sha256(evidence_path)
    engine.find_gateway_receipt(
        method="POST", target=RECONCILE_LOOPBACK_TARGET, status=200, body_sha256=response_sha,
        generation=generation, not_before_epoch_s=float(activated_at),
        max_age_s=RECONCILE_LOOPBACK_MAX_AGE_S, consume=True)
    updated = dict(record)
    # Original error_code/error/result are preserved verbatim; result stays
    # whatever the runner reported (never a fabricated runner success).
    updated["state"] = "reconciled"
    updated["updated_at_epoch_s"] = now
    updated["reconciliation"] = {
        "schema": RECONCILE_SCHEMA,
        "decision": evidence_record["decision"],
        "evidence_record": f"{paths.reconciliation_root.name}/{tx}.json",
        "evidence_record_sha256": evidence_sha,
        "coordinator_transaction_id": journal["transaction_id"],
        "release_id": journal["release_id"],
        "reconciled_at_epoch_s": evidence_record["reconciled_at_epoch_s"],
        "controller_generation": evidence_record["controller_generation"],
    }
    _atomic_json(paths.deployment_record, updated)
    server._reconcile_point("reconcile.after_api_record")
    sys.stderr.write(f"plasma-bootstrap DEPLOYMENT_RECONCILED:{tx}:{journal['transaction_id']}\n")
    return {"deployment": updated, "evidence_record_sha256": evidence_sha}


class BootstrapHandler(BaseHTTPRequestHandler):
    server_version = "PlasmaBootstrap/1"

    @property
    def owner(self) -> BootstrapHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("bootstrap-http " + (fmt % args) + "\n")

    _auth_context: Any = None
    _auth_credential: str | None = None

    def _json(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if self._auth_context is not None and self._auth_credential is not None:
            # Every response to an authenticated request proves this PPU holds
            # the paired credential and binds status/body to that request.
            self.send_header(
                self.owner.request_auth.RESPONSE_HEADER,
                self.owner.request_auth.sign_response(
                    credential=self._auth_credential, context=self._auth_context,
                    status=int(status), body=body,
                ),
            )
        self.end_headers()
        self.wfile.write(body)

    def _raw_body(self) -> bytes:
        raw_length = self.headers.get("Content-Length")
        try:
            size = int(raw_length or "0")
        except ValueError as exc:
            raise BootstrapServiceError("invalid Content-Length") from exc
        if size <= 0 or size > MAX_JSON_BODY:
            raise BootstrapServiceError("request body size is invalid")
        return self.rfile.read(size)

    def _body(self, raw: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapServiceError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise BootstrapServiceError("request body must be a JSON object")
        return payload

    _fence_held = False

    def _controller_error(self, exc: Any) -> None:
        payload = exc.payload()
        if exc.code == "CONTROLLER_UNAUTHENTICATED":
            # P2A-1 wire contract plus the (non-secret) current generation so a
            # replaced Manager can tell it was revoked.
            payload = {"ok": False, "error": "unauthorized", "code": exc.code,
                       **(exc.detail or {})}
        self._json(exc.http_status, payload)

    def _release_fence(self) -> None:
        if self._fence_held:
            self._fence_held = False
            self.owner.engine.fence.release_shared()

    def _authenticate(
        self, *, required: bool, read_body: bool,
        operation_for: Callable[[bytes | None], str] | None = None,
    ) -> tuple[bool, bytes | None]:
        """Mutual request authentication; returns (proceed, raw body).

        The credential never crosses the wire. Header syntax, device identity
        and the single-use nonce are checked BEFORE the body is read; the MAC
        then binds method, exact request target and body SHA256 under the
        CURRENT controller record (re-read per request), and the operation
        class is checked against the controller mode. On success the
        transition fence is held shared until ``_release_fence`` so no
        takeover can commit while this request is being admitted.
        """
        self._auth_context = self._auth_credential = None  # never carry proof across requests
        header = self.headers.get("Authorization")
        if header is None and not required:
            return True, None          # anonymous read-only discovery
        engine = self.owner.engine
        controller = self.owner.controller_module
        try:
            admitted = engine.admit_header(header)
        except controller.ControllerError as exc:
            self._controller_error(exc)
            return False, None
        # A malformed body is a request rejection (409 by the caller), read
        # under the already-consumed nonce and bounded by MAX_JSON_BODY.
        raw = self._raw_body() if read_body else None
        operation = operation_for(raw) if operation_for is not None else "status.read"
        try:
            engine.fence.acquire_shared()
        except controller.ControllerError as exc:
            self._controller_error(exc)
            return False, None
        self._fence_held = True
        try:
            admission = engine.verify_admitted(
                admitted, method=self.command, target=self.path, operation=operation, body=raw)
        except controller.ControllerError as exc:
            self._release_fence()
            self._controller_error(exc)
            return False, None
        self._auth_context, self._auth_credential = admission.context, admission.credential
        return True, raw

    def _post_operation(self, path: str, raw: bytes | None) -> str:
        """Every authenticated POST maps to exactly one operation class."""
        if path == "/v1/uploads" or re.fullmatch(r"/v1/uploads/[0-9a-f]{32}/(chunks|commit)", path):
            return "bundle.upload"
        if path == "/v1/deployments":
            body = self._body(raw or b"")
            if body.get("kind") == "bundle":
                if "fpga_load" in body or "mode" in body:
                    return "fpga.load" if body.get("fpga_load") is True else "bundle.install"
                return "bundle.admit"
            return "runtime.deploy"
        if path == "/v1/deployment/reconcile":
            return "deployment.reconcile"
        if path == "/v1/controller/recovery":
            action = self._body(raw or b"").get("action")
            if action in {"site.diagnose", "site.recover", "outcome.reconcile", "recovery.complete"}:
                return action
        return "unclassified"

    def _small_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        try:
            size = int(raw_length or "0")
        except ValueError as exc:
            raise BootstrapServiceError("invalid Content-Length") from exc
        if size <= 0 or size > 4096:
            raise BootstrapServiceError("request body size is invalid")
        return self._body(self.rfile.read(size))

    def _enrollment_post(self, path: str) -> None:
        """Anonymous, inert-unless-armed enrollment exchange (P2A-0 §5, §3.1)."""
        engine = self.owner.engine
        controller = self.owner.controller_module
        try:
            body = self._small_body()
            now = controller.boot_clock()
            if path == "/v1/enrollment/button-request":
                self._json(HTTPStatus.OK, {"ok": True, **engine.button_request(body, now)})
            else:
                self._json(HTTPStatus.OK, {"ok": True, **engine.claim(body, now)})
        except controller.ControllerError as exc:
            self._controller_error(exc)
        except BootstrapServiceError as exc:
            self._json(HTTPStatus.BAD_REQUEST,
                       {"ok": False, "error": "enrollment_request_invalid", "message": str(exc)})

    def _recovery_action(self, body: Mapping[str, Any]) -> None:
        """Explicit RECOVERY_ONLY actions (P2A-0 §7). The engine re-checks the
        credential and takes the fence itself, so the admission hold is released."""
        self._release_fence()
        engine = self.owner.engine
        credential = self._auth_credential
        explicit = body.get("explicit_request") is True
        action = body.get("action")
        site = body.get("site")
        if action in {"site.diagnose", "site.recover"} and (type(site) is not int or site < 1):
            raise BootstrapServiceError("recovery site must be a positive integer")
        try:
            if action == "site.diagnose":
                result = engine.diagnose_site(credential, site, explicit_request=explicit)
            elif action == "site.recover":
                generation = (engine.controller() or {}).get("generation")
                result = engine.recover_site(credential, site, explicit_request=explicit,
                                             operator=f"controller-generation-{generation}")
            elif action == "outcome.reconcile":
                result = engine.reconcile(
                    credential, str(body.get("transaction")), str(body.get("decision")),
                    body.get("evidence"), explicit_request=explicit)
            else:
                result = {"mode": engine.recovery_complete(
                    credential, observed_device_id=str(body.get("observed_device_id")))}
        except self.owner.controller_module.ControllerError as exc:
            self._controller_error(exc)      # MACed: this request was authenticated
            return
        except ValueError as exc:
            raise BootstrapServiceError(str(exc)) from exc
        self._json(HTTPStatus.OK, {"ok": True, "action": action, "result": result})

    def do_GET(self) -> None:  # noqa: N802
        self._auth_context = self._auth_credential = None
        path = urlparse(self.path).path
        if path == self.owner.request_auth.CHALLENGE_PATH and self.path == path:
            # P2A-1 challenge + current controller generation (LOM-P2A-2 §5.5).
            self._json(HTTPStatus.OK, self.owner.engine.auth_challenge())
            return
        if path == "/v1/enrollment/challenge" and self.path == path:
            controller = self.owner.controller_module
            try:
                self._json(HTTPStatus.OK, {
                    "ok": True, **self.owner.engine.challenge(controller.boot_clock())})
            except controller.ControllerError as exc:
                self._controller_error(exc)
            return
        if path in {"/v1/status", "/v1/assets", "/v1/deployment"}:
            # Read-only discovery stays anonymous; an authenticated read is
            # MACed so a client can trust the paired device's own status.
            proceed, _raw = self._authenticate(required=False, read_body=False)
            self._release_fence()       # reads need no fence beyond verification
            if not proceed:
                return
        if path == "/v1/assets":
            try:
                deployment = _load_script(
                    Path(__file__).with_name("ppu-bootstrap-deployment.py"),
                    "plasma_ppu_assets_status_engine",
                )
                current = deployment.DeploymentCoordinator(
                    paths=deployment.DeploymentPaths(
                        product_root=self.owner.bootstrap_paths.product_root,
                        bootstrap_state_root=self.owner.bootstrap_paths.state_root),
                    installer=self.owner.base_module,
                ).asset_status()
                self._json(HTTPStatus.OK, {"ok": True, "assets": current})
            except Exception:
                # An untrusted or corrupt pointer must not be returned as
                # matching SHA; otherwise Console could skip a needed update.
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"ok": False, "error": "asset_set_identity_untrusted"},
                )
            return
        if path == "/v1/health":
            self._json(
                HTTPStatus.OK,
                {"ok": True, "service": "plasma-ppu-bootstrap", "api_version": API_VERSION},
            )
            return
        if path == "/v1/status":
            try:
                base_paths = self.owner.base_module.BootstrapPaths(
                    self.owner.bootstrap_paths.product_root,
                    self.owner.bootstrap_paths.state_root,
                    self.owner.bootstrap_paths.machine_id_path,
                )
                payload = self.owner.base_module.status_document(base_paths)
                controller_status = self.owner.engine.public_status(
                    self.owner.controller_module.boot_clock())
                payload["capabilities"]["runtime_deployment"] = (
                    controller_status["controller_state"] in {"NORMAL", "RECOVERY_ONLY"}
                    and self.owner.bootstrap_paths.kit_tool.is_file()
                )
                factory_files_ready = all(
                    path.is_file() and not path.is_symlink() for path in (
                        self.owner.bootstrap_paths.bundle_install_policy,
                        self.owner.bootstrap_paths.deployment_engine_script,
                        self.owner.bootstrap_paths.z2_installer_script,
                    )
                )
                b3_policy = None
                if factory_files_ready:
                    try:
                        b3_policy = _trusted_b3_install_policy(self.owner.bootstrap_paths)
                    except BootstrapServiceError:
                        pass
                payload["capabilities"]["bundle_v3_b3_install"] = b3_policy is not None
                if b3_policy is not None:
                    payload["capabilities"]["bundle_v3_b3_mode"] = b3_policy["mode"]
                payload["security"] = {
                    "controller": controller_status,
                    "local_enrollment": self.owner.controller_module.SCHEMA,
                    "transport_confidentiality": "not_qualified",
                    "publisher_authenticity": "not_qualified",
                    "operation_authorization": "plasma.ppu.owner-operation-authorization.v1",
                    "request_authentication": self.owner.request_auth.SCHEMA,
                }
                payload["deployment"] = _deployment_api_record(self.owner.bootstrap_paths)
                self._json(HTTPStatus.OK, payload)
            except BootstrapServiceError as exc:
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"ok": False, "error": "bootstrap_state_invalid", "message": str(exc)},
                )
            return
        if path == "/v1/deployment":
            try:
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "deployment": _deployment_api_record(self.owner.bootstrap_paths)},
                )
            except BootstrapServiceError as exc:
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"ok": False, "error": "bootstrap_state_invalid", "message": str(exc)},
                )
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        self._auth_context = self._auth_credential = None
        path = urlparse(self.path).path
        if path in {"/v1/enrollment/button-request", "/v1/enrollment/claim"} and self.path == path:
            self._enrollment_post(path)
            return
        try:
            self._do_authenticated_post(path)
        finally:
            self._release_fence()

    def _do_authenticated_post(self, path: str) -> None:
        try:
            proceed, raw = self._authenticate(
                required=True, read_body=True,
                operation_for=lambda raw: self._post_operation(path, raw))
        except BootstrapServiceError as exc:
            self._json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": "bootstrap_request_rejected", "message": str(exc)},
            )
            return
        if not proceed:
            return
        try:
            body = self._body(raw or b"")
            if path == "/v1/controller/recovery":
                self._recovery_action(body)
                return
            if path == "/v1/deployment/reconcile":
                try:
                    result = reconcile_runtime_activation(self.owner, body)
                except ReconciliationDenied as exc:
                    self._json(HTTPStatus.CONFLICT, {
                        "ok": False, "error": "deployment_reconciliation_denied",
                        "code": exc.code, "detail": exc.detail})
                    return
                self._json(HTTPStatus.OK, {"ok": True, "reconciliation": result})
                return
            with self.owner.mutation_lock:
                if path == "/v1/uploads":
                    upload = create_upload(
                        self.owner.bootstrap_paths,
                        size=body.get("size"),
                        sha256=body.get("sha256"),
                    )
                    self._json(HTTPStatus.CREATED, {"ok": True, "upload": upload})
                    return
                match = re.fullmatch(r"/v1/uploads/([0-9a-f]{32})/chunks", path)
                if match:
                    upload = append_chunk(
                        self.owner.bootstrap_paths,
                        match.group(1),
                        offset=body.get("offset"),
                        data_base64=body.get("data_base64"),
                        sha256=body.get("sha256"),
                    )
                    self._json(HTTPStatus.OK, {"ok": True, "upload": upload})
                    return
                match = re.fullmatch(r"/v1/uploads/([0-9a-f]{32})/commit", path)
                if match:
                    upload = commit_upload(self.owner.bootstrap_paths, match.group(1))
                    self._json(HTTPStatus.OK, {"ok": True, "upload": upload})
                    return
            if path == "/v1/deployments":
                record = self.owner.start_deployment(body)
                status = (HTTPStatus.OK if (record.get("result") or {}).get("stage") == "package_admission_only"
                          else HTTPStatus.ACCEPTED)
                self._json(status, {"ok": True, "deployment": record})
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except BootstrapServiceError as exc:
            self._json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": "bootstrap_request_rejected", "message": str(exc)},
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plasma PPU Bootstrap authenticated service")
    parser.add_argument("--product-root", type=Path, default=Path("/opt/plasma"))
    parser.add_argument("--state-root", type=Path, default=Path("/var/lib/plasma-bootstrap"))
    parser.add_argument("--machine-id", type=Path, default=Path("/etc/machine-id"))
    parser.add_argument("--package-target-file", type=Path,
                        default=Path("/etc/plasma/ppu-package-target.json"))
    parser.add_argument(
        "--bootstrap-script",
        type=Path,
        default=Path(__file__).with_name("ppu-bootstrap.py"),
    )
    parser.add_argument(
        "--kit-tool",
        type=Path,
        default=Path(__file__).with_name("ppu-bootstrap-kit.py"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve")
    serve.add_argument("--host", required=True)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = ServicePaths(
        product_root=args.product_root,
        state_root=args.state_root,
        machine_id_path=args.machine_id,
        bootstrap_script=args.bootstrap_script,
        kit_tool=args.kit_tool,
        package_target_file=args.package_target_file,
    )
    try:
        base = _load_script(paths.bootstrap_script, "plasma_ppu_bootstrap_base")
        server = BootstrapHTTPServer((args.host, args.port), paths=paths, base_module=base)
        server.start_controller_services()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except BootstrapServiceError as exc:
        print(f"ppu-bootstrap-service: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
