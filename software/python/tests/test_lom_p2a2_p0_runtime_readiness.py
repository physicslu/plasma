"""LOM-P2A-2 P0 work 1: the kit's local Runtime check is read-only G13 readiness.

The kit is not the controller: it must never sign, never read the controller
record and never pass against an unauthenticated (host-lab) Gateway. The signed
PS loopback is the Manager's controller-authorized acceptance; its normal,
unauthorized, wrong-signature, revoked, response-forgery and restart cases are
covered here against the real Bootstrap admission socket and G13 mixin.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from plasma_manager import bootstrap_request_auth as manager_auth
from plasma_manager.bootstrap import BootstrapManagerError, ControllerReplacedError

from . import lom_p0_lab
from .lom_p0_lab import LOOPBACK, ROOT, GatewayRoutes, close_lab, make_lab

readiness = lom_p0_lab.load_script("lom_p0_runtime_local_readiness", "ppu_runtime_local_readiness.py")
Z2_PS = ROOT / "scripts" / "plasmactl-z2-ps"
LOOPBACK_BODY = {"endpoint": "ps", "test_id": "kit-p0", "sequence": 1, "pattern": "zero", "seed": "",
                 "payload_length": 1, "payload_base64": "AA==", "tx_crc32": "d202ef8d",
                 "timeout_ms": 5000}


@pytest.fixture
def lab(tmp_path: Path):
    lab = make_lab(tmp_path)
    lab.start_ppu()
    try:
        yield lab
    finally:
        close_lab(lab)


def _signed_loopback(lab, coordinator):
    return lab.gateway_client(coordinator).relay(
        "POST", LOOPBACK, headers={"Content-Type": "application/json"},
        body=json.dumps(LOOPBACK_BODY).encode(), timeout_s=10.0, max_response_bytes=65536)


# --- kit local readiness (read-only) ---------------------------------------------

def test_readiness_passes_with_an_enrolled_controller_using_get_only(lab):
    _store, coordinator = lab.manager("a")
    lab.enroll(coordinator)
    evidence = readiness.check(lab.gateway_url(), lab.bootstrap_url())
    assert evidence["result"] == "PASS"
    assert evidence["g13"]["controller_generation"] == 1
    assert evidence["g13"]["bound_to_bootstrap_identity"] is True
    assert evidence["http_methods_used"] == ["GET"]
    assert evidence["signed_ps_loopback"] == "DELEGATED_TO_MANAGER_ACCEPTANCE"
    assert evidence["controller_credential_access"] == "NONE"
    assert GatewayRoutes.loopbacks == []                 # no write of any kind


def test_readiness_passes_on_a_fresh_ppu_without_controller(lab):
    evidence = readiness.check(lab.gateway_url(), lab.bootstrap_url())
    assert evidence["g13"]["controller_generation"] == 0


def test_readiness_fails_against_an_unauthenticated_host_lab_gateway(tmp_path):
    lab = make_lab(tmp_path, gateway_cls=lom_p0_lab.HostLabGateway, host_lab=True)
    lab.start_ppu()
    try:
        with pytest.raises(readiness.ReadinessFailed, match="G13 controller challenge"):
            readiness.check(lab.gateway_url(), lab.bootstrap_url())
    finally:
        close_lab(lab)


def test_readiness_fails_when_the_admission_socket_is_gone(lab):
    lab.paths.admission_socket.unlink()
    with pytest.raises(readiness.ReadinessFailed, match="HTTP 503"):
        readiness.check(lab.gateway_url(), lab.bootstrap_url())


def test_readiness_fails_when_gateway_is_not_ready(lab):
    GatewayRoutes.ready = {"gateway": "alive", "execution": "blocked"}
    with pytest.raises(readiness.ReadinessFailed, match="alive/ready"):
        readiness.check(lab.gateway_url(), lab.bootstrap_url())


def test_readiness_fails_when_challenge_is_for_another_device(lab, tmp_path):
    # A second, independent Bootstrap (different machine identity) answers /v1/status.
    other_root = tmp_path / "other"
    other_root.mkdir()
    (other_root / "machine-id").write_text("f" * 32 + "\n", encoding="utf-8")
    other_paths = lom_p0_lab.service.ServicePaths(
        product_root=other_root / "product", state_root=other_root / "state",
        machine_id_path=other_root / "machine-id",
        bootstrap_script=ROOT / "scripts" / "ppu-bootstrap.py",
        kit_tool=ROOT / "scripts" / "ppu-bootstrap-kit.py",
        admission_socket=other_root / "adm.sock", seal_dir=other_root / "seals",
        runtime_control_socket=other_root / "control.sock", reload_fence=other_root / "mmio.lock",
        button_profile=other_root / "none.json", site_recovery_script=other_root / "none.py")
    other = lom_p0_lab.service.BootstrapHTTPServer(("127.0.0.1", 0), paths=other_paths,
                                                    base_module=lom_p0_lab.bootstrap_base)
    import threading
    threading.Thread(target=other.serve_forever, daemon=True).start()
    try:
        with pytest.raises(readiness.ReadinessFailed, match="not bound to this PPU"):
            readiness.check(lab.gateway_url(), f"http://127.0.0.1:{other.server_port}")
    finally:
        other.shutdown()
        other.server_close()


def test_readiness_cli_emits_json_and_exit_code(lab, capsys):
    assert readiness.main(["--gateway", lab.gateway_url(), "--bootstrap", lab.bootstrap_url()]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "PASS"
    GatewayRoutes.ready = {}
    assert readiness.main(["--gateway", lab.gateway_url(), "--bootstrap", lab.bootstrap_url()]) == 1
    assert json.loads(capsys.readouterr().out)["result"] == "FAIL"


def test_readiness_tool_never_touches_controller_credentials():
    source = (ROOT / "scripts" / "ppu_runtime_local_readiness.py").read_text(encoding="utf-8")
    code = source.split('"""', 2)[2]          # executable part, after the module docstring
    for forbidden in ("controller.json", "plasma-bootstrap/controller", "control-token",
                      "Authorization", "credential\"", "sign_request", "hmac", "POST", "PUT"):
        assert forbidden not in code, forbidden


