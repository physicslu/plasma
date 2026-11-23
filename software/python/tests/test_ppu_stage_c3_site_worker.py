"""Stage C-3: single-appliance Site Worker (Host-only; real Unix socket + processes).

Mock hardware adapters only. No Z2, MMIO, FPGA, OpenOCD or DUT is touched.
"""
from __future__ import annotations

import hashlib
import json
import re
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_site_worker as worker  # noqa: E402
import ppu_site_adapter_abi5 as abi5  # noqa: E402
from plasma_interfaces.site_worker_c3 import SiteWorkerControlClient

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or os.geteuid() == 0,
                                reason="Linux SO_PEERCRED, non-root")
JOB = "1" * 32
F103 = {"icpn": "STM32F103C8T6", "target_config": "target/stm32f1x.cfg",
        "flash_base": 0x08000000, "flash_size": 0x10000, "erase_granularity": 1024}


def test_control_socket_streams_stage_events_before_final_reply(tmp_path, monkeypatch):
    class FakeCore:
        def handle(self, request, peer, role, event_sink):
            assert role == "control" and request["op"] == "run"
            assert request["observe_stages"] is True
            sequence = 0
            for stage in ("erase", "program", "verify"):
                for state in ("started", "completed"):
                    sequence += 1
                    event_sink({"job_id": JOB, "site_id": 1, "session_id": "session",
                                "sequence": sequence, "stage": stage, "state": state})
            return {"ok": True, "result": {"result": "PASS"}}

    server = worker.SiteWorkerServer(FakeCore(), tmp_path / "stages.sock", role="control")
    monkeypatch.setattr(worker, "peer_credentials", lambda _conn: (os.getpid(), os.getuid(), os.getgid()))

    class FakeConnection:
        def __init__(self, request):
            self.request, self.output = request, b""
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def settimeout(self, _value): pass
        def recv(self, _size):
            request, self.request = self.request, b""
            return request
        def sendall(self, data): self.output += data

    class FakeClientSocket:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def settimeout(self, _value): pass
        def connect(self, _path): pass
        def sendall(self, request):
            connection = FakeConnection(request)
            server._one(connection)
            self.output = connection.output
        def recv(self, _size):
            output, self.output = self.output, b""
            return output

    monkeypatch.setattr("plasma_interfaces.site_worker_c3.socket.socket",
                        lambda *_args, **_kwargs: FakeClientSocket())
    events = []
    result = SiteWorkerControlClient(tmp_path / "stages.sock").call(
        "run", session_id="session", site=1, operation="programming",
        observe_stages=True, stage_event=events.append)
    assert result == {"result": "PASS"}
    assert [(event["stage"], event["state"], event["sequence"]) for event in events] == [
        (stage, state, sequence) for sequence, (stage, state) in enumerate(
            ((stage, state) for stage in ("erase", "program", "verify")
             for state in ("started", "completed")), 1)]


def flash_image(payload: bytes, profile=None, digest=None, load_address=None):
    profile = dict(profile or F103)
    return worker.FlashImage(worker.parse_flash_profile(profile), payload,
                             digest or hashlib.sha256(payload).hexdigest(),
                             profile["flash_base"] if load_address is None else load_address)


class MockAdapter:
    name = "mock-swd"
    supported_sites = frozenset({1, 2})
    operations = frozenset({"probe"})

    def __init__(self):
        self.calls = []
        self.behaviour = "pass"
        self.gate = threading.Event()
        self.started = threading.Event()
        self.startup = set()
        # Root journal snapshot as the C3 core sees it (change detection only).
        self.ident = {"image_id": "any-compatible-image", "session_id": "s1"}

    def identity(self):
        return dict(self.ident)

    def startup_sealed_sites(self):
        return set(self.startup)

    def run(self, site, operation, *, deadline, cancel, image=None, operations=None, flash_range=None):
        self.calls.append((site, operation))
        self.started.set()
        b = self.behaviour
        if b == "block":   # waits for gate, cancel or deadline
            while not self.gate.is_set():
                if cancel.is_set():
                    raise worker.TransportUnknown("CANCELLED_DURING_OPERATION")
                if time.monotonic() >= deadline:
                    raise worker.TransportUnknown("OPERATION_TIMEOUT")
                time.sleep(0.01)
        if b == "deny":
            raise worker.TransportDenied("ADMISSION_DENIED")
        if b == "fail_safe":
            raise worker.TransportFailed("OPERATION_TIMEOUT")
        if b == "unknown":
            raise worker.TransportUnknown("SAFE_OFF_NOT_VERIFIED")
        if b == "crash":
            raise RuntimeError("adapter bug")
        return {"result": "PASS", "dpidr": "0x1ba01477", "safe_off": True}


class Rig:
    def __init__(self, tmp_path, adapter=None):
        self.tmp = tmp_path
        self.adapter = adapter or MockAdapter()
        self.image_root = tmp_path / "normalized-images"
        self.image_root.mkdir(parents=True, exist_ok=True)
        self.lease = {JOB}
        self.sock = tmp_path / "w.sock"
        self.seals = tmp_path / "seals"
        self.start()

    def start(self):
        self.core = worker.SiteWorkerCore(
            self.adapter, runtime_pid=os.getpid, lease_verifier=lambda j, kind: j in self.lease,
            seal_dir=self.seals, image_root=self.image_root)
        self.server = worker.SiteWorkerServer(self.core, self.sock, mode=0o600)
        self.server.start()
        self.client = worker.SiteWorkerClient(self.sock, timeout_s=20)

    def restart(self):  # Worker crash + restart: in-memory sessions are lost
        self.server.close()
        self.start()

    def package(self, body: str, *, new_session=True):
        """A real Package-like process speaking the raw JSON line protocol."""
        code = ("import json,socket,sys,time\n"
                f"S={str(self.sock)!r}\n"
                "def call(req):\n"
                " s=socket.socket(socket.AF_UNIX); s.connect(S)\n"
                " s.sendall((json.dumps(dict(protocol='plasma.ppu.site-worker.v3',**req))+'\\n').encode())\n"
                " d=b''\n"
                " while not d.endswith(b'\\n'):\n"
                "  c=s.recv(65536)\n"
                "  if not c: break\n"
                "  d+=c\n"
                " return json.loads(d)\n"
                "sys.stdin.readline()\n" + body)
        return subprocess.Popen([sys.executable, "-I", "-c", code], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, text=True, start_new_session=new_session)

    def open(self, child, sites=(2,), runtime=30, profile=None):
        return self.client.open_session(job_id=JOB, sites=list(sites), pgid=os.getpgid(child.pid),
                                        uid=os.getuid(), max_runtime_s=runtime, profile=profile)

    @staticmethod
    def reap(*children):
        for child in children:
            child.kill()
            child.wait()
            for stream in (child.stdin, child.stdout):
                if stream:
                    stream.close()

    @staticmethod
    def go(child):
        child.stdin.write("go\n"); child.stdin.flush()
        out, _ = child.communicate(timeout=30)
        return [json.loads(line) for line in out.splitlines() if line.strip()]

    def close(self):
        self.server.close()


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    yield r
    r.close()


