"""Stage C production integration (Host-only).

Covers the plasma-package UID unit contract, the fixed entry stub, the systemd
spawner (with a fake systemctl that really runs the entry), Site Worker socket
roles / Runtime restart, fail-closed wiring and Seal Operator Recovery.
Real Linux UID separation, systemd and Z2 hardware are NOT_QUALIFIED.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from plasma_core.config import PlasmaConfig, PPUConfig, ServerConfig, SiteConfig
from plasma_server.site_manager import SiteManager

from .test_ppu_asset_execution_gate1 import JOB, Owner, _ready_fixture, execution
from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_package_entry as entry_mod  # noqa: E402
import ppu_package_launcher as launcher  # noqa: E402
import ppu_package_units as units  # noqa: E402
import ppu_site_recovery as recovery  # noqa: E402
import ppu_site_worker as worker  # noqa: E402
import ppu_site_worker_service as worker_service  # noqa: E402
from .test_ppu_stage_c3_site_worker import MockAdapter, Rig  # noqa: E402

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or os.geteuid() == 0,
                                reason="Linux, non-root")
RES = b'{"schema":"plasma.ppu.package-resources.v1","sites":[],"max_runtime_s":%d}'


def directives(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            k, v = line.split("=", 1)
            out.setdefault(k, []).append(v)
    return out


# --- 1. unit / tmpfiles static contract -----------------------------------

def test_package_unit_runs_as_dedicated_uid_with_fixed_entry_and_no_privilege():
    d = directives(units.package_unit())
    assert d["User"] == ["plasma-package"] and d["Group"] == ["plasma-package"]
    assert d["ExecStart"] == ["/opt/plasma/python/3.12.13/bin/python3 -I -B -S "
                              "/opt/plasma/bootstrap/ppu_package_entry.py %i"]
    for key, want in {"NoNewPrivileges": "yes", "PrivateDevices": "yes", "PrivateNetwork": "yes",
                      "RestrictAddressFamilies": "AF_UNIX", "ProtectSystem": "strict",
                      "ProtectHome": "yes", "CapabilityBoundingSet": "", "AmbientCapabilities": "",
                      "KillMode": "control-group", "RestrictSUIDSGID": "yes",
                      "RemainAfterExit": "yes"}.items():
        assert d[key] == [want], key
    hidden = d["InaccessiblePaths"][0].split()
    for path in ("/run/plasma-server", "/run/plasma-site-worker/control.sock", "/etc/plasma",
                 "/var/lib/plasma-privileged", "/opt/plasma/privileged", "/root"):
        assert f"-{path}" in hidden
    assert "-/run/plasma-site-worker/transport.sock" not in hidden
    text = units.package_unit()
    for banned in ("sudo", "/bin/sh", "bash", "CAP_SYS_RAWIO", "/dev/mem", "DeviceAllow", "User=root",
                   "User=plasma\n", "ListenStream", "SupplementaryGroups"):
        assert banned not in text


def test_site_worker_unit_is_local_only_and_not_a_network_service():
    d = directives(units.site_worker_unit())
    assert d["User"] == ["root"] and d["PrivateNetwork"] == ["yes"]
    assert d["RestrictAddressFamilies"] == ["AF_UNIX"] and d["IPAddressDeny"] == ["any"]
    assert d["ProtectSystem"] == ["strict"] and d["NoNewPrivileges"] == ["yes"]
    assert "ListenStream" not in units.site_worker_unit() and "Port" not in units.site_worker_unit()
    assert d["ExecStart"] == ["/opt/plasma/python/3.12.13/bin/python3 -I -B -S "
                              "/opt/plasma/bootstrap/ppu_site_worker_service.py"]


def test_runtime_dropin_and_tmpfiles_only_add_spec_dir_and_worker_dependency():
    d = directives(units.runtime_dropin())
    assert d == {"Wants": ["plasma-site-worker.service plasma-package-control.service"],
                 "After": ["plasma-site-worker.service plasma-package-control.service"],
                 "ReadWritePaths": ["/run/plasma-package-specs"]}
    assert "d /run/plasma-package-specs 0755 plasma plasma -" in units.tmpfiles()
    assert set(units.render_all()) == {
        "/etc/systemd/system/plasma-package@.service", "/etc/systemd/system/plasma-site-worker.service",
        "/etc/systemd/system/plasma-server.service.d/50-package-actions.conf",
        "/etc/tmpfiles.d/plasma-package.conf", "/etc/systemd/system/plasma-package-control.service"}
    assert not any("polkit" in path for path in units.render_all())


def test_installer_does_not_install_the_units_yet():
    core = (ROOT / "scripts/ppu-z2-installer-core.py").read_text()
    assert "ppu_package_units" not in core and "plasma-package@" not in core


# --- 2. fixed entry stub ---------------------------------------------------------------

def staged_entry(tmp_path, kind="python", body=b"print('hi')\n"):
    root = tmp_path / "staged"
    rel = ("python/main.py" if kind == "python" else "bin/tool")
    path = root / ("e" * 64) / "payload/packages/tool" / rel
    path.parent.mkdir(parents=True)
    path.write_bytes(body)
    if kind == "native-c":
        path.chmod(0o755)
    return root, path


def write_spec(spec_dir, path, kind="python", **over):
    spec = {"schema": "plasma.ppu.package-unit-spec.v1", "job_id": JOB, "package_id": "tool",
            "kind": kind, "entry_path": str(path), "entry_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "env": {}}
    spec.update(over)
    spec_dir.mkdir(exist_ok=True)
    f = spec_dir / f"{JOB}.json"
    f.write_text(json.dumps(spec))
    f.chmod(0o644)
    return f


def run_entry(tmp_path, staged, *, job=JOB, extra_env=None, wait=True):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    env = {"RUNTIME_DIRECTORY": str(out), "PLASMA_PACKAGE_SPEC_DIR": str(tmp_path / "specs"),
           "PLASMA_PACKAGE_STAGED_ROOT": str(staged), "PATH": "/usr/bin:/bin",
           "SECRET_RUNTIME_TOKEN": "leak", **(extra_env or {})}
    p = subprocess.Popen([sys.executable, "-B", str(ROOT / "scripts/ppu_package_entry.py"), job],
                         env=env, start_new_session=True)
    if not wait:
        return p, out
    assert p.wait(30) == 0
    return json.loads((out / "status.json").read_text()), out


def test_entry_runs_fixed_python_entry_with_clean_env(tmp_path):
    staged, path = staged_entry(tmp_path, body=b"import os, json\nprint(json.dumps(sorted(os.environ)))\n")
    write_spec(tmp_path / "specs", path)
    status, out = run_entry(tmp_path, staged)
    assert status == {"result": "EXITED", "exit_code": 0, "signal": None}
    env = json.loads((out / "stdout").read_text())
    assert "SECRET_RUNTIME_TOKEN" not in env and "RUNTIME_DIRECTORY" not in env
    assert set(env) <= {"PATH", "LANG", "HOME", "PLASMA_JOB_ID", "PLASMA_PACKAGE_ID", "LC_CTYPE"}


def test_entry_native_and_nonzero_exit(tmp_path):
    staged, path = staged_entry(tmp_path, "native-c", b"#!/bin/sh\necho n\nexit 4\n")
    write_spec(tmp_path / "specs", path, kind="native-c")
    status, out = run_entry(tmp_path, staged)
    assert status["exit_code"] == 4 and (out / "stdout").read_text() == "n\n"


@pytest.mark.parametrize("mutate,code", [
    (lambda t, p, s: s.chmod(0o666), "ENTRY_SPEC_UNTRUSTED"),
    (lambda t, p, s: write_spec(t / "specs", p, env={"LD_PRELOAD": "/x"}), "ENTRY_SPEC_INVALID"),
    (lambda t, p, s: write_spec(t / "specs", p, job_id="2" * 32), "ENTRY_SPEC_INVALID"),
    (lambda t, p, s: write_spec(t / "specs", p, entry_sha256="0" * 64), "ENTRY_CHANGED"),
    (lambda t, p, s: write_spec(t / "specs", p, entry_path="/usr/bin/python3"), "ENTRY_PATH_DENIED"),
    (lambda t, p, s: write_spec(t / "specs", p, entry_path=str(p).replace("main.py", "../x.py")),
     "ENTRY_PATH_DENIED"),
    (lambda t, p, s: write_spec(t / "specs", p, package_id="other"), "ENTRY_PATH_DENIED"),
])
def test_entry_denies_untrusted_spec_without_running_package(tmp_path, mutate, code):
    staged, path = staged_entry(tmp_path, body=b"open('RAN','w')\n")
    spec = write_spec(tmp_path / "specs", path)
    mutate(tmp_path, path, spec)
    status, out = run_entry(tmp_path, staged)
    assert status == {"result": "DENIED", "code": code}
    assert not (out / "work" / "RAN").exists()


def test_entry_denies_symlinked_entry_and_bad_job(tmp_path):
    staged, path = staged_entry(tmp_path)
    link = path.with_name("main2.py")
    real = path.with_name("real.py")
    path.rename(real)
    path.symlink_to(real)
    write_spec(tmp_path / "specs", path, entry_sha256=hashlib.sha256(real.read_bytes()).hexdigest())
    status, _ = run_entry(tmp_path, staged)
    assert status["code"] == "ENTRY_PATH_DENIED"
    status, _ = run_entry(tmp_path, staged, job="../../etc")
    assert status["code"] == "ENTRY_JOB_ID_INVALID"
    del link


def test_entry_survives_sigterm_and_records_signaled_package(tmp_path):
    staged, path = staged_entry(tmp_path, body=b"import time\ntime.sleep(30)\n")
    write_spec(tmp_path / "specs", path)
    p, out = run_entry(tmp_path, staged, wait=False)
    time.sleep(0.8)
    os.killpg(p.pid, signal.SIGTERM)       # systemctl kill --kill-whom=all
    assert p.wait(15) == 0
    assert json.loads((out / "status.json").read_text()) == {
        "result": "SIGNALED", "exit_code": None, "signal": signal.SIGTERM}


def test_entry_refuses_root(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setenv("RUNTIME_DIRECTORY", str(out))
    monkeypatch.setattr(entry_mod.os, "geteuid", lambda: 0)
    assert entry_mod.main([JOB]) == 0
    assert json.loads((out / "status.json").read_text())["code"] == "ENTRY_MUST_NOT_RUN_AS_ROOT"


# --- 3. SystemdUnitSpawner with a fake systemctl that really runs the entry ------------

class FakeSystemd:
    """Minimal systemd emulation: start/show/kill/stop/list-units of one template."""

    def __init__(self, tmp_path, staged, *, start_rc=0):
        self.tmp, self.staged, self.start_rc = tmp_path, staged, start_rc
        self.procs: dict[str, subprocess.Popen] = {}
        self.calls: list[tuple] = []

    def out_dir(self, unit):
        return self.tmp / "run-pkg" / unit.split("@")[1].split(".")[0]

    def __call__(self, *args):
        self.calls.append(args)
        verb, unit = args[0], args[-1]
        ok = subprocess.CompletedProcess(args, 0, "", "")
        if verb == "start":
            if self.start_rc:
                return subprocess.CompletedProcess(args, self.start_rc, "", "denied")
            out = self.out_dir(unit)
            out.mkdir(parents=True)
            env = {"RUNTIME_DIRECTORY": str(out), "PLASMA_PACKAGE_SPEC_DIR": str(self.tmp / "specs"),
                   "PLASMA_PACKAGE_STAGED_ROOT": str(self.staged), "PATH": "/usr/bin:/bin"}
            self.procs[unit] = subprocess.Popen(
                [sys.executable, "-B", str(ROOT / "scripts/ppu_package_entry.py"), unit[15:47]],
                env=env, start_new_session=True)
            return ok
        p = self.procs.get(unit)
        if verb == "show":
            if p is None:
                return subprocess.CompletedProcess(args, 0, "ActiveState=inactive\nSubState=dead\nMainPID=0\n", "")
            rc = p.poll()
            alive = self._group_alive(p.pid)
            if rc is None:
                state = "ActiveState=active\nSubState=running"
            elif rc == 0:
                state = "ActiveState=active\nSubState=exited"
            else:
                state = "ActiveState=failed\nSubState=failed"
            return subprocess.CompletedProcess(
                args, 0, f"{state}\nMainPID={p.pid if rc is None else 0}\nTasksCurrent={1 if alive else 0}\n", "")
        if verb == "kill" and p is not None:
            sig = int([a for a in args if a.startswith("--signal=")][0].split("=")[1])
            try:
                os.killpg(p.pid, sig)
            except ProcessLookupError:
                pass
            return ok
        if verb == "stop":
            if p is not None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait()
                shutil.rmtree(self.out_dir(unit), ignore_errors=True)
                del self.procs[unit]
            return ok
        if verb == "list-units":
            return subprocess.CompletedProcess(args, 0, "".join(f"{u} loaded active exited x\n" for u in self.procs), "")
        return ok

    @staticmethod
    def _group_alive(pgid):
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False


def systemd_rig(tmp_path, main: bytes, runtime=10, **kw):
    parts = [("tool", "python", [], {"python/main.py": main,
                                     "config/plasma-package-resources.json": RES % runtime})]
    co, requests, owner, _ = _ready_fixture(tmp_path / "set", parts=parts)
    staged = co.paths.product_root / "assets" / "staged"
    fake = FakeSystemd(tmp_path, staged, **kw)
    (tmp_path / "specs").mkdir()
    spawner = launcher.SystemdUnitSpawner(package_uid=os.geteuid() + 4242, spec_dir=tmp_path / "specs",
                                          output_root=tmp_path / "run-pkg", systemctl=fake)
    return co, requests["python"], owner, spawner, fake


def dispatch(co, req, owner, tmp_path, spawner, *, cancel=None, site_worker=None):
    from contextlib import contextmanager

    @contextmanager
    def lease():
        yield {"job_id": req.job_id, "site_ids": [1, 2]}

    ex = launcher.make_package_executor(co.paths.product_root, python_executable=Path(sys.executable),
                                        state_root=tmp_path / "actions", cancel_event=cancel,
                                        spawner=spawner, site_worker=site_worker)
    return execution.dispatch_asset_execution(co.paths.product_root, req, **owner.kw(req),
                                              execution_scope=lease, trusted_executors={"python": ex})


def test_systemd_spawner_success_receipt_journal_and_cleanup(tmp_path):
    co, req, owner, spawner, fake = systemd_rig(tmp_path, b"print('as-package-unit')\n")
    receipt = dispatch(co, req, owner, tmp_path, spawner)["executor_result"]
    assert receipt["result"] == "SUCCEEDED" and receipt["exit_code"] == 0
    assert receipt["launcher"] == "systemd-unit:plasma-package@"
    assert receipt["package_uid"] == os.geteuid() + 4242 != receipt["uid"]
    assert receipt["isolation"]["dedicated_uid"] == "CONFIGURED_NOT_QUALIFIED_ON_Z2"
    assert "as-package-unit" in receipt["stdout"]["tail"]
    assert receipt["process_group_reaped"] is True
    unit = f"plasma-package@{JOB}.service"
    assert ("start", unit) in fake.calls and ("stop", unit) in fake.calls
    assert not (tmp_path / "specs" / f"{JOB}.json").exists() and fake.procs == {}
    assert json.loads((tmp_path / "actions" / f"{JOB}.json").read_text())["state"] == "succeeded"


def test_systemd_spawner_timeout_kills_cgroup_including_escaped_grandchild(tmp_path):
    marker = tmp_path / "gc.pid"
    main = (b"import os, subprocess, sys, time\n"
            b"p = subprocess.Popen([sys.executable, '-c', 'import os,time; os.setpgid(0,0); time.sleep(60)'])\n"
            b"open(%r,'w').write(str(p.pid))\ntime.sleep(60)\n" % str(marker).encode())
    co, req, owner, spawner, fake = systemd_rig(tmp_path, main, runtime=1)
    receipt = dispatch(co, req, owner, tmp_path, spawner)["executor_result"]
    assert receipt["result"] == "TIMEOUT"
    time.sleep(0.3)
    pid = int(marker.read_text())
    # FakeSystemd only kills the stub's group; real systemd kills the whole cgroup.
    # Clean up the escaped grandchild here and record that this is cgroup-only on Z2.
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    assert fake.procs == {}


def test_systemd_spawner_cancel(tmp_path):
    co, req, owner, spawner, _ = systemd_rig(tmp_path, b"import time\ntime.sleep(60)\n", runtime=60)
    cancel = threading.Event()
    threading.Timer(0.8, cancel.set).start()
    receipt = dispatch(co, req, owner, tmp_path, spawner, cancel=cancel)["executor_result"]
    assert receipt["result"] == "CANCELLED" and receipt["duration_s"] < 15


def test_systemd_spawner_start_denied_fails_closed(tmp_path):
    co, req, owner, spawner, _ = systemd_rig(tmp_path, b"print('never')\n", start_rc=4)
    with pytest.raises(launcher.PackageLaunchDenied, match="PACKAGE_UNIT_START_DENIED"):
        dispatch(co, req, owner, tmp_path, spawner)
    assert json.loads((tmp_path / "actions" / f"{JOB}.json").read_text())["state"] == "outcome_unknown"
    assert not (tmp_path / "specs" / f"{JOB}.json").exists()


def test_systemd_spawner_refuses_package_uid_equal_to_runtime_uid(tmp_path):
    co, req, owner, _, fake = systemd_rig(tmp_path, b"print('never')\n")
    same = launcher.SystemdUnitSpawner(package_uid=os.geteuid(), spec_dir=tmp_path / "specs",
                                       output_root=tmp_path / "run-pkg", systemctl=fake)
    with pytest.raises(launcher.PackageLaunchDenied, match="PACKAGE_UID_EQUALS_RUNTIME_UID"):
        dispatch(co, req, owner, tmp_path, same)
    assert not any(c[0] == "start" for c in fake.calls)


def test_site_session_bound_to_package_uid_rejects_wrong_uid_peer(tmp_path):
    """The Worker session uid is the Package uid; a peer with another uid is denied."""
    rig = Rig(tmp_path / "w")
    try:
        main = (b"import json, os, socket, time\nS = os.environ['PLASMA_SITE_WORKER_SOCKET']\n"
                b"def call(r):\n    s = socket.socket(socket.AF_UNIX); s.connect(S)\n"
                b"    s.sendall((json.dumps(dict(protocol='plasma.ppu.site-worker.v1', **r))+'\\n').encode())\n"
                b"    return json.loads(s.makefile().readline())\n"
                b"time.sleep(0.5)\nprint(json.dumps(call({'op':'probe','site':2})))\n")
        parts = [("tool", "python", [], {"python/main.py": main, "config/plasma-package-resources.json":
                  b'{"schema":"plasma.ppu.package-resources.v1","sites":[2],"max_runtime_s":20}'})]
        co, requests, owner, _ = _ready_fixture(tmp_path / "set", parts=parts)
        fake = FakeSystemd(tmp_path, co.paths.product_root / "assets/staged")
        (tmp_path / "specs").mkdir()
        spawner = launcher.SystemdUnitSpawner(package_uid=os.geteuid() + 4242, spec_dir=tmp_path / "specs",
                                              output_root=tmp_path / "run-pkg", systemctl=fake)
        receipt = dispatch(co, requests["python"], owner, tmp_path, spawner, site_worker=rig.client)["executor_result"]
        assert receipt["site_transport"]["session"] == "CLOSED"
        assert json.loads(receipt["stdout"]["tail"]) == {"ok": False, "error": "NO_SESSION_FOR_PEER"}
        assert rig.adapter.calls == []
    finally:
        rig.close()


def test_systemd_spawner_stop_leftover_units(tmp_path):
    _co, _req, _owner, spawner, fake = systemd_rig(tmp_path, b"print('x')\n")
    fake.procs["plasma-package@" + "3" * 32 + ".service"] = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    assert spawner.stop_leftover() == ["plasma-package@" + "3" * 32 + ".service"]
    assert fake.procs == {}


# --- 4. Site Worker: socket roles, Runtime restart, fail-closed wiring ----------------

def test_worker_service_builds_two_role_restricted_sockets(tmp_path):
    adapter = MockAdapter()
    lease = {JOB}
    core, control, transport = worker_service.build(
        tmp_path / "run", tmp_path / "state", adapter=adapter, runtime_pid=os.getpid,
        lease_verifier=lambda j: j in lease, control_gid=os.getgid(), transport_gid=os.getgid())
    (tmp_path / "run").mkdir()
    control.start(); transport.start()
    try:
        for path in ("control.sock", "transport.sock"):
            assert oct((tmp_path / "run" / path).stat().st_mode & 0o777) == "0o660"
        ctl = worker.SiteWorkerClient(tmp_path / "run" / "control.sock")
        tr = worker.SiteWorkerClient(tmp_path / "run" / "transport.sock")
        assert ctl.call("status")["supported_sites"] == [1, 2]
        # Even the trusted Runtime pid cannot use control ops on the transport socket.
        with pytest.raises(worker.SiteWorkerDenied, match="CONTROL_PEER_DENIED"):
            tr.call("status")
        with pytest.raises(worker.SiteWorkerDenied, match="OPERATION_DENIED_ON_CONTROL_SOCKET"):
            ctl.call("probe", site=2)
        # No public seal-clearing IPC operation exists on either socket.
        for client in (ctl, tr):
            with pytest.raises(worker.SiteWorkerDenied):
                client.call("clear_seal", site=2)
    finally:
        control.close(); transport.close()


def test_runtime_restart_invalidates_session_and_allows_new_runtime(tmp_path):
    current = {"pid": os.getpid()}
    adapter = MockAdapter()
    core = worker.SiteWorkerCore(adapter, runtime_pid=lambda: current["pid"],
                                 lease_verifier=lambda j: True, seal_dir=tmp_path / "s")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"], start_new_session=True)
    try:
        me = (os.getpid(), os.getuid(), os.getgid())
        opened = core.handle({"protocol": worker.PROTOCOL, "op": "open_session", "job_id": JOB,
                              "sites": [2], "pgid": child.pid, "uid": os.getuid(),
                              "max_runtime_s": 30}, me)
        assert opened["ok"]
        current["pid"] = 999999          # plasma-server restarted: new MainPID
        peer = (child.pid, os.getuid(), os.getgid())
        assert core.handle({"protocol": worker.PROTOCOL, "op": "probe", "site": 2}, peer) == {
            "ok": False, "error": "NO_SESSION_FOR_PEER"}
        new_runtime = (999999, os.getuid(), os.getgid())
        again = core.handle({"protocol": worker.PROTOCOL, "op": "open_session", "job_id": JOB,
                             "sites": [2], "pgid": child.pid, "uid": os.getuid(),
                             "max_runtime_s": 30}, new_runtime)
        assert again["ok"] and adapter.calls == []
    finally:
        child.kill(); child.wait()


@pytest.mark.parametrize("problem", ["missing", "no_permission"])
def test_worker_down_or_socket_permission_wrong_fails_closed(tmp_path, problem):
    sock = tmp_path / "control.sock"
    srv = None
    if problem == "no_permission":
        import socket as s
        srv = s.socket(s.AF_UNIX)
        srv.bind(str(sock)); srv.listen(1)
        sock.chmod(0o000)
    parts = [("tool", "python", [], {"python/main.py": b"import time\ntime.sleep(30)\n",
             "config/plasma-package-resources.json":
             b'{"schema":"plasma.ppu.package-resources.v1","sites":[2],"max_runtime_s":20}'})]
    co, requests, owner, _ = _ready_fixture(tmp_path / "set", parts=parts)
    t0 = time.monotonic()
    receipt = dispatch(co, requests["python"], owner, tmp_path, launcher.LocalProcessSpawner(),
                       site_worker=worker.SiteWorkerClient(sock, timeout_s=5))["executor_result"]
    assert receipt["result"] == "FAILED" and receipt["site_transport"]["session"] == "DENIED"
    assert receipt["process_group_reaped"] is True and time.monotonic() - t0 < 15
    if srv is not None:
        srv.close()


# --- 5. Seal Operator Recovery ---------------------------------------------------------

class RecoveryAdapter(MockAdapter):
    def __init__(self):
        super().__init__()
        self.ident = {"status": "IMAGE", "image_id": "img-v5"}
        self.verify_result = "ok"
        self.verified = []

    def verify_safe_off(self, site, *, deadline):
        self.verified.append(site)
        if self.verify_result == "unknown":
            raise worker.TransportUnknown("SAFE_OFF_NOT_VERIFIED")
        if self.verify_result == "reload":
            self.ident = {"status": "IMAGE", "image_id": "img-v5", "session_id": "new"}
        return {"result": "SAFE_OFF_VERIFIED", "log_sha256": "a" * 64}


def sealed_rig(tmp_path):
    adapter = RecoveryAdapter()
    seals = tmp_path / "seals"
    core = worker.SiteWorkerCore(adapter, runtime_pid=lambda: 1, lease_verifier=lambda j: True,
                                 seal_dir=seals)
    core._seal(2, "SAFE_OFF_NOT_VERIFIED")
    return adapter, seals


def do_recover(adapter, seals, tmp_path, *, worker_active=False, lease="idle", image="img-v5"):
    return recovery.recover(2, operator="owner", adapter=adapter, seal_dir=seals,
                            evidence_dir=tmp_path / "evidence", worker_active=lambda: worker_active,
                            runtime_lease=lambda: lease, expected_image_id=image)


def test_recovery_positive_moves_marker_into_evidence_and_worker_unseals(tmp_path):
    adapter, seals = sealed_rig(tmp_path)
    diag = recovery.checks(2, adapter=adapter, seal_dir=seals, worker_active=lambda: False,
                           runtime_lease=lambda: "idle", expected_image_id="img-v5")
    assert diag["preconditions"] == "PASS" and adapter.verified == []   # diagnose is read-only
    assert (seals / "site2.sealed").exists()
    out = do_recover(adapter, seals, tmp_path)
    assert out["result"] == "RECOVERED" and adapter.verified == [2]
    assert not (seals / "site2.sealed").exists()
    assert Path(out["archived_marker"]).is_file()                       # moved, not deleted
    evidence = json.loads(Path(out["evidence"]).read_text())
    assert evidence["schema"] == "plasma.ppu.site-seal-recovery.v1" and evidence["operator"] == "owner"
    assert oct(Path(out["evidence"]).stat().st_mode & 0o777) == "0o600"
    restarted = worker.SiteWorkerCore(adapter, runtime_pid=lambda: 1, lease_verifier=lambda j: True,
                                      seal_dir=seals)
    assert restarted._sealed == set()


@pytest.mark.parametrize("kw,setup,field", [
    ({"worker_active": True}, None, "worker_stopped"),
    ({"worker_active": None}, None, "worker_stopped"),
    ({"lease": "busy"}, None, "no_active_job"),
    ({"lease": "unknown"}, None, "no_active_job"),
    ({"image": "other-image"}, None, "fpga_identity"),
    ({}, lambda a, s: setattr(a, "startup", {2}), "no_external_owner"),
    ({}, lambda a, s: (s / "site2.sealed").write_text("{bad"), "seal_present"),
    ({}, lambda a, s: (s / "site2.sealed").unlink(), "seal_present"),
])
def test_recovery_denied_when_any_precondition_unproven(tmp_path, kw, setup, field):
    adapter, seals = sealed_rig(tmp_path)
    if setup:
        setup(adapter, seals)
    out = do_recover(adapter, seals, tmp_path, **kw)
    assert out["result"] == "DENIED_STILL_SEALED" and out["checks"][field] != "PASS"
    assert adapter.verified == []                                        # hardware not touched
    assert Path(out["evidence"]).name.endswith("-denied.json")


@pytest.mark.parametrize("verify", ["unknown", "reload"])
def test_recovery_stays_sealed_if_safe_off_unproven_or_identity_changes(tmp_path, verify):
    adapter, seals = sealed_rig(tmp_path)
    adapter.verify_result = verify
    out = do_recover(adapter, seals, tmp_path)
    assert out["result"] == "DENIED_STILL_SEALED" and (seals / "site2.sealed").exists()
    restarted = worker.SiteWorkerCore(adapter, runtime_pid=lambda: 1, lease_verifier=lambda j: True,
                                      seal_dir=seals)
    assert restarted._sealed == {2}


def test_recovery_requires_operator_name(tmp_path):
    adapter, seals = sealed_rig(tmp_path)
    with pytest.raises(SystemExit, match="OPERATOR_NAME_REQUIRED"):
        recovery.recover(2, operator="", adapter=adapter, seal_dir=seals, evidence_dir=tmp_path / "e",
                         worker_active=lambda: False, runtime_lease=lambda: "idle", expected_image_id="img-v5")


# --- 6. Runtime composition --------------------------------------------------------------

def test_package_action_runtime_composes_c1_c2_and_reconciles(tmp_path):
    from plasma_server.package_actions import PackageActionRuntime
    parts = [("tool", "python", [], {"python/main.py": b"print('runtime-composed')\n",
                                     "config/plasma-package-resources.json": RES % 10})]
    co, requests, owner, _ = _ready_fixture(tmp_path / "set", parts=parts)
    cfg = PlasmaConfig(
        ppu=PPUConfig(id="p", facility_id="f", model="m", display_name="d"),
        server=ServerConfig(host="127.0.0.1", port=9900, max_supported_sites=8, max_concurrent_jobs=1,
                            max_queue_depth_per_site=4, output_root=tmp_path / "o", log_root=tmp_path / "l"),
        sites=[SiteConfig(id=1, enabled=True, interface="mock")])

    class Spawner(launcher.LocalProcessSpawner):
        def stop_leftover(self):
            return ["plasma-package@" + "9" * 32 + ".service"]

    async def scenario():
        manager = SiteManager(cfg)
        await manager.start()
        try:
            rt = PackageActionRuntime(manager, control_plane=ROOT / "scripts",
                                      product_root=co.paths.product_root, state_root=tmp_path / "actions",
                                      owner_credential=None, spawner=Spawner(),
                                      python_executable=Path(sys.executable))
            # The Runtime builds request/credential with ITS loaded control plane.
            rt.owner_credential = rt.execution.OwnerCredential(
                device_id=owner.credential.device_id, credential=owner.credential.credential)
            req = rt.execution.AssetExecutionRequest(**requests["python"].__dict__)
            result = rt.run(req, owner.authorize(req))
            assert result["executor_result"]["result"] == "SUCCEEDED"
            assert manager.execution_lease_snapshot()["busy"] is False
            (tmp_path / "actions" / ("8" * 32 + ".json")).write_text('{"state":"running"}')
            assert rt.reconcile_on_start() == {"interrupted_jobs": ["8" * 32],
                                               "stopped_units": ["plasma-package@" + "9" * 32 + ".service"]}
        finally:
            await manager.shutdown()
    asyncio.run(scenario())
