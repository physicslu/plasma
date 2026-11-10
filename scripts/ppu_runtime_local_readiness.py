#!/usr/bin/env python3
"""Read-only local Runtime readiness for the Z2 PS kit (LOM-P2A-2 G13 aware).

The kit installer is NOT the PPU controller. It holds no controller credential,
never reads ``/var/lib/plasma-bootstrap/controller`` and never signs a Gateway
write. A signed PS loopback is the Manager's remote, controller-authorized
acceptance; this tool only proves locally that:

1. the Gateway is alive and its execution plane is ready;
2. the Gateway serves the G13 challenge through the Bootstrap controller
   admission socket (``GET /api/auth/challenge``), for the same device the
   local Bootstrap reports;
3. nothing else: it sends only GET requests. It never sends a write, signed or
   unsigned. G13 refusal of unsigned writes is proven by Host tests and by the
   Manager acceptance, not by the installer.

An unauthenticated (host-lab) Gateway has no challenge route and fails step 2.
Stdlib only, Python 3.10+ (stock PYNQ system Python).
"""
from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
from typing import Any
from urllib.parse import urlsplit

SCHEMA = "plasma.ppu.runtime-local-readiness.v1"
AUTH_SCHEMA = "plasma.ppu.bootstrap-request-auth.v1"
DEVICE_RE = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")
NONCE_RE = re.compile(r"[0-9a-f]{32}\Z")
MAX_RESPONSE = 65536


class ReadinessFailed(RuntimeError):
    pass


def _endpoint(url: str) -> tuple[str, int]:
    parts = urlsplit(url)
    if parts.scheme != "http" or not parts.hostname or parts.path not in ("", "/") or parts.query:
        raise ReadinessFailed(f"endpoint must be http://host:port, got {url!r}")
    return parts.hostname, parts.port or 80


def _get(url: str, path: str, *, timeout_s: float) -> tuple[int, Any]:
    method = "GET"
    host, port = _endpoint(url)
    connection = http.client.HTTPConnection(host, port, timeout=timeout_s)
    try:
        connection.request(method, path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        raw = response.read(MAX_RESPONSE + 1)
        status = response.status
    except OSError as exc:
        raise ReadinessFailed(f"{method} {path} transport failed: {type(exc).__name__}") from exc
    finally:
        connection.close()
    if len(raw) > MAX_RESPONSE:
        raise ReadinessFailed(f"{method} {path} response is too large")
    try:
        return status, json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, ValueError):
        return status, None


def _error_code(payload: Any) -> str | None:
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return error.get("code") if isinstance(error.get("code"), str) else None
    return error if isinstance(error, str) else None


def check(gateway: str, bootstrap: str, *, timeout_s: float = 5.0) -> dict[str, Any]:
    status, ready = _get(gateway, "/api/health/ready", timeout_s=timeout_s)
    if status != 200 or not isinstance(ready, dict) or ready.get("gateway") != "alive" \
            or ready.get("execution") != "ready":
        raise ReadinessFailed(f"Gateway readiness is not alive/ready: HTTP {status} {ready!r}")

    status, challenge = _get(gateway, "/api/auth/challenge", timeout_s=timeout_s)
    if status != 200 or not isinstance(challenge, dict):
        raise ReadinessFailed(
            f"Gateway does not serve the G13 controller challenge (HTTP {status}, "
            f"code {_error_code(challenge)!r}); the controller admission socket is not wired")
    generation = challenge.get("controller_generation")
    device_id = challenge.get("device_id")
    if (challenge.get("schema") != AUTH_SCHEMA or type(device_id) is not str
            or not DEVICE_RE.fullmatch(device_id) or type(challenge.get("nonce")) is not str
            or not NONCE_RE.fullmatch(challenge["nonce"])
            or type(generation) is not int or generation < 0):
        raise ReadinessFailed("Gateway G13 challenge is malformed")

    status, bootstrap_status = _get(bootstrap, "/v1/status", timeout_s=timeout_s)
    identity = bootstrap_status.get("identity") if isinstance(bootstrap_status, dict) else None
    if status != 200 or not isinstance(identity, dict) or identity.get("device_id") != device_id:
        raise ReadinessFailed("Gateway G13 challenge is not bound to this PPU's Bootstrap identity")

    return {
        "schema": SCHEMA,
        "result": "PASS",
        "gateway": {"gateway": "alive", "execution": "ready"},
        "g13": {
            "admission": "controller-admission-socket",
            "device_id": device_id,
            "controller_generation": generation,
            "bound_to_bootstrap_identity": True,
        },
        "signed_ps_loopback": "DELEGATED_TO_MANAGER_ACCEPTANCE",
        "controller_credential_access": "NONE",
        "http_methods_used": ["GET"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gateway", required=True, help="http://host:18080")
    parser.add_argument("--bootstrap", required=True, help="http://host:18081")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        evidence = check(args.gateway, args.bootstrap, timeout_s=args.timeout_s)
    except ReadinessFailed as exc:
        print(json.dumps({"schema": SCHEMA, "result": "FAIL", "reason": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
