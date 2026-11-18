"""LOM-P2A-2 P0 on stock-PYNQ Python (3.10, stdlib + scripts only).

The Z2 Bootstrap runs on the system Python 3.10. This test imports no
``plasma_*`` package: it plays the Gateway over the real controller admission
socket protocol (exactly the calls ``ControllerWriteAdmissionMixin`` makes),
then closes the failed Runtime transaction through the real Bootstrap HTTP
endpoint and runs the kit's read-only readiness tool.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import socketserver
import sys
import threading
import time
import uuid
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TX = "370e51bc99fa43329e974ee43a8fd319"
RELEASE = "0.2.1-7e90f95bceb6"
ARTIFACT = "6f2506a6814df6f27d3dcf6735ff715d6597ce8b763e104509694cceefda9a92"
LOOPBACK = "/api/engineering/diagnostics/loopback"
TOKEN = "p0-stdlib-controller-credential-0123456789abcdef"


def _load(name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


service = _load("p0_stdlib_service", "ppu-bootstrap-service.py")
base = _load("p0_stdlib_base", "ppu-bootstrap.py")
auth = _load("p0_stdlib_auth", "ppu_bootstrap_request_auth.py")
readiness = _load("p0_stdlib_readiness", "ppu_runtime_local_readiness.py")


def _private(path: Path, payload) -> None:
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload, encoding="utf-8")
    os.chmod(path, 0o600)


def _admission(sock_path: Path, message: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.connect(str(sock_path))
        conn.sendall(json.dumps(message).encode() + b"\n")
        return json.loads(conn.makefile("rb").readline())


class _Lease(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.rfile.readline()
        self.wfile.write(b'{"ok": true, "result": {"busy": false}}\n')


class _LeaseServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def _gateway_handler(sock_path: Path):
    class Gateway(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/api/health/ready":
                payload, status = {"gateway": "alive", "execution": "ready"}, 200
            elif self.path == "/api/auth/challenge":
                payload, status = _admission(sock_path, {"op": "challenge"}), 200
            else:
                payload, status = {"ok": False}, 404
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    return Gateway


@pytest.fixture
def z2(tmp_path: Path):
    machine = tmp_path / "machine-id"
    machine.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    lease = _LeaseServer(str(tmp_path / "control.sock"), _Lease)
    gateway = ThreadingHTTPServer(("127.0.0.1", 0), _gateway_handler(tmp_path / "adm.sock"))
    paths = service.ServicePaths(
        product_root=tmp_path / "product", state_root=tmp_path / "state", machine_id_path=machine,
        bootstrap_script=ROOT / "scripts" / "ppu-bootstrap.py",
        kit_tool=ROOT / "scripts" / "ppu-bootstrap-kit.py", admission_socket=tmp_path / "adm.sock",
        seal_dir=tmp_path / "seals", runtime_control_socket=tmp_path / "control.sock",
        reload_fence=tmp_path / "mmio.lock", button_profile=tmp_path / "none.json",
        site_recovery_script=tmp_path / "none.py", gateway_port=gateway.server_port)
    product, state = paths.product_root, paths.state_root
    (product / "releases" / RELEASE).mkdir(parents=True)
    (product / "current").symlink_to(product / "releases" / RELEASE)
    (product / "install").mkdir()
    (product / "install" / "last-install.json").write_text(json.dumps(
        {"result": "PASS", "release_id": RELEASE, "archive_sha256": ARTIFACT, "gateway_host": "127.0.0.1"}))
    state.mkdir(mode=0o700)
    _private(state / "control-token", TOKEN + "\n")      # P2A-1 file -> controller generation 1
    journal = {"schema_version": 1, "transaction_id": str(uuid.uuid4()), "sequence": 8,
               "state": "runtime_active", "kind": "ppu-runtime", "api_transaction_id": TX,
               "release_id": RELEASE, "artifact_sha256": ARTIFACT, "updated_at_epoch_s": time.time() - 30}
    _private(state / "deployment.json", journal)
    _private(state / "deployment-api.json", {
        "schema_version": 1, "transaction_id": TX, "upload_id": "6b820ce1488449dfa75311bad5b11f85",
        "state": "recovery_required", "error_code": "coordinator_result_unreconciled",
        "error": "kit PS loopback 401", "result": None, "updated_at_epoch_s": time.time() - 20})
    ppu = service.BootstrapHTTPServer(("127.0.0.1", 0), paths=paths, base_module=base)
    ppu.start_controller_services()
    servers = (lease, gateway, ppu)
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield ppu, gateway, paths, journal
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def _gateway_admitted_loopback(paths: Path, device_id: str) -> bytes:
    """What the G13 Gateway does for one signed PS loopback, over the real socket."""
    request = json.dumps({"endpoint": "ps", "test_id": "p0", "sequence": 1}).encode()
    nonce = _admission(paths.admission_socket, {"op": "challenge"})["nonce"]
    header, _ctx = auth.sign_request(credential=TOKEN, method="POST", path=LOOPBACK, body=request,
                                     device_id=device_id, nonce=nonce)
    response = json.dumps({"ok": True, "loopback": {"endpoint": "ps", "source": "ps",
                                                    "tx_crc32": "d202ef8d", "rx_crc32": "d202ef8d"}}).encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.connect(str(paths.admission_socket))
        stream = conn.makefile("rwb")
        for message in ({"op": "admit_header", "authorization": header},
                        {"op": "admit", "method": "POST", "target": LOOPBACK, "operation": "engineering.write",
                         "body_sha256": hashlib.sha256(request).hexdigest()},
                        {"op": "sign_response", "status": 200,
                         "body_sha256": hashlib.sha256(response).hexdigest()}):
            stream.write(json.dumps(message).encode() + b"\n")
            stream.flush()
            assert json.loads(stream.readline())["ok"] is True
    return response


def _signed_bootstrap_post(ppu, path: str, body: dict) -> tuple[int, dict]:
    conn = HTTPConnection("127.0.0.1", ppu.server_port, timeout=30)
    conn.request("GET", "/v1/auth/challenge")
    challenge = json.loads(conn.getresponse().read())
    raw = json.dumps(body).encode()
    header, _ctx = auth.sign_request(credential=TOKEN, method="POST", path=path, body=raw,
                                     device_id=challenge["device_id"], nonce=challenge["nonce"])
    conn.request("POST", path, body=raw, headers={"Authorization": header, "Content-Type": "application/json"})
    response = conn.getresponse()
    payload = json.loads(response.read())
    conn.close()
    return response.status, payload


def _body(journal: dict, response: bytes) -> dict:
    import base64
    return {"action": "runtime.activation.reconcile", "transaction_id": TX, "explicit_request": True,
            "expected": {"coordinator_transaction_id": journal["transaction_id"], "release_id": RELEASE,
                         "artifact_sha256": ARTIFACT},
            "ps_loopback": {"target": LOOPBACK, "response_base64": base64.b64encode(response).decode()}}


def test_reconcile_on_stock_pynq_python(z2):
    ppu, _gateway, paths, journal = z2
    assert ppu.engine.controller()["generation"] == 1                 # migrated, not re-enrolled
    response = _gateway_admitted_loopback(paths, ppu.engine.device_id)
    status, payload = _signed_bootstrap_post(ppu, "/v1/deployment/reconcile", _body(journal, response))
    assert status == 200 and payload["ok"] is True, payload
    record = json.loads((paths.state_root / "deployment-api.json").read_text())
    assert record["state"] == "reconciled" and record["error_code"] == "coordinator_result_unreconciled"
    assert json.loads((paths.state_root / "deployment.json").read_text()) == journal


def test_reconcile_without_admitted_loopback_is_refused_on_stock_pynq_python(z2):
    ppu, _gateway, paths, journal = z2
    forged = json.dumps({"ok": True, "loopback": {"endpoint": "ps", "source": "ps",
                                                  "tx_crc32": "1", "rx_crc32": "1"}}).encode()
    status, payload = _signed_bootstrap_post(ppu, "/v1/deployment/reconcile", _body(journal, forged))
    assert status == 409 and payload["code"] == "RECONCILE_LOOPBACK_NOT_ADMITTED"
    assert json.loads((paths.state_root / "deployment-api.json").read_text())["state"] == "recovery_required"


def test_kit_readiness_tool_on_stock_pynq_python(z2):
    ppu, gateway, _paths, _journal = z2
    evidence = readiness.check(f"http://127.0.0.1:{gateway.server_port}", f"http://127.0.0.1:{ppu.server_port}")
    assert evidence["result"] == "PASS" and evidence["http_methods_used"] == ["GET"]
    assert evidence["g13"]["controller_generation"] == 1