def test_kit_verify_no_longer_sends_an_unsigned_loopback_write():
    source = Z2_PS.read_text(encoding="utf-8")
    verify = source[source.index("verify_runtime() {"):source.index("show_status() {")]
    assert "diagnostics/loopback" not in verify
    assert "--data" not in verify and "curl" not in verify.split("verify_p3_runtime_activation_contract")[1]
    assert '"$readiness_tool" --gateway "$base"' in verify
    assert 'readiness_tool="${PLASMA_Z2_RUNTIME_READINESS_TOOL:-$script_dir/ppu_runtime_local_readiness.py}"' in source
    for forbidden in ("controller.json", "plasma-bootstrap/controller", "--host-lab-unauthenticated-writes"):
        assert forbidden not in source


def test_every_kit_assembly_ships_the_readiness_tool():
    name = "ppu_runtime_local_readiness.py"
    for path in (".github/workflows/z2-ps-release.yml", ".github/workflows/z2like-demo-qemu.yml"):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert f'cp scripts/{name} "$root/scripts/{name}"' in text, path
    assert f'"{name}",' in (ROOT / "scripts" / "z2like-demo-qemu-build-kit.py").read_text(encoding="utf-8")
    assert f'scripts / "{name}"' in (ROOT / "scripts" / "ppu-bootstrap-kit.py").read_text(encoding="utf-8")


# --- Manager-side signed PS loopback (the remote, authorized E2E) -----------------

def test_signed_loopback_normal_is_proven_by_the_ppu(lab):
    _store, coordinator = lab.manager("a")
    lab.enroll(coordinator)
    status, headers, body = _signed_loopback(lab, coordinator)
    assert status == 200 and json.loads(body)["loopback"]["rx_crc32"] == "d202ef8d"
    assert manager_auth.RESPONSE_HEADER in headers
    assert len(GatewayRoutes.loopbacks) == 1


def test_unsigned_and_wrong_signature_loopback_are_refused(lab):
    store, coordinator = lab.manager("a")
    lab.enroll(coordinator)
    from http.client import HTTPConnection
    conn = HTTPConnection("127.0.0.1", lab.gateway.server_port, timeout=10)
    conn.request("POST", LOOPBACK, body=json.dumps(LOOPBACK_BODY), headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    assert response.status == 401 and json.loads(response.read())["error"]["code"] == "CONTROLLER_UNAUTHENTICATED"
    conn.close()
    good = store.record_for("z2")
    store.set("z2", good.device_id, "w" * 64, generation=good.generation)   # wrong key, same generation
    status, _headers, _body = _signed_loopback(lab, coordinator)
    assert status == 401
    assert GatewayRoutes.loopbacks == []


def test_revoked_controller_cannot_run_the_loopback(lab):
    _store_a, manager_a = lab.manager("a")
    lab.enroll(manager_a, "cs-a")
    _store_b, manager_b = lab.manager("b")
    assert lab.enroll(manager_b, "cs-b")["controller_generation"] == 2
    with pytest.raises(ControllerReplacedError):
        _signed_loopback(lab, manager_a)
    status, _h, _b = _signed_loopback(lab, manager_b)
    assert status == 200 and len(GatewayRoutes.loopbacks) == 1


def test_forged_or_missing_response_proof_is_rejected_by_the_manager(lab, monkeypatch):
    _store, coordinator = lab.manager("a")
    lab.enroll(coordinator)
    real = manager_auth.verify_response

    def tampered(**kwargs):
        kwargs["header"] = re.sub(r"[0-9a-f]$", lambda m: "0" if m.group(0) != "0" else "1", kwargs["header"])
        return real(**kwargs)

    monkeypatch.setattr(manager_auth, "verify_response", tampered)
    with pytest.raises(BootstrapManagerError, match="not authenticated by the enrolled PPU"):
        _signed_loopback(lab, coordinator)


def test_credential_and_g13_survive_a_bootstrap_restart(lab):
    store, coordinator = lab.manager("a")
    lab.enroll(coordinator)
    before = store.record_for("z2")
    lab.restart_ppu()                      # same state root; new process-local nonces
    assert store.record_for("z2") == before
    assert coordinator.status("z2")["pairing"]["device_authenticated"] is True
    status, headers, _body = _signed_loopback(lab, coordinator)
    assert status == 200 and manager_auth.RESPONSE_HEADER in headers
    evidence = readiness.check(lab.gateway_url(), lab.bootstrap_url())
    assert evidence["g13"]["controller_generation"] == 1
