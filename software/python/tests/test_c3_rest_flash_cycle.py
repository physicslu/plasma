"""REST Job -> plasma-server -> C-3 Site Worker -> (fake) OpenOCD, Host-only.

Real pieces: Gateway HTTP handler, PlasmaServer, SiteManager/SiteWorker,
SiteExecutionRouter, OpenOCDInterface C-3 backend, the Runtime control socket
(C-1 execution lease), the C-3 SiteWorkerCore on a real Unix socket and the
ABI-v5 adapter argv/admission/readback logic. Fake: the root admission helper
and the OpenOCD process (a Flash simulator). No Z2, FPGA, C driver or DUT.

Also covers the deployment-selected OpenOCD engine (no versioned path), the
Runtime-resolved Flash profile and the canonical Job ID rule.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from contextlib import ExitStack
from unittest.mock import patch
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from plasma_client.client import PlasmaClient
from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.enums import Operation
from plasma_core.errors import PlasmaError
from plasma_core.ic_support import get_default_ic_support_resolver
from plasma_core.models import JOB_ID_PATTERN, JobRequest, new_job_id
from plasma_interfaces.openocd import OpenOCDInterface, c3_flash_profile
from plasma_interfaces.site_worker_c3 import C3FlashProfile, SiteWorkerRefused, run_flash_cycle
from plasma_server.runtime_control import RuntimeControlServer
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager
from plasma_server.package_actions import PackageActionRuntime
from plasma_web.gateway import PlasmaWebHandler
from plasma_web import gateway as gateway_module
from plasma_web.device_catalog import DeviceCatalogIntegrityError

from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_site_adapter_abi5 as abi5  # noqa: E402
import ppu_site_worker as worker  # noqa: E402
import ppu_site_worker_service as service  # noqa: E402

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="Linux AF_UNIX + SO_PEERCRED")
TERMINAL = {"success", "failed", "error", "timeout", "cancelled", "aborted"}
SAFE = b"Info : SWD DPIDR 0x1ba01477\nSAFE_OFF_MODE_OFF_VERIFIED\n"


# --- fake OpenOCD engine installs ------------------------------------------------------

def make_engine(base: Path, name: str, *, binary: bytes = b"\x7fELF-fake-openocd",
                configs=("stm32f1x.cfg",)) -> dict:
    root = base / name
    (root / "bin").mkdir(parents=True)
    (root / "libexec").mkdir()
    target = root / "share" / "openocd" / "scripts" / "target"
    target.mkdir(parents=True)
    for cfg in configs:
        (target / cfg).write_text("# fake\n")
    (root / "bin" / "openocd").write_bytes(binary)
    (root / "libexec" / "plasma_swd_site_admission.py").write_text("# fake admission\n")
    for path in root.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    return {"schema": service.ENGINE_SCHEMA, "openocd_root": str(root),
            "openocd_sha256": hashlib.sha256(binary).hexdigest(),
            "admission_sha256": hashlib.sha256(b"# fake admission\n").hexdigest(),
            "adapter_driver": "plasma_swd", "driver_abi": 5, "adapter_khz": 500}


def write_selection(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data))
    path.chmod(0o644)
    return path


def load(record: Path, base: Path):
    return service.load_engine(record, base=base, require_root=False)


def test_two_engine_installs_each_selected_explicitly(tmp_path):
    base = tmp_path / "openocd"
    a = make_engine(base, "0.12.0-aaaa-plasma-swd-111111111111", binary=b"A")
    b = make_engine(base, "0.12.0-bbbb-plasma-swd-222222222222", binary=b"B")
    record = tmp_path / "engine.json"
    for chosen in (a, b):
        engine = load(write_selection(record, chosen), base)
        assert str(engine.openocd_root) == chosen["openocd_root"]
        adapter = service.default_adapter(record, base=base, require_root=False)
        assert isinstance(adapter, abi5.Abi5OpenocdAdapter)
        assert str(adapter.openocd) == chosen["openocd_root"] + "/bin/openocd"
        assert adapter._argv(2)[2] == chosen["openocd_root"] + "/share/openocd/scripts"
        assert adapter.adapter_khz == 500


@pytest.mark.parametrize("mutate,code", [
    (lambda d, base: d.update(openocd_sha256="0" * 64), "OPENOCD_SHA256_MISMATCH"),
    (lambda d, base: d.update(admission_sha256="1" * 64), "ADMISSION_SHA256_MISMATCH"),
    (lambda d, base: d.update(openocd_root=str(base / "0.12.0-missing")), "SELECTION_ROOT_NOT_INSTALLED"),
    (lambda d, base: d.update(openocd_root="/usr/bin"), "SELECTION_ROOT_NOT_INSTALLED"),
    (lambda d, base: d.update(openocd_root="relative/x"), "SELECTION_ROOT_INVALID"),
    (lambda d, base: d.update(adapter_driver="cmsis_dap"), "SELECTION_DRIVER_ABI_UNSUPPORTED"),
    (lambda d, base: d.update(driver_abi=4), "SELECTION_DRIVER_ABI_UNSUPPORTED"),
    (lambda d, base: d.update(adapter_khz=0), "SELECTION_ADAPTER_KHZ_INVALID"),
    (lambda d, base: d.update(schema="other"), "SELECTION_SCHEMA_UNSUPPORTED"),
    (lambda d, base: d.update(extra=1), "SELECTION_FIELDS_INVALID"),
])
def test_bad_selection_is_not_ready_and_never_falls_back(tmp_path, mutate, code):
    base = tmp_path / "openocd"
    good = make_engine(base, "0.12.0-good-plasma-swd-333333333333")  # a valid install exists
    data = dict(good)
    mutate(data, base)
    record = write_selection(tmp_path / "engine.json", data)
    with pytest.raises(service.EngineNotReady, match=code):
        load(record, base)
    adapter = service.default_adapter(record, base=base, require_root=False)
    assert isinstance(adapter, service.NotReadyAdapter) and adapter.not_ready.startswith(code)


def test_missing_unsafe_or_symlinked_selection_is_not_ready(tmp_path):
    base = tmp_path / "openocd"
    good = make_engine(base, "0.12.0-good-plasma-swd-444444444444")
    with pytest.raises(service.EngineNotReady, match="MISSING:engine.json"):
        load(tmp_path / "engine.json", base)
    record = write_selection(tmp_path / "engine.json", good)
    record.chmod(0o666)
    with pytest.raises(service.EngineNotReady, match="WRITABLE_BY_OTHERS"):
        load(record, base)
    record.chmod(0o644)
    link = tmp_path / "link.json"
    link.symlink_to(record)
    with pytest.raises(service.EngineNotReady, match="NOT_REGULAR_FILE"):
        load(link, base)
    binary = Path(good["openocd_root"]) / "bin" / "openocd"
    binary.unlink()
    with pytest.raises(service.EngineNotReady, match="MISSING:openocd"):
        load(record, base)
    # Production additionally requires root ownership.
    if os.geteuid() != 0:
        with pytest.raises(service.EngineNotReady, match="NOT_ROOT_OWNED"):
            service.load_engine(record, base=base)


def test_not_ready_engine_refuses_every_session_explicitly(tmp_path):
    core = worker.SiteWorkerCore(service.NotReadyAdapter("MISSING:site-worker-engine.json"),
                                 runtime_pid=os.getpid, lease_verifier=lambda j, k: True,
                                 seal_dir=tmp_path / "seals")
    me = (os.getpid(), os.getuid(), os.getgid())
    status = core.handle({"protocol": worker.PROTOCOL, "op": "status"}, me, "control")
    assert status["result"]["not_ready"] == "MISSING:site-worker-engine.json"
    reply = core.handle({"protocol": worker.PROTOCOL, "op": "open_job_session",
                         "job_id": "job-1", "sites": [2], "max_runtime_s": 30}, me, "control")
    assert reply == {"ok": False, "error": "ENGINE_NOT_READY:MISSING:site-worker-engine.json"}


def test_service_python_is_the_running_interpreter_not_a_versioned_path():
    assert service.PYTHON == Path(sys.executable)
    source = (ROOT / "scripts" / "ppu_site_worker_service.py").read_text()
    assert "/opt/plasma/python/" not in source and "plasma-swd-" not in source
    assert "EXPECTED_IMAGE" not in source


# --- Runtime-resolved Flash profile ----------------------------------------------------

@pytest.mark.parametrize("field,value,code", [
    ("target_config", "target/../../etc/passwd.cfg", "PROFILE_TARGET_CONFIG_INVALID"),
    ("target_config", "/abs/target/x.cfg", "PROFILE_TARGET_CONFIG_INVALID"),
    ("target_config", "target/x.cfg; shutdown", "PROFILE_TARGET_CONFIG_INVALID"),
    ("target_config", "target/[exec rm].cfg", "PROFILE_TARGET_CONFIG_INVALID"),
    ("erase_granularity", 1000, "PROFILE_GEOMETRY_INVALID"),
    ("flash_size", 0, "PROFILE_GEOMETRY_INVALID"),
    ("flash_base", 0xFFFFFC00, "PROFILE_GEOMETRY_INVALID"),
    ("icpn", "STM32 F103", "PROFILE_ICPN_INVALID"),
])
def test_flash_profile_shape_is_validated(field, value, code):
    raw = {"icpn": "STM32F103C8T6", "target_config": "target/stm32f1x.cfg",
           "flash_base": 0x08000000, "flash_size": 0x10000, "erase_granularity": 1024}
    raw[field] = value
    with pytest.raises(worker.SiteWorkerDenied, match=code):
        worker.parse_flash_profile(raw)


def test_profile_comes_from_exact_icpn_ic_support():
    resolver = get_default_ic_support_resolver()
    profile = c3_flash_profile(resolver.require_exact("STM32F103C8T6"))
    assert profile.to_wire() == {"icpn": "STM32F103C8T6", "target_config": "target/stm32f1x.cfg",
                                 "flash_base": 0x08000000, "flash_size": 65536,
                                 "erase_granularity": 1024}
    # A different exact ICPN changes target config / geometry / readback range.
    other = [icpn for icpn in ("STM32F103CBT6", "STM32F103RBT6", "STM32F103C6T6")
             if resolver.resolve_exact(icpn) is not None]
    if other:
        alt = c3_flash_profile(resolver.require_exact(other[0]))
        assert alt.icpn == other[0] and alt.to_wire() != profile.to_wire()


def test_canonical_job_id_rule_is_shared_by_rest_and_c3():
    samples = [new_job_id(), "1" * 32, "a", "job.1_x-2", "A" * 128, "A" * 129, "-x", ".x",
               "a/b", "a b", "", "a\n", "../x"]
    for value in samples:
        assert (worker.JOB_ID.fullmatch(value) is not None) == (
            JOB_ID_PATTERN.fullmatch(value) is not None), value
    assert worker.JOB_ID.fullmatch(new_job_id())


# --- live REST -> C3 integration -------------------------------------------------------

class FlashSim:
    """Fake admission + OpenOCD for the ABI-v5 adapter (argv-driven)."""

    def __init__(self, base: int, size: int) -> None:
        self.base, self.memory = base, bytearray(b"\xff" * size)
        self.argvs: list[list[str]] = []
        self.corrupt = False
        self.fail_at = None
        self.hang = threading.Event()  # set -> OpenOCD never exits until killed

    def run(self, argv, **_kw):
        out = "SITE_ADMISSION_RECORD_ISSUED" if argv[-2] == "admit" else "revoked"
        return subprocess.CompletedProcess(argv, 0, out, "")

    def popen(self, argv, **_kw):
        self.argvs.append(list(argv))
        commands = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "-c"]
        rc = 0
        for command in commands:
            path = re.search(r"\{([^{}]+)\}", command)
            parts = command.split()
            if command.startswith("flash erase_address "):
                if self.fail_at == "erase":
                    rc = 5
                start, length = int(parts[2], 0) - self.base, int(parts[3], 0)
                self.memory[start:start + length] = b"\xff" * length
            elif command.startswith("flash write_image "):
                if self.fail_at == "write":
                    rc = 5
                data = Path(path.group(1)).read_bytes()
                self.memory[:len(data)] = data
            elif command.startswith("flash verify_image "):
                if self.fail_at == "verify":
                    rc = 5
                data = Path(path.group(1)).read_bytes()
                rc = rc or (0 if self.memory[:len(data)] == data else 5)
            elif command.startswith("dump_image "):
                length = int(parts[-1], 0)
                data = bytes(self.memory[:length])
                Path(path.group(1)).write_bytes(b"X" + data[1:] if self.corrupt else data)
        return _Proc(SAFE, rc, self.hang.is_set())


class _Proc:
    def __init__(self, log, rc, hang):
        self.pid, self._log, self._rc, self._hang = 999999, log, rc, hang
        self.returncode = None
        self.stdout = self

    def read(self):
        return self._log

    def poll(self):
        if self._hang:
            return None
        self.returncode = self._rc
        return self._rc

    def wait(self):
        self.returncode = -9
        return -9


class Stack:
    def __init__(self, root: Path, *, site_target="STM32F103C8T6", adapter=None,
                 max_retries=0, in_process=False, bundle_options=None):
        self.root = root
        self.in_process = in_process
        self.bundle_options = bundle_options or {}
        self.sim = FlashSim(0x08000000, 0x10000)
        engine = make_engine(root / "openocd", "0.12.0-test-plasma-swd-555555555555")
        journal = root / "journal.json"
        journal.write_text('{"status":"IMAGE","image_id":"any-compatible","session_id":"s"}')
        self.adapter = adapter or abi5.Abi5OpenocdAdapter(
            openocd_root=Path(engine["openocd_root"]), python=Path(sys.executable),
            adapter_khz=500, journal=journal, record_dir=root / "rec",
            run=self.sim.run, popen=self.sim.popen, openocd_running=lambda: False, poll_s=0.01,
            evidence_dir=root / "openocd-evidence")
        (root / "rec").mkdir()
        self.images = root / "normalized-images"
        self.site_target = site_target
        self.max_retries = max_retries

    async def __aenter__(self):
        # Real installed/verified Bundle + production Runtime composition.
        # Only root ownership and physical process edges are test substitutes.
        from .test_opf_4a_openocd_reference import installed_bundle
        import ppu_site_engine

        self.opf_context = ExitStack()
        self.opf = self.opf_context.enter_context(installed_bundle(
            with_control_socket=False, **self.bundle_options))
        if isinstance(self.adapter, abi5.Abi5OpenocdAdapter):
            self.adapter = self.opf["adapter"]
            self.sim = self.opf["sim"]
        self.images = self.opf["image_root"]
        original_load = ppu_site_engine.load_engine

        def test_engine(*args, **kwargs):
            return original_load(self.opf["engine_record"],
                                 base=self.opf["engine_base"], require_root=False)

        self.opf_context.enter_context(patch.object(ppu_site_engine, "load_engine", test_engine))
        root = self.root
        config = PlasmaConfig(
            server=ServerConfig(host="127.0.0.1", port=0, output_root=root / "output",
                                log_root=root / "logs", max_supported_sites=2,
                                max_concurrent_jobs=1),
            sites=[SiteConfig(id=2, enabled=True, interface="openocd", target=self.site_target,
                              max_retries=self.max_retries, retry_backoff_s=0,
                              openocd={"site_worker_socket": str(root / "c3.sock"),
                                       "normalized_image_root": str(self.images)})],
        )
        resolver = get_default_ic_support_resolver()
        self.manager = SiteManager(config, ic_support_resolver=resolver)
        self.package_runtime = PackageActionRuntime(
            self.manager, control_plane=ROOT / "scripts", product_root=self.opf["product_root"],
            state_root=root / "package-state", owner_credential=None, spawner=None,
            python_executable=Path(sys.executable))
        self.server = PlasmaServer(config, self.manager)
        if self.in_process:
            self.worker_requests = []
            await self.manager.start()
        else:
            await self.server.start()
        self.control = RuntimeControlServer(self.manager, root / "runtime.sock")
        if not self.in_process:
            await self.control.start()
        self.core = worker.SiteWorkerCore(
            self.adapter, runtime_pid=os.getpid,
            lease_verifier=(lambda job, kind: kind == "rest_job" and job in
                            self.manager.execution_lease_snapshot().get("job_ids", []))
            if self.in_process else worker.runtime_lease_verifier(root / "runtime.sock"),
            seal_dir=root / "seals", image_root=self.images)
        self.c3 = worker.SiteWorkerServer(self.core, root / "c3.sock", mode=0o600)
        if not self.in_process:
            self.c3.start()

        class Gateway(PlasmaWebHandler):
            pass

        if self.in_process:
            loop = asyncio.get_running_loop()
            server = self.server

            class InProcessClient(PlasmaClient):
                async def _exchange(self, frame, **kwargs):
                    pending = asyncio.run_coroutine_threadsafe(
                        server._dispatch(frame, ("in-process-test", 0)), loop)
                    # No socketpair wakeup is assumed in the workspace sandbox.
                    for _ in range(1000):
                        if pending.done():
                            return pending.result()
                        await asyncio.sleep(0.01)
                    raise AssertionError("test protocol transport did not complete")

            Gateway.client_factory = staticmethod(InProcessClient)

            def worker_call(op, *, timeout_s=None, **fields):
                self.worker_requests.append({"op": op, **fields})
                reply = self.core.handle({"protocol": worker.PROTOCOL, "op": op, **fields},
                                         (os.getpid(), os.getuid(), os.getgid()), "control")
                if not reply["ok"]:
                    raise SiteWorkerRefused(reply["error"])
                return reply["result"]

            self.manager.interfaces[2]._site_worker.call = worker_call
        else:
            host, port = self.server.address
            Gateway.client_factory = staticmethod(lambda: PlasmaClient(host, port))
        Gateway.output_root = root / "output"
        Gateway.engineering_provider = None
        Gateway.batch_runtime = None
        Gateway.static_root = None
        self.gateway = Gateway
        if self.in_process:
            return self
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        return self

    async def __aexit__(self, *exc):
        if not self.in_process:
            await asyncio.to_thread(self.http.shutdown)
            self.http.server_close()
            self.thread.join(timeout=5)
            self.c3.close()
            await self.control.close()
        await self.server.close()
        self.opf_context.close()

    async def api(self, method, endpoint, payload=None):
        def request():
            if self.in_process:
                handler = object.__new__(self.gateway)
                handler.path = endpoint
                handler.command = method
                data = json.dumps(payload).encode() if payload is not None else b""
                handler.headers = {"Content-Length": str(len(data))}
                handler.rfile = io.BytesIO(data)
                response = []
                handler._json = lambda status, body: response.append((status, body))
                getattr(handler, "do_" + method)()
                return response[0]
            conn = HTTPConnection("127.0.0.1", self.http.server_port, timeout=30)
            try:
                data = json.dumps(payload).encode() if payload is not None else None
                conn.request(method, endpoint, data,
                             {"Content-Type": "application/json"} if data else {})
                response = conn.getresponse()
                raw = response.read()
                kind = response.getheader("Content-Type", "")
                return response.status, (json.loads(raw) if "application/json" in kind else raw)
            finally:
                conn.close()
        return await asyncio.wait_for(asyncio.to_thread(request), timeout=10)

    async def flash(self, image: bytes, **extra):
        body = {"site_id": 2, "operation": "flash_cycle", "asset_name": "fw.bin",
                "asset_type": "image", "asset_format": "binary", "asset_size": len(image),
                "asset_sha256": hashlib.sha256(image).hexdigest(),
                "asset_base64": base64.b64encode(image).decode(), **extra}
        status, payload = await self.api("POST", "/api/jobs", body)
        if status != 202:
            return status, payload
        job_id = payload["job"]["job_id"]
        for _ in range(500):
            status, observation = await self.api("GET", "/api/status?job=" + job_id)
            if observation["job"]["state"] in TERMINAL:
                return job_id, observation["job"]
            await asyncio.sleep(0.02)
        raise AssertionError("Job never terminal")


def short_tmp():
    return tempfile.TemporaryDirectory(prefix="c3-", dir="/tmp")


def run(coro):
    async def main():
        # Timers let thread completions progress even where the sandbox denies
        # socketpair wakeups. No network permission is needed or changed.
        loop = asyncio.get_running_loop()

        def tick():
            loop.call_later(0.01, tick)

        tick()
        return await coro

    return asyncio.run(main())


@pytest.mark.parametrize("in_process", [False, True], ids=["sockets", "in-process"])
def test_rest_flash_cycle_through_c3_passes_with_full_readback(in_process):
    image = bytes(range(256)) * 9  # 2304 B -> 3 pages erased
    digest = hashlib.sha256(image).hexdigest()

    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory), in_process=in_process) as stack:
                job_id, job = await stack.flash(image)
                assert job["state"] == "success", json.dumps(job, indent=2)
                # The unchanged REST Job ID format is accepted by C-3 as-is.
                assert job_id.startswith("job-") and worker.JOB_ID.fullmatch(job_id)
                result = job["result"]
                evidence = result["details"]["flash_cycle"]
                assert evidence["result"] == "PASS" and evidence["safe_off"] is True
                assert evidence["readback_sha256"] == digest == result["image_sha256"]
                assert evidence["bytes_verified"] == len(image)
                assert evidence["icpn"] == "STM32F103C8T6" and evidence["adapter_khz"] == 500
                assert evidence["opf_asset_set_sha256"] == stack.opf["asset_set_sha256"]
                assert evidence["opf_provider_package"] == "openocd-reference"
                assert evidence["opf_worker_engine_selection_sha256"] == evidence["opf_engine_selection_sha256"]
                runtime = stack.manager.registry.get(job_id)
                assert runtime.active_asset_set["asset_set_sha256"] == evidence["opf_asset_set_sha256"]
                if in_process:
                    [opened] = [r for r in stack.worker_requests if r["op"] == "open_job_session"]
                    assert opened["deadline_monotonic"] == runtime.deadline_monotonic
                    assert opened["provider_route"]["site_id"] == 2
                assert bytes(stack.sim.memory[:len(image)]) == image
                [argv] = stack.sim.argvs
                commands = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "-c"]
                assert argv[argv.index("-f") + 1] == "target/stm32f1x.cfg"
                assert "adapter speed 500" in commands
                erase = "flash erase_address 0x08000000 0x00000c00"
                index = commands.index("reset halt")
                assert commands[index:index + 4] == [
                    "reset halt", "poll off", "flash probe 0", erase
                ]
                assert any(c.startswith("dump_image ") for c in commands)
                # Job-owned staged image removed; session closed; Site not sealed.
                assert not stack.images.exists() or list(stack.images.iterdir()) == []
                status = stack.core.handle({"protocol": worker.PROTOCOL, "op": "status"},
                                           (os.getpid(), 0, 0), "control")["result"]
                assert status["session"] is None and status["sealed_sites"] == []
    run(scenario())



def test_rest_opf_flash_does_not_require_unrelated_device_catalog(monkeypatch):
    """The actual Gateway -> Runtime -> C3 fake-OpenOCD path stays available
    when a slim PPU has no full Microchip/Production browsing Catalog."""
    def catalog_not_installed():
        raise DeviceCatalogIntegrityError("production Device Catalog unavailable")

    monkeypatch.setattr(gateway_module, "get_default_device_catalog", catalog_not_installed)

    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory), in_process=True) as stack:
                payload = b"HOST-ONLY-NO-MICROCHIP-CATALOG"
                _job_id, job = await stack.flash(payload)
                assert job["state"] == "success", job
                cycle = job["result"]["details"]["flash_cycle"]
                assert cycle["result"] == "PASS"
                assert cycle["readback_sha256"] == hashlib.sha256(payload).hexdigest()
                assert cycle["safe_off"] is True

    run(scenario())


def test_opf_ordinary_job_does_not_require_historical_qualification_metadata():
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory), in_process=True) as stack:
                journal = stack.adapter.journal
                data = json.loads(journal.read_text())
                # Historical qualification metadata is optional. Current boot
                # and firmware identity remain required for the installed
                # platform observation before live C3 admission.
                for key in ("schema", "manifest_sha256"):
                    data.pop(key, None)
                data["test_count"] = 0
                journal.write_text(json.dumps(data))
                for _ in range(2):
                    _job_id, job = await stack.flash(b"UNCHANGED-QUALIFIED-SESSION")
                    assert job["state"] == "success", job
                assert len(stack.sim.argvs) == 2
                assert not stack.core._sessions and not stack.core._site_owners
                assert not stack.core._sealed
    run(scenario())


@pytest.mark.parametrize("in_process", [False, True], ids=["sockets", "in-process"])
def test_rest_flash_cycle_readback_mismatch_is_never_success(in_process):
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory), in_process=in_process) as stack:
                stack.sim.corrupt = True
                _job_id, job = await stack.flash(b"INTENDED-FIRMWARE")
                assert job["state"] != "success"
                assert "READBACK_MISMATCH" in json.dumps(job)
                assert list(stack.images.iterdir()) == []
    run(scenario())


@pytest.mark.parametrize("case,options,code", [
    ("empty", {}, "OPF_ACTIVE_SET_REQUIRED"),
    ("stale", {}, "ACTIVE_SET_MISMATCH"),
    ("profile", {"profile_change": {"flash_size": 131072}}, "REFERENCE_PROFILE_RUNTIME_MISMATCH"),
    ("driver", {"descriptor_change": {"driver_abi": "plasma_swd:6"}}, "FPGA_DRIVER_UNVERIFIED"),
    ("engine", {"engine_binary": b"different-installed-engine"}, "REFERENCE_ENGINE_BINARY_MISMATCH"),
    ("unverified-worker", {"verified_worker": False}, "WORKER_ENGINE_UNVERIFIED"),
    ("image", {}, "OPF_FPGA_IDENTITY_UNVERIFIED"),
    ("unsafe", {}, "OPF_FPGA_IDENTITY_UNVERIFIED"),
    ("lease", {}, "JOB_LEASE_NOT_HELD"),
    ("unwired", {}, "OPF_RUNTIME_NOT_WIRED"),
    ("sealed", {}, "SITE_SEALED"),
    ("external-owner", {}, "EXTERNAL_SITE_OWNER_PRESENT"),
    ("race", {}, "WORKER_FPGA_IDENTITY_MISMATCH"),
    ("reselected", {}, "WORKER_ENGINE_SELECTION_MISMATCH"),
    ("transport", {"descriptor_change": {"transport": "ps-only", "driver_abi": None,
                                          "fpga_package": None}}, "PS_TRANSPORT_UNVERIFIED"),
])
def test_opf_rest_fail_closed_before_flash(case, options, code):
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory), in_process=True, bundle_options=options) as stack:
                reader = stack.manager._active_asset_set_reader
                if case == "empty":
                    stack.manager._active_asset_set_reader = lambda: {"state": "EMPTY"}
                elif case == "stale":
                    pinned = reader()
                    stack.manager._active_asset_set_reader = lambda: {**pinned, "generation": 999}
                elif case in {"image", "unsafe"}:
                    journal = stack.adapter.journal
                    data = json.loads(journal.read_text())
                    journal.write_text(json.dumps({**data, **({"image_id": "different-image"} if case == "image"
                                                       else {"status": "UNKNOWN"})}))
                elif case == "unwired":
                    stack.manager.interfaces[2].opf_flash_executor = None
                elif case == "sealed":
                    stack.core._sealed.add(2)
                elif case == "external-owner":
                    stack.adapter._record(2).touch()
                elif case == "lease":
                    stack.core.lease_verifier = lambda *_: False
                elif case == "race":
                    client = stack.manager.interfaces[2]._site_worker
                    original_call = client.call

                    def changed_after_status(op, **fields):
                        reply = original_call(op, **fields)
                        if op == "status":
                            journal = stack.adapter.journal
                            data = json.loads(journal.read_text())
                            journal.write_text(json.dumps({**data, "session_id": "changed"}))
                        return reply

                    client.call = changed_after_status
                elif case == "reselected":
                    write_selection(stack.opf["engine_record"],
                                    {**stack.opf["engine_data"], "adapter_khz": 2000})
                _job_id, job = await stack.flash(b"DENIED")
                assert job["state"] != "success" and code in json.dumps(job), job
                assert not stack.sim.argvs
                assert stack.core._sessions == {} and stack.core._site_owners == {}
                assert not stack.images.exists() or list(stack.images.iterdir()) == []
                assert stack.manager.execution_lease_snapshot()["busy"] is False
    run(scenario())


def test_opf_runtime_retries_keep_one_job_deadline_and_release_owner():
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory), in_process=True, max_retries=2) as stack:
                stack.sim.fail_at = "verify"
                result = await stack.manager.submit(JobRequest(
                    site_id=2, operation=Operation.FLASH_CYCLE, image=b"RETRY",
                    target="STM32F103C8T6", max_retries=2, retry_backoff_s=0, timeout_s=5))
                assert result.state.value != "success"
                assert len(result.attempt_history) == 3 and result.retry_exhausted
                opens = [r for r in stack.worker_requests if r["op"] == "open_job_session"]
                assert len(opens) == 3
                deadline = stack.manager.registry.get(result.job_id).deadline_monotonic
                assert all(r["deadline_monotonic"] == deadline for r in opens)
                assert len(stack.sim.argvs) == 3
                assert not stack.core._sessions and not stack.core._site_owners
                assert not stack.core._sealed
                assert stack.manager.execution_lease_snapshot()["busy"] is False
    run(scenario())


@pytest.mark.parametrize("phase", ["erase", "write", "verify", "readback"])
def test_safe_flash_failure_allows_next_independent_job(phase):
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory)) as stack:
                stack.sim.corrupt = phase == "readback"
                stack.sim.fail_at = None if phase == "readback" else phase
                _first_id, failed = await stack.flash(b"FIRST")
                assert failed["state"] != "success"
                assert stack.core.handle({"protocol": worker.PROTOCOL, "op": "status"},
                                         (os.getpid(), 0, 0), "control")["result"]["sealed_sites"] == []
                stack.sim.corrupt = False
                stack.sim.fail_at = None
                _next_id, passed = await stack.flash(b"SECOND")
                assert passed["state"] == "success", passed
    run(scenario())


def test_safe_flash_failure_uses_bounded_runtime_attempt_history():
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory), max_retries=2) as stack:
                stack.sim.fail_at = "verify"
                host, port = stack.server.address
                response = await PlasmaClient(host, port).submit(JobRequest(
                    site_id=2, operation=Operation.FLASH_CYCLE, image=b"RETRY",
                    target="STM32F103C8T6", max_retries=2, retry_backoff_s=0,
                ))
                failed = response["result"]
                assert failed["state"] != "success"
                assert len(failed["attempt_history"]) == 3, json.dumps(failed, indent=2)
                assert [a["retry_scheduled"] for a in failed["attempt_history"]] == [
                    True, True, False]
                assert failed["retry_exhausted"] is True
                assert len(stack.sim.argvs) == 3
    run(scenario())


def test_unconfirmed_session_close_prevents_safe_failure_retry(tmp_path):
    class RefusingClose:
        def call(self, op, **_fields):
            if op == "open_job_session":
                return {"session_id": "session"}
            if op == "bind_image":
                return {"bound": True}
            if op == "run":
                return {"result": "FAIL", "code": "WRITE_FAILED", "safe_off": True}
            raise SiteWorkerRefused("SITE_WORKER_UNREACHABLE")

    async def scenario():
        with pytest.raises(PlasmaError) as caught:
            await run_flash_cycle(
                RefusingClose(), job_id="job-close-failure", site_id=2,
                profile=C3FlashProfile("STM32F103C8T6", "target/stm32f1x.cfg",
                                       0x08000000, 0x10000, 1024),
                image=b"FW", image_root=tmp_path, max_runtime_s=30)
        assert caught.value.recoverable is False
        assert "close did not confirm" in str(caught.value)
        assert list(tmp_path.iterdir()) == []
    run(scenario())


def test_rest_flash_cycle_engine_not_ready_fails_explicitly():
    async def scenario():
        with short_tmp() as directory:
            root = Path(directory)
            async with Stack(root, adapter=service.NotReadyAdapter("MISSING:engine")) as stack:
                _job_id, job = await stack.flash(b"FW")
                assert job["state"] != "success"
                assert "ENGINE_NOT_READY" in json.dumps(job)
                assert not stack.images.exists() or list(stack.images.iterdir()) == []
    run(scenario())


@pytest.mark.parametrize("in_process", [False, True], ids=["sockets", "in-process"])
def test_rest_flash_cycle_timeout_never_reports_success_and_seals(in_process):
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory), in_process=in_process) as stack:
                stack.sim.hang.set()
                _job_id, job = await stack.flash(b"FW-THAT-HANGS", timeout_s=1.5)
                assert job["state"] != "success"
                for _ in range(200):  # the Worker finishes cancelling OpenOCD
                    status = stack.core.handle({"protocol": worker.PROTOCOL, "op": "status"},
                                               (os.getpid(), 0, 0), "control")["result"]
                    if status["sealed_sites"]:
                        break
                    await asyncio.sleep(0.02)
                assert status["sealed_sites"] == [2] and status["session"] is None
                assert list(stack.images.iterdir()) == []
                # A sealed Site refuses the next Job (operator recovery required).
                _job_id, nxt = await stack.flash(b"NEXT")
                assert nxt["state"] != "success" and "SITE_SEALED" in json.dumps(nxt)
    run(scenario())


def test_rest_job_without_any_target_is_refused_before_execution():
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory), site_target=None) as stack:
                status, payload = await stack.flash(b"FW")
                assert status in (400, 422), payload
                assert "target" in json.dumps(payload)
                assert stack.sim.argvs == []
    run(scenario())


def test_rest_job_unsupported_target_never_reaches_c3():
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory)) as stack:
                status, payload = await stack.flash(b"FW", target="NOT-A-REAL-ICPN")
                assert status == 400 and "NOT-A-REAL-ICPN" in payload["error"]["message"]
                assert stack.sim.argvs == []
    run(scenario())


def test_c3_path_offers_only_the_complete_flash_cycle():
    async def scenario():
        with short_tmp() as directory:
            async with Stack(Path(directory)) as stack:
                status, payload = await stack.api("POST", "/api/jobs",
                                                  {"site_id": 2, "operation": "erase"})
                assert status == 400 and "not runtime-ready" in payload["error"]["message"]
                assert stack.sim.argvs == []
    run(scenario())


def test_lease_violation_is_refused_by_c3(tmp_path):
    """A Job that does not hold the C-1 lease cannot open a C-3 session."""
    core = worker.SiteWorkerCore(abi5_stub(), runtime_pid=os.getpid,
                                 lease_verifier=lambda j, k: False, seal_dir=tmp_path / "s")
    me = (os.getpid(), os.getuid(), os.getgid())
    reply = core.handle({"protocol": worker.PROTOCOL, "op": "open_job_session",
                         "job_id": new_job_id(), "sites": [2], "max_runtime_s": 30},
                        me, "control")
    assert reply == {"ok": False, "error": "JOB_LEASE_NOT_HELD"}
    # A foreign (non-Runtime) process can never open a Runtime Job session.
    reply = core.handle({"protocol": worker.PROTOCOL, "op": "open_job_session",
                         "job_id": new_job_id(), "sites": [2], "max_runtime_s": 30},
                        (os.getpid() + 1, os.getuid(), os.getgid()), "control")
    assert reply == {"ok": False, "error": "CONTROL_PEER_DENIED"}


def test_package_peer_cannot_run_on_a_runtime_job_session(tmp_path):
    core = worker.SiteWorkerCore(abi5_stub(), runtime_pid=os.getpid,
                                 lease_verifier=lambda j, k: True, seal_dir=tmp_path / "s")
    me = (os.getpid(), os.getuid(), os.getgid())
    opened = core.handle({"protocol": worker.PROTOCOL, "op": "open_job_session",
                          "job_id": "job-x", "sites": [2], "max_runtime_s": 30}, me, "control")
    assert opened["ok"] and opened["result"]["owner_kind"] == "rest_job"
    reply = core.handle({"protocol": worker.PROTOCOL, "op": "probe", "site": 2}, me, "transport")
    assert reply == {"ok": False, "error": "NO_SESSION_FOR_PEER"}


def abi5_stub():
    class Stub:
        name = "stub"
        supported_sites = frozenset({1, 2})
        operations = frozenset({"probe", "flash_cycle"})

        def identity(self):
            return {"image_id": "x"}

        def startup_sealed_sites(self):
            return set()

        def run(self, *a, **k):
            return {"result": "PASS"}
    return Stub()


def test_target_config_must_exist_in_selected_engine_before_admission(tmp_path):
    sim = FlashSim(0x08000000, 0x10000)
    engine = make_engine(tmp_path / "openocd", "0.12.0-x-plasma-swd-666666666666",
                         configs=("other.cfg",))
    adapter = abi5.Abi5OpenocdAdapter(
        openocd_root=Path(engine["openocd_root"]), python=Path(sys.executable), adapter_khz=500,
        journal=tmp_path / "j", record_dir=tmp_path / "rec", run=sim.run, popen=sim.popen,
        openocd_running=lambda: False, poll_s=0.01)
    (tmp_path / "rec").mkdir()
    payload = b"FW"
    image = worker.FlashImage(worker.parse_flash_profile({
        "icpn": "STM32F103C8T6", "target_config": "target/stm32f1x.cfg",
        "flash_base": 0x08000000, "flash_size": 0x10000, "erase_granularity": 1024}),
        payload, hashlib.sha256(payload).hexdigest())
    with pytest.raises(worker.TransportDenied, match="TARGET_CONFIG_NOT_FOUND"):
        adapter.run(2, "flash_cycle", image=image, deadline=1e12, cancel=threading.Event())
    assert sim.argvs == []


def test_image_larger_than_profile_flash_is_refused_at_bind(tmp_path):
    core = worker.SiteWorkerCore(abi5_stub(), runtime_pid=os.getpid,
                                 lease_verifier=lambda j, k: True, seal_dir=tmp_path / "s",
                                 image_root=tmp_path / "img")
    me = (os.getpid(), os.getuid(), os.getgid())
    sid = core.handle({"protocol": worker.PROTOCOL, "op": "open_job_session", "job_id": "job-y",
                       "sites": [2], "max_runtime_s": 30}, me, "control")["result"]["session_id"]
    reply = core.handle({"protocol": worker.PROTOCOL, "op": "bind_image", "session_id": sid,
                         "profile": {"icpn": "TINY", "target_config": "target/t.cfg",
                                     "flash_base": 0, "flash_size": 1024,
                                     "erase_granularity": 1024},
                         "image_sha256": "0" * 64, "image_size": 2048}, me, "control")
    assert reply == {"ok": False, "error": "IMAGE_SIZE_INVALID"}
