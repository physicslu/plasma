"""Stage C Runtime trigger: root operator CLI -> Runtime control op -> C-1/C-2.

Host-only. The root peer check is exercised for denial (tests run non-root)
and patched only to reach the positive path. No Z2 / systemd / hardware.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import time
from pathlib import Path

import pytest

from .ppu_control_plane_fixture import installed_control_plane

from plasma_core.config import PlasmaConfig, PPUConfig, ServerConfig, SiteConfig
from plasma_server import runtime_control
from plasma_server.package_actions import PackageActionRuntime, from_config
from plasma_server.runtime_control import RuntimeControlServer
from plasma_server.site_manager import SiteManager

from .test_ppu_asset_execution_gate1 import JOB, _ready_fixture
from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_package_action as cli  # noqa: E402
import ppu_package_launcher as launcher  # noqa: E402

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or os.geteuid() == 0,
                                reason="Linux, non-root")
RES = b'{"schema":"plasma.ppu.package-resources.v1","sites":[],"max_runtime_s":%d}'
TOKEN = "paired-bootstrap-credential-" + "z" * 20


@pytest.fixture
def device(tmp_path, monkeypatch):
    machine = tmp_path / "machine-id"
    machine.write_text("0123456789abcdef0123456789abcdef\n")
    token = tmp_path / "controller.json"            # LOM-P2A-2 controller record
    token.write_text(json.dumps({"generation": 1, "mode": "NORMAL", "credential": TOKEN}))
    token.chmod(0o600)
    monkeypatch.setattr(cli, "BOOTSTRAP_DIR", ROOT / "scripts")
    monkeypatch.setattr(cli, "CONTROLLER_RECORD", token)
    monkeypatch.setattr(cli, "MACHINE_ID", machine)
    owner = cli._load("t_owner", ROOT / "scripts/ppu_owner_authorization.py")
    ident = cli._load("t_ident", ROOT / "scripts/ppu-bootstrap.py")
    return owner, ident._machine_device_id(machine), token


def ready(tmp_path, main=b"print('triggered')\n", runtime=10):
    parts = [("tool", "python", [], {"python/main.py": main,
                                     "config/plasma-package-resources.json": RES % runtime})]
    co, requests, _owner, _ = _ready_fixture(tmp_path / "set", parts=parts)
    req = requests["python"]
    return co, {k: getattr(req, k) for k in cli.REQUEST_FIELDS}


def owner_auth(owner, dev, request, **over):
    claims = dict(credential=TOKEN, action=owner.EXECUTE, device_id=dev,
                  subject_sha256=request["asset_set_sha256"], transaction_id=request["job_id"],
                  package_identity_sha256=request["package_identity_sha256"])
    claims.update(over)
    return owner.issue(**claims)


# --- 1. root operator CLI verification --------------------------------------------

def test_cli_verifies_owner_auth_and_reissues_under_one_time_credential(tmp_path, device):
    owner, dev, _ = device
    _co, request = ready(tmp_path)
    control = cli.prepare(request, owner_auth(owner, dev, request))
    assert control["operation"] == "package_action" and control["device_id"] == dev
    one_time = control["ephemeral_credential"]
    assert one_time != TOKEN and TOKEN not in json.dumps(control)
    owner.verify(control["authorization"], credential=one_time, action=owner.EXECUTE, device_id=dev,
                 subject_sha256=request["asset_set_sha256"], transaction_id=request["job_id"],
                 package_identity_sha256=request["package_identity_sha256"])
    with pytest.raises(owner.OwnerAuthorizationDenied):   # Bootstrap token does not verify it
        owner.verify(control["authorization"], credential=TOKEN, action=owner.EXECUTE, device_id=dev,
                     subject_sha256=request["asset_set_sha256"], transaction_id=request["job_id"],
                     package_identity_sha256=request["package_identity_sha256"])
    assert cli.prepare(request, owner_auth(owner, dev, request))["ephemeral_credential"] != one_time


@pytest.mark.parametrize("over,code", [
    ({"credential": "forged-credential-" + "q" * 20}, "OWNER_AUTHORIZATION_INVALID"),
    ({"device_id": "ppu-device-" + "e" * 24}, "OWNER_AUTHORIZATION_DEVICE_MISMATCH"),
    ({"transaction_id": "2" * 32}, "OWNER_AUTHORIZATION_TRANSACTION_MISMATCH"),
    ({"subject_sha256": "e" * 64}, "OWNER_AUTHORIZATION_SUBJECT_MISMATCH"),
    ({"package_identity_sha256": "d" * 64}, "OWNER_AUTHORIZATION_PACKAGE_MISMATCH"),
    ({"action": "bundle.install", "package_identity_sha256": None}, "OWNER_AUTHORIZATION_ACTION_MISMATCH"),
])
def test_cli_refuses_unverifiable_owner_authorization(tmp_path, device, over, code):
    owner, dev, _ = device
    _co, request = ready(tmp_path)
    with pytest.raises(cli.ActionDenied, match=code):
        cli.prepare(request, owner_auth(owner, dev, request, **over))


def test_cli_refuses_bad_request_and_untrusted_token(tmp_path, device):
    owner, dev, token = device
    _co, request = ready(tmp_path)
    with pytest.raises(cli.ActionDenied, match="REQUEST_INVALID"):
        cli.prepare({**request, "argv": ["sh"]}, owner_auth(owner, dev, request))
    token.chmod(0o644)
    with pytest.raises(cli.ActionDenied, match="BOOTSTRAP_CREDENTIAL_UNTRUSTED"):
        cli.prepare(request, owner_auth(owner, dev, request))


def test_cli_requires_root():
    assert cli.main(["run", "--request", "r", "--authorization", "a"]) == 77
    assert cli.main(["run"]) == 64


# --- 2/3. Runtime control op + end-to-end ------------------------------------------

def config(tmp_path):
    return PlasmaConfig(
        ppu=PPUConfig(id="p", facility_id="f", model="m", display_name="d"),
        server=ServerConfig(host="127.0.0.1", port=9900, max_supported_sites=8, max_concurrent_jobs=1,
                            max_queue_depth_per_site=4, output_root=tmp_path / "o", log_root=tmp_path / "l"),
        sites=[SiteConfig(id=1, enabled=True, interface="mock")])


def call(sock_path: Path, payload: dict, *, close_after_send=False, timeout=30) -> dict | None:
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(timeout)
        s.connect(str(sock_path))
        s.sendall((json.dumps(payload) + "\n").encode())
        if close_after_send:
            return None
        return json.loads(s.makefile().readline())


def scenario(tmp_path, body, *, root_peer=True, enabled=True, monkeypatch=None):
    co = body["co"]

    async def run():
        manager = SiteManager(config(tmp_path))
        await manager.start()
        rt = (PackageActionRuntime(manager, control_plane=ROOT / "scripts", product_root=co.paths.product_root,
                                   state_root=tmp_path / "actions", owner_credential=None,
                                   spawner=launcher.LocalProcessSpawner(),
                                   python_executable=Path(sys.executable)) if enabled else None)
        server = RuntimeControlServer(manager, tmp_path / "control.sock", rt)
        await server.start()
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, body["client"], tmp_path / "control.sock", manager)
        finally:
            await server.close()
            await manager.shutdown()

    if root_peer:
        monkeypatch.setattr(runtime_control, "_peer_uid", lambda writer: 0)
    return asyncio.run(run())


def test_runtime_package_action_denied_for_non_root_peer(tmp_path, device, monkeypatch):
    owner, dev, _ = device
    co, request = ready(tmp_path)
    control = cli.prepare(request, owner_auth(owner, dev, request))
    reply = scenario(tmp_path, {"co": co, "client": lambda p, m: call(p, control)}, root_peer=False,
                     monkeypatch=monkeypatch)
    assert reply["ok"] is False and "local root operator" in reply["error"]["message"]
    assert not (tmp_path / "actions" / f"{JOB}.json").exists()


def test_runtime_package_action_disabled_by_default(tmp_path, device, monkeypatch):
    owner, dev, _ = device
    co, request = ready(tmp_path)
    control = cli.prepare(request, owner_auth(owner, dev, request))
    reply = scenario(tmp_path, {"co": co, "client": lambda p, m: call(p, control)}, enabled=False,
                     monkeypatch=monkeypatch)
    assert reply["ok"] is False and "not enabled" in reply["error"]["message"]


def test_runtime_package_action_end_to_end_and_single_use(tmp_path, device, monkeypatch):
    owner, dev, _ = device
    co, request = ready(tmp_path)
    auth = owner_auth(owner, dev, request)

    def client(path, manager):
        first = call(path, cli.prepare(request, auth))
        busy_after = manager.execution_lease_snapshot()["busy"]
        second = call(path, cli.prepare(request, auth))        # same job_id again
        tampered = cli.prepare(request, auth)
        tampered["authorization"]["mac"] = "0" * 64
        third = call(path, tampered)
        extra = call(path, {**cli.prepare(request, auth), "argv": ["sh"]})
        return first, busy_after, second, third, extra

    first, busy_after, second, third, extra = scenario(
        tmp_path, {"co": co, "client": client}, monkeypatch=monkeypatch)
    assert first["ok"] is True
    receipt = first["result"]["executor_result"]
    assert receipt["result"] == "SUCCEEDED" and "triggered" in receipt["stdout"]["tail"]
    assert first["result"]["job_id"] == JOB and busy_after is False
    assert second["ok"] is False and "JOB_ALREADY_RECORDED" in second["error"]["message"]
    assert third["ok"] is False and "OWNER_AUTHORIZATION_INVALID" in third["error"]["message"]
    assert extra["ok"] is False and "fields are invalid" in extra["error"]["message"]


def test_operator_disconnect_cancels_the_action(tmp_path, device, monkeypatch):
    owner, dev, _ = device
    co, request = ready(tmp_path, main=b"import time\ntime.sleep(60)\n", runtime=60)
    control = cli.prepare(request, owner_auth(owner, dev, request))
    journal = tmp_path / "actions" / f"{JOB}.json"

    def client(path, manager):
        call(path, control, close_after_send=True)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if journal.exists() and json.loads(journal.read_text())["state"] != "running":
                break
            time.sleep(0.1)
        return json.loads(journal.read_text())["state"], manager.execution_lease_snapshot()["busy"]

    state, busy = scenario(tmp_path, {"co": co, "client": client}, monkeypatch=monkeypatch)
    assert state == "cancelled" and busy is False


# --- 4. production config wiring ---------------------------------------------------------

def test_from_config_validates_and_wires_helper_spawner(tmp_path):
    import pwd
    me = pwd.getpwuid(os.getuid()).pw_name
    control_plane, product = installed_control_plane(tmp_path)
    cfg = {"schema": "plasma.ppu.package-actions-config.v1", "control_plane": str(control_plane),
           "product_root": str(product), "state_root": str(tmp_path / "state"),
           "python": sys.executable, "package_user": me,
           "helper_socket": str(tmp_path / "helper.sock"), "site_worker_control_socket": None}
    path = tmp_path / "pa.json"
    path.write_text(json.dumps(cfg))
    rt = from_config(object(), path)
    assert type(rt.spawner).__name__ == "SystemdUnitSpawner" and rt.site_worker is None
    assert type(rt.spawner.systemctl).__name__ == "HelperSystemctl"
    cfg["site_worker_control_socket"] = str(tmp_path / "w.sock")
    path.write_text(json.dumps(cfg))
    assert type(from_config(object(), path).site_worker).__name__ == "SiteWorkerClient"
    for bad in ({**cfg, "schema": "x"}, {**cfg, "shell": "/bin/sh"}):
        path.write_text(json.dumps(bad))
        with pytest.raises(RuntimeError, match="PACKAGE_ACTIONS_CONFIG_INVALID"):
            from_config(object(), path)


def test_runtime_server_requires_control_socket_for_package_actions(tmp_path, monkeypatch):
    import plasma_server.runtime_server as rs
    monkeypatch.setattr(rs, "load_config", lambda _p: config(tmp_path))
    with pytest.raises(SystemExit, match="requires --runtime-control-socket"):
        asyncio.run(rs._run(tmp_path / "cfg", None, tmp_path / "pa.json"))


def test_rendered_package_actions_config_is_accepted_by_from_config(tmp_path, monkeypatch):
    import pwd
    import ppu_package_units as units
    cfg = json.loads(units.package_actions_config())
    assert cfg["control_plane"] == "/opt/plasma/bootstrap" and cfg["package_user"] == "plasma-package"
    control_plane, product = installed_control_plane(tmp_path)
    cfg.update(control_plane=str(control_plane), product_root=str(product),
               package_user=pwd.getpwuid(os.getuid()).pw_name)
    path = tmp_path / "pa.json"
    path.write_text(json.dumps(cfg))
    rt = from_config(object(), path)
    assert type(rt.site_worker).__name__ == "SiteWorkerClient"


def test_runtime_server_reads_package_actions_env(tmp_path, monkeypatch):
    import plasma_server.runtime_server as rs
    seen = {}

    async def fake_run(config, control, package_actions):
        seen.update(config=config, control=control, package_actions=package_actions)
    monkeypatch.setattr(rs, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", ["ppu", "--config", "c.yaml", "--runtime-control-socket", "s.sock"])
    monkeypatch.setenv("PLASMA_PACKAGE_ACTIONS_CONFIG", "/etc/plasma/ppu-package-actions.json")
    rs.main()
    assert seen["package_actions"] == Path("/etc/plasma/ppu-package-actions.json")
    monkeypatch.delenv("PLASMA_PACKAGE_ACTIONS_CONFIG")
    rs.main()
    assert seen["package_actions"] is None
