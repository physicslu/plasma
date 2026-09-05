from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_PRODUCTION_CATALOG_SIZE = 459
EXPECTED_ICPNS = {
    "STM32F410TBY3TR": "-40 to 125 C",
    "STM32F410TBY6TR": "-40 to 85 C",
    "STM32F410TBY7TR": "-40 to 105 C",
}


def test_phase42t_exact_icpns_are_resolved_by_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size == EXPECTED_PRODUCTION_CATALOG_SIZE
    for icpn, temperature_grade in EXPECTED_ICPNS.items():
        matches = catalog.search(icpn.lower(), limit=5)
        assert {record.icpn for record in matches} == {icpn}
        row = matches[0]
        assert row.package == "WLCSP"
        assert row.pin_count == "36"
        assert row.flash_size == "128 KiB"
        assert row.temperature_grade == temperature_grade
        assert row.option_suffix == "TR"
        assert row.target_config == "tcl/target/stm32f4x.cfg"
        assert row.production_admitted


def test_phase42t_exact_icpn_is_exposed_by_rest_catalog() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for icpn in EXPECTED_ICPNS:
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", f"/api/devices/search?q={icpn}&limit=5")
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            assert response.status == 200
            assert payload["rest_contract_version"] == "3"
            assert payload["catalog_size"] == EXPECTED_PRODUCTION_CATALOG_SIZE
            assert payload["count"] == 1
            result = payload["results"][0]
            assert result["icpn"] == icpn
            assert result["package"] == "WLCSP"
            assert result["pin_count"] == "36"
            assert result["flash_size"] == "128 KiB"
            assert result["backend"]["target_config"] == "tcl/target/stm32f4x.cfg"
            assert result["catalog"]["scope"] == "production_admitted"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
