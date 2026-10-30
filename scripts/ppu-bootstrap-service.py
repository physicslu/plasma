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
import tarfile
import tempfile
import sys
import threading
import time
import uuid
import zipfile
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
DEPLOYMENT_API_TERMINAL_STATES = {"succeeded", "failed", "recovery_required"}
COORDINATOR_SAFE_RESTART_STATES = {
    "runtime_active", "engineering_active", "package_active", "rolled_back", "verify_failed",
}
MAX_COORDINATOR_JOURNAL_BYTES = 1024 * 1024


class BootstrapServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServicePaths:
    product_root: Path = Path("/opt/plasma")
    state_root: Path = Path("/var/lib/plasma-bootstrap")
    machine_id_path: Path = Path("/etc/machine-id")
    bootstrap_script: Path = Path("/opt/plasma/bootstrap/ppu-bootstrap.py")
    kit_tool: Path = Path("/opt/plasma/bootstrap/ppu-bootstrap-kit.py")

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


def _reconcile_package_result(
    paths: ServicePaths, *, api_transaction_id: str,
    previous_coordinator_id: str | None, runner_result: Mapping[str, Any],
    request: Mapping[str, str],
) -> dict[str, str]:
    """Test-only package projection of the same authoritative journal."""
    journal = _read_coordinator_journal(paths)
    transaction = runner_result.get("transaction")
    if (runner_result.get("result") != "PASS" or runner_result.get("host_only") is not True
            or runner_result.get("install_qualified") is not False
            or not isinstance(transaction, Mapping) or journal is None
            or dict(transaction) != journal
            or journal.get("state") != "package_active"
            or journal.get("kind") != "host-only-package"
            or journal.get("package_kind") != request["kind"]
            or journal.get("source_commit") != request["source_commit"]
            or journal.get("publisher") != request["publisher"]
            or journal.get("artifact_sha256") != request["artifact_sha256"]
            or journal.get("api_transaction_id") != api_transaction_id
            or journal["transaction_id"] == previous_coordinator_id
            or not journal.get("release_id")):
        raise BootstrapServiceError("host-only package Coordinator result is not reconciled")
    return {
        "api_transaction_id": api_transaction_id,
        "coordinator_transaction_id": journal["transaction_id"],
        "coordinator_release_id": journal["release_id"],
        "coordinator_state": journal["state"],
        "publisher": request["publisher"],
        "source_commit": request["source_commit"],
        "artifact_sha256": request["artifact_sha256"],
    }


def _recover_interrupted_api_deployment(paths: ServicePaths) -> dict[str, Any] | None:
    record = _deployment_api_record(paths)
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
    # The legacy runtime kit consumes tar.gz, while generic v1 packages are ZIP.
    # Never pass a generic ZIP to the runtime installer just because the upload
    # store currently gives every committed artifact a .tar.gz suffix.
    if zipfile.is_zipfile(upload.committed):
        raise BootstrapServiceError("GENERIC_PACKAGE_RUNTIME_INSTALLER_DENIED")
    # A file extension and upload digest do not prove the runtime archive type.
    # A truncated/corrupted ZIP or arbitrary bytes must not enter the kit tool.
    if not tarfile.is_tarfile(upload.committed):
        raise BootstrapServiceError("RUNTIME_ARCHIVE_FORMAT_INVALID")
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


class BootstrapHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        paths: ServicePaths,
        base_module: ModuleType,
        deployment_runner: Callable[[ServicePaths, str, Mapping[str, Any]], Mapping[str, Any]] = run_deployment_subprocess,
        host_only_package_admission: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        # Test composition only: never selectable by HTTP, CLI or configuration.
        # Admission supplies independently trusted publisher/source identity;
        # the injected runner must hold the programming exclusion through verify.
        if host_only_package_admission is not None:
            root = paths.state_root
            if (deployment_runner is run_deployment_subprocess or root.is_symlink()
                    or not root.is_absolute()
                    or root.resolve() == Path(tempfile.gettempdir()).resolve()
                    or not root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())):
                raise BootstrapServiceError("HOST_ONLY_PACKAGE_COMPOSITION_DENIED")
        self.bootstrap_paths = paths
        self.base_module = base_module
        self.deployment_runner = deployment_runner
        self.host_only_package_admission = host_only_package_admission
        self.mutation_lock = threading.RLock()
        self.deployment_thread: threading.Thread | None = None
        self.recovered_deployment = _recover_interrupted_api_deployment(paths)
        super().__init__(address, BootstrapHandler)

    def start_deployment(self, body: Mapping[str, Any]) -> dict[str, Any]:
        kind = body.get("kind")
        package_request = isinstance(kind, str) and kind in {"native-c", "python", "fpga-image"}
        if package_request and self.host_only_package_admission is not None:
            if set(body) != {"kind", "upload_id"}:
                raise BootstrapServiceError("HOST_ONLY_CALLER_AUTHORITY_DENIED")
            if not isinstance(body["upload_id"], str) or not UPLOAD_ID_RE.fullmatch(body["upload_id"]):
                raise BootstrapServiceError("deployment upload_id is invalid")
            # Never take provenance or target authority from the upload manifest.
            request = dict(self.host_only_package_admission(body))
            if (request.get("kind") != body["kind"]
                    or request.get("upload_id") != body["upload_id"]
                    or not isinstance(request.get("publisher"), str)
                    or not request["publisher"]
                    or type(request.get("source_commit")) is not str
                    or not re.fullmatch(r"[0-9a-f]{40}", request["source_commit"])
                    or type(request.get("artifact_sha256")) is not str
                    or not HEX64_RE.fullmatch(request["artifact_sha256"])):
                raise BootstrapServiceError("HOST_ONLY_PACKAGE_AUTHORITY_INVALID")
        else:
            request = _deployment_request(body)
        upload_id = request["upload_id"]
        upload = _upload_paths(self.bootstrap_paths, upload_id)
        meta = _read_json(upload.meta)
        if meta.get("state") != "committed":
            raise BootstrapServiceError("deployment upload is not committed")
        if package_request and (meta.get("sha256") != request["artifact_sha256"]
                                or _sha256(upload.committed) != request["artifact_sha256"]):
            raise BootstrapServiceError("HOST_ONLY_PACKAGE_UPLOAD_IDENTITY_MISMATCH")
        if package_request:
            contract = _load_script(Path(__file__).with_name("ppu_unified_deployment.py"),
                                    "ppu_bootstrap_package_preflight")
            try:
                package = contract.verify_host_only_package(
                    upload.committed, expected_sha256=request["artifact_sha256"],
                    source_commit=request["source_commit"],
                    target_profile=request.get("target_profile"),
                )
            except ValueError as exc:
                raise BootstrapServiceError(f"host-only package preflight failed: {exc}") from exc
            if package.kind != request["kind"]:
                raise BootstrapServiceError("HOST_ONLY_PACKAGE_KIND_MISMATCH")
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
                    reconcile = _reconcile_package_result if package_request else _reconcile_runtime_result
                    receipt = reconcile(
                        self.bootstrap_paths,
                        api_transaction_id=transaction_id,
                        previous_coordinator_id=(
                            previous_coordinator["transaction_id"] if previous_coordinator else None
                        ),
                        runner_result=result,
                        **({"request": request} if package_request else {}),
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
                payload["security"] = {
                    "control_token_provisioned": self.owner.bootstrap_paths.token_file.is_file(),
                    "transport_confidentiality": "not_qualified",
                    "publisher_authenticity": "not_qualified",
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
                self._json(HTTPStatus.ACCEPTED, {"ok": True, "deployment": record})
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