PROBE2 = "print(json.dumps(call({'op':'probe','site':2})))\n"


def test_authorized_package_probe_succeeds(rig):
    child = rig.package(PROBE2)
    s = rig.open(child)
    assert s["sites"] == [2] and len(s["session_id"]) == 32
    [reply] = rig.go(child)
    assert reply == {"ok": True, "result": {"adapter": "mock-swd", "dpidr": "0x1ba01477",
                                            "operation": "probe", "result": "PASS",
                                            "safe_off": True, "site": 2}}
    assert rig.client.close_session(s["session_id"]) == {
        "closed": True, "session_id": s["session_id"], "sealed_sites": []}
    assert not (rig.seals / "site2.sealed").exists()


def test_process_outside_the_session_group_is_denied(rig):
    member = rig.package("import time; time.sleep(30)\n")
    rig.open(member)
    stranger = rig.package(PROBE2)          # same uid, different process group
    [reply] = rig.go(stranger)
    assert reply == {"ok": False, "error": "NO_SESSION_FOR_PEER"}
    rig.reap(member)
    assert rig.adapter.calls == []


def test_package_that_escapes_its_session_loses_access(rig):
    # A forked descendant that leaves the registered process group via setsid().
    child = rig.package("import os\npid = os.fork()\nif pid == 0:\n    os.setsid()\n"
                        "    print(json.dumps(call({'op':'probe','site':2})), flush=True)\n"
                        "    os._exit(0)\nos.waitpid(pid, 0)\n")
    rig.open(child)
    [reply] = rig.go(child)
    assert reply == {"ok": False, "error": "NO_SESSION_FOR_PEER"}


def test_site_outside_session_and_unsupported_site_denied(rig):
    child = rig.package("print(json.dumps(call({'op':'probe','site':1})))\n"
                        "print(json.dumps(call({'op':'probe','site':3})))\n")
    rig.open(child, sites=(2,))
    replies = rig.go(child)
    assert [r["error"] for r in replies] == ["SITE_NOT_AUTHORIZED", "SITE_NOT_AUTHORIZED"]
    other = rig.package("import time; time.sleep(5)\n")
    with pytest.raises(worker.SiteWorkerDenied, match="SITE_NOT_SUPPORTED"):
        rig.client.open_session(job_id=JOB, sites=[3], pgid=os.getpgid(other.pid),
                                uid=os.getuid(), max_runtime_s=10)
    rig.reap(other)


@pytest.mark.parametrize("op", ["mmio_write", "mmio_read", "shell", "exec", "reload_fpga", "program"])
def test_operation_outside_adapter_allowlist_denied(rig, op):
    child = rig.package(f"print(json.dumps(call({{'op':{op!r},'site':2}})))\n")
    rig.open(child)
    [reply] = rig.go(child)
    assert reply == {"ok": False, "error": "OPERATION_DENIED"}
    assert rig.adapter.calls == []


def test_extra_claims_in_transport_request_denied(rig):
    child = rig.package("print(json.dumps(call({'op':'probe','site':2,'job_id':'9'*32})))\n"
                        "print(json.dumps(call({'op':'probe','site':2,'address':0x43C01000})))\n")
    rig.open(child)
    assert [r["error"] for r in rig.go(child)] == ["REQUEST_INVALID", "REQUEST_INVALID"]


def test_control_operations_only_from_trusted_runtime_pid(rig):
    body = ("print(json.dumps(call({'op':'open_session','job_id':'1'*32,'sites':[2],"
            "'pgid':os.getpgid(0),'uid':os.getuid(),'max_runtime_s':10})))\n"
            "print(json.dumps(call({'op':'status'})))\n")
    child = rig.package("import os\n" + body)
    replies = rig.go(child)
    assert [r["error"] for r in replies] == ["CONTROL_PEER_DENIED", "CONTROL_PEER_DENIED"]


def test_job_lease_required_at_open_and_rechecked_per_operation(rig):
    rig.lease.clear()
    child = rig.package(PROBE2)
    with pytest.raises(worker.SiteWorkerDenied, match="JOB_LEASE_NOT_HELD"):
        rig.open(child)
    rig.lease.add(JOB)
    rig.open(child)
    rig.lease.clear()                 # C-1 lease released / job expired
    [reply] = rig.go(child)
    assert reply == {"ok": False, "error": "JOB_LEASE_NOT_HELD"}
    assert rig.adapter.calls == []


def test_session_expiry_denies_operations(rig):
    child = rig.package("import time\ntime.sleep(1.3)\n" + PROBE2)
    rig.open(child, runtime=1)
    [reply] = rig.go(child)
    assert reply == {"ok": False, "error": "SESSION_EXPIRED"}


def test_concurrent_operation_on_same_site_is_busy(rig):
    rig.adapter.behaviour = "block"
    child = rig.package("import threading\nout=[]\n"
                        "t=threading.Thread(target=lambda: out.append(call({'op':'probe','site':2})))\n"
                        "t.start(); time.sleep(0.5)\n"
                        "print(json.dumps(call({'op':'probe','site':2})))\n"
                        "t.join(); print(json.dumps(out[0]))\n")
    rig.open(child)
    threading.Timer(1.5, rig.adapter.gate.set).start()
    first, second = rig.go(child)
    assert first == {"ok": False, "error": "SITE_BUSY"}
    assert second["ok"] is True


