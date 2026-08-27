from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from plasma_web.secure_gateway_app import (
    DeployedSecurePlasmaWebHandler,
    load_security_controller_from_env,
)
from tests.test_secure_gateway_deployment import TOKEN, _write_config
from tests.test_secure_gateway_rest import FakeLocalClient


def test_security_me_requires_auth_and_returns_backend_principal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "security.yaml"
    state_path = tmp_path / "security-state.sqlite3"
    _write_config(config_path)
    monkeypatch.setenv("PLASMA_SECURITY_CONFIG", str(config_path))
    monkeypatch.setenv("PLASMA_SECURITY_STATE", str(state_path))

    controller = load_security_controller_from_env()
    DeployedSecurePlasmaWebHandler.security_controller = controller
    DeployedSecurePlasmaWebHandler.client_factory = staticmethod(lambda: FakeLocalClient())
    DeployedSecurePlasmaWebHandler.batch_runtime = None
    DeployedSecurePlasmaWebHandler.allowed_origins = frozenset({"*"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), DeployedSecurePlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", "/api/security/me")
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 401
        assert payload["error"]["error_code"] == "E4101"
        connection.close()

        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "GET",
            "/api/security/me",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["ok"] is True
        assert payload["principal"]["id"] == "deployment-admin"
        assert payload["principal"]["roles"] == ["admin"]
        assert "settings.gateway.write" in payload["principal"]["permissions"]
        assert payload["principal"]["scopes"] == [
            {"facility_id": "*", "ppu_id": "*", "site_ids": "*"}
        ]
        assert "token" not in json.dumps(payload).lower()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        controller.close()
        for attribute in ("security_controller", "client_factory", "batch_runtime", "allowed_origins"):
            if attribute in DeployedSecurePlasmaWebHandler.__dict__:
                delattr(DeployedSecurePlasmaWebHandler, attribute)
