from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_PRODUCTION_CATALOG_SIZE = 439
EXPECTED_ICPNS = {
    "STM32F413MGY6TR": ("STM32F413MG", "1024 KiB", "-40 to 85 C"),
    "STM32F413MHY6TR": ("STM32F413MH", "1536 KiB", "-40 to 85 C"),
    "STM32F423MHY3TR": ("STM32F423MH", "1536 KiB", "-40 to 125 C"),
    "STM32F423MHY6TR": ("STM32F423MH", "1536 KiB", "-40 to 85 C"),
    "STM32F446MCY6TR": ("STM32F446MC", "256 KiB", "-40 to 85 C"),
    "STM32F446MEY6MTR": ("STM32F446ME", "512 KiB", "-40 to 85 C"),
    "STM32F446MEY6TR": ("STM32F446ME", "512 KiB", "-40 to 85 C"),
}
EXCLUDED = {"STM32F413MGY3TR", "STM32F413MHY3TR"}


def test_phase42x_exact_icpns_are_resolved_by_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size == EXPECTED_PRODUCTION_CATALOG_SIZE
    for icpn, (base_device, flash_size, temperature_grade) in EXPECTED_ICPNS.items():
        matches = catalog.search(icpn.lower(), limit=5)
        assert matches[0].icpn == icpn
        row = next(record for record in matches if record.icpn == icpn)
        assert row.base_device == base_device
        assert row.package == "WLCSP"
        assert row.pin_count == "81"
        assert row.flash_size == flash_size
        assert row.temperature_grade == temperature_grade
        assert row.target_config == "tcl/target/stm32f4x.cfg"
        assert row.production_admitted
    for icpn in EXCLUDED:
        assert catalog.search(icpn, limit=5) == []


def test_phase42x_exact_icpns_are_exposed_by_rest_catalog() -> None:
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
            assert result["package"] == "WLCSP"
            assert result["pin_count"] == "81"
            assert result["flash_size"] == flash_size
            assert result["backend"]["target_config"] == "tcl/target/stm32f4x.cfg"
            assert result["catalog"]["scope"] == "production_admitted"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