def test_timeout_seals_site_and_seal_survives_worker_restart(rig):
    rig.adapter.behaviour = "block"
    child = rig.package(PROBE2 + PROBE2)
    s = rig.open(child, runtime=1)
    first, second = rig.go(child)
    assert first == {"ok": False, "error": "OUTCOME_UNKNOWN_SITE_SEALED:OPERATION_TIMEOUT"}
    assert second["error"] in ("SITE_SEALED", "SESSION_EXPIRED")
    assert rig.client.close_session(s["session_id"])["sealed_sites"] == [2]
    rig.restart()
    assert rig.client.call("status")["sealed_sites"] == [2]
    again = rig.package("import time; time.sleep(5)\n")
    with pytest.raises(worker.SiteWorkerDenied, match="SITE_SEALED"):
        rig.open(again)
    rig.reap(again)
    assert (rig.seals / "site2.sealed").is_file()


def test_cancel_by_runtime_close_stops_in_flight_operation_and_seals(rig):
    rig.adapter.behaviour = "block"
    child = rig.package(PROBE2)
    s = rig.open(child, runtime=60)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("r", rig.go(child)))
    t.start()
    assert rig.adapter.started.wait(10)
    closed = rig.client.close_session(s["session_id"])
    t.join(30)
    assert closed["sealed_sites"] == [2]
    assert result["r"] == [{"ok": False, "error": "OUTCOME_UNKNOWN_SITE_SEALED:CANCELLED_DURING_OPERATION"}]


@pytest.mark.parametrize("behaviour,error", [
    ("unknown", "OUTCOME_UNKNOWN_SITE_SEALED:SAFE_OFF_NOT_VERIFIED"),
    ("crash", "OUTCOME_UNKNOWN_SITE_SEALED:UNCLASSIFIED_ADAPTER_EXCEPTION"),
])
def test_unknown_hardware_outcomes_and_software_errors(rig, behaviour, error):
    rig.adapter.behaviour = behaviour
    child = rig.package(PROBE2 + PROBE2)
    rig.open(child)
    first, second = rig.go(child)
    assert first == {"ok": False, "error": error}
    assert second["ok"] is False
    # Neither an unknown transport outcome nor an unclassified Python crash
    # proves SAFE_OFF. Both must seal Site 2 and prevent the second I/O.
    assert len(rig.adapter.calls) == 1
    assert 2 in rig.client.call("status")["sealed_sites"]
    assert (rig.seals / "site2.sealed").is_file()


def test_denied_before_hardware_keeps_site_usable(rig):
    rig.adapter.behaviour = "deny"
    child = rig.package(PROBE2)
    s = rig.open(child)
    # The refusal carries the Worker's structured statement for THIS Job,
    # Site, session and stage; consumers judge it, never the code text.
    assert rig.go(child) == [{"ok": False, "error": "TRANSPORT_DENIED:ADMISSION_DENIED",
                              "safety": {
        "schema": "plasma.ppu.site-safety.v1", "class": "PRE_HARDWARE_DENIED",
        "job_id": JOB, "session_id": s["session_id"], "site": 2, "operation": "probe",
        "stage": "run", "code": "ADMISSION_DENIED", "hardware_touched": False,
        "safe_off": None}}]
    assert rig.client.close_session(s["session_id"])["sealed_sites"] == []
    assert rig.client.call("status")["sealed_sites"] == []
    assert not (rig.seals / "site2.sealed").exists()


def test_failed_with_safe_off_verified_states_it_and_keeps_site_usable(rig):
    rig.adapter.behaviour = "fail_safe"
    child = rig.package(PROBE2)
    s = rig.open(child)
    [reply] = rig.go(child)
    assert reply["error"] == "OPERATION_FAILED_SAFE:OPERATION_TIMEOUT"
    assert reply["safety"] == {
        "schema": "plasma.ppu.site-safety.v1", "class": "FAILED_SAFE_OFF_VERIFIED",
        "job_id": JOB, "session_id": s["session_id"], "site": 2, "operation": "probe",
        "stage": "run", "code": "OPERATION_TIMEOUT", "hardware_touched": True,
        "safe_off": True}
    assert rig.client.close_session(s["session_id"])["sealed_sites"] == []
    assert not (rig.seals / "site2.sealed").exists()


def test_refusals_before_the_adapter_carry_no_safety_statement(rig):
    """SITE_BUSY / lease / session refusals prove nothing about the Site."""
    child = rig.package(PROBE2)
    rig.open(child)
    rig.lease.clear()  # the Job lease ends before run: JOB_LEASE_NOT_HELD
    [reply] = rig.go(child)
    assert reply["ok"] is False and "safety" not in reply
    assert rig.adapter.calls == []


def test_guard_not_durable_prevents_all_hardware_operations(rig, monkeypatch):
    """A storage fault before native admission is a hard stop, not a retry."""
    original = worker.os.fsync
    def refuse_fsync(fd):
        raise OSError("simulated storage I/O failure")
    monkeypatch.setattr(worker.os, "fsync", refuse_fsync)
    child = rig.package(PROBE2)
    rig.open(child)
    assert rig.go(child) == [{
        "ok": False, "error": "OPERATION_GUARD_NOT_DURABLE"
    }]
    assert rig.adapter.calls == []
    assert 2 in rig.client.call("status")["sealed_sites"]
    monkeypatch.setattr(worker.os, "fsync", original)
    rig.restart()
    assert 2 in rig.client.call("status")["sealed_sites"]


def test_crash_leftover_operation_guard_blocks_after_worker_restart(tmp_path):
    """A durable pre-I/O marker survives a Worker death before SAFE_OFF."""
    rig = Rig(tmp_path)
    try:
        rig.core._begin_operation_guard(2)
        marker = rig.seals / "site2.sealed"
        assert marker.is_file()
        assert json.loads(marker.read_text())["code"] == "OPERATION_IN_PROGRESS"
        rig.restart()
        assert 2 in rig.client.call("status")["sealed_sites"]
        child = rig.package("import time; time.sleep(5)\n")
        with pytest.raises(worker.SiteWorkerDenied, match="SITE_SEALED"):
            rig.open(child)
        rig.reap(child)
        assert rig.adapter.calls == []
    finally:
        rig.close()


