"""Bounded SWPC HTTP API transport for the *existing* PPU Bootstrap service.

No SSH, subprocess, Root or devices. A generic package may be submitted for
manifest/SHA256 admission only; this never authorizes install or FPGA loading.
Legacy engineering-module installation remains explicitly unqualified.

HTTPS with validated server certificates is required. Today's Bootstrap
service is private commissioning HTTP and not yet production TLS-qualified.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import ssl
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)

_CHUNK_BYTES = 1024 * 1024
_MAX_UPLOAD = 512 * 1024 * 1024
_MAX_JSON = 2 * 1024 * 1024
_HEX32 = re.compile(r"[a-f0-9]{32}\Z")
_HEX64 = re.compile(r"[a-f0-9]{64}\Z")
_TERMINAL = frozenset({"succeeded", "admitted", "failed", "recovery_required"})
_INFLIGHT = frozenset({"queued", "running"})


class DeploymentAPIError(RuntimeError):
    """Fail-closed transport/contract error, never contains a bearer token."""


class DeploymentOutcomeUnknown(DeploymentAPIError):
    """Write or activation outcome is unknown; do not automatically retry."""


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward Authorization to a different URL/origin.
        return None


def _endpoint(url: str) -> str:
    if not isinstance(url, str):
        raise DeploymentAPIError("HTTPS_ENDPOINT_REQUIRED")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or parsed.username is not None
        or parsed.password is not None or not parsed.hostname
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or any(ch in url for ch in ("\r", "\n", "\\"))
    ):
        raise DeploymentAPIError("HTTPS_ENDPOINT_REQUIRED")
    try:
        port = parsed.port
    except ValueError as exc:
        raise DeploymentAPIError("INVALID_HTTPS_PORT") from exc
    if port is not None and not 1 <= port <= 65535:
        raise DeploymentAPIError("INVALID_HTTPS_PORT")
    # RFC1918, public DNS or IPv6 are allowed only with valid TLS certificates.
    # Do not permit URL username/password or HTTP as an implicit fallback.
    return url.rstrip("/")


def _bounded_json(raw: bytes, *, expected: bool = True) -> dict[str, Any]:
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_JSON:
        raise DeploymentAPIError("API_RESPONSE_SIZE_INVALID")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise DeploymentAPIError("API_RESPONSE_JSON_INVALID") from exc
    if not isinstance(obj, dict) or (expected and obj.get("ok") is not True):
        raise DeploymentAPIError("API_RESPONSE_REJECTED")
    return obj


def _valid_package_admission(receipt: Mapping[str, Any], *, kind: str | None = None) -> bool:
    """An admitted package is verified, never installed or executable."""
    result = receipt.get("result")
    if (receipt.get("state") != "admitted"
            or not isinstance(result, dict)
            or result.get("result") != "PASS"
            or result.get("stage") != "package_admission_only"
            or result.get("install_qualified") is not False):
        return False
    plan = result.get("plan")
    valid = (
        isinstance(plan, dict)
        and plan.get("execution_permitted") is False
        and type(plan.get("kind")) is str
        and plan["kind"] in {"python", "native-c", "fpga-image", "bundle"}
        and (kind is None or plan["kind"] == kind)
        and type(plan.get("archive_sha256")) is str
        and _HEX64.fullmatch(plan["archive_sha256"]) is not None
        and isinstance(plan.get("files"), list)
        and isinstance(plan.get("requested_actions"), list)
    )
    if not valid:
        return False
    if plan["kind"] != "bundle":
        return False
    if plan.get("bundle_schema") != "plasma.ppu.bundle.v3" or "components" in plan:
        return False
    packages = plan.get("packages")
    valid = (
        type(plan.get("purpose")) is str and bool(plan["purpose"])
        and type(packages) is list and 1 <= len(packages) <= 32
        and all(isinstance(package, dict)
                and type(package.get("id")) is str and bool(package["id"])
                and type(package.get("kind")) is str and bool(package["kind"])
                and type(package.get("version")) is str and bool(package["version"])
                and type(package.get("requires")) is list
                and type(package.get("files")) is list
                for package in packages)
        and len({package["id"] for package in packages}) == len(packages)
    )
    if not valid:
        return False
    # B2 PASS = Master-authorized source + static Asset qualification only.
    # It is never an FPGA load, Identity readback or execution grant.
    has_fpga = any(package["kind"] == "fpga-image" for package in packages)
    return (
        result.get("source_authorized") is True
        and result.get("fpga_loaded") is False
        and result.get("identity_readback") == "NOT_RUN"
        and result.get("fpga_static_qualification")
        == ("STATIC_QUALIFIED" if has_fpga else "NOT_APPLICABLE")
    )


@dataclass(frozen=True)
class DeploymentSubmission:
    upload_id: str
    transaction_id: str
    state: str


class BootstrapAPIClient:
    """API client only; NOT a PPU authority, installer or Master identity."""

    def __init__(
        self,
        base_url: str,
        bearer_token: str,
        *,
        transport: Callable[[str, str, bytes | None, Mapping[str, str]], tuple[int, bytes]] | None = None,
    ) -> None:
        self.base_url = _endpoint(base_url)
        if (
            not isinstance(bearer_token, str) or len(bearer_token) < 32
            or len(bearer_token) > 512
            or any(ord(ch) < 33 or ord(ch) > 126 for ch in bearer_token)
        ):
            raise DeploymentAPIError("BEARER_CREDENTIAL_NOT_PROVISIONED")
        self._token = bearer_token
        self._transport = transport or self._https

    def _https(
        self, method: str, path: str, payload: bytes | None,
        headers: Mapping[str, str],
    ) -> tuple[int, bytes]:
        opener = build_opener(
            ProxyHandler({}),  # avoid leaking an appliance Bearer token to env-configured proxies
            HTTPSHandler(context=ssl.create_default_context()),
            _RejectRedirect(),
        )
        request = Request(
            self.base_url + path, method=method, data=payload, headers=dict(headers)
        )
        try:
            with opener.open(request, timeout=15) as response:
                raw = response.read(_MAX_JSON + 1)
                return response.status, raw
        except HTTPError as exc:
            # Never echo response headers/body (could contain secrets).
            raise DeploymentAPIError(f"API_HTTP_REJECTED:{exc.code}") from None
        except (URLError, OSError, TimeoutError) as exc:
            raise DeploymentOutcomeUnknown(
                f"API_TRANSPORT_OUTCOME_UNKNOWN:{type(exc).__name__}"
            ) from None

    def _call(self, method: str, path: str, body: Mapping[str, object] | None) -> dict[str, Any]:
        if (
            method not in ("GET", "POST") or not path.startswith("/v1/")
            or ".." in path or "?" in path or "#" in path or "\\" in path
            or "\r" in path or "\n" in path
        ):
            raise DeploymentAPIError("API_METHOD_OR_PATH_DENIED")
        payload = (
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if body is not None else None
        )
        if payload is not None and len(payload) > _MAX_JSON:
            raise DeploymentAPIError("API_REQUEST_TOO_LARGE")
        headers = {
            "Authorization": "Bearer " + self._token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            status, raw = self._transport(method, path, payload, headers)
        except DeploymentAPIError:
            raise
        except Exception as exc:
            raise DeploymentOutcomeUnknown(
                f"API_TRANSPORT_OUTCOME_UNKNOWN:{type(exc).__name__}"
            ) from None
        if status < 200 or status >= 300:
            raise DeploymentAPIError(f"API_HTTP_REJECTED:{status}")
        return _bounded_json(raw)

    def upload(self, archive: bytes) -> str:
        """Reuses existing /v1/uploads chunk protocol with no new server API."""
        if not isinstance(archive, bytes) or not 0 < len(archive) <= _MAX_UPLOAD:
            raise DeploymentAPIError("API_ARCHIVE_SIZE_DENIED")
        uploaded = self._call("POST", "/v1/uploads", {
            "size": len(archive),
            "sha256": hashlib.sha256(archive).hexdigest(),
        }).get("upload")
        if not isinstance(uploaded, dict):
            raise DeploymentAPIError("API_UPLOAD_RECEIPT_INVALID")
        upload_id = uploaded.get("upload_id")
        if not isinstance(upload_id, str) or not _HEX32.fullmatch(upload_id):
            raise DeploymentAPIError("API_UPLOAD_ID_INVALID")
        for offset in range(0, len(archive), _CHUNK_BYTES):
            part = archive[offset : offset + _CHUNK_BYTES]
            receipt = self._call("POST", f"/v1/uploads/{upload_id}/chunks", {
                "offset": offset,
                "data_base64": base64.b64encode(part).decode("ascii"),
                "sha256": hashlib.sha256(part).hexdigest(),
            }).get("upload")
            if (
                not isinstance(receipt, dict)
                or receipt.get("upload_id") != upload_id
                or type(receipt.get("received_bytes")) is not int
                or receipt["received_bytes"] != offset + len(part)
            ):
                raise DeploymentOutcomeUnknown("API_UPLOAD_PROGRESS_UNKNOWN")
        committed = self._call("POST", f"/v1/uploads/{upload_id}/commit", {})
        receipt = committed.get("upload")
        if (
            not isinstance(receipt, dict)
            or receipt.get("state") != "committed"
            or receipt.get("upload_id") != upload_id
            or receipt.get("sha256") != hashlib.sha256(archive).hexdigest()
        ):
            raise DeploymentOutcomeUnknown("API_UPLOAD_COMMIT_UNKNOWN")
        return upload_id

    def submit(
        self,
        *,
        kind: str,
        upload_id: str,
        gateway_host: str | None = None,
        ppu_id: str | None = None,
        facility_id: str | None = None,
        display_name: str | None = None,
        module: str | None = None,
    ) -> DeploymentSubmission:
        """Runtime deploy unchanged; Bundle B2 remains admission-only until install_bundle()."""
        if kind == "engineering-module":
            raise DeploymentAPIError("ENGINEERING_INSTALL_NOT_QUALIFIED")
        if kind not in {"ppu-runtime", "python", "native-c", "fpga-image", "bundle"} or module is not None:
            raise DeploymentAPIError("API_DEPLOYMENT_KIND_DENIED")
        if not isinstance(upload_id, str) or not _HEX32.fullmatch(upload_id):
            raise DeploymentAPIError("API_UPLOAD_ID_INVALID")
        if kind == "ppu-runtime":
            if any(type(value) is not str or not value for value in
                   (gateway_host, ppu_id, facility_id, display_name)):
                raise DeploymentAPIError("API_RUNTIME_IDENTITY_REQUIRED")
            body = {
                "kind": kind, "upload_id": upload_id,
                "gateway_host": gateway_host, "ppu_id": ppu_id,
                "facility_id": facility_id, "display_name": display_name,
            }
        else:
            if any(value is not None for value in
                   (gateway_host, ppu_id, facility_id, display_name)):
                raise DeploymentAPIError("API_GENERIC_CALLER_AUTHORITY_DENIED")
            body = {"kind": kind, "upload_id": upload_id}
        response = self._call("POST", "/v1/deployments", body)
        receipt = response.get("deployment")
        if not isinstance(receipt, dict):
            raise DeploymentOutcomeUnknown("API_SUBMISSION_RECEIPT_UNKNOWN")
        tx, state = receipt.get("transaction_id"), receipt.get("state")
        if not isinstance(tx, str) or not _HEX32.fullmatch(tx):
            raise DeploymentOutcomeUnknown("API_SUBMISSION_RECEIPT_UNKNOWN")
        if kind == "ppu-runtime":
            if state not in _INFLIGHT:
                raise DeploymentOutcomeUnknown("API_SUBMISSION_RECEIPT_UNKNOWN")
        elif not _valid_package_admission(receipt, kind=kind):
            raise DeploymentOutcomeUnknown("API_ADMISSION_RECEIPT_UNKNOWN")
        return DeploymentSubmission(upload_id, tx, state)

    def install_bundle(self, admitted: DeploymentSubmission) -> DeploymentSubmission:
        """Explicit B3 install-only of the EXACT current B2 admitted Bundle.

        No implicit B4 activation, FPGA download or package execution.
        The admission receipt must be read back from the current device; a
        prior arbitrary transaction or locally constructed claim is not an
        install authorization. This method never auto-retries on uncertainty.
        """
        if (not isinstance(admitted, DeploymentSubmission)
                or admitted.state != "admitted"
                or not _HEX32.fullmatch(admitted.upload_id)
                or not _HEX32.fullmatch(admitted.transaction_id)):
            raise DeploymentAPIError("B3_VALID_B2_ADMISSION_REQUIRED")
        b2 = self.deployment_state(admitted.transaction_id)
        result = b2.get("result")
        plan = result.get("plan") if isinstance(result, dict) else None
        if (b2.get("upload_id") != admitted.upload_id
                or not _valid_package_admission(b2, kind="bundle")
                or not isinstance(plan, dict)
                or plan.get("requested_actions") != ["install", "verify"]):
            raise DeploymentOutcomeUnknown("B3_DEVICE_ADMISSION_CHANGED")
        reply = self._call("POST", "/v1/deployments", {
            "kind": "bundle", "upload_id": admitted.upload_id,
            "install_only": True,
        })
        record = reply.get("deployment")
        if (not isinstance(record, dict)
                or record.get("upload_id") != admitted.upload_id
                or type(record.get("transaction_id")) is not str
                or not _HEX32.fullmatch(record["transaction_id"])
                or record.get("transaction_id") == admitted.transaction_id
                or record.get("state") not in _INFLIGHT):
            raise DeploymentOutcomeUnknown("B3_INSTALL_SUBMISSION_UNKNOWN")
        return DeploymentSubmission(
            admitted.upload_id, record["transaction_id"], record["state"],
        )

    def deployment_state(self, transaction_id: str) -> dict[str, Any]:
        """One read, no implicit retries, polling loop or automatic resubmit."""
        if not isinstance(transaction_id, str) or not _HEX32.fullmatch(transaction_id):
            raise DeploymentAPIError("API_TRANSACTION_ID_DENIED")
        receipt = self._call("GET", "/v1/deployment", None).get("deployment")
        if (
            not isinstance(receipt, dict)
            or receipt.get("transaction_id") != transaction_id
            or receipt.get("state") not in _TERMINAL | _INFLIGHT
        ):
            raise DeploymentOutcomeUnknown("API_TRANSACTION_STATE_UNKNOWN")
        if receipt["state"] == "succeeded":
            evidence = receipt.get("result")
            if not isinstance(evidence, dict) or evidence.get("result") != "PASS":
                raise DeploymentOutcomeUnknown("API_SUCCESS_EVIDENCE_MISSING")
        if receipt["state"] == "admitted" and not _valid_package_admission(receipt):
            raise DeploymentOutcomeUnknown("API_ADMISSION_EVIDENCE_MISSING")
        return receipt

    def assets_status(self) -> dict[str, Any]:
        """Read PPU-verified Active Set identity, not local cached metadata."""
        record = self._call("GET", "/v1/assets", None).get("assets")
        if (not isinstance(record, dict)
                or record.get("schema") != "plasma.ppu.active-assets.v1"
                or record.get("state") not in {"EMPTY", "ACTIVE"}
                or record.get("ready") is not False):
            raise DeploymentOutcomeUnknown("ASSET_SET_STATUS_UNTRUSTED")
        if record["state"] == "ACTIVE":
            if (type(record.get("asset_set_sha256")) is not str
                    or not _HEX64.fullmatch(record["asset_set_sha256"])):
                raise DeploymentOutcomeUnknown("ASSET_SET_STATUS_UNTRUSTED")
        elif record.get("asset_set_sha256") is not None:
            raise DeploymentOutcomeUnknown("ASSET_SET_STATUS_UNTRUSTED")
        return record

    def reconcile_bundle_assets(self, archive: bytes) -> dict[str, Any]:
        """Compare whole Bundle SHA; on mismatch explicitly B1 -> B2 -> B3.

        Returns the B3 transaction ID for explicit observation. Does NOT
        activate the Set, load an FPGA, launch a job or claim READY.
        """
        if not isinstance(archive, bytes) or not 0 < len(archive) <= _MAX_UPLOAD:
            raise DeploymentAPIError("ASSET_SET_BUNDLE_INVALID")
        digest = hashlib.sha256(archive).hexdigest()
        active = self.assets_status()
        if active["state"] == "ACTIVE" and active["asset_set_sha256"] == digest:
            return {
                "result": "ALREADY_ACTIVE", "asset_set_sha256": digest,
                "ready": False, "b3": None, "fpga": "NOT_RUN",
            }
        uploaded = self.upload(archive)
        b2 = self.submit(kind="bundle", upload_id=uploaded)
        b3 = self.install_bundle(b2)
        return {
            "result": "B3_INSTALL_QUEUED", "asset_set_sha256": digest,
            "ready": False, "b3": {
                "upload_id": b3.upload_id,
                "transaction_id": b3.transaction_id,
                "state": b3.state,
            }, "fpga": "NOT_RUN",
        }

    def status(self) -> dict[str, Any]:
        return self._call("GET", "/v1/status", None)
