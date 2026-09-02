from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_PRODUCTION_CATALOG_SIZE = 286
EXPECTED_ICPN = "STM32F405OEY6TR"


def test_phase42i_exact_icpn_is_resolved_by_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size == EXPECTED_PRODUCTION_CATALOG_SIZE

    matches = catalog.search(EXPECTED_ICPN.lower(), limit=5)
    assert len(matches) == 1
    record = matches[0]
    assert record.icpn == EXPECTED_ICPN
    assert record.identifier == EXPECTED_ICPN
    assert record.family == "STM32F4"
    assert record.package == "WLCSP"
    assert record.pin_count == "90"
    assert record.flash_size == "512 KiB"
    assert record.target_config == "tcl/target/stm32f4x.cfg"
    assert record.production_admitted


def test_phase42i_exact_icpn_is_exposed_by_rest_catalog() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", f"/api/devices/search?q={EXPECTED_ICPN}&limit=5")
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()

        assert response.status == 200
        assert payload["rest_contract_version"] == "3"
        assert payload["catalog_size"] == EXPECTED_PRODUCTION_CATALOG_SIZE
        assert payload["count"] == 1
        result = payload["results"][0]
        assert result["icpn"] == EXPECTED_ICPN
        assert result["family"] == "STM32F4"
        assert result["package"] == "WLCSP"
        assert result["pin_count"] == "90"
        assert result["flash_size"] == "512 KiB"
        assert result["backend"]["target_config"] == "tcl/target/stm32f4x.cfg"
        assert result["catalog"]["scope"] == "production_admitted"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
