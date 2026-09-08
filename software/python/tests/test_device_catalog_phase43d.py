from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler


EXPECTED = {
    "STM32F205RBT6": ("LQFP", "64", "128 KiB"),
    "STM32F207ICH6": ("UFBGA", "176", "256 KiB"),
}


def _assert_phase43d_payload(payload: dict, icpn: str) -> None:
    package, pin_count, flash_size = EXPECTED[icpn]
    assert payload["icpn"] == icpn
    assert payload["family"] == "STM32F2"
    assert payload["package"] == package
    assert payload["pin_count"] == pin_count
    assert payload["flash_size"] == flash_size
    assert payload["backend"]["target_config"] == "tcl/target/stm32f2x.cfg"
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_phase43d_exact_icpns_are_catalog_admitted_without_runtime_claims() -> None:
    catalog = get_default_device_catalog()
    for icpn in EXPECTED:
        record = catalog.resolve("STMicroelectronics", icpn)
        assert record is not None
        assert record.production_admitted
        _assert_phase43d_payload(record.to_payload(), icpn)


def test_phase43d_exact_icpns_are_exposed_by_rest_catalog() -> None:
    expected_catalog_size = get_default_device_catalog().size
    server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for icpn in EXPECTED:
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", f"/api/devices/search?q={icpn}&limit=5")
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            assert response.status == 200
            assert payload["catalog_size"] == expected_catalog_size
            result = next(item for item in payload["results"] if item["icpn"] == icpn)
            _assert_phase43d_payload(result, icpn)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main() -> int:
    test_phase43d_exact_icpns_are_catalog_admitted_without_runtime_claims()
    test_phase43d_exact_icpns_are_exposed_by_rest_catalog()
    print("Phase 4.3D runtime and REST closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
