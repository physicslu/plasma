from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_PRODUCTION_CATALOG_SIZE = 439
EXPECTED_ICPNS = {
    "STM32F410C8U6": ("STM32F410C8", "UFQFPN", "48", "-40 to 85 C"),
    "STM32F410C8U6TR": ("STM32F410C8", "UFQFPN", "48", "-40 to 85 C"),
    "STM32F410C8U7": ("STM32F410C8", "UFQFPN", "48", "-40 to 105 C"),
    "STM32F410C8U7TR": ("STM32F410C8", "UFQFPN", "48", "-40 to 105 C"),
    "STM32F410T8Y6TR": ("STM32F410T8", "WLCSP", "36", "-40 to 85 C"),
}


def test_phase42ac_exact_icpns_are_resolved_by_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size == EXPECTED_PRODUCTION_CATALOG_SIZE
    for icpn, (base_device, package, pin_count, temperature_grade) in EXPECTED_ICPNS.items():
        matches = catalog.search(icpn.lower(), limit=5)
        assert matches[0].icpn == icpn
        row = next(record for record in matches if record.icpn == icpn)
        assert row.base_device == base_device
        assert row.package == package
        assert row.pin_count == pin_count
        assert row.flash_size == "64 KiB"
        assert row.temperature_grade == temperature_grade
        assert row.target_config == "tcl/target/stm32f4x.cfg"
        assert row.production_admitted


def test_phase42ac_exact_icpns_are_exposed_by_rest_catalog() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for icpn, (base_device, package, pin_count, _temperature_grade) in EXPECTED_ICPNS.items():
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
            assert result["package"] == package
            assert result["pin_count"] == pin_count
            assert result["flash_size"] == "64 KiB"
            assert result["backend"]["target_config"] == "tcl/target/stm32f4x.cfg"
            assert result["catalog"]["scope"] == "production_admitted"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
