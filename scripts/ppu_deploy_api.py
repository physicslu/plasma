"""Bounded SWPC HTTP API transport for the *existing* PPU Bootstrap service.

No SSH, subprocess, Root or devices. For this Gate 1 the adapter is used only
in Host-only mock tests; no production CLI calls it. Engineering / FPGA install
must be rejected BEFORE uploading any bytes until qualified on-device support
and authenticated Master + publisher authorization exist.

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
_TERMINAL = frozenset({"succeeded", "failed", "recovery_required"})
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
        gateway_host: str,
        ppu_id: str,
        facility_id: str,
        display_name: str,
        module: str | None = None,
    ) -> DeploymentSubmission:
        """Fail closed *before network* for engineering/FPGA packages.

        PPU Runtime is also only a client protocol, not an authorization to
        deploy. Caller still needs explicit owner-controlled deployment Gate.
        """
        if kind == "engineering-module":
            raise DeploymentAPIError("ENGINEERING_INSTALL_NOT_QUALIFIED")
        if kind == "fpga-image":
            raise DeploymentAPIError("FPGA_IMAGE_INSTALL_NOT_QUALIFIED")
        if kind != "ppu-runtime" or module is not None:
            raise DeploymentAPIError("API_DEPLOYMENT_KIND_DENIED")
        if not isinstance(upload_id, str) or not _HEX32.fullmatch(upload_id):
            raise DeploymentAPIError("API_UPLOAD_ID_INVALID")
        body = {
            "kind": "ppu-runtime",
            "upload_id": upload_id,
            "gateway_host": gateway_host,
            "ppu_id": ppu_id,
            "facility_id": facility_id,
            "display_name": display_name,
        }
        response = self._call("POST", "/v1/deployments", body)
        receipt = response.get("deployment")
        if not isinstance(receipt, dict):
            raise DeploymentOutcomeUnknown("API_SUBMISSION_RECEIPT_UNKNOWN")
        tx = receipt.get("transaction_id")
        state = receipt.get("state")
        if not isinstance(tx, str) or not _HEX32.fullmatch(tx) or state not in _INFLIGHT:
            raise DeploymentOutcomeUnknown("API_SUBMISSION_RECEIPT_UNKNOWN")
        return DeploymentSubmission(upload_id, tx, state)

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
        return receipt

    def status(self) -> dict[str, Any]:
        return self._call("GET", "/v1/status", None)
