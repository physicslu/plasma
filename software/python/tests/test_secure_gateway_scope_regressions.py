from __future__ import annotations

import hashlib
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from plasma_web.gateway_security import GatewaySecurityController
from plasma_web.secure_gateway import SecurePlasmaWebHandler
from tests.test_secure_gateway_rest import FakeLocalClient


TOKEN = "operator-token-scope-regression-0123456789abcdef0123456789abcdef"


@pytest.fixture
def scoped_gateway(tmp_path: Path):
    config_path = tmp_path / "security.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "principals": [
                    {
                        "id": "site-operator",
                        "token_sha256": hashlib.sha256(TOKEN.encode("utf-8")).hexdigest(),
                        "roles": ["operator"],
                        "scopes": [
                            {
                                "facility_id": "facility-1",
                                "ppu_id": "ppu-1",
                                "site_ids": [1, 2],
                            }
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
    local_client = FakeLocalClient()
    SecurePlasmaWebHandler.security_controller = security
    SecurePlasmaWebHandler.client_factory = staticmethod(lambda: local_client)
    SecurePlasmaWebHandler.batch_runtime = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), SecurePlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, local_client
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        security.close()
        SecurePlasmaWebHandler.security_controller = None
        SecurePlasmaWebHandler.batch_runtime = None


def _request(
    server: ThreadingHTTPServer,
    method: str,
    path: str,
    body=None,
    *,
    command_id: str | None = None,
):
    connection = HTTPConnection("127.0.0.1", server.server_port)
    raw = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if raw is not None:
        headers["Content-Type"] = "application/json"
    if command_id is not None:
        headers["Idempotency-Key"] = command_id
    connection.request(method, path, raw, headers)
    response = connection.getresponse()
    payload = json.loads(response.read())
    status = response.status
    connection.close()
    return status, payload


def test_decimal_string_site_id_cannot_bypass_site_scope(scoped_gateway) -> None:
    server, local_client = scoped_gateway
    before = local_client.start_calls
    status, payload = _request(
        server,
        "POST",
        "/api/jobs",
        {"site_id": "3", "operation": "read", "offset": 0, "length": 16},
        command_id="cmd-string-site-0001",
    )
    assert status == 403
    assert payload["error"]["error_code"] == "E4102"
    assert local_client.start_calls == before


def test_site_scoped_principal_cannot_read_parent_ppu_status(scoped_gateway) -> None:
    server, _ = scoped_gateway
    status, payload = _request(server, "GET", "/api/status")
    assert status == 403
    assert payload["error"]["error_code"] == "E4102"


def test_site_scoped_principal_can_read_an_allowed_site(scoped_gateway) -> None:
    server, _ = scoped_gateway
    status, payload = _request(server, "GET", "/api/status?site=2")
    assert status == 200
    assert payload["ok"] is True


def test_authenticated_unclassified_api_route_fails_closed(scoped_gateway) -> None:
    server, _ = scoped_gateway
    status, payload = _request(server, "GET", "/api/future-write-surface")
    assert status == 403
    assert payload["error"]["error_code"] == "E4102"
