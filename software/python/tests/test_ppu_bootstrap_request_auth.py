"""LOM-P2A-1: PPU Bootstrap mutual request authentication (Host-only).

Real Bootstrap HTTP service on 127.0.0.1 and the real Manager
``BootstrapHttpClient``; no SSH, Z2, FPGA, DUT or external network. Proves the
paired credential never crosses the wire, a spoofed endpoint cannot obtain or
fake the proof, and replayed/tampered/wrong-device/legacy-Bearer requests fail
closed before any side effect.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from plasma_manager import bootstrap_request_auth as manager_auth
from plasma_manager.bootstrap import (
    MANAGED_BOOTSTRAP_PATH_PREFIX,
    MANAGED_BOOTSTRAP_TRANSPORT,
    MANAGED_BOOTSTRAP_TRANSPORT_ENV,
    BootstrapCredentialError,
    BootstrapCredentialStore,
    ControllerReplacedError,
    BootstrapHttpClient,
    BootstrapManagerError,
)
from plasma_manager.config import PPURegistryEntry
from plasma_manager.registry import PPURegistryStore
from plasma_manager.verified_bootstrap import VerifiedManagerBootstrapCoordinator

from .ppu_controller_fixture import clear_controller, seed_controller

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file_name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


auth = _load("ppu_request_auth_p2a1", "ppu_bootstrap_request_auth.py")
bootstrap = _load("ppu_request_auth_p2a1_base", "ppu-bootstrap.py")
service = _load("ppu_request_auth_p2a1_service", "ppu-bootstrap-service.py")
TOKEN = "t" * 40
WRONG = "w" * 40
DEVICE = "ppu-device-0123456789abcdef01234567"
OTHER_DEVICE = "ppu-device-fedcba9876543210"
NONCE = "1" * 32
CNONCE = "2" * 32


# --- protocol / cross-implementation ----------------------------------------

def test_manager_and_ppu_produce_byte_identical_request_proofs():
    for method, path, body in (("GET", "/v1/status", None),
                               ("POST", "/v1/uploads", b'{"size":1}'),
                               ("POST", "/v1/deployments", b"{}")):
        ppu_header, ppu_ctx = auth.sign_request(credential=TOKEN, method=method, path=path,
                                                body=body, device_id=DEVICE, nonce=NONCE,
                                                cnonce=CNONCE)
        mgr_header, mgr_ctx = manager_auth.sign_request(credential=TOKEN, method=method,
                                                        path=path, body=body, device_id=DEVICE,
                                                        nonce=NONCE, cnonce=CNONCE)
        assert ppu_header == mgr_header
        assert ppu_ctx.mac == mgr_ctx.mac
        assert TOKEN not in ppu_header
        assert ppu_header.startswith("PLASMA-PPU-HMAC-V1 device_id=" + DEVICE)
    assert manager_auth.SCHEMA == auth.SCHEMA
    assert manager_auth.RESPONSE_HEADER == auth.RESPONSE_HEADER
    assert manager_auth.CHALLENGE_PATH == auth.CHALLENGE_PATH


def test_ppu_response_proof_is_bound_to_request_status_body_and_credential():
    _header, ppu_ctx = auth.sign_request(credential=TOKEN, method="POST", path="/v1/uploads",
                                         body=b"{}", device_id=DEVICE, nonce=NONCE, cnonce=CNONCE)
    _header, mgr_ctx = manager_auth.sign_request(credential=TOKEN, method="POST",
                                                 path="/v1/uploads", body=b"{}",
                                                 device_id=DEVICE, nonce=NONCE, cnonce=CNONCE)
    proof = auth.sign_response(credential=TOKEN, context=ppu_ctx, status=201, body=b'{"ok":true}')
    manager_auth.verify_response(credential=TOKEN, context=mgr_ctx, status=201,
                                 body=b'{"ok":true}', header=proof)
    _h, other_ctx = manager_auth.sign_request(credential=TOKEN, method="POST",
                                              path="/v1/uploads", body=b"{}", device_id=DEVICE,
                                              nonce="3" * 32, cnonce=CNONCE)
    for kwargs in ({"status": 200}, {"body": b'{"ok":false}'}, {"credential": WRONG},
                   {"context": other_ctx}, {"header": None}, {"header": "v1 mac=" + "0" * 64},
                   {"header": proof.upper()}):
        values = {"credential": TOKEN, "context": mgr_ctx, "status": 201,
                  "body": b'{"ok":true}', "header": proof, **kwargs}
        with pytest.raises(manager_auth.BootstrapRequestAuthError):
            manager_auth.verify_response(**values)


def test_nonces_are_single_use_expiring_and_bounded():
    now = [100.0]
    registry = auth.NonceRegistry(ttl_s=60, capacity=3, clock=lambda: now[0])
    first = registry.issue()
    assert registry.consume(first) is True
    assert registry.consume(first) is False  # replay
    expired = registry.issue()
    now[0] += 60
    assert registry.consume(expired) is False
    issued = [registry.issue() for _ in range(4)]
    assert registry.consume(issued[0]) is False  # evicted, never authenticates
    assert all(registry.consume(nonce) for nonce in issued[1:])


@pytest.mark.parametrize("header", [
    None, "", "Bearer " + TOKEN,
    "PLASMA-PPU-HMAC-V1 device_id=%s,nonce=%s,cnonce=%s,mac=%s" % (DEVICE, NONCE, CNONCE, "0" * 63),
    "PLASMA-PPU-HMAC-V1 device_id=%s,nonce=%s,cnonce=%s,mac=%s " % (DEVICE, NONCE, CNONCE, "0" * 64),
])
def test_malformed_or_legacy_headers_are_rejected_before_body(header):
    registry = auth.NonceRegistry()
    with pytest.raises(auth.RequestAuthError):
        auth.admit_request_header(header=header, device_id=DEVICE, nonces=registry)


def test_wrong_device_consumes_nonce_and_rejects():
    registry = auth.NonceRegistry()
    nonce = registry.issue()
    header, _ctx = auth.sign_request(credential=TOKEN, method="GET", path="/v1/status",
                                     body=None, device_id=OTHER_DEVICE, nonce=nonce)
    with pytest.raises(auth.RequestAuthError, match="not for this device"):
        auth.admit_request_header(header=header, device_id=DEVICE, nonces=registry)
    assert registry.consume(nonce) is False


# --- real Bootstrap service ---------------------------------------------------

@pytest.fixture
def ppu(tmp_path: Path):
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    paths = service.ServicePaths(
        product_root=tmp_path / "product", state_root=tmp_path / "state",
        machine_id_path=machine_id,
        bootstrap_script=ROOT / "scripts" / "ppu-bootstrap.py",
        kit_tool=ROOT / "scripts" / "ppu-bootstrap-kit.py",
    )
    seed_controller(paths.state_root, TOKEN)
    server = service.BootstrapHTTPServer(("127.0.0.1", 0), paths=paths, base_module=bootstrap)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, paths
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _http(port: int, method: str, path: str, *, body: bytes | None = None,
          headers: dict[str, str] | None = None):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers={
            "Accept": "application/json", "Content-Type": "application/json", **(headers or {})})
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        connection.close()


def _challenge(port: int) -> dict:
    status, raw, _headers = _http(port, "GET", "/v1/auth/challenge")
    assert status == 200
    return json.loads(raw)


UPLOAD = json.dumps({"size": 4, "sha256": "0" * 64}).encode()


def _signed(port: int, method: str, path: str, body: bytes | None, *, credential=TOKEN,
            device_id=None, send_path=None, send_body=None):
    challenge = _challenge(port)
    header, context = auth.sign_request(credential=credential, method=method, path=path,
                                        body=body, device_id=device_id or challenge["device_id"],
                                        nonce=challenge["nonce"])
    status, raw, headers = _http(port, method, send_path or path,
                                 body=send_body if send_body is not None else body,
                                 headers={"Authorization": header})
    return status, raw, headers, header, context


def _uploads(paths) -> list[Path]:
    # One upload = one record (+ its .part payload).
    return sorted(paths.uploads_root.glob("*.part")) if paths.uploads_root.exists() else []


def test_challenge_names_this_device_and_status_reports_scheme(ppu):
    server, _paths = ppu
    challenge = _challenge(server.server_port)
    assert challenge["schema"] == auth.SCHEMA and challenge["expires_in_s"] == 60
    assert challenge["device_id"] == server.device_id()
    assert _challenge(server.server_port)["nonce"] != challenge["nonce"]
    status, raw, headers = _http(server.server_port, "GET", "/v1/status")
    assert status == 200
    assert json.loads(raw)["security"]["request_authentication"] == auth.SCHEMA
    assert auth.RESPONSE_HEADER not in headers  # anonymous read carries no proof


def test_authenticated_upload_succeeds_with_response_proof(ppu):
    server, paths = ppu
    status, raw, headers, _header, context = _signed(server.server_port, "POST", "/v1/uploads", UPLOAD)
    assert status == 201, raw
    auth.verify_response(credential=TOKEN, context=context, status=status, body=raw,
                         header=headers.get(auth.RESPONSE_HEADER))
    assert len(_uploads(paths)) == 1


def test_replayed_request_is_rejected_without_second_side_effect(ppu):
    server, paths = ppu
    status, _raw, _headers, header, _context = _signed(server.server_port, "POST", "/v1/uploads", UPLOAD)
    assert status == 201
    replay, raw, headers = _http(server.server_port, "POST", "/v1/uploads", body=UPLOAD,
                                 headers={"Authorization": header})
    assert replay == 401 and json.loads(raw)["error"] == "unauthorized"
    assert auth.RESPONSE_HEADER not in headers
    assert len(_uploads(paths)) == 1


@pytest.mark.parametrize("variant", ["legacy_bearer", "anonymous", "wrong_credential",
                                     "wrong_device", "tampered_body", "other_path"])
def test_unauthenticated_mutations_fail_closed_before_side_effects(ppu, variant):
    server, paths = ppu
    port = server.server_port
    if variant == "legacy_bearer":
        status, raw, headers = _http(port, "POST", "/v1/uploads", body=UPLOAD,
                                     headers={"Authorization": "Bearer " + TOKEN})
    elif variant == "anonymous":
        status, raw, headers = _http(port, "POST", "/v1/uploads", body=UPLOAD)
    elif variant == "wrong_credential":
        status, raw, headers, *_ = _signed(port, "POST", "/v1/uploads", UPLOAD, credential=WRONG)
    elif variant == "wrong_device":
        status, raw, headers, *_ = _signed(port, "POST", "/v1/uploads", UPLOAD, device_id=OTHER_DEVICE)
    elif variant == "tampered_body":
        status, raw, headers, *_ = _signed(
            port, "POST", "/v1/uploads", UPLOAD,
            send_body=json.dumps({"size": 5, "sha256": "0" * 64}).encode())
    else:
        status, raw, headers, *_ = _signed(port, "POST", "/v1/uploads", UPLOAD,
                                           send_path="/v1/deployments")
    # P2A-1 contract plus the non-secret current generation (LOM-P2A-2 §5.5).
    assert status == 401 and json.loads(raw) == {
        "ok": False, "error": "unauthorized", "code": "CONTROLLER_UNAUTHENTICATED",
        "controller_generation": 1}
    assert auth.RESPONSE_HEADER not in headers
    assert _uploads(paths) == []
    assert not paths.deployment_record.exists()


def test_unprovisioned_device_refuses_mutation(ppu):
    server, paths = ppu
    clear_controller(paths.state_root)
    status, raw, _headers, *_ = _signed(server.server_port, "POST", "/v1/uploads", UPLOAD)
    assert status == 503 and json.loads(raw)["error"] == "CONTROLLER_NOT_ENROLLED"
    assert _uploads(paths) == []


# --- real Manager client against the real service ----------------------------

def _manager(tmp_path: Path, port: int, *, endpoint_port: int | None = None):
    registry = PPURegistryStore(
        (PPURegistryEntry(endpoint="http://127.0.0.1:18080", alias="z2"),),
        tmp_path / "registry.json",
    )
    store = BootstrapCredentialStore(tmp_path / "bootstrap-credentials.json")

    def factory(_endpoint: str, timeout_s: float):
        return BootstrapHttpClient(f"http://127.0.0.1:{endpoint_port or port}", timeout_s)

    return store, VerifiedManagerBootstrapCoordinator(registry, store, 3.0, client_factory=factory)


def test_enrolled_manager_writes_with_mutual_proof(ppu, tmp_path: Path):
    server, paths = ppu
    store, coordinator = _manager(tmp_path, server.server_port)
    store.set("z2", server.device_id(), TOKEN, generation=1)       # enrollment result
    status = coordinator.status("z2")
    assert status["pairing"]["device_authenticated"] is True
    assert status["pairing"]["device_match"] is True
    assert status["pairing"]["controller_generation"] == 1
    code, payload = coordinator.create_upload("z2", {"size": 4, "sha256": "0" * 64})
    assert code == 201 and payload["upload"]["upload_id"]
    assert len(_uploads(paths)) == 1


def test_takeover_by_another_controller_stops_the_manager_without_retry(ppu, tmp_path: Path):
    server, paths = ppu
    store, coordinator = _manager(tmp_path, server.server_port)
    store.set("z2", server.device_id(), TOKEN, generation=1)
    seed_controller(paths.state_root, "r" * 40)     # takeover by another controller (gen 2)
    pairing = coordinator.status("z2")["pairing"]
    assert pairing["device_authenticated"] is False and pairing["controller_replaced"] is True
    with pytest.raises(ControllerReplacedError, match="another Control Station"):
        coordinator.create_upload("z2", {"size": 4, "sha256": "0" * 64})
    assert _uploads(paths) == []


class _SpoofHandler(BaseHTTPRequestHandler):
    """Impersonates a PPU: copies the real device identity, records requests."""

    seen: list[str] = []
    device_id = DEVICE

    def log_message(self, *_args):
        return

    def _reply(self, status: int, payload: dict, extra: dict[str, str] | None = None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        self.seen.append(self.path + " " + str(self.headers.get("Authorization")))
        if self.path == "/v1/auth/challenge":
            self._reply(200, {"ok": True, "schema": auth.SCHEMA, "device_id": self.device_id,
                              "nonce": "9" * 32, "expires_in_s": 60, "controller_generation": 1})
            return
        self._reply(200, {"bootstrap": {"state": "bootstrap_ready"},
                          "identity": {"device_id": self.device_id}, "runtime": {}},
                    {auth.RESPONSE_HEADER: "v1 mac=" + "0" * 64})


def test_spoofed_endpoint_cannot_learn_or_fake_the_credential(ppu, tmp_path: Path):
    server, _paths = ppu
    _SpoofHandler.seen = []
    _SpoofHandler.device_id = server.device_id()
    spoof = ThreadingHTTPServer(("127.0.0.1", 0), _SpoofHandler)
    thread = threading.Thread(target=spoof.serve_forever, daemon=True)
    thread.start()
    try:
        store, coordinator = _manager(tmp_path, server.server_port,
                                      endpoint_port=spoof.server_address[1])
        store.set("z2", server.device_id(), TOKEN, generation=1)
        with pytest.raises(BootstrapManagerError, match="not authenticated by the paired device"):
            coordinator.create_upload("z2", {"size": 4, "sha256": "0" * 64})
        assert _SpoofHandler.seen and all(TOKEN not in line for line in _SpoofHandler.seen)
        assert any("PLASMA-PPU-HMAC-V1" in line for line in _SpoofHandler.seen)
    finally:
        spoof.shutdown()
        spoof.server_close()
        thread.join(timeout=2)


def test_managed_prefix_signs_the_ppu_local_path(ppu, tmp_path: Path, monkeypatch):
    """The managed ingress strips /__plasma/bootstrap; the MAC covers /v1/..."""
    server, paths = ppu
    monkeypatch.setenv(MANAGED_BOOTSTRAP_TRANSPORT_ENV, MANAGED_BOOTSTRAP_TRANSPORT)
    forwarded: list[str] = []

    class StrippingIngress:
        def relay(self, method, path, *, headers, body, timeout_s, max_response_bytes,
                  extra_response_headers=frozenset()):
            assert path.startswith(MANAGED_BOOTSTRAP_PATH_PREFIX + "/v1/")
            local = path[len(MANAGED_BOOTSTRAP_PATH_PREFIX):]
            forwarded.append(local)
            status, raw, response_headers = _http(server.server_port, method, local,
                                                  body=body, headers=headers)
            keep = {key: value for key, value in response_headers.items()
                    if key.lower() == "content-type" or key.lower() in extra_response_headers}
            return status, keep, raw

    client = BootstrapHttpClient("https://ppu-managed.example", 3.0)
    client.client = StrippingIngress()  # type: ignore[assignment]
    status, payload = client.create_upload(TOKEN, server.device_id(),
                                           {"size": 4, "sha256": "0" * 64})
    assert status == 201 and payload["ok"] is True
    assert forwarded == ["/v1/auth/challenge", "/v1/uploads"]
    assert len(_uploads(paths)) == 1


def test_manager_rejects_challenge_for_a_different_device(ppu, tmp_path: Path):
    server, _paths = ppu
    client = BootstrapHttpClient(f"http://127.0.0.1:{server.server_port}", 3.0)
    with pytest.raises(BootstrapCredentialError, match="different PPU device_id"):
        client.status(TOKEN, OTHER_DEVICE)


def test_manager_rejects_unproven_success(ppu, tmp_path: Path):
    server, _paths = ppu

    class DroppingRelay:
        """A relay that strips the PPU proof (e.g. a tampering middlebox)."""
        def relay(self, method, path, *, headers, body, timeout_s, max_response_bytes,
                  extra_response_headers=frozenset()):
            status, raw, response_headers = _http(server.server_port, method, path,
                                                  body=body, headers=headers)
            return status, {"Content-Type": response_headers["Content-Type"]}, raw

    client = BootstrapHttpClient(f"http://127.0.0.1:{server.server_port}", 3.0)
    client.client = DroppingRelay()  # type: ignore[assignment]
    with pytest.raises(BootstrapManagerError, match="not authenticated by the paired device"):
        client.status(TOKEN, server.device_id())
