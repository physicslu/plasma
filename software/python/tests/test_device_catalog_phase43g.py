from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED = {
    "STM32F205RCT7TR": ("LQFP", "64", "256 KiB", "-40 to 105 C", "TR"),
    "STM32F207IEH6TR": ("UFBGA", "176", "512 KiB", "-40 to 85 C", "TR"),
    "STM32F215RGT6": ("LQFP", "64", "1024 KiB", "-40 to 85 C", None),
    "STM32F217IGH6": ("UFBGA", "176", "1024 KiB", "-40 to 85 C", None),
}


def _assert_payload(payload: dict, icpn: str) -> None:
    package, pins, flash, temperature, suffix = EXPECTED[icpn]
    assert payload["icpn"] == icpn and payload["family"] == "STM32F2"
    assert (payload["package"], payload["pin_count"], payload["flash_size"]) == (package, pins, flash)
    assert payload["temperature_grade"] == temperature and payload["option_suffix"] == suffix
    assert payload["backend"]["target_config"] == "tcl/target/stm32f2x.cfg"
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence", "ppu_status": "no_evidence", "socket_status": "no_evidence",
    }


def test_phase43g_exact_icpns_are_catalog_admitted_without_runtime_claims() -> None:
    catalog = get_default_device_catalog()
    for icpn in EXPECTED:
        record = catalog.resolve("STMicroelectronics", icpn)
        assert record is not None and record.production_admitted
        _assert_payload(record.to_payload(), icpn)


def test_phase43g_exact_icpns_are_exposed_by_rest_catalog() -> None:
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
            _assert_payload(next(item for item in payload["results"] if item["icpn"] == icpn), icpn)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main() -> int:
    test_phase43g_exact_icpns_are_catalog_admitted_without_runtime_claims()
    test_phase43g_exact_icpns_are_exposed_by_rest_catalog()
    print("Phase 4.3G runtime and REST closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
