from __future__ import annotations

import base64
import hashlib
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from plasma_core.diagnostics import (
    DIAGNOSTIC_PROTOCOL_VERSION,
    DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
    ECHO_TRANSFORM,
    LOOPBACK_DIAGNOSTIC_TYPE,
    PS_LOOPBACK_ENDPOINT,
    crc32_hex,
)
from plasma_web.gateway_security import GatewaySecurityController
from plasma_web.secure_gateway import SecurePlasmaWebHandler


TOKEN = "diagnostics-viewer-token-0123456789abcdef0123456789abcdef"


class SecureDiagnosticClient:
    def __init__(self) -> None:
        self.status_calls = 0
        self.diagnostic_calls = 0

    async def status(self, *, job_id=None, site_id=None):
        self.status_calls += 1
        return {
            "ok": True,
            "ppu": {
                "ppu_id": "ppu-1",
                "facility_id": "facility-1",
                "model": "TEST",
                "display_name": "Test PPU",
                "site_count": 1,
                "enabled_site_count": 1,
                "capabilities": {"max_supported_sites": 1, "operations": ["erase", "program", "verify", "read"]},
            },
            "sites": [{"site_id": 1, "enabled": True, "state": "idle", "current_job_id": None}],
        }

    async def diagnostic_loopback(
        self,
        payload: bytes,
        *,
        test_id: str,
        sequence: int,
        endpoint: str,
        pattern: str | None,
        seed: str | None,
        response_timeout_s: float | None,
    ):
        self.diagnostic_calls += 1
        crc32 = crc32_hex(payload)
        return (
            {
                "ok": True,
                "message_type": DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
                "diagnostic_type": LOOPBACK_DIAGNOSTIC_TYPE,
                "diagnostic_version": DIAGNOSTIC_PROTOCOL_VERSION,
                "endpoint": PS_LOOPBACK_ENDPOINT,
                "source": PS_LOOPBACK_ENDPOINT,
                "test_id": test_id,
                "sequence": sequence,
                "transform": ECHO_TRANSFORM,
                "payload_length": len(payload),
                "tx_crc32": crc32,
                "rx_crc32": crc32,
                "pattern": pattern,
                "seed": seed,
            },
            payload,
        )


@pytest.fixture
def secure_diagnostics_gateway(tmp_path: Path):
    config_path = tmp_path / "security.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "principals": [
                    {
                        "id": "diagnostics-viewer",
                        "token_sha256": hashlib.sha256(TOKEN.encode("utf-8")).hexdigest(),
                        "roles": ["viewer"],
                        "scopes": [
                            {"facility_id": "facility-1", "ppu_id": "ppu-1", "site_ids": "*"}
                        ],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    security = GatewaySecurityController.from_paths(
        config_path,
        tmp_path / "security-state.sqlite3",
    )
    client = SecureDiagnosticClient()
    SecurePlasmaWebHandler.security_controller = security
    SecurePlasmaWebHandler.client_factory = staticmethod(lambda: client)
    SecurePlasmaWebHandler.engineering_provider = None
    SecurePlasmaWebHandler.batch_runtime = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), SecurePlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, client
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        security.close()
        SecurePlasmaWebHandler.security_controller = None
        SecurePlasmaWebHandler.engineering_provider = None
        SecurePlasmaWebHandler.batch_runtime = None


def request(server: ThreadingHTTPServer, *, token: str | None):
    source = b"secure-ps-real-path"
    body = {
        "endpoint": "ps",
        "test_id": "secure-loopback",
        "sequence": 1,
        "pattern": "increment",
        "seed": "",
        "payload_length": len(source),
        "payload_base64": base64.b64encode(source).decode("ascii"),
        "tx_crc32": crc32_hex(source),
        "timeout_ms": 1000,
    }
    connection = HTTPConnection("127.0.0.1", server.server_port)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    connection.request(
        "POST",
        "/api/engineering/diagnostics/loopback",
        json.dumps(body).encode(),
        headers,
    )
    response = connection.getresponse()
    payload = json.loads(response.read())
    status = response.status
    connection.close()
    return status, payload


def test_secure_diagnostics_requires_authentication_before_ppu_lookup(secure_diagnostics_gateway) -> None:
    server, client = secure_diagnostics_gateway
    status_before = client.status_calls
    diagnostic_before = client.diagnostic_calls
    status, payload = request(server, token=None)
    assert status == 401
    assert payload["error"]["error_code"] == "E4101"
    assert client.status_calls == status_before
    assert client.diagnostic_calls == diagnostic_before


def test_viewer_status_scope_can_run_non_destructive_ps_diagnostic(secure_diagnostics_gateway) -> None:
    server, client = secure_diagnostics_gateway
    status, payload = request(server, token=TOKEN)
    assert status == 200
    assert payload["ok"] is True
    assert payload["loopback"]["source"] == "ps"
    assert client.status_calls >= 1
    assert client.diagnostic_calls == 1
