"""PR-C1: PPU Gateway / Runtime Packaging / Installer without any IC Catalog.

Owner decision (OPF S0-S5): IC Catalog, IC Support and L0-L2 qualification are
offline governance; the Device Selector belongs to Manager. The PPU Gateway must
start, report Health and run Programming Jobs / Batches with no Catalog data, no
Catalog-only modules and no Catalog environment. The legacy Selector endpoint
must answer an explicit 503 when unavailable, never an empty (fake) result.

Host-only: fake OpenOCD / Mock interfaces; no Z2, FPGA, C driver or DUT. A fake
OpenOCD PASS is never a physical Flash PASS (HIL: NOT_RUN).
"""
from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from plasma_web import gateway

from .test_ppu_bundle_v3_packages_contract import ROOT
from .test_ppu_runtime_catalog_free import CatalogTripwire, _scenario

CATALOG_ENV = ("PLASMA_DEVICE_CATALOG_MANIFEST", "PLASMA_IC_SUPPORT_ROOT")


def _load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


packaging = _load_script("ppu_runtime_pr_c1", "ppu-runtime.py")
CATALOG_ONLY = tuple(m[:-3].replace("/", ".") for m in packaging.CATALOG_ONLY_MODULES)
GATEWAY_MODULES = (
    "plasma_web.gateway", "plasma_web.gateway_phase2", "plasma_web.gateway_phase3",
    "plasma_web.gateway_runner", "plasma_web.secure_gateway",
    "plasma_web.runtime_activation_helper", "plasma_server.runtime_server",
)

_PROBE = textwrap.dedent("""
    import importlib, importlib.abc, json, os, sys
    blocked, modules, roots, extra = json.loads(sys.argv[1])
    attempts = []
    class CatalogBlocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if any(name == b or name.startswith(b + ".") for b in blocked):
                attempts.append(name)
                raise ImportError("CATALOG_BLOCKED:" + name)
    sys.meta_path.insert(0, CatalogBlocker())
    for key in ("PLASMA_DEVICE_CATALOG_MANIFEST", "PLASMA_IC_SUPPORT_ROOT"):
        os.environ.pop(key, None)
    sys.path[:0] = roots
    result = {}
    for module in modules:
        try:
            importlib.import_module(module)
            result[module] = "OK"
        except Exception as exc:
            result[module] = type(exc).__name__ + ": " + str(exc)
    report = {"imports": result}
    if extra:
        from plasma_web import gateway
        report["warm"] = gateway.warm_legacy_device_selector()
        try:
            gateway._legacy_device_selector()
            report["selector"] = "LOADED"
        except gateway.DeviceSelectorUnavailable as exc:
            report["selector"] = "UNAVAILABLE"
    report["attempts_before_selector"] = [a for a in attempts if a != "plasma_web.legacy_device_selector"]
    report["loaded"] = sorted(k for k in sys.modules if any(k == b or k.startswith(b + ".") for b in blocked))
    print(json.dumps(report))
""")


def _probe(blocked, modules, *, extra=False):
    roots = [str(ROOT / "software/python")]
    completed = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE, json.dumps([list(blocked), list(modules), roots, extra])],
        check=True, capture_output=True, text=True, timeout=120, cwd="/")
    return json.loads(completed.stdout.strip().splitlines()[-1])


# --- import layer -----------------------------------------------------------------------

def test_gateway_and_runtime_entrypoints_import_with_every_catalog_module_blocked():
    report = _probe(CATALOG_ONLY, GATEWAY_MODULES, extra=True)
    assert report["imports"] == {m: "OK" for m in GATEWAY_MODULES}, report
    # Startup never touched a Catalog module; only the optional Selector probe did.
    assert report["attempts_before_selector"] == [] and report["loaded"] == [], report
    assert report["warm"] is False and report["selector"] == "UNAVAILABLE"


def test_catalog_blocker_negative_control():
    report = _probe(CATALOG_ONLY, ("plasma_web.legacy_device_selector", "plasma_web.device_catalog"))
    assert all(v.startswith("ImportError: CATALOG_BLOCKED:") for v in report["imports"].values())


