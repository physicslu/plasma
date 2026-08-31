from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler


class DeviceCatalogWebGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path: str):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def test_exact_admitted_icpn_search_exposes_production_catalog_without_ppu_runtime(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F103C8T6&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["rest_contract_version"], "3")
        self.assertEqual(payload["catalog_size"], 199)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F103C8T6")
        self.assertEqual(result["identifier_kind"], "manufacturer_part_number")
        self.assertEqual(result["catalog"]["scope"], "production_admitted")
        self.assertEqual(result["catalog"]["version"], "1.0.0")
        self.assertEqual(len(result["catalog"]["revision_sha256"]), 64)
        self.assertTrue(result["catalog_verification"]["status"].startswith("verified_"))
        self.assertEqual(result["backend"]["mapping_status"], "mapped")
        self.assertEqual(result["physical_validation"]["engineering_status"], "no_evidence")
        self.assertEqual(result["physical_validation"]["ppu_status"], "no_evidence")
        self.assertEqual(result["physical_validation"]["socket_status"], "no_evidence")

    def test_search_is_case_insensitive(self) -> None:
        status, payload = self.request("/api/devices/search?q=stm32f103c8t6")
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"][0]["identifier"], "STM32F103C8T6")

    def test_family_and_vendor_queries_return_only_admitted_rows(self) -> None:
        status, payload = self.request("/api/devices/search?q=STMicroelectronics%20STM32F4&limit=100")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 100)
        self.assertEqual(payload["catalog_size"], 199)
        self.assertEqual({item["family"] for item in payload["results"]}, {"STM32F4"})
        self.assertTrue(all(item["icpn"] for item in payload["results"]))

    def test_new_scaleout_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F429ZGY6TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["icpn"], "STM32F429ZGY6TR")
        self.assertEqual(payload["results"][0]["family"], "STM32F4")
        self.assertEqual(payload["results"][0]["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_batch2_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F437VGT7TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["icpn"], "STM32F437VGT7TR")
        self.assertEqual(payload["results"][0]["family"], "STM32F4")
        self.assertEqual(payload["results"][0]["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_f446_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F446ZEJ7TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F446ZEJ7TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "UFBGA")
        self.assertEqual(result["pin_count"], "144")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_foundation_batch2_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F405VGT7TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F405VGT7TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "100")
        self.assertEqual(result["flash_size"], "1024 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_foundation_batch3_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F412ZET7TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F412ZET7TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "144")
        self.assertEqual(result["flash_size"], "512 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_foundation_batch4_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F427ZIT7TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F427ZIT7TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "144")
        self.assertEqual(result["flash_size"], "2048 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_foundation_batch5_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F437ZIT7TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F437ZIT7TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "144")
        self.assertEqual(result["flash_size"], "2048 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_research_only_identifier_is_not_exposed_by_production_search(self) -> None:
        status, payload = self.request("/api/devices/search?q=ADUC7019BCPZ62I")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["results"], [])

    def test_empty_query_is_valid_for_catalog_metadata_idle_state(self) -> None:
        status, payload = self.request("/api/devices/search?q=")
        self.assertEqual(status, 200)
        self.assertEqual(payload["catalog_size"], 199)
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["results"], [])

    def test_invalid_limit_fails_closed(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32&limit=101")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["error_type"], "INVALID_DEVICE_SEARCH")

    def test_engineering_job_target_device_resolves_to_admitted_exact_icpn(self) -> None:
        record = get_default_device_catalog().search("STM32F407VGT6", limit=1)[0]
        handler = PlasmaWebHandler.__new__(PlasmaWebHandler)
        request = handler._job_request(
            {
                "site_id": 1,
                "operation": "erase",
                "target_device": {"vendor": record.vendor, "identifier": record.identifier},
            },
            client_id="plasma-web-engineering",
            allow_inline_asset=False,
        )
        self.assertEqual(request.target, "STM32F407VGT6")
        self.assertEqual(request.metadata["target_device"]["vendor"], record.vendor)
        self.assertEqual(request.metadata["target_device"]["identifier"], record.identifier)
        self.assertEqual(request.metadata["target_device"]["identifier_kind"], "manufacturer_part_number")
        self.assertEqual(request.metadata["target_device"]["icpn"], "STM32F407VGT6")

    def test_engineering_job_target_device_fails_closed_when_not_admitted(self) -> None:
        handler = PlasmaWebHandler.__new__(PlasmaWebHandler)
        with self.assertRaisesRegex(ValueError, "canonical Device Catalog record"):
            handler._job_request(
                {
                    "site_id": 1,
                    "operation": "erase",
                    "target_device": {"vendor": "Analog Devices", "identifier": "ADUC7019BCPZ62I"},
                },
                client_id="plasma-web-engineering",
                allow_inline_asset=False,
            )


if __name__ == "__main__":
    unittest.main()
