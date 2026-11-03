"""Fixed-purpose Package unit control helper (Host-only; replaces polkit on Z2 0.105).

Real Unix socket + SO_PEERCRED; systemctl is a recording fake or the
FakeSystemd that really runs the entry stub. No Z2 / systemd / root.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_package_launcher as launcher  # noqa: E402
import ppu_package_unit_helper as helper_mod  # noqa: E402
import ppu_package_units as units  # noqa: E402
from .test_ppu_stage_c_production_integration import (  # noqa: E402
    FakeSystemd, RES, dispatch, directives,
)
from .test_ppu_asset_execution_gate1 import JOB, _ready_fixture  # noqa: E402

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or os.geteuid() == 0,
                                reason="Linux SO_PEERCRED, non-root")
UNIT = f"plasma-package@{JOB}.service"


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if args[0] == "show":
            return subprocess.CompletedProcess(args, 0, "ActiveState=active\nSubState=running\n"
                                               "MainPID=4242\nTasksCurrent=1\nSecret=leak\n", "")
        if args[0] == "list-units":
            return subprocess.CompletedProcess(args, 0, f"{UNIT} loaded active\nssh.service loaded active\n"
                                               "plasma-site-worker.service loaded active\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")


class Rig:
    def __init__(self, tmp_path, systemctl=None, runtime_pid=None):
        self.spec_dir = tmp_path / "specs"
        self.spec_dir.mkdir(exist_ok=True)
        self.systemctl = systemctl or Recorder()
        self.pid = {"v": os.getpid() if runtime_pid is None else runtime_pid}
        self.helper = helper_mod.PackageUnitHelper(runtime_pid=lambda: self.pid["v"],
                                                   runtime_uid=os.getuid(), spec_dir=self.spec_dir,
                                                   systemctl=self.systemctl)
        self.sock = tmp_path / "helper.sock"
        self.server = helper_mod.HelperServer(self.helper, self.sock)
        self.server.start()
        self.client = helper_mod.HelperSystemctl(self.sock, timeout_s=20)

    def spec(self, job=JOB, mode=0o644):
        path = self.spec_dir / f"{job}.json"
        path.write_text("{}")
        path.chmod(mode)
        return path

    def raw(self, request):
        import socket
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(str(self.sock))
            s.sendall((json.dumps(request) + "\n").encode())
            return json.loads(s.makefile().readline())

    def close(self):
        self.server.close()


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    yield r
    r.close()


def P(**kw):
    return {"protocol": helper_mod.PROTOCOL, **kw}


def test_helper_builds_fixed_systemctl_argv_for_each_allowed_op(rig):
    rig.spec()
    assert rig.client("start", UNIT).returncode == 0
    assert rig.client("kill", "--signal=15", "--kill-who=all", UNIT).returncode == 0
    assert rig.client("kill", "--signal=9", "--kill-who=all", UNIT).returncode == 0
    shown = rig.client("show", "--property=ActiveState,SubState,MainPID,TasksCurrent", UNIT)
    assert dict(line.split("=", 1) for line in shown.stdout.splitlines()) == {
        "ActiveState": "active", "SubState": "running", "MainPID": "4242", "TasksCurrent": "1"}
    assert rig.client("stop", UNIT).returncode == 0
    listed = rig.client("list-units", "--all", "--plain", "--no-legend", "plasma-package@*")
    assert listed.stdout == f"{UNIT} loaded\n"         # foreign units never reported
    assert rig.systemctl.calls == [
        ("start", UNIT),
        ("kill", "--signal=15", "--kill-who=all", UNIT),
        ("kill", "--signal=9", "--kill-who=all", UNIT),
        ("show", "--property=ActiveState,SubState,MainPID,TasksCurrent", UNIT),
        ("stop", UNIT),
        ("list-units", "--all", "--plain", "--no-legend", "plasma-package@*"),
    ]


@pytest.mark.parametrize("request_", [
    P(op="start", job_id="A" * 32), P(op="start", job_id="1" * 31), P(op="start", job_id="../x"),
    P(op="start", job_id=JOB, unit="ssh.service"), P(op="restart", job_id=JOB),
    P(op="exec", job_id=JOB), P(op="enable", job_id=JOB), P(op="daemon-reload"),
    P(op="kill", job_id=JOB), P(op="list", job_id=JOB), {"op": "start", "job_id": JOB},
    P(op="show", job_id=JOB, property="ExecStart"), [], "x",
])
def test_helper_rejects_anything_outside_the_fixed_ops(rig, request_):
    rig.spec()
    reply = rig.raw(request_)
    assert reply["ok"] is False and reply["error"] == "REQUEST_INVALID"
    assert rig.systemctl.calls == []


@pytest.mark.parametrize("signal_", [1, 2, 10, 19, "9", 9.0, True])
def test_helper_kill_allows_only_sigterm_and_sigkill(rig, signal_):
    reply = rig.raw(P(op="kill", job_id=JOB, signal=signal_))
    assert reply == {"ok": False, "error": "SIGNAL_DENIED"}
    assert rig.systemctl.calls == []


def test_helper_start_requires_runtime_owned_spec(rig):
    assert rig.raw(P(op="start", job_id=JOB)) == {"ok": False, "error": "JOB_SPEC_MISSING"}
    rig.spec(mode=0o666)
    assert rig.raw(P(op="start", job_id=JOB)) == {"ok": False, "error": "JOB_SPEC_UNTRUSTED"}
    path = rig.spec_dir / f"{JOB}.json"
    path.unlink()
    target = rig.spec_dir / "real.json"
    target.write_text("{}"); target.chmod(0o644)
    path.symlink_to(target)
    assert rig.raw(P(op="start", job_id=JOB)) == {"ok": False, "error": "JOB_SPEC_UNTRUSTED"}
    assert rig.systemctl.calls == []


def test_helper_only_answers_the_trusted_runtime_pid(tmp_path):
    r = Rig(tmp_path, runtime_pid=999999)
    try:
        r.spec()
        for op in ("start", "stop", "show"):
            assert r.raw(P(op=op, job_id=JOB)) == {"ok": False, "error": "PEER_NOT_TRUSTED_RUNTIME"}
        assert r.raw(P(op="list")) == {"ok": False, "error": "PEER_NOT_TRUSTED_RUNTIME"}
        # A Package-like child process (not the Runtime MainPID) is refused too.
        r.pid["v"] = os.getpid()
        code = ("import json,socket,sys\ns=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1])\n"
                "s.sendall((json.dumps({'protocol':'plasma.ppu.package-unit-control.v1','op':'list'})+'\\n').encode())\n"
                "print(s.makefile().readline())")
        out = subprocess.run([sys.executable, "-c", code, str(r.sock)], capture_output=True, text=True, timeout=20)
        assert json.loads(out.stdout) == {"ok": False, "error": "PEER_NOT_TRUSTED_RUNTIME"}
        assert r.systemctl.calls == []
    finally:
        r.close()


def test_client_refuses_unexpected_calls_locally(rig):
    for args in (("start", "ssh.service"), ("daemon-reload",), ("kill", "--signal=15", UNIT),
                 ("show", "--property=ExecStart", "ssh.service"), ("enable", UNIT)):
        r = rig.client(*args)
        assert r.returncode == 1 and r.stderr in ("UNIT_DENIED", "CALL_DENIED")
    assert rig.systemctl.calls == []


def test_helper_down_fails_closed(tmp_path):
    client = helper_mod.HelperSystemctl(tmp_path / "missing.sock", timeout_s=2)
    r = client("start", UNIT)
    assert r.returncode == 1 and r.stderr in ("FileNotFoundError", "ConnectionRefusedError")


def test_spawner_end_to_end_through_helper(tmp_path):
    parts = [("tool", "python", [], {"python/main.py": b"print('via-helper')\n",
                                     "config/plasma-package-resources.json": RES % 10})]
    co, requests, owner, _ = _ready_fixture(tmp_path / "set", parts=parts)
    fake = FakeSystemd(tmp_path, co.paths.product_root / "assets/staged")
    r = Rig(tmp_path, systemctl=fake)
    try:
        spawner = launcher.SystemdUnitSpawner(package_uid=os.geteuid() + 4242, spec_dir=r.spec_dir,
                                              output_root=tmp_path / "run-pkg", systemctl=r.client)
        receipt = dispatch(co, requests["python"], owner, tmp_path, spawner)["executor_result"]
        assert receipt["result"] == "SUCCEEDED" and "via-helper" in receipt["stdout"]["tail"]
        assert ("start", UNIT) in fake.calls and ("stop", UNIT) in fake.calls
        assert fake.procs == {}
        assert spawner.stop_leftover() == []
    finally:
        r.close()


def test_helper_unit_static_contract():
    text = units.package_control_helper_unit()
    d = directives(text)
    assert d["User"] == ["root"] and d["Group"] == ["plasma"]
    assert d["ExecStart"] == ["/opt/plasma/python/3.12.13/bin/python3 -I -B -S "
                              "/opt/plasma/bootstrap/ppu_package_unit_helper.py"]
    for key, want in {"PrivateNetwork": "yes", "RestrictAddressFamilies": "AF_UNIX",
                      "ProtectSystem": "strict", "ProtectHome": "yes", "PrivateDevices": "yes",
                      "NoNewPrivileges": "yes", "RuntimeDirectoryMode": "0750"}.items():
        assert d[key] == [want], key
    assert "ListenStream" not in text and "ReadWritePaths" not in text
    source = (ROOT / "scripts/ppu_package_unit_helper.py").read_text()
    for banned in ("shell=True", "os.system", "sudo", "pkexec", "eval(", "exec("):
        assert banned not in source