def test_gateway_module_holds_no_catalog_symbol():
    source = (ROOT / "software/python/plasma_web/gateway.py").read_text(encoding="utf-8")
    for module in CATALOG_ONLY:
        if module.endswith("legacy_device_selector"):
            continue
        leaf = module.rsplit(".", 1)[-1]
        assert f"import {leaf}" not in source and f".{leaf} import" not in source, leaf
    for attr in ("get_default_device_catalog", "get_default_programming_qualification_registry",
                 "get_default_ic_support_resolver", "_device_search_payload"):
        assert not hasattr(gateway, attr), attr


# --- Selector: optional, explicit, never fake-empty ---------------------------------------

def _get(handler_class, path):
    handler = object.__new__(handler_class)
    handler.path = path
    handler.command = "GET"
    handler.headers = {}
    response = []
    handler._json = lambda status, body: response.append((int(status), body))
    handler.do_GET()
    return response[0]


def test_selector_absent_is_503_not_empty(monkeypatch):
    monkeypatch.setitem(sys.modules, gateway.LEGACY_DEVICE_SELECTOR_MODULE, None)
    status, body = _get(gateway.PlasmaWebHandler, "/api/devices/search?q=STM32&limit=5")
    assert status == 503, body
    assert body["ok"] is False and "results" not in body
    assert body["error"]["error_type"] == "DEVICE_SELECTOR_UNAVAILABLE"
    assert gateway.warm_legacy_device_selector() is False


def test_selector_catalog_data_failure_is_503_and_bad_query_is_400(monkeypatch):
    from plasma_web import legacy_device_selector
    from plasma_web.device_catalog import DeviceCatalogIntegrityError

    def unavailable():
        raise DeviceCatalogIntegrityError("Catalog data absent")

    status, body = _get(gateway.PlasmaWebHandler, "/api/devices/search?q=STM32&limit=0")
    assert status == 400 and body["error"]["error_type"] == "INVALID_DEVICE_SEARCH"
    monkeypatch.setattr(legacy_device_selector, "get_default_device_catalog", unavailable)
    status, body = _get(gateway.PlasmaWebHandler, "/api/devices/search?q=STM32&limit=5")
    assert status == 503 and "results" not in body
    assert body["error"]["error_type"] == "DEVICE_SELECTOR_UNAVAILABLE"


# --- call layer: Bundle v3 Mock path with the Selector module absent ----------------------

@pytest.fixture
def selector_absent(monkeypatch):
    for key in CATALOG_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(sys.modules, gateway.LEGACY_DEVICE_SELECTOR_MODULE, None)
    return CatalogTripwire(monkeypatch)


def test_bundle_v3_mock_flash_passes_with_selector_and_catalog_absent(selector_absent):
    outcome = _scenario("non-catalog-bundle")
    assert outcome["state"] == "success", outcome
    assert (outcome["result"], outcome["safe_off"]) == ("PASS", True)
    assert selector_absent.calls == []


@pytest.mark.parametrize("case,code", [
    ("catalog-qualified-target-without-bundle", "REFERENCE_TARGET_MISMATCH"),
    ("no-active-set", "OPF_ACTIVE_SET_REQUIRED"),
    ("unsupported-operation", None),
])
def test_bundle_target_provider_negatives_hold_with_selector_absent(selector_absent, case, code):
    outcome = _scenario(case)
    assert outcome["state"] != "success", outcome
    if code is not None:
        assert code in outcome["detail"], outcome
    assert outcome["argvs"] == 0 and outcome["sessions"] == 0
    assert selector_absent.calls == []