def test_c3_accepts_any_image_id_but_detects_reload_within_a_session(tmp_path):
    """No static FPGA Image pin: any loaded image is accepted at session open,
    but a Root journal change (FPGA reload) inside the session invalidates it."""
    adapter = MockAdapter()
    adapter.ident = {"image_id": "z2-some-other-build-0123abcd", "session_id": "s9"}
    r = Rig(tmp_path, adapter)
    try:
        child = r.package(PROBE2 + "sys.stdout.flush(); sys.stdin.readline()\n" + PROBE2)
        session = r.open(child)
        child.stdin.write("go\n"); child.stdin.flush()
        first = json.loads(child.stdout.readline())
        assert first["ok"] is True and first["result"]["result"] == "PASS"
        adapter.ident = {"image_id": "z2-some-other-build-0123abcd", "session_id": "s10"}
        child.stdin.write("again\n"); child.stdin.flush()
        second = json.loads(child.stdout.readline())
        assert second == {"ok": False, "error": "SESSION_INVALIDATED_FPGA_IDENTITY_CHANGED"}
        assert adapter.calls == [(2, "probe")]
        assert r.client.close_session(session["session_id"])["sealed_sites"] == []
        r.reap(child)
    finally:
        r.close()


def test_unobservable_fpga_identity_after_operation_seals_site(tmp_path):
    class UnobservableAdapter(MockAdapter):
        def identity(self):
            if self.calls:
                raise RuntimeError("FPGA state cannot be observed after I/O")
            return super().identity()

    r = Rig(tmp_path, UnobservableAdapter())
    try:
        child = r.package(PROBE2)
        session = r.open(child)
        assert r.go(child) == [{
            "ok": False,
            "error": "OUTCOME_UNKNOWN_SITE_SEALED:FPGA_IDENTITY_OBSERVATION_FAILED",
        }]
        assert (r.seals / "site2.sealed").is_file()
        assert r.client.close_session(session["session_id"])["sealed_sites"] == [2]
        r.restart()
        assert 2 in r.core._sealed
    finally:
        r.close()


def test_fpga_reload_during_operation_seals_the_site(tmp_path):
    class ReloadingAdapter(MockAdapter):
        def run(self, site, operation, *, deadline, cancel, image=None, operations=None, flash_range=None):
            self.ident = {"image_id": "reloaded", "session_id": "s2"}
            return super().run(site, operation, deadline=deadline, cancel=cancel)

    adapter = ReloadingAdapter()
    r = Rig(tmp_path, adapter)
    try:
        child = r.package(PROBE2)
        session = r.open(child)
        assert r.go(child) == [{"ok": False, "error":
                                "OUTCOME_UNKNOWN_SITE_SEALED:FPGA_IDENTITY_CHANGED_DURING_OPERATION"}]
        assert r.client.close_session(session["session_id"])["sealed_sites"] == [2]
    finally:
        r.close()


def test_worker_crash_invalidates_sessions(rig):
    child = rig.package(PROBE2)
    rig.open(child)
    rig.restart()
    assert rig.go(child) == [{"ok": False, "error": "NO_SESSION_FOR_PEER"}]


def test_runtime_restart_keeps_in_flight_site_reserved(tmp_path):
    """Do not re-admit an old Runtime's Site while an adapter is still running."""
    class DelayedSafeAdapter(MockAdapter):
        def __init__(self):
            super().__init__()
            self.release = threading.Event()

        def run(self, site, operation, *, deadline, cancel, image=None, operations=None, flash_range=None):
            self.started.set()
            # Simulate an uninterruptible adapter which finishes with proven
            # SAFE_OFF even after the former Runtime loses ownership.
            assert self.release.wait(10), "adapter did not reach SAFE_OFF"
            return {"result": "PASS", "safe_off": True}

    adapter = DelayedSafeAdapter()
    rig = Rig(tmp_path, adapter)
    child = rig.package(PROBE2)
    current = os.getpid()
    new_runtime = current + 9999
    thread = None
    result = {}
    try:
        rig.open(child, sites=(2,))
        thread = threading.Thread(target=lambda: result.setdefault("reply", rig.go(child)))
        thread.start()
        assert adapter.started.wait(8)
        rig.core.runtime_pid = lambda: new_runtime
        req = {"protocol": worker.PROTOCOL, "op": "open_job_session",
               "job_id": JOB, "sites": [2], "max_runtime_s": 30}
        peer = (new_runtime, os.getuid(), os.getgid())
        denied = rig.core.handle(req, peer, "control")
        assert denied == {"ok": False, "error": "SITE_BUSY"}
        assert rig.core._site_owners and len(rig.core._sessions) == 1
        adapter.release.set()
        thread.join(10)
        assert not thread.is_alive()
        assert result["reply"] == [{"ok": False, "error": "SESSION_CLOSED"}]
        opened = rig.core.handle(req, peer, "control")
        assert opened["ok"] is True
        assert list(rig.core._site_owners) == [2]
        closed = rig.core.handle(
            {"protocol": worker.PROTOCOL, "op": "close_session",
             "session_id": opened["result"]["session_id"]}, peer, "control")
        assert closed["result"]["sealed_sites"] == []
        assert not rig.core._site_owners
    finally:
        adapter.release.set()
        if thread is not None:
            thread.join(10)
        rig.close()
        if child.poll() is None:
            rig.reap(child)


def test_external_owner_blocks_only_while_present(tmp_path):
    adapter = MockAdapter()
    adapter.startup = {1}
    r = Rig(tmp_path, adapter)
    try:
        assert r.client.call("status")["sealed_sites"] == []
        with pytest.raises(worker.SiteWorkerDenied, match="EXTERNAL_SITE_OWNER_PRESENT"):
            r.client.open_job_session(job_id=JOB, sites=[1], max_runtime_s=30)
        adapter.startup.clear()
        opened = r.client.open_job_session(job_id=JOB, sites=[1], max_runtime_s=30)
        assert r.client.close_session(opened["session_id"])["sealed_sites"] == []
    finally:
        r.close()


