from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_MIN_PRODUCTION_CATALOG_SIZE = 301
UFBGA_ICPN = "STM32F407IEH6"
LQFP_ICPN = "STM32F417IGT7"
EXCLUDED_NRND = "STM32F417IGH6W"


def test_phase42k_exact_icpns_are_resolved_by_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size >= EXPECTED_MIN_PRODUCTION_CATALOG_SIZE

    ufbga = catalog.search(UFBGA_ICPN.lower(), limit=5)
    assert {record.icpn for record in ufbga} == {UFBGA_ICPN, f"{UFBGA_ICPN}TR"}
    ufbga_record = next(record for record in ufbga if record.icpn == UFBGA_ICPN)
    assert ufbga_record.icpn == UFBGA_ICPN
    assert ufbga_record.package == "UFBGA"
    assert ufbga_record.pin_count == "176"
    assert ufbga_record.flash_size == "512 KiB"
    assert ufbga_record.target_config == "tcl/target/stm32f4x.cfg"
    assert ufbga_record.production_admitted

    lqfp = catalog.search(LQFP_ICPN.lower(), limit=5)
    assert len(lqfp) == 1
    lqfp_record = lqfp[0]
    assert lqfp_record.icpn == LQFP_ICPN
    assert lqfp_record.package == "LQFP"
    assert lqfp_record.pin_count == "176"
    assert lqfp_record.flash_size == "1024 KiB"
    assert lqfp_record.target_config == "tcl/target/stm32f4x.cfg"
    assert lqfp_record.production_admitted

    assert catalog.search(EXCLUDED_NRND.lower(), limit=5) == []


def test_phase42k_exact_icpn_is_exposed_by_rest_catalog_and_nrnd_is_absent() -> None:
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
        assert payload["count"] == 2
        assert {item["icpn"] for item in payload["results"]} == {
            UFBGA_ICPN,
            f"{UFBGA_ICPN}TR",
        }
        result = next(item for item in payload["results"] if item["icpn"] == UFBGA_ICPN)
        assert result["icpn"] == UFBGA_ICPN
        assert result["package"] == "UFBGA"
        assert result["pin_count"] == "176"
        assert result["flash_size"] == "512 KiB"
        assert result["backend"]["target_config"] == "tcl/target/stm32f4x.cfg"
        assert result["catalog"]["scope"] == "production_admitted"

        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", f"/api/devices/search?q={EXCLUDED_NRND}&limit=5")
        response = connection.getresponse()
        excluded_payload = json.loads(response.read())
        connection.close()
        assert response.status == 200
        assert excluded_payload["count"] == 0
        assert excluded_payload["results"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