@pytest.mark.parametrize("case", [
    "non-catalog-bundle", "catalog-known-bundle",
    "catalog-qualified-target-without-bundle", "no-active-set", "unsupported-operation",
])
def test_selector_availability_never_changes_job_decision(monkeypatch, case):
    with_selector = _scenario(case)
    monkeypatch.setitem(sys.modules, gateway.LEGACY_DEVICE_SELECTOR_MODULE, None)
    tripwire = CatalogTripwire(monkeypatch)
    without_selector = _scenario(case)
    keys = ("state", "http", "result", "icpn", "safe_off", "argvs", "sessions")
    assert {k: with_selector.get(k) for k in keys} == {k: without_selector.get(k) for k in keys}
    assert tripwire.calls == []


# --- packaged runtime: real ppu.pyz Server + Gateway processes, no Catalog -----------------

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux process runtime")
def test_packaged_runtime_gateway_health_passes_without_catalog(tmp_path: Path):
    acceptance = _load_script("ppu_armv7_acceptance_pr_c1", "ppu-armv7-runtime-acceptance.py")
    runtime_dir = tmp_path / "runtime"
    packaging.build_runtime(repo_root=ROOT, output_dir=runtime_dir)
    assert not (runtime_dir / "data").exists()
    app = runtime_dir / "ppu" / "ppu.pyz"
    server_port, gateway_port = _free_port(), _free_port()
    work = tmp_path / "work"
    config = acceptance._write_config(work, server_port=server_port)
    (work / "gateway-output").mkdir(parents=True)
    env = {"PATH": "/usr/bin:/bin", "PYTHONUNBUFFERED": "1"}
    # -I -S: like the Plasma-owned PPU Python, no site-packages; an installed
    # (e.g. editable) Plasma package must never shadow the packaged zipapp.
    origin = subprocess.run(
        [sys.executable, "-I", "-S", "-c",
         f"import sys; sys.path.insert(0, {str(app)!r}); import plasma_web, importlib.util as u; "
         "print(plasma_web.__file__); print(u.find_spec('plasma_web.legacy_device_selector'))"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=True)
    module_file, selector_spec = origin.stdout.split()[:2]
    assert module_file.startswith(str(app)), origin.stdout
    assert selector_spec == "None", origin.stdout
    logs = {name: work / f"{name}.log" for name in ("server", "gateway")}
    procs = {}
    try:
        with logs["server"].open("wb") as s_log, logs["gateway"].open("wb") as g_log:
            procs["server"] = subprocess.Popen(
                [sys.executable, "-I", "-S", str(app), "server", "--config", str(config)],
                cwd=work, env=env, stdout=s_log, stderr=subprocess.STDOUT)
            procs["gateway"] = subprocess.Popen(
                [sys.executable, "-I", "-S", str(app), "gateway", "--host", "127.0.0.1",
                 "--port", str(gateway_port), "--plasma-host", "127.0.0.1",
                 "--plasma-port", str(server_port), "--output-root", str(work / "gateway-output")],
                cwd=work, env=env, stdout=g_log, stderr=subprocess.STDOUT)
            base_url = f"http://127.0.0.1:{gateway_port}"
            ready = acceptance._wait_ready(
                base_url, deadline_s=60, server=procs["server"], gateway=procs["gateway"],
                server_log=logs["server"], gateway_log=logs["gateway"])
            assert ready["execution"] == "ready"
            status, live = acceptance._request_json(f"{base_url}/api/health/live")
            assert status == 200 and live["gateway"] == "alive"
            status, node = acceptance._request_json(f"{base_url}/api/node")
            assert status == 200 and node["node_role"] == "ppu"
            loopback = acceptance._run_loopback(base_url)
            assert loopback
            status, selector = acceptance._request_json(f"{base_url}/api/devices/search?q=STM32")
            assert status == 503, selector
            assert selector["error"]["error_type"] == "DEVICE_SELECTOR_UNAVAILABLE"
            assert "results" not in selector
            for name, proc in procs.items():
                assert proc.poll() is None, logs[name].read_text(errors="replace")
    finally:
        for proc in procs.values():
            acceptance._terminate(proc)
    gateway_log = logs["gateway"].read_text(errors="replace")
    assert "Traceback" not in gateway_log, gateway_log