def test_independent_site_sessions_and_overlap_denial(rig):
    a = rig.package("import time; time.sleep(5)\n")
    b = rig.package("import time; time.sleep(5)\n")
    c = rig.package("import time; time.sleep(5)\n")
    try:
        first = rig.open(a, sites=(1,))
        second = rig.open(b, sites=(2,))
        assert first["session_id"] != second["session_id"]
        assert [x["sites"] for x in rig.client.call("status")["sessions"]] == [[1], [2]]
        with pytest.raises(worker.SiteWorkerDenied, match="SITE_BUSY"):
            rig.open(c, sites=(1,))
        rig.client.close_session(first["session_id"])
        with pytest.raises(worker.SiteWorkerDenied, match="SESSION_UNKNOWN"):
            rig.client.close_session(first["session_id"])
        third = rig.open(c, sites=(1,))
        assert [x["sites"] for x in rig.client.call("status")["sessions"]] == [[1], [2]]
        rig.client.close_session(third["session_id"])
        rig.client.close_session(second["session_id"])
        assert rig.client.call("status")["sessions"] == []
    finally:
        rig.reap(a, b, c)


def test_multi_site_package_reserves_all_sites_atomically(rig):
    a = rig.package("import time; time.sleep(5)\n")
    b = rig.package("import time; time.sleep(5)\n")
    try:
        both = rig.open(a, sites=(1, 2))
        with pytest.raises(worker.SiteWorkerDenied, match="SITE_BUSY"):
            rig.open(b, sites=(2,))
        with pytest.raises(worker.SiteWorkerDenied, match="SITE_BUSY"):
            rig.open(b, sites=(1,))
        assert rig.client.call("status")["sessions"][0]["sites"] == [1, 2]
        rig.client.close_session(both["session_id"])
        other = rig.open(b, sites=(2,))
        rig.client.close_session(other["session_id"])
    finally:
        rig.reap(a, b)


def test_independent_sites_can_execute_concurrently(tmp_path):
    class OverlapAdapter(MockAdapter):
        def __init__(self):
            super().__init__()
            self.arrivals = set()
            self.both_started = threading.Event()
            self.release = threading.Event()
            self.guard = threading.Lock()

        def run(self, site, operation, *, deadline, cancel, image=None, operations=None, flash_range=None):
            with self.guard:
                self.arrivals.add(site)
                if self.arrivals == {1, 2}:
                    self.both_started.set()
            while not self.release.wait(0.01):
                if cancel.is_set() or time.monotonic() >= deadline:
                    raise worker.TransportUnknown("CONCURRENT_PROBE_ABORTED")
            return {"result": "PASS", "safe_off": True}

    adapter = OverlapAdapter()
    rig = Rig(tmp_path, adapter)
    a = rig.package("print(json.dumps(call({'op':'probe','site':1})))\n")
    b = rig.package(PROBE2)
    try:
        one = rig.open(a, sites=(1,))
        two = rig.open(b, sites=(2,))
        out = {}
        ta = threading.Thread(target=lambda: out.setdefault("one", rig.go(a)))
        tb = threading.Thread(target=lambda: out.setdefault("two", rig.go(b)))
        ta.start()
        tb.start()
        assert adapter.both_started.wait(8), "two independent Site operations did not overlap"
        adapter.release.set()
        ta.join(10)
        tb.join(10)
        assert out["one"][0]["ok"] is True
        assert out["two"][0]["ok"] is True
        assert rig.client.close_session(one["session_id"])["sealed_sites"] == []
        assert rig.client.close_session(two["session_id"])["sealed_sites"] == []
    finally:
        adapter.release.set()
        rig.close()
        if a.poll() is None or b.poll() is None:
            rig.reap(*(child for child in (a, b) if child.poll() is None))


def test_cancel_one_site_does_not_cancel_unrelated_site(tmp_path):
    class PerSiteAdapter(MockAdapter):
        def __init__(self):
            super().__init__()
            self.site1_started = threading.Event()

        def run(self, site, operation, *, deadline, cancel, image=None, operations=None, flash_range=None):
            if site == 1:
                self.site1_started.set()
                while not cancel.is_set() and time.monotonic() < deadline:
                    time.sleep(0.01)
                raise worker.TransportUnknown("SITE1_CANCELLED")
            return {"result": "PASS", "safe_off": True}

    adapter = PerSiteAdapter()
    rig = Rig(tmp_path, adapter)
    a = rig.package("print(json.dumps(call({'op':'probe','site':1})))\n")
    b = rig.package(PROBE2)
    try:
        one = rig.open(a, sites=(1,))
        two = rig.open(b, sites=(2,))
        out = {}
        t = threading.Thread(target=lambda: out.setdefault("one", rig.go(a)))
        t.start()
        assert adapter.site1_started.wait(8)
        assert rig.go(b)[0]["ok"] is True
        assert rig.client.close_session(one["session_id"])["sealed_sites"] == [1]
        t.join(10)
        assert out["one"][0]["error"] == "OUTCOME_UNKNOWN_SITE_SEALED:SITE1_CANCELLED"
        assert rig.client.call("status")["sealed_sites"] == [1]
        assert rig.client.close_session(two["session_id"])["sealed_sites"] == []
    finally:
        rig.close()
        if a.poll() is None or b.poll() is None:
            rig.reap(*(child for child in (a, b) if child.poll() is None))


@pytest.mark.parametrize("raw", [b"not json\n", b"[]\n", b'{"op":"probe","site":2}\n',
                                 b"x" * 5000 + b"\n", b'{"protocol":"plasma.ppu.site-worker.v3"}\n'])
def test_malformed_requests_rejected(rig, raw):
    import socket as s
    with s.socket(s.AF_UNIX) as sock:
        sock.connect(str(rig.sock))
        sock.sendall(raw)
        reply = json.loads(sock.makefile().readline())
    assert reply == {"ok": False, "error": "REQUEST_INVALID"}



class FlashMockAdapter(MockAdapter):
    # Supports binding tests; programming without a Provider route is refused.
    operations = frozenset({"probe", "programming"})


