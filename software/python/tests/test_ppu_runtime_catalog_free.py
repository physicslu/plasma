"""S5: the PPU Runtime executes a verified Bundle v3 without any IC Catalog.

Owner decision 2026-11-08: IC Catalog / L0-L2 qualification / admission data is
independent offline governance and never a direct or indirect PPU Runtime
execution dependency. PPU execution is decided only by the verified Active
Bundle, device capability, authorization and hardware safety.

Two layers are proven Host-only (no Z2/FPGA/DUT; a fake OpenOCD is never a
physical Flash PASS):

* import layer: a clean interpreter with every Catalog / retired-compiler module
  blocked and no Catalog data roots imports all PPU Runtime execution modules;
* call layer: the real installed-Bundle -> Runtime -> C-3 path runs while every
  Catalog query entry point is a tripwire, and its decisions are identical with
  and without a Catalog.

The Web Gateway's own Catalog imports (Device Selector) are a separate PR-C scope.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from .test_c3_rest_flash_cycle import Stack, run, short_tmp
from .test_ppu_bundle_v3_packages_contract import ROOT

CATALOG_MODULES = (
    "plasma_core.ic_support",
    "plasma_core.manufacturer_device_basic",
    "plasma_web",
    "plasma_interfaces.compiler_registry",
    "plasma_interfaces.openocd_plan",
    "plasma_interfaces.openocd_executor",
    "plasma_interfaces.kl25_openocd_plan",
)
RUNTIME_EXECUTION_MODULES = (
    "plasma_server.runtime_server", "plasma_server.server", "plasma_server.site_manager",
    "plasma_server.package_actions", "plasma_server.execution_router",
    "plasma_interfaces.openocd", "plasma_interfaces.site_worker_c3", "plasma_client.client",
    "plasma_opf",
    "ppu_site_worker_service", "ppu_site_worker", "ppu_site_engine", "ppu_site_adapter_abi5",
    "ppu_site_recovery", "ppu_opf_reference_openocd", "ppu_opf_site_session",
    "ppu_asset_set", "ppu_asset_execution", "ppu_unified_deployment", "ppu_provider_contract",
    "ppu_package_entry", "ppu_package_launcher", "ppu_package_unit_helper",
)
CATALOG_GETTER_MODULES = (
    "plasma_core.ic_support", "plasma_core.manufacturer_device_basic",
    "plasma_web.device_catalog", "plasma_web.programming_qualification",
    "plasma_web.openocd_software_qualification", "plasma_web.backend_candidate_registry",
    "plasma_web.openocd_provider_registry", "plasma_web.nxp_kl25_qualification",
    "plasma_web.nxp_manufacturer_device_evidence",
)
NON_CATALOG_ICPN = "ACME-NOCAT-0001"
CATALOG_KNOWN_ICPN = "STM32F103C8T6"

_PROBE = textwrap.dedent("""
    import importlib, importlib.abc, json, os, sys
    blocked, modules, roots = json.loads(sys.argv[1])
    attempts = []
    class CatalogBlocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if any(name == b or name.startswith(b + ".") for b in blocked):
                attempts.append(name)
                raise ImportError("CATALOG_BLOCKED:" + name)
    sys.meta_path.insert(0, CatalogBlocker())
    os.environ["PLASMA_IC_SUPPORT_ROOT"] = "/nonexistent/plasma-ic-support"
    os.environ["PLASMA_DEVICE_CATALOG_MANIFEST"] = "/nonexistent/plasma-catalog.json"
    sys.path[:0] = roots
    result = {}
    for module in modules:
        try:
            importlib.import_module(module)
            result[module] = "OK"
        except Exception as exc:
            result[module] = type(exc).__name__ + ": " + str(exc)
    loaded = sorted(k for k in sys.modules if any(k == b or k.startswith(b + ".") for b in blocked))
    print(json.dumps({"imports": result, "attempts": attempts, "loaded": loaded}))
