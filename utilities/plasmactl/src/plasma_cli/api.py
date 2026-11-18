"""Manager REST transport. No credentials, no PPU protocol, no hardware access.

Every Manager response is classified exactly once:

* a JSON ``ok: true`` 2xx answer is a result;
* a JSON ``ok: false`` 4xx answer is a definite refusal (nothing was done);
* anything else - network error, timeout, 5xx, oversized or malformed body -
  is ``ManagerUnknown`` for a POST: the request may or may not have taken
  effect, so the caller must reconcile read-only and never resend.
"""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_MAX_BYTES = 8 * 1024 * 1024
HEX32 = re.compile(r"[0-9a-f]{32}\Z")


class FleetError(RuntimeError):
    """A usage, contract or read failure. Nothing was mutated by the CLI."""


class ManagerRefused(FleetError):
    """The Manager answered with a definite 4xx refusal."""

    def __init__(self, status: int, code: str | None, message: str | None):
        super().__init__(f"Manager refused HTTP {status}: {code or 'unknown'}")
        self.status, self.code, self.message = status, code, message


class ManagerUnknown(FleetError):
    """The outcome of this POST is unknown. Reconcile; never resend."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _origin(url: str, timeout: float) -> str:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or not 0 < timeout <= 60
        ):
            raise ValueError("invalid Manager base URL or timeout")
        parsed.port  # Reject invalid port syntax.
    except ValueError as exc:
        raise FleetError("Manager URL must be an HTTP(S) origin without credentials") from exc
    return url.rstrip("/")


def _decode(data: bytes) -> dict | None:
    if len(data) > _MAX_BYTES:
        return None
    try:
        body = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


def manager_call(url: str, method: str, route: str, body: dict | None = None,
                 *, timeout: float = 5.0) -> dict:
    """One bounded Manager request; never retried, never redirected."""
    origin = _origin(url, timeout)
    data = None if body is None else json.dumps(body, sort_keys=True).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(origin + route, data=data, method=method, headers=headers)
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(_MAX_BYTES + 1)
    except HTTPError as exc:
        payload = _decode(exc.read(_MAX_BYTES + 1)) if 400 <= exc.code < 500 else None
        if payload is not None and payload.get("ok") is False:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            raise ManagerRefused(exc.code, error.get("code"), error.get("message")) from exc
        if method == "GET":
            raise FleetError(f"Manager GET failed: HTTP {exc.code}") from exc
        raise ManagerUnknown(f"Manager {method} answer unknown: HTTP {exc.code}") from exc
    except (URLError, OSError, TimeoutError) as exc:
        if method == "GET":
            raise FleetError(f"Manager GET failed: {type(exc).__name__}") from exc
        raise ManagerUnknown(f"Manager {method} answer unknown: {type(exc).__name__}") from exc
    payload = _decode(raw)
    if payload is None or payload.get("ok") is not True:
        if method == "GET":
            raise FleetError("Manager response violates the expected contract")
        raise ManagerUnknown(f"Manager {method} answer is not a valid result")
    return payload


def require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or HEX32.fullmatch(value) is None:
        raise FleetError(f"{label} must be exactly 32 lowercase hexadecimal characters")
    return value


def manager_fleet(url: str, *, timeout: float = 5.0) -> dict:
    body = manager_call(url, "GET", "/api/fleet", timeout=timeout)
    if not isinstance(body.get("ppus"), list):
        raise FleetError("Manager Fleet response violates the expected contract")
    return body


def manager_batch(url: str, batch_id: str, *, timeout: float = 5.0) -> dict:
    """Observe an existing Manager Batch; never issue Start or POST."""
    require_id(batch_id, "Batch ID")
    body = manager_call(url, "GET", "/api/programming/batches/" + batch_id, timeout=timeout)
    batch = body.get("batch")
    if not isinstance(batch, dict) or batch.get("batch_id") != batch_id:
        raise FleetError("Manager Batch identity or response contract mismatch")
    return batch


def manager_deployment_status(url: str, ppu_alias: str, *, timeout: float = 5.0) -> dict:
    """Read installed PPU Bootstrap state via Manager; never deploy anything."""
    if (
        not isinstance(ppu_alias, str) or not 1 <= len(ppu_alias) <= 128
        or ppu_alias != ppu_alias.strip() or ppu_alias in (".", "..")
        or "/" in ppu_alias or "\\" in ppu_alias
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in ppu_alias)
    ):
        raise FleetError("invalid PPU alias for Deployment status")
    body = manager_call(url, "GET", "/api/registry/" + quote(ppu_alias, safe="") + "/bootstrap",
                        timeout=timeout)
    if body.get("ppu_alias") != ppu_alias or not isinstance(body.get("bootstrap"), dict):
        raise FleetError("Manager Deployment status identity or contract mismatch")
    pairing = body.get("pairing")
    bootstrap = body["bootstrap"]
    if not isinstance(pairing, dict):
        raise FleetError("Manager Deployment status is missing pairing state")
    deployment = bootstrap.get("deployment")
    runtime = bootstrap.get("runtime")
    return {
        "ppu_alias": ppu_alias,
        "status": "OBSERVED",
        "pairing": {
            "paired": pairing.get("paired"),
            "device_match": pairing.get("device_match"),
            "device_authenticated": pairing.get("device_authenticated"),
        },
        "deployment_state": deployment.get("state") if isinstance(deployment, dict) else None,
        "runtime_state": runtime.get("state") if isinstance(runtime, dict) else None,
        "evidence_kind": "MANAGER_BOOTSTRAP_STATUS_ONLY",
    }