def test_parallel_flash_sessions_reject_different_image_or_mcu(tmp_path):
    adapter = FlashMockAdapter()
    rig = Rig(tmp_path, adapter)
    other_job = "2" * 32
    rig.lease.add(other_job)
    payload = b"FIRMWARE-A"
    other_payload = b"FIRMWARE-B"
    digest = hashlib.sha256(payload).hexdigest()
    other_digest = hashlib.sha256(other_payload).hexdigest()
    different_target = {**F103, "icpn": "STM32F101C8T6"}
    (rig.image_root / (JOB + ".bin")).write_bytes(payload)
    (rig.image_root / (other_job + ".bin")).write_bytes(other_payload)
    try:
        first = rig.client.open_job_session(job_id=JOB, sites=[1], max_runtime_s=30,
                                            profile=F103)
        second = rig.client.open_job_session(job_id=other_job, sites=[2], max_runtime_s=30,
                                             profile=F103)
        rig.client.bind_image(first["session_id"], image_sha256=digest, image_size=len(payload), load_address=0x08000000)
        with pytest.raises(worker.SiteWorkerDenied, match="PPU_IMAGE_OR_TARGET_CONFLICT"):
            rig.client.bind_image(second["session_id"], image_sha256=other_digest,
                                  image_size=len(other_payload), load_address=0x08000000)
        rig.client.close_session(second["session_id"])
        (rig.image_root / (other_job + ".bin")).write_bytes(payload)
        second = rig.client.open_job_session(job_id=other_job, sites=[2], max_runtime_s=30,
                                             profile=different_target)
        with pytest.raises(worker.SiteWorkerDenied, match="PPU_IMAGE_OR_TARGET_CONFLICT"):
            rig.client.bind_image(second["session_id"], image_sha256=digest, image_size=len(payload), load_address=0x08000000)
        rig.client.close_session(second["session_id"])
        second = rig.client.open_job_session(job_id=other_job, sites=[2], max_runtime_s=30,
                                             profile=F103)
        accepted = rig.client.bind_image(second["session_id"], image_sha256=digest,
                                         image_size=len(payload), load_address=0x08000000)
        assert accepted["bound"] is True
        rig.client.close_session(first["session_id"])
        rig.client.close_session(second["session_id"])
        # No active Site sessions: another Job may now select a different MCU/firmware.
        third = rig.client.open_job_session(job_id=other_job, sites=[2], max_runtime_s=30,
                                            profile=different_target)
        (rig.image_root / (other_job + ".bin")).write_bytes(other_payload)
        rig.client.bind_image(third["session_id"], image_sha256=other_digest,
                              image_size=len(other_payload), load_address=0x08000000)
        assert rig.client.close_session(third["session_id"])["sealed_sites"] == []
    finally:
        rig.close()




