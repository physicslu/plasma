from __future__ import annotations

import hashlib
import json
import os
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from plasma_core.errors import ErrorCode, PlasmaError
import plasma_web.secure_gateway_app as secure_gateway_app
from plasma_web.secure_gateway_app import (
    DeployedSecurePlasmaWebHandler,
    load_security_controller_from_env,
)
from tests.test_secure_gateway_rest import FakeLocalClient


TOKEN = "deployment-admin-token-0123456789abcdef0123456789abcdef"


def _write_config(path: Path, *, mode: int = 0o600) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "principals": [
                    {
                        "id": "deployment-admin",
                        "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
                        "roles": ["admin"],
                        "scopes": [
                            {
                                "facility_id": "*",
                                "ppu_id": "*",
                                "site_ids": "*",
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    path.chmod(mode)


def test_secure_launcher_requires_explicit_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLASMA_SECURITY_CONFIG", raising=False)
    monkeypatch.delenv("PLASMA_SECURITY_STATE", raising=False)
    with pytest.raises(PlasmaError) as exc_info:
        load_security_controller_from_env()
    assert exc_info.value.code is ErrorCode.CONFIG_INVALID


def test_secure_launcher_rejects_same_config_and_state_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "security.yaml"
    _write_config(config_path)
    monkeypatch.setenv("PLASMA_SECURITY_CONFIG", str(config_path))
    monkeypatch.setenv("PLASMA_SECURITY_STATE", str(config_path))
    with pytest.raises(PlasmaError) as exc_info:
        load_security_controller_from_env()
    assert exc_info.value.code is ErrorCode.CONFIG_INVALID


def test_secure_launcher_rejects_group_or_world_readable_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "security.yaml"
    state_path = tmp_path / "security-state.sqlite3"
    _write_config(config_path, mode=0o644)
    monkeypatch.setenv("PLASMA_SECURITY_CONFIG", str(config_path))
    monkeypatch.setenv("PLASMA_SECURITY_STATE", str(state_path))
    with pytest.raises(PlasmaError) as exc_info:
        load_security_controller_from_env()
    assert exc_info.value.code is ErrorCode.CONFIG_INVALID
    assert not state_path.exists()


def test_secure_launcher_rejects_existing_readable_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "security.yaml"
    state_path = tmp_path / "security-state.sqlite3"
    _write_config(config_path)
    state_path.write_bytes(b"")
    state_path.chmod(0o644)
    monkeypatch.setenv("PLASMA_SECURITY_CONFIG", str(config_path))
    monkeypatch.setenv("PLASMA_SECURITY_STATE", str(state_path))
    with pytest.raises(PlasmaError) as exc_info:
        load_security_controller_from_env()
    assert exc_info.value.code is ErrorCode.CONFIG_INVALID


def test_secure_launcher_creates_owner_only_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "security.yaml"
    state_path = tmp_path / "state" / "security-state.sqlite3"
    _write_config(config_path)
    monkeypatch.setenv("PLASMA_SECURITY_CONFIG", str(config_path))
    monkeypatch.setenv("PLASMA_SECURITY_STATE", str(state_path))
    controller = load_security_controller_from_env()
    try:
        assert state_path.is_file()
        assert os.stat(state_path).st_mode & 0o077 == 0
    finally:
        controller.close()


def test_secure_launcher_keeps_gateway_created_material_owner_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "security.yaml"
    state_path = tmp_path / "security-state.sqlite3"
    output_path = tmp_path / "readback.bin"
    _write_config(config_path)
    monkeypatch.setenv("PLASMA_SECURITY_CONFIG", str(config_path))
    monkeypatch.setenv("PLASMA_SECURITY_STATE", str(state_path))
    original_handler = secure_gateway_app.gateway.PlasmaWebHandler

    def fake_gateway_main() -> None:
        assert secure_gateway_app.gateway.PlasmaWebHandler is DeployedSecurePlasmaWebHandler
        output_path.write_bytes(b"target-readback")

    monkeypatch.setattr(secure_gateway_app.gateway, "main", fake_gateway_main)
    secure_gateway_app.main()

    assert output_path.is_file()
    assert os.stat(output_path).st_mode & 0o077 == 0
    assert secure_gateway_app.gateway.PlasmaWebHandler is original_handler
    assert DeployedSecurePlasmaWebHandler.security_controller is None


def test_deployed_secure_handler_exposes_auth_cors_and_enforces_write_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "security.yaml"
    state_path = tmp_path / "security-state.sqlite3"
    _write_config(config_path)
    monkeypatch.setenv("PLASMA_SECURITY_CONFIG", str(config_path))
    monkeypatch.setenv("PLASMA_SECURITY_STATE", str(state_path))
    controller = load_security_controller_from_env()
    local_client = FakeLocalClient()
    DeployedSecurePlasmaWebHandler.security_controller = controller
    DeployedSecurePlasmaWebHandler.client_factory = staticmethod(lambda: local_client)
    DeployedSecurePlasmaWebHandler.batch_runtime = None
    DeployedSecurePlasmaWebHandler.allowed_origins = frozenset({"https://console.example"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), DeployedSecurePlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "OPTIONS",
            "/api/jobs",
            headers={
                "Origin": "https://console.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,idempotency-key,content-type",
            },
        )
        response = connection.getresponse()
        response.read()
        assert response.status == 204
        allowed = response.getheader("Access-Control-Allow-Headers") or ""
        assert "Authorization" in allowed
        assert "Idempotency-Key" in allowed
        connection.close()

        connection = HTTPConnection("127.0.0.1", server.server_port)
        body = json.dumps({"site_id": 1, "operation": "read", "offset": 0, "length": 16})
        connection.request(
            "POST",
            "/api/jobs",
            body=body,
            headers={"Content-Type": "application/json", "Idempotency-Key": "deploy-no-auth-0001"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 401
        assert payload["error"]["error_code"] == "E4101"
        connection.close()

        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "POST",
            "/api/jobs",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN}",
                "Idempotency-Key": "deploy-read-0001",
            },
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 202
        assert payload["job"]["site_id"] == 1
        assert local_client.start_calls == 1
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        controller.close()
        for attribute in ("security_controller", "client_factory", "batch_runtime", "allowed_origins"):
            if attribute in DeployedSecurePlasmaWebHandler.__dict__:
                delattr(DeployedSecurePlasmaWebHandler, attribute)
