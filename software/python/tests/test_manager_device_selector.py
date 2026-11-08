"""PR-C2: Plasma Manager owns the Catalog-only Device Selector.

The Console reaches ``GET /api/devices/search`` through its Manager BFF; the
Manager answers in-process from Catalog data it owns and never relays the
query to a PPU (a Catalog-free PPU answers 503). Host-only; no PPU, Z2, FPGA or
DUT is contacted.
"""
from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from plasma_manager import server as manager_server
from plasma_web import gateway_base, legacy_device_selector

ROOT = Path(__file__).resolve().parents[3]


def _get(port: int, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=60) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.fixture
def manager_port():
    httpd = manager_server.PlasmaManagerHTTPServer(("127.0.0.1", 0), manager_server.PlasmaManagerHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_port
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_selector_contract_version_matches_web_rest_contract():
    assert legacy_device_selector.WEB_REST_CONTRACT_VERSION == gateway_base.WEB_REST_CONTRACT_VERSION


def test_manager_serves_device_search_in_process(manager_port):
    status, body = _get(manager_port, "/api/devices/search?q=STM32F103C8T6&limit=1")
    assert status == 200, body
    assert body["scope"] == "customer_ic_selector"
    assert body["results"][0]["icpn"] == "STM32F103C8T6"
    assert body["results"][0]["selected_profile"]["icpn"] == "STM32F103C8T6"
    status, body = _get(manager_port, "/api/devices/search?q=MCXA185VLH&limit=1")
    assert status == 200 and body["total_count"] == 0  # Level 0 stays internal


def test_manager_rejects_invalid_search_with_400(manager_port):
    status, body = _get(manager_port, "/api/devices/search?q=STM32&limit=0")
    assert status == 400 and body["error"]["error_type"] == "INVALID_DEVICE_SEARCH"
    status, body = _get(manager_port, "/api/devices/search?levels=0")
    assert status == 400 and body["error"]["error_type"] == "INVALID_DEVICE_SEARCH"


def test_manager_selector_unavailable_is_503_not_empty(manager_port, monkeypatch):
    monkeypatch.setitem(sys.modules, manager_server.DEVICE_SELECTOR_MODULE, None)
    status, body = _get(manager_port, "/api/devices/search?q=STM32")
    assert status == 503 and "results" not in body
    assert body["error"]["error_type"] == "DEVICE_SELECTOR_UNAVAILABLE"
    assert manager_server.warm_device_selector() is False


def test_manager_catalog_data_failure_is_503(manager_port, monkeypatch):
    from plasma_web.device_catalog import DeviceCatalogIntegrityError

    def unavailable():
        raise DeviceCatalogIntegrityError("Catalog data absent")

    monkeypatch.setattr(legacy_device_selector, "get_default_device_catalog", unavailable)
    status, body = _get(manager_port, "/api/devices/search?q=STM32")
    assert status == 503 and "results" not in body
    assert body["error"]["error_type"] == "DEVICE_SELECTOR_UNAVAILABLE"


def test_manager_no_longer_relays_device_search_to_a_ppu():
    handler = manager_server.PlasmaManagerHandler
    assert not handler._managed_route_allowed("GET", "/api/devices/search")
    # Programming / Health relays are unchanged.
    for path in ("/api/status", "/api/health/ready", "/api/batches/b-1"):
        assert handler._managed_route_allowed("GET", path), path


# --- packaged Control Station Manager --------------------------------------------------

def _load_packager():
    spec = importlib.util.spec_from_file_location(
        "control_station_runtime_pr_c2", ROOT / "scripts" / "control-station-runtime.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _standalone(tmp_path: Path) -> Path:
    console = tmp_path / "standalone"
    (console / ".next").mkdir(parents=True)
    (console / "server.js").write_text("console.log('fake console')\n", encoding="utf-8")
    (console / "package.json").write_text('{"name":"plasma-web"}\n', encoding="utf-8")
    (console / ".next" / "BUILD_ID").write_text("test\n", encoding="utf-8")
    return console


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux process runtime")
def test_packaged_manager_serves_selector_from_its_own_catalog(tmp_path: Path):
    packager = _load_packager()
    output = tmp_path / "runtime"
    try:
        packager.build_runtime(repo_root=ROOT, standalone_console=_standalone(tmp_path), output_dir=output)
    except packager.RuntimePackagingError as exc:
        if "standalone" in str(exc).lower() or "console" in str(exc).lower():
            pytest.skip(f"fake standalone Console not accepted: {exc}")
        raise
    app = output / "manager" / "manager.pyz"
    catalog = output / "manager" / "catalog"
    assert (catalog / packager.CATALOG_MANIFEST_RELATIVE).is_file()
    shipped = [p for p in catalog.rglob("*") if p.is_file()]
    assert 0 < len(shipped) < 400 and not [p for p in shipped if p.suffix == ".py"]
    import zipfile
    names = set(zipfile.ZipFile(app).namelist())
    assert "plasma_web/legacy_device_selector.py" in names
    assert "plasma_web/device_catalog.py" in names
    # The Manager ships the Selector projection only, never the PPU Gateway.
    assert not [n for n in names if n.startswith(("plasma_web/gateway", "plasma_server/", "plasma_interfaces/"))]

    port = _free_port()
    config = tmp_path / "manager.yaml"
    config.write_text(
        "manager:\n  host: 127.0.0.1\n"
        f"  port: {port}\n  request_timeout_s: 0.2\n  poll_interval_s: 0.5\n"
        f"  registry_state_path: {tmp_path / 'registry.json'}\nppus: []\n",
        encoding="utf-8",
    )
    log = tmp_path / "manager.log"
    env = {"PATH": "/usr/bin:/bin", "PYTHONUNBUFFERED": "1"}  # no Catalog env, no site-packages
    with log.open("wb") as stream:
        process = subprocess.Popen([sys.executable, "-I", "-S", str(app), "--config", str(config)],
                                   cwd=tmp_path, env=env, stdout=stream, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 60
        while True:
            assert process.poll() is None, log.read_text(errors="replace")
            try:
                status, body = _get(port, "/api/health/live")
                if status == 200:
                    break
            except OSError:
                pass
            assert time.monotonic() < deadline, log.read_text(errors="replace")
            time.sleep(0.2)
        status, body = _get(port, "/api/devices/search?q=STM32F103C8T6&limit=1")
        assert status == 200, (body, log.read_text(errors="replace"))
        assert body["results"][0]["icpn"] == "STM32F103C8T6"
        assert body["results"][0]["selected_profile"]["icpn"] == "STM32F103C8T6"
        for query, vendor in (("MKL25Z128VLK4", "NXP"), ("ATSAML10E16A", "Microchip"),
                              ("PIC32MX", "Microchip"), ("STM32H503CBT6", "STMicroelectronics")):
            status, body = _get(port, f"/api/devices/search?q={query}&limit=5")
            assert status == 200 and body["results"], (query, body)
            assert body["results"][0]["vendor"] == vendor, (query, body["results"][0]["vendor"])
    finally:
        process.terminate()
        process.wait(timeout=10)
    text = log.read_text(errors="replace")
    assert "Traceback" not in text, text
