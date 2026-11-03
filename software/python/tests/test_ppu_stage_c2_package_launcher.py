"""Stage C-2: non-root Package process executor (Host-only, REAL child processes).

Runs tiny test Packages from a B3-staged Active Set through the real dispatch
seam and SiteManager lease. No Z2, FPGA, MMIO or DUT. Must run as non-root.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from plasma_core.config import PlasmaConfig, PPUConfig, ServerConfig, SiteConfig
from plasma_server.site_manager import SiteManager

from .test_ppu_asset_execution_gate1 import JOB, Owner, _ready_fixture, execution
from .test_ppu_bundle_v3_packages_contract import ROOT

spec = importlib.util.spec_from_file_location("ppu_package_launcher_c2", ROOT / "scripts/ppu_package_launcher.py")
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)

pytestmark = pytest.mark.skipif(os.geteuid() == 0, reason="launcher contract requires non-root")


def res(sites=(), runtime=10) -> bytes:
    return json.dumps({"schema": "plasma.ppu.package-resources.v1",
                       "sites": list(sites), "max_runtime_s": runtime}).encode()


def parts(main: bytes, *, sites=(), runtime=10, native: bytes | None = None):
    out = [("tool", "python", [], {"python/main.py": main,
                                     "config/plasma-package-resources.json": res(sites, runtime)})]
    if native is not None:
        out.append(("ntool", "native-c", [], {"bin/ntool": native,
                                                "config/plasma-package-resources.json": res(sites, runtime)}))
    return out


def ready(tmp_path, main: bytes, **kw):
    co, requests, owner, _ = _ready_fixture(tmp_path / "set", parts=parts(main, **kw))
    return co, requests, owner


def run(co, request, owner, tmp_path, *, cancel=None, scope=None):
    executor = launcher.make_package_executor(
        co.paths.product_root, python_executable=Path(sys.executable),
        state_root=tmp_path / "actions", cancel_event=cancel)

    from contextlib import contextmanager

    @contextmanager
    def lease():
        yield {"job_id": request.job_id, "site_ids": [1, 2]}

    return execution.dispatch_asset_execution(
        co.paths.product_root, request, **owner.kw(request),
        execution_scope=scope or lease,
        trusted_executors={request.package_kind: executor})


def journal(tmp_path):
    return json.loads((tmp_path / "actions" / f"{JOB}.json").read_text())


def test_python_package_runs_non_root_with_clean_env_and_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("PLASMA_SECRET_SHOULD_NOT_LEAK", "s3cret")
    main = (b"import os, json\n"
            b"print(json.dumps({'uid': os.getuid(), 'cwd': os.getcwd(), 'env': sorted(os.environ)}))\n")
    co, requests, owner = ready(tmp_path, main)
    result = run(co, requests["python"], owner, tmp_path)
    receipt = result["executor_result"]
    assert receipt["schema"] == "plasma.ppu.package-action-receipt.v1"
    assert receipt["result"] == "SUCCEEDED" and receipt["exit_code"] == 0
    assert receipt["job_id"] == JOB and receipt["hardware"] == "NONE"
    assert receipt["process_group_reaped"] is True and receipt["uid"] != 0
    seen = json.loads(receipt["stdout"]["tail"])
    assert seen["uid"] == os.getuid() != 0
    assert "PLASMA_SECRET_SHOULD_NOT_LEAK" not in seen["env"]
    assert set(seen["env"]) <= {"PATH", "LANG", "HOME", "PLASMA_JOB_ID", "PLASMA_PACKAGE_ID", "LC_CTYPE"}
    assert Path(seen["cwd"]).parent == tmp_path / "actions"
    assert not Path(seen["cwd"]).exists()  # private work dir removed
    rec = journal(tmp_path)
    assert rec["state"] == "succeeded" and rec["job_id"] == JOB
    assert launcher.interrupted_actions(tmp_path / "actions") == []


def test_package_cannot_open_dev_mem(tmp_path):
    main = (b"try:\n open('/dev/mem','rb'); print('OPENED')\n"
            b"except OSError as e:\n print('DENIED', type(e).__name__)\n")
    co, requests, owner = ready(tmp_path, main)
    receipt = run(co, requests["python"], owner, tmp_path)["executor_result"]
    assert receipt["result"] == "SUCCEEDED"
    assert "DENIED" in receipt["stdout"]["tail"] and "OPENED" not in receipt["stdout"]["tail"]


def test_nonzero_exit_is_failed(tmp_path):
    co, requests, owner = ready(tmp_path, b"import sys\nsys.stderr.write('boom')\nsys.exit(3)\n")
    receipt = run(co, requests["python"], owner, tmp_path)["executor_result"]
    assert receipt["result"] == "FAILED" and receipt["exit_code"] == 3
    assert receipt["stderr"]["tail"] == "boom"
    assert journal(tmp_path)["state"] == "failed"


def test_timeout_kills_whole_process_group_including_grandchild(tmp_path):
    marker = tmp_path / "grandchild.pid"
    main = (b"import os, subprocess, sys, time\n"
            b"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            b"open(%r, 'w').write(str(p.pid))\n"
            b"time.sleep(60)\n" % str(marker).encode())
    co, requests, owner = ready(tmp_path, main, runtime=1)
    t0 = time.monotonic()
    receipt = run(co, requests["python"], owner, tmp_path)["executor_result"]
    assert receipt["result"] == "TIMEOUT" and receipt["signal"] is not None
    assert time.monotonic() - t0 < 10
    assert receipt["process_group_reaped"] is True
    pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert journal(tmp_path)["state"] == "timeout"


def test_cancel_event_kills_the_package(tmp_path):
    co, requests, owner = ready(tmp_path, b"import time\ntime.sleep(60)\n", runtime=60)
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    receipt = run(co, requests["python"], owner, tmp_path, cancel=cancel)["executor_result"]
    assert receipt["result"] == "CANCELLED" and receipt["duration_s"] < 10
    assert journal(tmp_path)["state"] == "cancelled"


def test_output_is_bounded(tmp_path):
    co, requests, owner = ready(tmp_path, b"import sys\nsys.stdout.write('x' * 200000)\n")
    receipt = run(co, requests["python"], owner, tmp_path)["executor_result"]
    assert receipt["stdout"]["truncated"] is True and receipt["stdout"]["bytes"] == 64 * 1024
    assert len(receipt["stdout"]["tail"]) == 4096


def test_native_c_entry_is_the_single_bin_executable(tmp_path):
    native = b"#!/bin/sh\necho native-ok\n"
    co, requests, owner = ready(tmp_path, b"pass\n", native=native)
    staged = co.paths.product_root / "assets/staged" / requests["native-c"].asset_set_sha256
    entry = staged / "payload/packages/ntool/bin/ntool"
    if not os.access(entry, os.X_OK):
        pytest.skip("staged installer did not preserve the executable bit on this host")
    receipt = run(co, requests["native-c"], owner, tmp_path)["executor_result"]
    assert receipt["result"] == "SUCCEEDED" and "native-ok" in receipt["stdout"]["tail"]


def test_package_declaring_sites_refused_until_site_transport(tmp_path):
    co, requests, owner = ready(tmp_path, b"print('never')\n", sites=(2,))
    with pytest.raises(launcher.PackageLaunchDenied, match="PACKAGE_SITE_TRANSPORT_NOT_WIRED"):
        run(co, requests["python"], owner, tmp_path)
    assert not (tmp_path / "actions" / f"{JOB}.json").exists()


def test_root_is_refused(tmp_path):
    co, requests, owner = ready(tmp_path, b"print('never')\n")
    plan = execution.prepare_asset_execution(co.paths.product_root, requests["python"],
                                             **owner.kw(requests["python"]))
    run_as_root = launcher.make_package_executor(
        co.paths.product_root, python_executable=Path(sys.executable),
        state_root=tmp_path / "actions", geteuid=lambda: 0)
    with pytest.raises(launcher.PackageLaunchDenied, match="MUST_NOT_RUN_AS_ROOT"):
        run_as_root(plan)


def test_tampered_entrypoint_is_refused_before_spawn(tmp_path):
    co, requests, owner = ready(tmp_path, b"print('original')\n")
    plan = execution.prepare_asset_execution(co.paths.product_root, requests["python"],
                                             **owner.kw(requests["python"]))
    path = co.paths.product_root / "assets/staged" / plan["asset_set_sha256"] / plan["entrypoint"]["path"]
    path.chmod(0o600)
    path.write_bytes(b"print('evil')\n")
    executor = launcher.make_package_executor(
        co.paths.product_root, python_executable=Path(sys.executable), state_root=tmp_path / "actions")
    with pytest.raises(launcher.PackageLaunchDenied, match="ENTRYPOINT_CHANGED"):
        executor(plan)
    for bad in (dict(plan, entrypoint=dict(plan["entrypoint"], path="payload/packages/other/python/main.py")),
                dict(plan, entrypoint=dict(plan["entrypoint"], path="payload/packages/tool/../x.py")),
                dict(plan, package_kind="fpga-image"), dict(plan, job_id="x")):
        with pytest.raises(launcher.PackageLaunchDenied):
            executor(bad)


def test_same_job_cannot_be_launched_twice(tmp_path):
    co, requests, owner = ready(tmp_path, b"print('once')\n")
    assert run(co, requests["python"], owner, tmp_path)["executor_result"]["result"] == "SUCCEEDED"
    with pytest.raises(launcher.PackageLaunchDenied, match="JOB_ALREADY_RECORDED"):
        run(co, requests["python"], owner, tmp_path)


def test_python_package_without_main_has_no_entrypoint(tmp_path):
    bad = [("tool", "python", [], {"python/other.py": b"pass\n",
                                     "config/plasma-package-resources.json": res()})]
    co, requests, owner, _ = _ready_fixture(tmp_path / "set", parts=bad)
    with pytest.raises(execution.AssetExecutionDenied, match="ENTRYPOINT_INVALID"):
        execution.prepare_asset_execution(co.paths.product_root, requests["python"],
                                          **owner.kw(requests["python"]))


def test_interrupted_running_record_is_reported(tmp_path):
    root = tmp_path / "actions"
    root.mkdir()
    (root / f"{'4' * 32}.json").write_text(json.dumps({"state": "running"}))
    (root / f"{'5' * 32}.json").write_text(json.dumps({"state": "succeeded"}))
    assert launcher.interrupted_actions(root) == ["4" * 32]


def test_end_to_end_through_real_site_manager_lease(tmp_path):
    co, requests, owner = ready(tmp_path, b"print('via-site-manager')\n")
    cfg = PlasmaConfig(
        ppu=PPUConfig(id="ppu-a", facility_id="lab", model="t", display_name="A"),
        server=ServerConfig(host="127.0.0.1", port=9900, max_supported_sites=8, max_concurrent_jobs=1,
                            max_queue_depth_per_site=4, output_root=tmp_path / "o", log_root=tmp_path / "l"),
        sites=[SiteConfig(id=1, enabled=True, interface="mock")])

    async def scenario():
        manager = SiteManager(cfg)
        await manager.start()
        try:
            req = requests["python"]
            result = run(co, req, owner, tmp_path,
                         scope=lambda: manager.package_action_scope(req.job_id))
            assert result["executor_result"]["result"] == "SUCCEEDED"
            assert "via-site-manager" in result["executor_result"]["stdout"]["tail"]
            assert manager.execution_lease_snapshot()["busy"] is False
        finally:
            await manager.shutdown()
    asyncio.run(scenario())
