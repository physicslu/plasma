"""Host-only helpers for ``plasma.ppu.bootstrap-request-auth.v1`` tests.

``AuthenticatedFakePPU`` turns a legacy in-memory Bootstrap fake into a PPU
that issues nonces, verifies each request MAC and MACs each response, so
existing contract fakes exercise the real wire authentication. Nothing here
touches a network beyond 127.0.0.1 test servers, SSH, FPGA or a DUT.
"""
from __future__ import annotations

import http.client
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

REPO = Path(__file__).resolve().parents[3]


def _load(name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / file_name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


auth = _load("plasma_bootstrap_request_auth_fixture", "ppu_bootstrap_request_auth.py")


def response_proof(headers: Mapping[str, str]) -> str | None:
    return next((value for key, value in headers.items()
                 if key.lower() == auth.RESPONSE_HEADER.lower()), None)


class AuthenticatedFakePPU:
    """Wrap ``inner(method, path, raw, headers) -> (status, body)``."""

    def __init__(self, inner: Callable[..., Any], *, credential: str, device_id: str) -> None:
        self.inner, self.credential, self.device_id = inner, credential, device_id
        self.nonces = auth.NonceRegistry()
        self.challenges = 0
        self.authenticated_requests = 0

    def __call__(self, method: str, path: str, raw: bytes | None, headers: Mapping[str, str]):
        if method == "GET" and path == auth.CHALLENGE_PATH:
            self.challenges += 1
            body = json.dumps({"ok": True, "schema": auth.SCHEMA, "device_id": self.device_id,
                               "nonce": self.nonces.issue(), "expires_in_s": 60}).encode()
            return 200, body, {}
        # Header check only: fixture credentials like "a"*48 also occur in SHA hex.
        assert self.credential not in json.dumps(dict(headers)), "credential must never cross the wire"
        assert "Bearer" not in headers.get("Authorization", "")
        admitted = auth.admit_request_header(
            header=headers.get("Authorization"), device_id=self.device_id, nonces=self.nonces)
        context = auth.verify_request(credential=self.credential, admitted=admitted,
                                      method=method, path=path, body=raw)
        self.authenticated_requests += 1
        status, body = self.inner(method, path, raw, headers)[:2]
        if not isinstance(body, bytes):
            return status, body, {}
        return status, body, {auth.RESPONSE_HEADER: auth.sign_response(
            credential=self.credential, context=context, status=status, body=body)}


def http_transport(port: int, host: str = "127.0.0.1"):
    """3-tuple transport to an in-process 127.0.0.1 Bootstrap test server."""
    def transport(method: str, path: str, raw: bytes | None, headers: Mapping[str, str]):
        connection = http.client.HTTPConnection(host, port, timeout=10)
        try:
            connection.request(method, path, body=raw, headers=dict(headers))
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()
    return transport


def signed_call(
    transport: Callable[..., Any], method: str, path: str, raw: bytes | None, *,
    credential: str, device_id: str | None = None, headers: Mapping[str, str] | None = None,
) -> tuple[int, bytes]:
    """One authenticated raw call; verifies the response proof when present."""
    status, challenge_raw, _ = transport("GET", auth.CHALLENGE_PATH, None,
                                         {"Accept": "application/json"})
    assert status == 200
    challenge = json.loads(challenge_raw)
    header, context = auth.sign_request(
        credential=credential, method=method, path=path, body=raw,
        device_id=device_id or challenge["device_id"], nonce=challenge["nonce"])
    status, body, response_headers = transport(method, path, raw, {
        "Accept": "application/json", "Content-Type": "application/json",
        **(headers or {}), "Authorization": header})
    proof = response_proof(response_headers)
    if proof is not None:
        auth.verify_response(credential=credential, context=context, status=status,
                             body=body, header=proof)
    else:
        assert status in (401, 503), "every authenticated non-refusal response is MACed"
    return status, body
