from __future__ import annotations

import hashlib
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from plasma_web.secure_gateway_app import (
    DeployedSecurePlasmaWebHandler,
    load_security_controller_from_env,
)
from tests.test_secure_gateway_deployment import TOKEN, _write_config
from tests.test_secure_gateway_rest import FakeLocalClient


ROLE_TOKENS = {
    role: f"entry-{role}-token-0123456789abcdef0123456789abcdef"
    for role in ("viewer", "operator", "engineer", "admin")
}


def _start_secure_server(controller):
    DeployedSecurePlasmaWebHandler.security_controller = controller
    DeployedSecurePlasmaWebHandler.client_factory = staticmethod(lambda: FakeLocalClient())
    DeployedSecurePlasmaWebHandler.batch_runtime = None
    DeployedSecurePlasmaWebHandler.allowed_origins = frozenset({"*"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), DeployedSecurePlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_secure_server(server: ThreadingHTTPServer, thread: threading.Thread, controller) -> None:
    server.shutdown()
    server.server_close()
    thread.join()
    controller.close()
    for attribute in ("security_controller", "client_factory", "batch_runtime", "allowed_origins"):
        if attribute in DeployedSecurePlasmaWebHandler.__dict__:
            delattr(DeployedSecurePlasmaWebHandler, attribute)


def _security_me(server: ThreadingHTTPServer, token: str | None = None) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", server.server_port)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    connection.request("GET", "/api/security/me", headers=headers)
    response = connection.getresponse()
    status = response.status
    payload = json.loads(response.read())
    connection.close()
    return status, payload


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
    server, thread = _start_secure_server(controller)
    try:
        status, payload = _security_me(server)
        assert status == 401
        assert payload["error"]["error_code"] == "E4101"

        status, payload = _security_me(server, TOKEN)
        assert status == 200
        assert payload["ok"] is True
        assert payload["principal"]["id"] == "deployment-admin"
        assert payload["principal"]["roles"] == ["admin"]
        assert "settings.gateway.write" in payload["principal"]["permissions"]
        assert "settings.site.write" in payload["principal"]["permissions"]
        assert payload["principal"]["scopes"] == [
            {"facility_id": "*", "ppu_id": "*", "site_ids": "*"}
        ]
        assert "token" not in json.dumps(payload).lower()
    finally:
        _stop_secure_server(server, thread, controller)


def test_security_me_exposes_role_permission_matrix_without_ui_escalation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "security.yaml"
    state_path = tmp_path / "security-state.sqlite3"
    principals = []
    for index, (role, token) in enumerate(ROLE_TOKENS.items(), start=1):
        principals.append(
            {
                "id": f"entry-{role}",
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "roles": [role],
                "scopes": [
                    {
                        "facility_id": "test-facility",
                        "ppu_id": "test-ppu",
                        "site_ids": [index],
                    }
                ],
            }
        )
    config_path.write_text(
        yaml.safe_dump({"version": 1, "principals": principals}, sort_keys=False),
        encoding="utf-8",
    )
    config_path.chmod(0o600)
    monkeypatch.setenv("PLASMA_SECURITY_CONFIG", str(config_path))
    monkeypatch.setenv("PLASMA_SECURITY_STATE", str(state_path))

    controller = load_security_controller_from_env()
    server, thread = _start_secure_server(controller)
    try:
        results: dict[str, dict] = {}
        for role, token in ROLE_TOKENS.items():
            status, payload = _security_me(server, token)
            assert status == 200
            principal = payload["principal"]
            assert principal["id"] == f"entry-{role}"
            assert principal["roles"] == [role]
            assert "status.read" in principal["permissions"]
            results[role] = principal

        assert "ppu.program" not in results["viewer"]["permissions"]
        assert "engineering.session.write" not in results["viewer"]["permissions"]
        assert "settings.site.write" not in results["viewer"]["permissions"]

        assert "ppu.program" in results["operator"]["permissions"]
        assert "engineering.session.write" in results["operator"]["permissions"]
        assert "settings.mock.write" not in results["operator"]["permissions"]
        assert "settings.site.write" not in results["operator"]["permissions"]

        assert "settings.mock.write" in results["engineer"]["permissions"]
        assert "settings.site.write" in results["engineer"]["permissions"]
        assert "settings.gateway.write" not in results["engineer"]["permissions"]

        assert "settings.mock.write" in results["admin"]["permissions"]
        assert "settings.site.write" in results["admin"]["permissions"]
        assert "settings.gateway.write" in results["admin"]["permissions"]

        assert results["viewer"]["scopes"] == [
            {"facility_id": "test-facility", "ppu_id": "test-ppu", "site_ids": [1]}
        ]
        assert results["admin"]["scopes"] == [
            {"facility_id": "test-facility", "ppu_id": "test-ppu", "site_ids": [4]}
        ]
    finally:
        _stop_secure_server(server, thread, controller)
