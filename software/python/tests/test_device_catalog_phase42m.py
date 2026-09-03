from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_MIN_PRODUCTION_CATALOG_SIZE = 329
UFBGA_ICPN = "STM32F439IIH7"
LQFP_ICPN = "STM32F437IIT7"


def test_phase42m_exact_icpns_are_resolved_by_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size >= EXPECTED_MIN_PRODUCTION_CATALOG_SIZE
    for icpn, package in ((UFBGA_ICPN, "UFBGA"), (LQFP_ICPN, "LQFP")):
        matches = catalog.search(icpn.lower(), limit=5)
        assert {record.icpn for record in matches} == {icpn}
        assert matches[0].package == package
        assert matches[0].pin_count == "176"
        assert matches[0].flash_size == "2048 KiB"
        assert matches[0].target_config == "tcl/target/stm32f4x.cfg"
        assert matches[0].production_admitted


def test_phase42m_exact_icpn_is_exposed_by_rest_catalog() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", f"/api/devices/search?q={UFBGA_ICPN}&limit=5")
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        assert response.status == 200
        assert payload["rest_contract_version"] == "3"
        assert payload["catalog_size"] >= EXPECTED_MIN_PRODUCTION_CATALOG_SIZE
        assert payload["count"] == 1
        result = payload["results"][0]
        assert result["icpn"] == UFBGA_ICPN
        assert result["package"] == "UFBGA"
        assert result["pin_count"] == "176"
        assert result["flash_size"] == "2048 KiB"
        assert result["backend"]["target_config"] == "tcl/target/stm32f4x.cfg"
        assert result["catalog"]["scope"] == "production_admitted"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