""")


def _probe(blocked, modules):
    roots = [str(ROOT / "software/python"), str(ROOT / "scripts")]
    completed = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE, json.dumps([list(blocked), list(modules), roots])],
        check=True, capture_output=True, text=True, timeout=120, cwd="/")
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_runtime_execution_modules_import_without_any_catalog_module_or_data():
    report = _probe(CATALOG_MODULES, RUNTIME_EXECUTION_MODULES)
    assert report["imports"] == {m: "OK" for m in RUNTIME_EXECUTION_MODULES}, report
    assert report["attempts"] == [] and report["loaded"] == [], report


def test_catalog_blocker_is_effective_negative_control():
    report = _probe(CATALOG_MODULES, ("plasma_core.ic_support", "plasma_web.device_catalog"))
    assert all(v.startswith("ImportError: CATALOG_BLOCKED:") for v in report["imports"].values())


class CatalogTripwire:
    """Replace every Catalog query entry point; any call is a Runtime violation."""

    def __init__(self, monkeypatch):
        self.calls: list[str] = []
        originals: dict[int, str] = {}
        for name in CATALOG_GETTER_MODULES:
            module = importlib.import_module(name)
            for attr, value in vars(module).items():
                if attr.startswith("get_default_") and callable(value) \
                        and getattr(value, "__module__", None) == name:
                    originals[id(value)] = f"{name}.{attr}"
        for module in list(sys.modules.values()):
            if module is None or not getattr(module, "__name__", "").startswith(("plasma_", "ppu_")):
                continue
            for attr, value in list(vars(module).items()):
                label = originals.get(id(value))
                if label is not None:
                    monkeypatch.setattr(module, attr, self._raiser(label))

    def _raiser(self, label):
        def tripwire(*_args, **_kwargs):
            self.calls.append(label)
            raise AssertionError("PPU Runtime queried the IC Catalog: " + label)
        return tripwire


@pytest.fixture
def no_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("PLASMA_IC_SUPPORT_ROOT", str(tmp_path / "absent-ic-support"))
    monkeypatch.setenv("PLASMA_DEVICE_CATALOG_MANIFEST", str(tmp_path / "absent-catalog.json"))
    return CatalogTripwire(monkeypatch)


def _scenario(case):
    """Run one Bundle-driven Job; return the Runtime decision summary."""
    bundle_icpn = NON_CATALOG_ICPN if case != "catalog-known-bundle" else CATALOG_KNOWN_ICPN
    target = {"non-catalog-bundle": NON_CATALOG_ICPN,
              "catalog-known-bundle": CATALOG_KNOWN_ICPN,
              "catalog-qualified-target-without-bundle": CATALOG_KNOWN_ICPN,
              "no-active-set": CATALOG_KNOWN_ICPN,
              "unsupported-operation": NON_CATALOG_ICPN}[case]

    async def body():
        with short_tmp() as directory:
            async with Stack(Path(directory), site_target=target, in_process=True,
                             bundle_options={"target_icpn": bundle_icpn}) as stack:
                if case == "no-active-set":
                    stack.manager._active_asset_set_reader = lambda: {"state": "EMPTY"}
                extra = {"operation": "erase"} if case == "unsupported-operation" else {}
                outcome = await stack.flash(b"CATALOG-FREE-" + case.encode(), **extra)
                summary = {"argvs": len(stack.sim.argvs), "sessions": len(stack.core._sessions)}
                if isinstance(outcome[0], int):
                    return {**summary, "state": "rejected", "http": outcome[0],
                            "detail": json.dumps(outcome[1], sort_keys=True)}
                _job_id, job = outcome
                summary.update(state=job["state"], detail=json.dumps(job, sort_keys=True))
                if job["state"] == "success":
                    cycle = job["result"]["details"]["flash_cycle"]
                    summary.update(result=cycle["result"], icpn=cycle["icpn"],
                                   safe_off=cycle["safe_off"])
                return summary
    return run(body())


def test_verified_bundle_for_non_catalog_icpn_flashes_without_catalog(no_catalog):
    outcome = _scenario("non-catalog-bundle")
    assert outcome["state"] == "success", outcome
    assert (outcome["result"], outcome["icpn"], outcome["safe_off"]) == ("PASS", NON_CATALOG_ICPN, True)
    assert outcome["argvs"] == 1 and outcome["sessions"] == 0
    assert no_catalog.calls == []


@pytest.mark.parametrize("case,code", [
    ("catalog-qualified-target-without-bundle", "REFERENCE_TARGET_MISMATCH"),
    ("no-active-set", "OPF_ACTIVE_SET_REQUIRED"),
    ("unsupported-operation", None),
])
def test_runtime_refuses_without_bundle_authority_and_never_queries_catalog(no_catalog, case, code):
    outcome = _scenario(case)
    assert outcome["state"] != "success", outcome
    if code is not None:
        assert code in outcome["detail"], outcome
    assert outcome["argvs"] == 0 and outcome["sessions"] == 0
    assert no_catalog.calls == []


@pytest.mark.parametrize("case", [
    "non-catalog-bundle", "catalog-known-bundle",
    "catalog-qualified-target-without-bundle", "no-active-set",
])
def test_catalog_presence_never_changes_the_runtime_decision(monkeypatch, tmp_path, case):
    with_catalog = _scenario(case)
    tripwire = CatalogTripwire(monkeypatch)
    monkeypatch.setenv("PLASMA_IC_SUPPORT_ROOT", str(tmp_path / "absent"))
    monkeypatch.setenv("PLASMA_DEVICE_CATALOG_MANIFEST", str(tmp_path / "absent.json"))
    without_catalog = _scenario(case)
    keys = ("state", "result", "icpn", "safe_off", "argvs", "sessions")
    assert {k: with_catalog.get(k) for k in keys} == {k: without_catalog.get(k) for k in keys}
    assert tripwire.calls == []
