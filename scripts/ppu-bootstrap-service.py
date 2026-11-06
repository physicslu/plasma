#!/usr/bin/env python3
"""Authenticated PPU Bootstrap service for Console-managed runtime deployment.

The service is intentionally independent from Plasma Server/Gateway. Read-only
health/status remain available when the product runtime is absent or broken.
All mutation endpoints require a device-local bearer token provisioned outside
the product runtime. Release transport is chunked and bounded so the Manager
never needs a single multi-hundred-megabyte request.

Bearer authentication over HTTP is acceptable only on the explicitly controlled
lab/private commissioning link. Production transport confidentiality and
publisher authenticity are not claimed by this service. Durable deployment API
state fails closed after a service restart so an interrupted deployment cannot
be silently overwritten by a later request.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import importlib.util
import json
import os
import re
import secrets
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
DEPLOYMENT_API_TERMINAL_STATES = {"succeeded", "admitted", "failed", "recovery_required"}
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
    # Factory-Bootstrap-shipped trusted FPGA Image Target/ABI contracts used by
    # B2 static FPGA qualification. Never supplied by a Bundle or HTTP.
    fpga_image_contracts: Path = Path("/opt/plasma/bootstrap/ppu-fpga-image-contracts.json")

    # Root-provisioned lab installation capability, independent of any
    # Bundle name, file SHA or test fixture; NEVER writable via HTTP.
    bundle_install_policy: Path = Path("/opt/plasma/bootstrap/ppu-bundle-install-policy.json")
    deployment_engine_script: Path = Path("/opt/plasma/bootstrap/ppu-bootstrap-deployment.py")
    z2_installer_script: Path = Path("/opt/plasma/bootstrap/ppu-z2-installer.py")

    @property
    def token_file(self) -> Path:
        return self.state_root / "control-token"

    @property
    def uploads_root(self) -> Path:
        return self.state_root / "uploads"

    @property
    def deployment_record(self) -> Path:
        return self.state_root / "deployment-api.json"

    @property
    def coordinator_journal(self) -> Path:
        return self.state_root / "deployment.json"


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


def _valid_token(value: str) -> bool:
    return 32 <= len(value) <= 256 and value.strip() == value and not any(ch.isspace() for ch in value)


def provision_token(path: Path, *, rotate: bool = False, token: str | None = None) -> str:
    if path.exists() and not rotate:
        raise BootstrapServiceError("bootstrap control token already exists; use --rotate explicitly")
    value = token if token is not None else secrets.token_urlsafe(32)
    if not _valid_token(value):
        raise BootstrapServiceError("bootstrap control token must be 32-256 non-whitespace characters")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(value + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)
    return value


def load_token(path: Path) -> str:
    try:
        metadata = path.stat()
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise BootstrapServiceError("bootstrap control token is not provisioned") from exc
    if metadata.st_mode & 0o077:
        raise BootstrapServiceError("bootstrap control token permissions must not allow group/other access")
    if not _valid_token(value):
        raise BootstrapServiceError("bootstrap control token is invalid")
    return value


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
    credential = load_token(paths.token_file)
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
    for script in (paths.deployment_engine_script, paths.z2_installer_script,
                   paths.z2_installer_script.with_name("ppu-z2-installer-core.py")):
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
    ) -> None:
        self.bootstrap_paths = paths
        self.base_module = base_module
        self.deployment_runner = deployment_runner
        self.mutation_lock = threading.RLock()
        self.deployment_thread: threading.Thread | None = None
        self.recovered_deployment = _recover_interrupted_api_deployment(paths)
        super().__init__(address, BootstrapHandler)

    def admit_package(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Receive -> verify -> plan only. NEVER dispatch the runtime Installer.

        Requires an explicit owner ``bundle.admit`` authorization bound to
        this device, the committed upload and its exact SHA256.
        """
        if set(body) != {"kind", "upload_id", "authorization"}:
            raise BootstrapServiceError("PACKAGE_REQUEST_FIELDS_DENIED")
        kind, upload_id = body["kind"], body["upload_id"]
        if type(kind) is not str or kind not in {"python", "native-c", "fpga-image", "bundle"}:
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
            if kind == "bundle":
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
                        contracts_path=self.bootstrap_paths.fpga_image_contracts,
                    )
                except (deployment.BundleV3AdmissionVerificationDenied,
                        deployment.BundleV3AdmissionQualificationDenied) as exc:
                    raise BootstrapServiceError(str(exc)) from exc
                fpga_qualification = plan["fpga_qualification"]
            else:
                # Non-Bundle package admission is outside the Bundle v3
                # consolidation; retain its existing verifier contract.
                contract = _load_script(
                    Path(__file__).with_name("ppu_unified_deployment.py"),
                    "plasma_ppu_package_admission_contract",
                )
                try:
                    verified = contract.verify_host_only_artifact(
                        upload.committed, expected_sha256=meta["sha256"],
                        target_profile=target,
                    )
                except contract.UnifiedDeploymentError as exc:
                    raise BootstrapServiceError(str(exc)) from exc
                if verified.kind != kind:
                    raise BootstrapServiceError("PACKAGE_KIND_MISMATCH")
                fpga_qualification = None
                plan = {
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
                }
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
                    contracts_path=self.bootstrap_paths.fpga_image_contracts,
                )
            except deployment.BundleV3AdmissionVerificationDenied as exc:
                raise BootstrapServiceError("B3_BUNDLE_REVERIFY_DENIED") from exc
            except deployment.BundleV3AdmissionQualificationDenied as exc:
                raise BootstrapServiceError("B3_FPGA_QUALIFICATION_DENIED") from exc
            # Re-qualification must match B2 even when the trusted FPGA
            # contracts change without changing the uploaded archive.
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
        if (type(body) is dict and body.get("kind") == "bundle"
                and ("fpga_load" in body or "mode" in body)):
            return self.start_bundle_install(body)
        if type(body.get("kind")) is str and body["kind"] in {"python", "native-c", "fpga-image", "bundle"}:
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


