"""PR-C1: PPU Gateway / Runtime Packaging / Installer without any IC Catalog.

Owner decision (OPF S0-S5): IC Catalog, IC Support and L0-L2 qualification are
offline governance; the Device Selector belongs to Manager. The PPU Gateway must
start, report Health and run Programming Jobs / Batches with no Catalog data, no
Catalog-only modules and no Catalog environment.

S5-B: the transitional PPU Selector route is deleted. ``GET /api/devices/search``
is served only by Plasma Manager; on the PPU Gateway it is an unknown route
(404, never a fake-empty result) and the Secure Gateway has no authorization
rule for it (fail-closed).

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
SELECTOR_MODULE = "plasma_web.legacy_device_selector"


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
    report["attempts"] = attempts
    report["loaded"] = sorted(k for k in sys.modules if any(k == b or k.startswith(b + ".") for b in blocked))
    print(json.dumps(report))
""")


def _probe(blocked, modules):
    roots = [str(ROOT / "software/python")]
    completed = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE, json.dumps([list(blocked), list(modules), roots, False])],
        check=True, capture_output=True, text=True, timeout=120, cwd="/")
    return json.loads(completed.stdout.strip().splitlines()[-1])


# --- import layer -----------------------------------------------------------------------

def test_gateway_and_runtime_entrypoints_import_with_every_catalog_module_blocked():
    report = _probe(CATALOG_ONLY, GATEWAY_MODULES)
    assert report["imports"] == {m: "OK" for m in GATEWAY_MODULES}, report
    # No Gateway / Runtime entrypoint even attempts a Catalog (or Selector) import.
    assert report["attempts"] == [] and report["loaded"] == [], report


def test_catalog_blocker_negative_control():
    report = _probe(CATALOG_ONLY, (SELECTOR_MODULE, "plasma_web.device_catalog"))
    assert all(v.startswith("ImportError: CATALOG_BLOCKED:") for v in report["imports"].values())


def test_gateway_module_holds_no_catalog_symbol():
    source = (ROOT / "software/python/plasma_web/gateway.py").read_text(encoding="utf-8")
    for module in CATALOG_ONLY:
        leaf = module.rsplit(".", 1)[-1]
        assert f"import {leaf}" not in source and f".{leaf} import" not in source, leaf
        assert module not in source, module
    for attr in ("get_default_device_catalog", "get_default_programming_qualification_registry",
                 "get_default_ic_support_resolver", "_device_search_payload",
                 # S5-B: transitional Selector adapter hooks are deleted.
                 "LEGACY_DEVICE_SELECTOR_MODULE", "DeviceSelectorUnavailable",
                 "_legacy_device_selector", "warm_legacy_device_selector"):
        assert not hasattr(gateway, attr), attr
    for attr in ("_is_device_search_path", "_device_search", "_device_selector_unavailable"):
        assert not hasattr(gateway.PlasmaWebHandler, attr), attr
    assert "/api/devices/search" not in source
    secure_source = (ROOT / "software/python/plasma_web/secure_gateway.py").read_text(encoding="utf-8")
    assert "/api/devices/search" not in secure_source


# --- Selector route: deleted from the PPU Gateway (owned by Manager) --------------------

def _get(handler_class, path):
    handler = object.__new__(handler_class)
    handler.path = path
    handler.command = "GET"
    handler.headers = {}
    response = []
    handler._json = lambda status, body: response.append((int(status), body))
    handler.do_GET()
    return response[0]


@pytest.mark.parametrize("path", ["/api/devices/search?q=STM32&limit=5",
                                  "/api/devices/search/?q=STM32F103C8T6",
                                  "/api/devices/search?q=STM32&limit=0"])
@pytest.mark.parametrize("selector_importable", [True, False])
def test_gateway_device_search_is_unknown_route_never_results(monkeypatch, path, selector_importable):
    if not selector_importable:
        monkeypatch.setitem(sys.modules, SELECTOR_MODULE, None)
    status, body = _get(gateway.PlasmaWebHandler, path)
    # Same answer whether or not Catalog code is importable: no Selector here.
    assert status == 404, body
    assert body["ok"] is False and "results" not in body and "catalog_size" not in body


def test_secure_gateway_has_no_device_search_authorization_rule():
    from plasma_core.errors import ErrorCode, PlasmaError
    from plasma_web import secure_gateway

    handler = object.__new__(secure_gateway.SecurePlasmaWebHandler)
    handler.path = "/api/devices/search?q=STM32"
    handler.command = "GET"
    handler._principal = lambda: type("P", (), {"principal_id": "p"})()
    handler._authorize = lambda *a, **k: pytest.fail(f"unexpected authorization rule {a}")
    with pytest.raises(PlasmaError) as caught:
        handler._guard_get()
    assert caught.value.code == ErrorCode.AUTHORIZATION_DENIED


# --- call layer: Bundle v3 Mock path with the Selector module absent ----------------------

@pytest.fixture
def selector_absent(monkeypatch):
    for key in CATALOG_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(sys.modules, SELECTOR_MODULE, None)
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
    monkeypatch.setitem(sys.modules, SELECTOR_MODULE, None)
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
            assert status == 404, selector  # S5-B: no Selector route on the PPU
            assert "results" not in selector
            for name, proc in procs.items():
                assert proc.poll() is None, logs[name].read_text(errors="replace")
    finally:
        for proc in procs.values():
            acceptance._terminate(proc)
    gateway_log = logs["gateway"].read_text(errors="replace")
    assert "Traceback" not in gateway_log, gateway_log
