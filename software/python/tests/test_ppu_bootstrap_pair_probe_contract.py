from __future__ import annotations

import importlib.util
import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, file_name: str):
    path = ROOT / "scripts" / file_name
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = _load("ppu_bootstrap_pair_probe_base", "ppu-bootstrap.py")
service = _load("ppu_bootstrap_pair_probe_service", "ppu-bootstrap-service.py")
TOKEN = "t" * 40
WRONG_TOKEN = "w" * 40


def _post(port: int, token: str):
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    body = json.dumps({"size": 0, "sha256": "0" * 64})
    connection.request(
        "POST",
        "/v1/uploads",
        body=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return response.status, payload


def test_zero_size_upload_is_side_effect_free_authenticated_pair_probe(tmp_path: Path) -> None:
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    paths = service.ServicePaths(
        product_root=tmp_path / "product",
        state_root=tmp_path / "state",
        machine_id_path=machine_id,
        bootstrap_script=ROOT / "scripts" / "ppu-bootstrap.py",
        kit_tool=ROOT / "scripts" / "ppu-bootstrap-kit.py",
    )
    service.provision_token(paths.token_file, token=TOKEN)
    server = service.BootstrapHTTPServer(("127.0.0.1", 0), paths=paths, base_module=bootstrap)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        wrong_status, wrong_payload = _post(server.server_port, WRONG_TOKEN)
        assert wrong_status == 401
        assert wrong_payload["error"] == "unauthorized"
        assert not paths.uploads_root.exists()

        status, payload = _post(server.server_port, TOKEN)
        assert status == 409
        assert payload["error"] == "bootstrap_request_rejected"
        assert payload["message"].startswith("size must be an integer in range 1..")
        assert not paths.uploads_root.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
