from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_PRODUCTION_CATALOG_SIZE = 427
EXPECTED_ICPNS = {
    "STM32F413CHU3": ("UFQFPN", "48", "-40 to 125 C"),
    "STM32F413CHU3TR": ("UFQFPN", "48", "-40 to 125 C"),
    "STM32F413CHU6": ("UFQFPN", "48", "-40 to 85 C"),
    "STM32F413CHU6TR": ("UFQFPN", "48", "-40 to 85 C"),
    "STM32F413RHT3": ("LQFP", "64", "-40 to 125 C"),
    "STM32F413RHT6": ("LQFP", "64", "-40 to 85 C"),
    "STM32F413RHT6TR": ("LQFP", "64", "-40 to 85 C"),
    "STM32F413VHH3": ("UFBGA", "100", "-40 to 125 C"),
    "STM32F413VHH6": ("UFBGA", "100", "-40 to 85 C"),
    "STM32F413VHT6": ("LQFP", "100", "-40 to 85 C"),
    "STM32F413ZHJ6": ("UFBGA", "144", "-40 to 85 C"),
    "STM32F413ZHJ6TR": ("UFBGA", "144", "-40 to 85 C"),
    "STM32F413ZHT3": ("LQFP", "144", "-40 to 125 C"),
    "STM32F413ZHT6": ("LQFP", "144", "-40 to 85 C"),
}
EXCLUDED = {"STM32F413VHT3", "STM32F413ZHJ3"}


def test_phase42u_exact_icpns_are_resolved_by_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size == EXPECTED_PRODUCTION_CATALOG_SIZE
    for icpn, (package, pin_count, temperature_grade) in EXPECTED_ICPNS.items():
        matches = catalog.search(icpn.lower(), limit=5)
        assert matches[0].icpn == icpn
        row = next(record for record in matches if record.icpn == icpn)
        assert row.package == package
        assert row.pin_count == pin_count
        assert row.flash_size == "1536 KiB"
        assert row.temperature_grade == temperature_grade
        assert row.target_config == "tcl/target/stm32f4x.cfg"
        assert row.production_admitted
    for icpn in EXCLUDED:
        assert catalog.search(icpn, limit=5) == []


def test_phase42u_exact_icpns_are_exposed_by_rest_catalog() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for icpn, (package, pin_count, _temperature_grade) in EXPECTED_ICPNS.items():
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
            assert result["icpn"] == icpn
            assert result["package"] == package
            assert result["pin_count"] == pin_count
            assert result["flash_size"] == "1536 KiB"
            assert result["backend"]["target_config"] == "tcl/target/stm32f4x.cfg"
            assert result["catalog"]["scope"] == "production_admitted"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
