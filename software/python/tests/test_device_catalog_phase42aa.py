from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_PRODUCTION_CATALOG_SIZE = 439
EXPECTED_ICPNS = {
    "STM32F469NEH6": ("STM32F469NE", "512 KiB", "-40 to 85 C"),
    "STM32F469NGH6": ("STM32F469NG", "1024 KiB", "-40 to 85 C"),
    "STM32F469NIH6": ("STM32F469NI", "2048 KiB", "-40 to 85 C"),
    "STM32F469NIH6TR": ("STM32F469NI", "2048 KiB", "-40 to 85 C"),
    "STM32F469NIH7": ("STM32F469NI", "2048 KiB", "-40 to 105 C"),
    "STM32F479NGH6": ("STM32F479NG", "1024 KiB", "-40 to 85 C"),
    "STM32F479NIH6": ("STM32F479NI", "2048 KiB", "-40 to 85 C"),
}


def test_phase42aa_exact_icpns_are_resolved_by_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size == EXPECTED_PRODUCTION_CATALOG_SIZE
    for icpn, (base_device, flash_size, temperature_grade) in EXPECTED_ICPNS.items():
        matches = catalog.search(icpn.lower(), limit=5)
        assert matches[0].icpn == icpn
        row = next(record for record in matches if record.icpn == icpn)
        assert row.base_device == base_device
        assert row.package == "TFBGA"
        assert row.pin_count == "216"
        assert row.flash_size == flash_size
        assert row.temperature_grade == temperature_grade
        assert row.target_config == "tcl/target/stm32f4x.cfg"
        assert row.production_admitted


def test_phase42aa_exact_icpns_are_exposed_by_rest_catalog() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for icpn, (base_device, flash_size, _temperature_grade) in EXPECTED_ICPNS.items():
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", f"/api/devices/search?q={icpn}&limit=5")
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            assert response.status == 200
            assert payload["rest_contract_version"] == "3"
            assert payload["catalog_size"] == EXPECTED_PRODUCTION_CATALOG_SIZE
            assert payload["count"] >= 1
            assert payload["results"][0]["icpn"] == icpn
            result = next(item for item in payload["results"] if item["icpn"] == icpn)
            assert result["base_device"] == base_device
            assert result["package"] == "TFBGA"
            assert result["pin_count"] == "216"
            assert result["flash_size"] == flash_size
            assert result["backend"]["target_config"] == "tcl/target/stm32f4x.cfg"
            assert result["catalog"]["scope"] == "production_admitted"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