@pytest.mark.parametrize("address,size,code", [
    (0x08000400, 4, None),
    (0x0800FC00, 1024, None),
    (0x0800FC00, 1025, "FLASH_RANGE_INVALID"),
    (0x08000200, 4, "FLASH_RANGE_INVALID"),
    (0x07FFFC00, 4, "FLASH_RANGE_INVALID"),
])
def test_worker_rederives_the_job_window_at_bind(tmp_path, address, size, code):
    adapter = FlashMockAdapter()
    r = Rig(tmp_path, adapter)
    try:
        payload = b"W" * size
        digest = hashlib.sha256(payload).hexdigest()
        (r.image_root / (JOB + ".bin")).write_bytes(payload)
        session = r.client.open_job_session(job_id=JOB, sites=[2], max_runtime_s=30,
                                            profile=F103)
        if code is not None:
            with pytest.raises(worker.SiteWorkerDenied, match=code):
                r.client.bind_image(session["session_id"], image_sha256=digest,
                                    image_size=size, load_address=address)
            assert r.core._sessions[session["session_id"]].image is None
        else:
            bound = r.client.bind_image(session["session_id"], image_sha256=digest,
                                        image_size=size, load_address=address)
            assert (bound["load_address"], bound["erase_address"]) == (address, address)
            assert bound["erase_length"] == -(-size // 1024) * 1024
        r.client.close_session(session["session_id"])
    finally:
        r.close()




def test_parallel_sessions_must_also_agree_on_the_write_address(tmp_path):
    adapter = FlashMockAdapter()
    rig = Rig(tmp_path, adapter)
    other_job = "2" * 32
    rig.lease.add(other_job)
    payload = b"FIRMWARE-A"
    digest = hashlib.sha256(payload).hexdigest()
    for job in (JOB, other_job):
        (rig.image_root / (job + ".bin")).write_bytes(payload)
    try:
        first = rig.client.open_job_session(job_id=JOB, sites=[1], max_runtime_s=30,
                                            profile=F103)
        second = rig.client.open_job_session(job_id=other_job, sites=[2], max_runtime_s=30,
                                             profile=F103)
        rig.client.bind_image(first["session_id"], image_sha256=digest,
                              image_size=len(payload), load_address=0x08000000)
        with pytest.raises(worker.SiteWorkerDenied, match="PPU_IMAGE_OR_TARGET_CONFLICT"):
            rig.client.bind_image(second["session_id"], image_sha256=digest,
                                  image_size=len(payload), load_address=0x08000400)
        rig.client.close_session(first["session_id"])
        rig.client.close_session(second["session_id"])
    finally:
        rig.close()


def test_c3_rejects_unbound_or_mismatched_firmware(tmp_path):
    adapter = FlashMockAdapter()
    r = Rig(tmp_path, adapter)
    try:
        payload = b"GOOD-FIRMWARE"
        (r.image_root / (JOB + ".bin")).write_bytes(payload)
        child = r.package("print(json.dumps(call({'op':'programming','site':2})))\n")
        session = r.open(child, profile=F103)
        with pytest.raises(worker.SiteWorkerDenied, match="IMAGE_SHA256_MISMATCH"):
            r.client.bind_image(
                session["session_id"], image_sha256="0" * 64, image_size=len(payload), load_address=0x08000000,
            )
        [result] = r.go(child)
        assert result == {"ok": False, "error": "OPERATIONS_NOT_BOUND"}
        assert adapter.calls == []
    finally:
        r.close()


# --- ABI-v5 OpenOCD adapter (fake processes; no hardware) ---------------------------

class FakeProc:
    def __init__(self, log: bytes, rc=0, hang=False):
        self.pid = 999999
        self._rc, self._hang = rc, hang
        self.stdout = __import__("io").BytesIO(log)
        self.returncode = None

    def poll(self):
        if self._hang:
            return None
        self.returncode = self._rc
        return self._rc

    def wait(self):
        self.returncode = -9
        return -9


def make_abi5(tmp_path, *, admit_ok=True, log=b"", rc=0, hang=False, hang_once=False, openocd=False,
              flash_readback=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    journal = tmp_path / "journal.json"
    calls = {"run": [], "popen": []}

    def run(argv, **kw):
        calls["run"].append(argv[-2:])
        out = "SITE_ADMISSION_RECORD_ISSUED" if (argv[-2] == "admit" and admit_ok) else "revoked"
        return subprocess.CompletedProcess(argv, 0 if (admit_ok or argv[-2] == "revoke") else 1, out, "")

    def popen(argv, **kw):
        calls["popen"].append(argv)
        for index, part in enumerate(argv[:-1]):
            if part == "-c" and argv[index + 1].startswith("dump_image "):
                command = argv[index + 1]
                path_match = re.search(r"\{([^{}]+)\}", command)
                assert path_match is not None
                if flash_readback is not None:
                    Path(path_match.group(1)).write_bytes(flash_readback)
        return FakeProc(log, rc, hang or (hang_once and len(calls["popen"]) == 1))

    scripts = tmp_path / "ocd" / "share" / "openocd" / "scripts" / "target"
    scripts.mkdir(parents=True)
    (scripts / "stm32f1x.cfg").write_text("# fake target config\n")
    a = abi5.Abi5OpenocdAdapter(openocd_root=tmp_path / "ocd", python=Path("/usr/bin/python3"),
                                adapter_khz=500, journal=journal,
                                record_dir=tmp_path / "rec", run=run, popen=popen,
                                openocd_running=lambda: openocd, poll_s=0.01,
                                evidence_dir=tmp_path / "openocd-evidence")
    (tmp_path / "rec").mkdir()
    return a, calls, journal


GOOD = b"Info : SWD DPIDR 0x1ba01477\nPLASMA_DPREG0=0x1ba01477\nSAFE_OFF_MODE_OFF_VERIFIED\n"

# Every Adapter receipt reports the safe release it observed, never a literal:
# the ps_owner marker AND the revoked root admission AND no cancel / timeout.
SAFE_OFF_RECEIPT = {"safe_off": True,
                    "safe_off_evidence": {"marker_present": True,
                                          "admission_revoked": True,
                                          "termination_reason": None}}



def flash_log(address: int, erase_length: int, size: int) -> bytes:
    """OpenOCD 0.12 command_print output for the executed Flash range."""
    return GOOD + (b"erased address 0x%08x (length %d) in 0.031s (32.258 KiB/s)\n"
                   b"wrote %d bytes from file image.bin in 0.1s (0.2 KiB/s)\n"
                   b"verified %d bytes in 0.05s (0.4 KiB/s)\n"
                   % (address, erase_length, size, size))









@pytest.mark.parametrize("address,size", [
    (0x08000000 - 1024, 4),            # below the bank
    (0x08000001, 4),                   # not on an erase boundary
    (0x08000200, 4),                   # half page
    (0x08010000, 4),                   # at the bank end
    (0x0800FC00, 1025),                # bytes fit? no: erase window crosses the end
    (0x0800F800, 2049),                # rounded erase window crosses the end
    (0x08000000, 0),                   # empty Image
    (True, 4),                         # bool is not an address
    ("0x08000000", 4),
    (2 ** 64, 4),
])
def test_flash_image_window_is_proven_in_bank_aligned_and_non_empty(address, size):
    with pytest.raises(worker.SiteWorkerDenied, match="FLASH_RANGE_INVALID"):
        flash_image(b"Z" * size, load_address=address)


def test_flash_window_allows_the_last_whole_page_exactly():
    image = flash_image(b"Z" * 1024, load_address=0x0800FC00)
    assert image.erase_range == (0x0800FC00, 1024)






def test_abi5_probe_uses_existing_admission_and_fixed_openocd_argv(tmp_path):
    a, calls, _ = make_abi5(tmp_path, log=GOOD)
    out = a.run(2, "probe", deadline=time.monotonic() + 30, cancel=threading.Event())
    assert out == {"result": "PASS", "dpidr": "0x1ba01477", **SAFE_OFF_RECEIPT}
    assert calls["run"] == [["admit", "2"], ["revoke", "2"]]
    argv = calls["popen"][0]
    assert argv[0].endswith("/bin/openocd") and "plasma_swd site 2" in argv
    for banned in ("program", "flash", "reset", "mww", "exec", "halt"):
        assert not any(banned in item for item in argv)
    assert a.supported_sites == {1, 2} and a.operations == {"probe", "programming", "read"}


@pytest.mark.parametrize("kw,exc,code", [
    ({"admit_ok": False}, worker.TransportDenied, "ADMISSION_DENIED"),
    ({"log": b"SWD DPIDR 0x1ba01477\n"}, worker.TransportUnknown, "SAFE_OFF_NOT_VERIFIED"),
    ({"hang": True}, worker.TransportUnknown, "OPERATION_TIMEOUT"),
])
def test_abi5_fail_closed_paths(tmp_path, kw, exc, code):
    a, calls, _ = make_abi5(tmp_path, **kw)
    with pytest.raises(exc, match=code):
        a.run(2, "probe", deadline=time.monotonic() + 0.3, cancel=threading.Event())
    if calls["run"] and calls["run"][0] == ["admit", "2"]:
        assert calls["run"][-1] == ["revoke", "2"]     # always revoked


@pytest.mark.parametrize("cancelled", [False, True])
def test_abi5_timeout_or_cancel_with_verified_cleanup_is_safe_failure(tmp_path, cancelled):
    a, calls, _ = make_abi5(tmp_path, log=GOOD, hang_once=True)
    cancel = threading.Event()
    if cancelled:
        cancel.set()
    with pytest.raises(worker.TransportFailed, match=(
        "CANCELLED_DURING_OPERATION" if cancelled else "OPERATION_TIMEOUT")):
        a.run(2, "probe", deadline=time.monotonic() + 0.2, cancel=cancel)
    assert len(calls["popen"]) == 2
    assert calls["run"] == [["admit", "2"], ["revoke", "2"],
                             ["admit", "2"], ["revoke", "2"]]


@pytest.mark.parametrize("reason", ["PS_OWNER_SITE_LOCK_UNAVAILABLE",
                                     "PS_OWNER_PL_IMAGE_NOT_LOADED"])
def test_native_pre_mmio_refusal_does_not_seal_site(tmp_path, reason):
    a, calls, _ = make_abi5(tmp_path, log=("Error: plasma_swd: " + reason).encode(), rc=1)
    with pytest.raises(worker.TransportDenied, match=reason):
        a.run(2, "probe", deadline=time.monotonic() + 5, cancel=threading.Event())
    assert calls["run"] == [["admit", "2"], ["revoke", "2"]]


def test_abi5_probe_is_independent_of_root_journal_and_image_id(tmp_path):
    a, calls, journal = make_abi5(tmp_path, log=GOOD)
    # A missing or unrelated Root journal must not block a valid C3 operation.
    assert not journal.exists()
    first = a.run(1, "probe", deadline=time.monotonic() + 5, cancel=threading.Event())
    assert first["result"] == "PASS"
    journal.write_text('{"status":"IMAGE","image_id":"other-fpga-build"}')
    second = a.run(1, "probe", deadline=time.monotonic() + 5, cancel=threading.Event())
    assert second["result"] == "PASS"
    journal.write_text("not-json")
    third = a.run(1, "probe", deadline=time.monotonic() + 5, cancel=threading.Event())
    assert third["result"] == "PASS"
    assert len(calls["popen"]) == 3


def test_abi5_admission_records_are_per_site_even_with_other_openocd(tmp_path):
    a, _c, _j = make_abi5(tmp_path)
    (tmp_path / "rec" / "swd-site1-admission").write_text("x")
    assert a.startup_sealed_sites() == {1}
    b, _c, _j = make_abi5(tmp_path / "b", openocd=True, log=GOOD)
    assert b.startup_sealed_sites() == set()
    assert b.run(2, "probe", deadline=time.monotonic() + 5,
                 cancel=threading.Event())["result"] == "PASS"


# --- C-1 lease op and C-2 wiring ------------------------------------------------------

def test_runtime_lease_verifier_uses_c1_execution_lease(tmp_path):
    import asyncio
    from plasma_server.runtime_control import RuntimeControlServer

    class Manager:
        def __init__(self): self.snap = {"busy": False, "owner_kind": None, "owner_id": None}
        def execution_lease_snapshot(self): return dict(self.snap)

    async def scenario():
        m = Manager()
        server = RuntimeControlServer(m, tmp_path / "control.sock")
        await server.start()
        try:
            verify = worker.runtime_lease_verifier(tmp_path / "control.sock")
            loop = asyncio.get_running_loop()
            pkg, rest = "package_action", "rest_job"
            assert await loop.run_in_executor(None, verify, JOB, pkg) is False
            m.snap = {"busy": True, "owner_kind": "package_action", "owner_id": JOB,
                      "job_ids": [JOB]}
            assert await loop.run_in_executor(None, verify, JOB, pkg) is True
            assert await loop.run_in_executor(None, verify, "2" * 32, pkg) is False
            # A Package Action lease never authorizes a Runtime REST Job session.
            assert await loop.run_in_executor(None, verify, JOB, rest) is False
            m.snap = {"busy": True, "owner_kind": "batch", "owner_id": "b-1",
                      "job_ids": [JOB]}
            assert await loop.run_in_executor(None, verify, JOB, pkg) is False
            assert await loop.run_in_executor(None, verify, JOB, rest) is True
            assert await loop.run_in_executor(None, verify, "job-other", rest) is False
            assert await loop.run_in_executor(None, verify, JOB, "client") is False
        finally:
            await server.close()
    asyncio.run(scenario())
    assert worker.runtime_lease_verifier(tmp_path / "missing.sock")(JOB, "package_action") is False


def test_c2_launcher_package_uses_site_worker_end_to_end(tmp_path, rig):
    from .test_ppu_asset_execution_gate1 import _ready_fixture, execution
    from contextlib import contextmanager

    main = ("import json, os, socket, time\n"
            "S = os.environ['PLASMA_SITE_WORKER_SOCKET']\n"
            "def call(req):\n"
            "    s = socket.socket(socket.AF_UNIX); s.connect(S)\n"
            "    s.sendall((json.dumps(dict(protocol='plasma.ppu.site-worker.v3', **req)) + '\\n').encode())\n"
            "    return json.loads(s.makefile().readline())\n"
            "for _ in range(100):\n"
            "    r = call({'op': 'probe', 'site': 2})\n"
            "    if r.get('error') != 'NO_SESSION_FOR_PEER': break\n"
            "    time.sleep(0.02)\n"
            "print(json.dumps(r))\n").encode()
    res = b'{"schema":"plasma.ppu.package-resources.v1","sites":[2],"max_runtime_s":20}'
    parts = [("tool", "python", [], {"python/main.py": main, "config/plasma-package-resources.json": res})]
    co, requests, owner, _ = _ready_fixture(tmp_path / "set", parts=parts)
    req = requests["python"]
    sys.path.insert(0, str(ROOT / "scripts"))
    import ppu_package_launcher as launcher

    @contextmanager
    def lease():
        yield {"job_id": req.job_id, "site_ids": [1, 2]}

    runs = []

    def dispatch(site_worker):
        runs.append(1)
        executor = launcher.make_package_executor(
            co.paths.product_root, python_executable=Path(sys.executable),
            state_root=tmp_path / f"actions-{len(runs)}", site_worker=site_worker)
        return execution.dispatch_asset_execution(
            co.paths.product_root, req, **owner.kw(req), execution_scope=lease,
            trusted_executors={"python": executor})

    # Default remains fail-closed without a Site Worker.
    with pytest.raises(launcher.PackageLaunchDenied, match="PACKAGE_SITE_TRANSPORT_NOT_WIRED"):
        dispatch(None)
    receipt = dispatch(rig.client)["executor_result"]
    assert receipt["result"] == "SUCCEEDED" and receipt["hardware"] == "SITE_WORKER"
    assert receipt["site_ids"] == [2] and receipt["site_transport"]["session"] == "CLOSED"
    out = json.loads(receipt["stdout"]["tail"])
    assert out["ok"] is True and out["result"]["dpidr"] == "0x1ba01477"
    assert rig.core._sessions == {}
    assert rig.core._site_owners == {}

    # Worker refuses the session (lease not held): the Package is killed, FAILED.
    rig.lease.clear()
    receipt = dispatch(rig.client)["executor_result"]
    assert receipt["result"] == "FAILED" and receipt["site_transport"]["session"] == "DENIED"