class BootstrapHandler(BaseHTTPRequestHandler):
    server_version = "PlasmaBootstrap/1"

    @property
    def owner(self) -> BootstrapHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("bootstrap-http " + (fmt % args) + "\n")

    def _json(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        try:
            size = int(raw_length or "0")
        except ValueError as exc:
            raise BootstrapServiceError("invalid Content-Length") from exc
        if size <= 0 or size > MAX_JSON_BODY:
            raise BootstrapServiceError("request body size is invalid")
        raw = self.rfile.read(size)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapServiceError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise BootstrapServiceError("request body must be a JSON object")
        return payload

    def _authorized(self) -> bool:
        try:
            expected = load_token(self.owner.bootstrap_paths.token_file)
        except BootstrapServiceError as exc:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": "control_not_provisioned", "message": str(exc)},
            )
            return False
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        supplied = header[len(prefix):] if header.startswith(prefix) else ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
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
                payload["capabilities"]["runtime_deployment"] = (
                    self.owner.bootstrap_paths.token_file.is_file()
                    and self.owner.bootstrap_paths.kit_tool.is_file()
                )
                factory_files_ready = all(
                    path.is_file() and not path.is_symlink() for path in (
                        self.owner.bootstrap_paths.bundle_install_policy,
                        self.owner.bootstrap_paths.deployment_engine_script,
                        self.owner.bootstrap_paths.z2_installer_script,
                        self.owner.bootstrap_paths.z2_installer_script.with_name(
                            "ppu-z2-installer-core.py"
                        ),
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
                    "control_token_provisioned": self.owner.bootstrap_paths.token_file.is_file(),
                    "transport_confidentiality": "not_qualified",
                    "publisher_authenticity": "not_qualified",
                    "operation_authorization": "plasma.ppu.owner-operation-authorization.v1",
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
        if not self._authorized():
            return
        path = urlparse(self.path).path
        try:
            body = self._body()
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

    provision = sub.add_parser("provision-token")
    provision.add_argument("--rotate", action="store_true")

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
        if args.command == "provision-token":
            token = provision_token(paths.token_file, rotate=args.rotate)
            print(token)
            return 0
        base = _load_script(paths.bootstrap_script, "plasma_ppu_bootstrap_base")
        server = BootstrapHTTPServer((args.host, args.port), paths=paths, base_module=base)
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
