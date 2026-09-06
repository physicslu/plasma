from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler

EXPECTED_PRODUCTION_CATALOG_SIZE = 459
EXPECTED_STM32F4_CATALOG_SIZE = 384
LIFECYCLE_ONLY_ICPNS = {
    "STM32F429BET6",
    "STM32F429BGT6",
    "STM32F429BIT6",
    "STM32F429BIT7",
    "STM32F439BGT6",
    "STM32F439BIT6",
    "STM32F439BIT7",
    "STM32F469BET6",
    "STM32F469BGT6",
    "STM32F469BIT6",
    "STM32F469BIT7",
    "STM32F479BGT6",
    "STM32F479BIT6",
}


def test_phase42ak_all_bt_lifecycle_icpns_remain_absent_from_runtime_catalog() -> None:
    catalog = get_default_device_catalog()
    assert catalog.size == EXPECTED_PRODUCTION_CATALOG_SIZE
    assert sum(record.family == "STM32F4" for record in catalog.records) == EXPECTED_STM32F4_CATALOG_SIZE
    runtime_icpns = {record.icpn for record in catalog.records}
    assert LIFECYCLE_ONLY_ICPNS.isdisjoint(runtime_icpns)
    for icpn in LIFECYCLE_ONLY_ICPNS:
        assert all(record.icpn != icpn for record in catalog.search(icpn, limit=100))


def test_phase42ak_all_bt_lifecycle_icpns_remain_absent_from_rest_catalog() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for icpn in sorted(LIFECYCLE_ONLY_ICPNS):
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", f"/api/devices/search?q={icpn}&limit=100")
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            assert response.status == 200
            assert payload["rest_contract_version"] == "3"
            assert payload["catalog_size"] == EXPECTED_PRODUCTION_CATALOG_SIZE
            assert all(item["icpn"] != icpn for item in payload["results"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main() -> int:
    test_phase42ak_all_bt_lifecycle_icpns_remain_absent_from_runtime_catalog()
    test_phase42ak_all_bt_lifecycle_icpns_remain_absent_from_rest_catalog()
    print("Phase 4.2AK runtime/REST closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
