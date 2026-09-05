from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_PRODUCTION_CATALOG_SIZE = 459
EXPECTED_ICPNS = {
    "STM32F469AEH6": ("STM32F469AE", "UFBGA", "169", "512 KiB"),
    "STM32F469AEH7": ("STM32F469AE", "UFBGA", "169", "512 KiB"),
    "STM32F469AEH7TR": ("STM32F469AE", "UFBGA", "169", "512 KiB"),
    "STM32F469AGH6": ("STM32F469AG", "UFBGA", "169", "1024 KiB"),
    "STM32F469AGH6TR": ("STM32F469AG", "UFBGA", "169", "1024 KiB"),
    "STM32F469AGY6TR": ("STM32F469AG", "WLCSP", "168", "1024 KiB"),
    "STM32F469AIH6": ("STM32F469AI", "UFBGA", "169", "2048 KiB"),
    "STM32F469AIY6TR": ("STM32F469AI", "WLCSP", "168", "2048 KiB"),
    "STM32F479AGH6": ("STM32F479AG", "UFBGA", "169", "1024 KiB"),
    "STM32F479AIH6": ("STM32F479AI", "UFBGA", "169", "2048 KiB"),
    "STM32F479AIY6TR": ("STM32F479AI", "WLCSP", "168", "2048 KiB"),
}


def test_phase42ai_exact_icpns_are_resolved_by_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size == EXPECTED_PRODUCTION_CATALOG_SIZE
    for icpn, (base_device, package, pin_count, flash_size) in EXPECTED_ICPNS.items():
        matches = catalog.search(icpn.lower(), limit=5)
        row = next(record for record in matches if record.icpn == icpn)
        assert row.base_device == base_device
        assert row.package == package
        assert row.pin_count == pin_count
        assert row.flash_size == flash_size
        assert row.target_config == "tcl/target/stm32f4x.cfg"
        assert row.production_admitted


def test_phase42ai_exact_icpns_are_exposed_by_rest_catalog() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for icpn, (base_device, package, pin_count, flash_size) in EXPECTED_ICPNS.items():
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", f"/api/devices/search?q={icpn}&limit=5")
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            assert response.status == 200
            assert payload["rest_contract_version"] == "3"
            assert payload["catalog_size"] == EXPECTED_PRODUCTION_CATALOG_SIZE
            assert payload["count"] >= 1
            result = next(item for item in payload["results"] if item["icpn"] == icpn)
            assert result["base_device"] == base_device
            assert result["package"] == package
            assert result["pin_count"] == pin_count
            assert result["flash_size"] == flash_size
            assert result["backend"]["target_config"] == "tcl/target/stm32f4x.cfg"
            assert result["catalog"]["scope"] == "production_admitted"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
