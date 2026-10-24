from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import quote

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler, _parse_target_device, _reject_unmapped_microchip_raw_job_target
from plasma_web.programming_qualification import get_default_programming_qualification_registry


_LEVEL_COUNTS = get_default_programming_qualification_registry().summary["catalog_level_counts"]
EXPECTED_CUSTOMER_SELECTOR_SIZE = sum(_LEVEL_COUNTS[str(level)] for level in (1, 2, 3))


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
        self.assertEqual(payload["scope"], "customer_ic_selector")
        self.assertEqual(payload["levels"], [1, 2, 3])
        self.assertEqual(payload["catalog_size"], EXPECTED_CUSTOMER_SELECTOR_SIZE)
        self.assertGreaterEqual(payload["total_count"], 1)
        self.assertEqual(payload["count"], payload["total_count"])
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F103C8T6")
        self.assertEqual(result["identity"]["state"], "IDENTIFIED")
        self.assertEqual(result["identifier_kind"], "manufacturer_part_number")
        self.assertEqual(result["catalog"]["scope"], "production_admitted")
        self.assertEqual(result["catalog"]["version"], "1.0.0")
        self.assertEqual(len(result["catalog"]["revision_sha256"]), 64)
        self.assertTrue(result["catalog_verification"]["status"].startswith("verified_"))
        self.assertEqual(result["backend"]["mapping_status"], "mapped")
        self.assertEqual(result["physical_validation"]["engineering_status"], "no_evidence")
        self.assertEqual(result["physical_validation"]["ppu_status"], "no_evidence")
        self.assertEqual(result["physical_validation"]["socket_status"], "no_evidence")

        basic = result["manufacturer_device_basic_profile"]
        self.assertIsNotNone(basic)
        self.assertEqual(basic["status"], "manufacturer_device_basic_available")
        self.assertEqual(basic["icpn"], "STM32F103C8T6")
        self.assertEqual(basic["ram_size"], "20 KiB")
        self.assertEqual(basic["operating_vdd_v"], {"min": 2.0, "max": 3.6})
        self.assertIsNone(basic["io_supply_v"])
        self.assertIsNone(basic["vdda_v"])
        self.assertEqual(basic["operating_temperature_c"], {"min": -40, "max": 85})
        self.assertFalse(basic["programming_profile_authority"])

        selected = result["selected_profile"]
        self.assertIsNotNone(selected)
        self.assertEqual(selected["status"], "manufacturer_profile_available")
        self.assertEqual(selected["icpn"], "STM32F103C8T6")
        self.assertEqual(selected["catalog_identity"]["flash_size"], "64 KiB")
        self.assertEqual(selected["device"]["memory_map"]["main_flash"]["size_bytes"], 64 * 1024)
        self.assertEqual(
            selected["device"]["operating_electrical"]["vdd_v"],
            {"min": 2.0, "max": 3.6},
        )
        self.assertEqual(
            selected["programming"]["electrical"]["vdd_programming_v"]["min"],
            2.0,
        )
        self.assertEqual(
            selected["programming"]["electrical"]["vdd_programming_v"]["max"],
            3.6,
        )
        self.assertIsNone(
            selected["programming"]["interfaces"]["SWD"]["clock_hz"]["manufacturer_max"]
        )
        self.assertEqual(
            selected["programming"]["interfaces"]["SWD"]["clock_hz"]["status"],
            "not_specified_by_locked_manufacturer_sources",
        )
        self.assertFalse(selected["plasma_compatibility"]["hardware_runtime_ready"])
        self.assertFalse(selected["plasma_compatibility"]["physical_programming_qualified"])

        qualification = result["programming_qualification"]
        self.assertIsNotNone(qualification)
        self.assertEqual(qualification["state"], "SUPPORTED")
        self.assertTrue(qualification["reviewed"])
        self.assertEqual(qualification["provider"]["version"], "0.12.0")
        self.assertEqual(qualification["provider"]["target_config"], "tcl/target/stm32f1x.cfg")
        self.assertEqual(qualification["provider"]["flash_driver"], "stm32f1x")
        self.assertEqual(qualification["operations"]["probe"]["state"], "SUPPORTED")
        self.assertEqual(qualification["operations"]["erase"]["state"], "SUPPORTED")
        self.assertEqual(qualification["operations"]["program"]["state"], "SUPPORTED")
        self.assertEqual(qualification["operations"]["read"]["state"], "SUPPORTED")
        self.assertEqual(qualification["operations"]["verify"]["state"], "SUPPORTED")
        self.assertEqual(
            qualification["programming"]["flash_geometry"]["main_flash_size_bytes"],
            64 * 1024,
        )
        self.assertEqual(result["catalog_level"], 2)
        self.assertEqual(result["catalog_level_state"], "PROGRAMMABLE")
        self.assertTrue(result["job_selectable"])
        self.assertEqual(qualification["catalog_level"], 2)
        self.assertEqual(qualification["catalog_level_state"], "PROGRAMMABLE")
        self.assertTrue(qualification["selector_visible"])
        self.assertTrue(qualification["job_selectable"])
        self.assertFalse(qualification["hardware_runtime_ready"])
        self.assertFalse(qualification["physical_programming_qualified"])

    def test_stm32f1_basic_profile_and_phase2_qualification_remain_independent(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F103R8T6&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F103R8T6")
        basic = result["manufacturer_device_basic_profile"]
        self.assertIsNotNone(basic)
        self.assertEqual(basic["base_device"], "STM32F103R8")
        self.assertEqual(basic["flash_size"], "64 KiB")
        self.assertEqual(basic["ram_size"], "20 KiB")
        self.assertEqual(basic["operating_vdd_v"], {"min": 2.0, "max": 3.6})
        self.assertFalse(basic["programming_profile_authority"])

        # The historical deep selected_profile remains absent; Phase 2 qualification
        # is an independent SW/PPU authority and must still project SUPPORTED.
        self.assertIsNone(result["selected_profile"])
        qualification = result["programming_qualification"]
        self.assertIsNotNone(qualification)
        self.assertEqual(qualification["state"], "SUPPORTED")
        self.assertTrue(qualification["reviewed"])
        self.assertEqual(qualification["provider"]["version"], "0.12.0")
        self.assertEqual(
            qualification["programming"]["memory_geometry_profile_id"],
            "stm32f103r8-64k-v0",
        )
        self.assertEqual(
            qualification["programming"]["flash_geometry"]["main_flash_size_bytes"],
            64 * 1024,
        )
        self.assertEqual(
            qualification["programming"]["flash_geometry"]["page_count"],
            64,
        )

    def test_unreviewed_vfqfpn36_source_mismatch_remains_unknown(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F103T8U6&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F103T8U6")
        self.assertEqual(result["backend"]["mapping_status"], "mapped")
        qualification = result["programming_qualification"]
        self.assertEqual(qualification["state"], "UNKNOWN")
        self.assertFalse(qualification["reviewed"])
        self.assertIsNone(qualification["provider"])
        self.assertEqual(qualification["operations"], {})
        self.assertIsNone(qualification["programming"])

    def test_stm32f103_bounded_direct_applicability_is_phase2_supported(self) -> None:
        cases = (
            ("STM32F103R8T6", "stm32f103r8-64k-v0", 64 * 1024, 64),
            ("STM32F103RBT6", "stm32f103rb-128k-v0", 128 * 1024, 128),
            ("STM32F103V8T6", "stm32f103v8-64k-v0", 64 * 1024, 64),
            ("STM32F103VBT6", "stm32f103vb-128k-v0", 128 * 1024, 128),
            ("STM32F103C8T7", "stm32f103c8-64k-v0", 64 * 1024, 64),
            ("STM32F103CBT7", "stm32f103cb-128k-v0", 128 * 1024, 128),
            ("STM32F103R8T7", "stm32f103r8-64k-v0", 64 * 1024, 64),
            ("STM32F103RBT7", "stm32f103rb-128k-v0", 128 * 1024, 128),
            ("STM32F103VBT7", "stm32f103vb-128k-v0", 128 * 1024, 128),
        )
        for icpn, geometry_id, expected_bytes, expected_pages in cases:
            with self.subTest(icpn=icpn):
                status, payload = self.request(f"/api/devices/search?q={icpn}&limit=1")
                self.assertEqual(status, 200)
                self.assertEqual(payload["count"], 1)
                result = payload["results"][0]
                self.assertEqual(result["icpn"], icpn)
                qualification = result["programming_qualification"]
                self.assertEqual(qualification["state"], "SUPPORTED")
                self.assertTrue(qualification["reviewed"])
                self.assertEqual(
                    qualification["programming"]["memory_geometry_profile_id"],
                    geometry_id,
                )
                self.assertEqual(
                    qualification["programming"]["flash_geometry"]["main_flash_size_bytes"],
                    expected_bytes,
                )
                self.assertEqual(
                    qualification["programming"]["flash_geometry"]["page_count"],
                    expected_pages,
                )
                self.assertFalse(qualification["hardware_runtime_ready"])
                self.assertFalse(qualification["physical_programming_qualified"])

    def test_stm32f103_high_density_r_lqfp_is_phase2_supported(self) -> None:
        cases = (
            ("STM32F103RCT6", "stm32f103rc-256k-v0", 256 * 1024, 128),
            ("STM32F103RCT7", "stm32f103rc-256k-v0", 256 * 1024, 128),
            ("STM32F103RDT6", "stm32f103rd-384k-v0", 384 * 1024, 192),
            ("STM32F103RET6", "stm32f103re-512k-v0", 512 * 1024, 256),
            ("STM32F103RET7", "stm32f103re-512k-v0", 512 * 1024, 256),
        )
        for icpn, geometry_id, expected_bytes, expected_pages in cases:
            with self.subTest(icpn=icpn):
                status, payload = self.request(f"/api/devices/search?q={icpn}&limit=1")
                self.assertEqual(status, 200)
                self.assertEqual(payload["count"], 1)
                qualification = payload["results"][0]["programming_qualification"]
                self.assertEqual(qualification["state"], "SUPPORTED")
                self.assertTrue(qualification["reviewed"])
                self.assertEqual(
                    qualification["programming"]["programming_profile_id"],
                    "stm32f1-high-density-flash-v0",
                )
                self.assertEqual(
                    qualification["programming"]["memory_geometry_profile_id"],
                    geometry_id,
                )
                flash = qualification["programming"]["flash_geometry"]
                self.assertEqual(flash["main_flash_size_bytes"], expected_bytes)
                self.assertEqual(flash["page_count"], expected_pages)
                self.assertEqual(flash["erase_unit_bytes"], 2048)
                self.assertEqual(flash["program_unit_bytes"], 2)
                self.assertFalse(qualification["hardware_runtime_ready"])
                self.assertFalse(qualification["physical_programming_qualified"])

    def test_stm32f103_high_density_wlcsp_package_is_l2_supported(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F103RCY6TR&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["catalog_level"], 2)
        self.assertTrue(result["job_selectable"])
        qualification = result["programming_qualification"]
        self.assertEqual(qualification["state"], "SUPPORTED")
        self.assertTrue(qualification["reviewed"])
        self.assertEqual(
            qualification["programming"]["programming_profile_id"],
            "stm32f1-high-density-flash-v0",
        )
        self.assertEqual(
            qualification["programming"]["memory_geometry_profile_id"],
            "stm32f103rc-256k-v0",
        )
        self.assertEqual(
            qualification["programming"]["flash_geometry"]["main_flash_size_bytes"],
            256 * 1024,
        )
        self.assertFalse(qualification["execution_authorized"])
        self.assertFalse(qualification["hardware_runtime_ready"])
        self.assertFalse(qualification["physical_programming_qualified"])

    def test_stm32f103_xl_density_remains_l1_unknown(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F103RFT6&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["catalog_level"], 1)
        self.assertFalse(result["job_selectable"])
        qualification = result["programming_qualification"]
        self.assertEqual(qualification["state"], "UNKNOWN")
        self.assertFalse(qualification["reviewed"])
        self.assertIsNone(qualification["provider"])
        self.assertIsNone(qualification["programming"])
        self.assertFalse(qualification["execution_authorized"])

    def test_stm32f103_tr_ordering_variants_are_phase2_supported(self) -> None:
        for icpn, expected_bytes, expected_pages in (
            ("STM32F103C8T6TR", 64 * 1024, 64),
            ("STM32F103CBT6TR", 128 * 1024, 128),
            ("STM32F103R8T6TR", 64 * 1024, 64),
            ("STM32F103RBT6TR", 128 * 1024, 128),
            ("STM32F103V8T6TR", 64 * 1024, 64),
            ("STM32F103VBT6TR", 128 * 1024, 128),
            ("STM32F103C8T7TR", 64 * 1024, 64),
            ("STM32F103CBT7TR", 128 * 1024, 128),
            ("STM32F103R8T7TR", 64 * 1024, 64),
            ("STM32F103RBT7TR", 128 * 1024, 128),
            ("STM32F103VBT7TR", 128 * 1024, 128),
            ("STM32F103RCT6TR", 256 * 1024, 128),
            ("STM32F103RCT7TR", 256 * 1024, 128),
            ("STM32F103RDT6TR", 384 * 1024, 192),
            ("STM32F103RET6TR", 512 * 1024, 256),
        ):
            with self.subTest(icpn=icpn):
                status, payload = self.request(f"/api/devices/search?q={icpn}&limit=1")
                self.assertEqual(status, 200)
                self.assertEqual(payload["count"], 1)
                result = payload["results"][0]
                self.assertEqual(result["icpn"], icpn)
                qualification = result["programming_qualification"]
                self.assertEqual(qualification["state"], "SUPPORTED")
                self.assertTrue(qualification["reviewed"])
                self.assertEqual(
                    qualification["programming"]["flash_geometry"]["main_flash_size_bytes"],
                    expected_bytes,
                )
                self.assertEqual(
                    qualification["programming"]["flash_geometry"]["page_count"],
                    expected_pages,
                )
                self.assertFalse(qualification["hardware_runtime_ready"])
                self.assertFalse(qualification["physical_programming_qualified"])

    def test_stm32f103cb_is_phase2_supported_even_without_legacy_selected_profile(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F103CBT6&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F103CBT6")
        self.assertIsNone(result["selected_profile"])
        qualification = result["programming_qualification"]
        self.assertIsNotNone(qualification)
        self.assertEqual(qualification["state"], "SUPPORTED")
        self.assertTrue(qualification["reviewed"])
        self.assertEqual(
            qualification["programming"]["programming_profile_id"],
            "stm32f1-medium-density-flash-v0",
        )
        self.assertEqual(
            qualification["programming"]["memory_geometry_profile_id"],
            "stm32f103cb-128k-v0",
        )
        self.assertEqual(
            qualification["programming"]["flash_geometry"]["main_flash_size_bytes"],
            128 * 1024,
        )
        self.assertEqual(
            qualification["programming"]["flash_geometry"]["page_count"],
            128,
        )

    def test_c0_and_g0_bulk_basic_profiles_are_exposed_without_programming_authority(self) -> None:
        cases = (
            ("STM32C011F4P6", "STM32C0", "6 KiB", {"min": 2.0, "max": 3.6}),
            ("STM32G031K8T3", "STM32G0", "8 KiB", {"min": 1.7, "max": 3.6}),
        )
        for icpn, family, ram, vdd in cases:
            with self.subTest(icpn=icpn):
                status, payload = self.request(f"/api/devices/search?q={icpn}&limit=1")
                self.assertEqual(status, 200)
                self.assertEqual(payload["count"], 1)
                result = payload["results"][0]
                self.assertEqual(result["icpn"], icpn)
                self.assertEqual(result["family"], family)
                basic = result["manufacturer_device_basic_profile"]
                self.assertIsNotNone(basic)
                assert basic is not None
                self.assertEqual(basic["ram_size"], ram)
                self.assertEqual(basic["operating_vdd_v"], vdd)
                self.assertIsNone(basic["io_supply_v"])
                self.assertIsNone(basic["vdda_v"])
                self.assertFalse(basic["programming_profile_authority"])
                self.assertIsNone(result["selected_profile"])

    def test_f2_basic_profile_is_exposed_without_programming_authority(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F205RBT6&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F205RBT6")
        self.assertEqual(result["family"], "STM32F2")
        basic = result["manufacturer_device_basic_profile"]
        self.assertIsNotNone(basic)
        assert basic is not None
        self.assertEqual(basic["profile_id"], "stm32f2-device-basic-v1")
        self.assertEqual(basic["ram_size"], "64 KiB")
        self.assertEqual(basic["operating_vdd_v"], {"min": 1.8, "max": 3.6})
        self.assertIsNone(basic["io_supply_v"])
        self.assertIsNone(basic["vdda_v"])
        self.assertFalse(basic["programming_profile_authority"])
        self.assertFalse(basic["hardware_runtime_ready"])
        self.assertFalse(basic["physical_programming_qualified"])
        self.assertIsNone(result["selected_profile"])

    def test_remaining_st_m1_batch_is_exposed_without_programming_authority(self) -> None:
        cases = (
            ("STM32U031C6T6", "STM32U0", "stm32u0-device-basic-v1", "12 KiB", {"min": 1.71, "max": 3.6}),
            ("STM32U375CET6", "STM32U3", "stm32u3-device-basic-v1", "256 KiB", {"min": 1.71, "max": 3.6}),
            ("STM32L552CCT6", "STM32L5", "stm32l5-device-basic-v1", "256 KiB", {"min": 1.71, "max": 3.6}),
            ("STM32H7R3A8I6", "STM32H7RS", "stm32h7rs-device-basic-v1", "620 KiB", {"min": 1.62, "max": 3.6}),
            ("STM32WBA50KGU6", "STM32WBA5X", "stm32wba5x-device-basic-v1", "64 KiB", {"min": 1.71, "max": 3.6}),
        )
        for icpn, family, profile_id, ram, vdd in cases:
            with self.subTest(icpn=icpn):
                status, payload = self.request(f"/api/devices/search?q={icpn}&limit=1")
                self.assertEqual(status, 200)
                self.assertEqual(payload["count"], 1)
                result = payload["results"][0]
                self.assertEqual(result["family"], family)
                basic = result["manufacturer_device_basic_profile"]
                self.assertIsNotNone(basic)
                assert basic is not None
                self.assertEqual(basic["profile_id"], profile_id)
                self.assertEqual(basic["ram_size"], ram)
                self.assertEqual(basic["operating_vdd_v"], vdd)
                self.assertIsNone(basic["io_supply_v"])
                self.assertIsNone(basic["vdda_v"])
                self.assertFalse(basic["programming_profile_authority"])
                self.assertFalse(basic["hardware_runtime_ready"])
                self.assertFalse(basic["physical_programming_qualified"])
                self.assertIsNone(result["selected_profile"])

    def test_st_n6_level0_identity_remains_internal_even_with_basic_profile(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32N645A0H3Q&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["total_count"], 0)
        self.assertEqual(payload["results"], [])

        catalog = get_default_device_catalog()
        record = catalog.resolve("STMicroelectronics", "STM32N645A0H3Q")
        self.assertIsNotNone(record)
        qualification = get_default_programming_qualification_registry().describe(
            "STMicroelectronics", "STM32N645A0H3Q"
        )
        self.assertEqual(qualification["catalog_level"], 0)
        self.assertEqual(qualification["catalog_level_state"], "DISCOVERED")
        self.assertFalse(qualification["selector_visible"])
        self.assertFalse(qualification["job_selectable"])

    def test_g4_basic_profile_exposes_direct_vdda_without_io_supply_inference(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32G474VCH3TR&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32G474VCH3TR")
        self.assertEqual(result["family"], "STM32G4")
        basic = result["manufacturer_device_basic_profile"]
        self.assertIsNotNone(basic)
        assert basic is not None
        self.assertEqual(basic["profile_id"], "stm32g4-device-basic-v1")
        self.assertEqual(basic["ram_size"], "128 KiB")
        self.assertEqual(basic["operating_vdd_v"], {"min": 1.71, "max": 3.6})
        self.assertIsNone(basic["io_supply_v"])
        self.assertEqual(basic["vdda_v"], {"min": 1.71, "max": 3.6})
        self.assertFalse(basic["programming_profile_authority"])
        self.assertIsNone(result["selected_profile"])

    def test_admitted_icpn_without_manufacturer_selected_profile_returns_null(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F407VGT6&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        self.assertIsNone(payload["results"][0]["manufacturer_device_basic_profile"])
        self.assertIsNone(payload["results"][0]["selected_profile"])

        qualification = payload["results"][0]["programming_qualification"]
        self.assertIsNotNone(qualification)
        self.assertEqual(qualification["state"], "UNKNOWN")
        self.assertFalse(qualification["reviewed"])

    def test_c8_selected_profile_does_not_use_blue_pill_128k_override(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F103C8T6&limit=1")
        self.assertEqual(status, 200)
        selected = payload["results"][0]["selected_profile"]
        self.assertEqual(selected["device"]["memory_map"]["main_flash"]["size_bytes"], 65536)
        self.assertEqual(selected["device"]["memory_map"]["main_flash"]["end"], "0x0800FFFF")
        self.assertNotEqual(selected["device"]["memory_map"]["main_flash"]["size_bytes"], 131072)

    def test_g0_bounded_backend_mapping_is_visible_without_physical_overclaim(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32G0B1RBI3N&limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32G0B1RBI3N")
        self.assertEqual(result["family"], "STM32G0")
        self.assertEqual(result["catalog"]["scope"], "production_admitted")
        self.assertEqual(result["backend"]["mapping_status"], "mapped")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32g0x.cfg")
        self.assertEqual(result["physical_validation"]["engineering_status"], "no_evidence")

    def test_microchip_phase1_identity_rejected_from_job_batch_target(self) -> None:
        catalog = get_default_device_catalog()
        rows = [r for r in catalog.records if r.vendor == "Microchip"]
        self.assertEqual(len(rows), 1015)
        for row in rows:
            with self.subTest(icpn=row.identifier):
                with self.assertRaisesRegex(ValueError, "no executable programming mapping"):
                    _parse_target_device(
                        {"vendor": "Microchip", "identifier": row.identifier},
                        label="Engineering target_device")
        with self.assertRaisesRegex(ValueError, "canonical Device Catalog"):
            _parse_target_device(
                {"vendor": "Microchip", "identifier": "ATSAML10E16A-MZTVAO"},
                label="Batch target_device")
        # Untyped Job.target string cannot bypass target_device's same guard.
        for row in rows:
            with self.subTest(raw_target=row.identifier):
                with self.assertRaisesRegex(ValueError, "lookup-only"):
                    _reject_unmapped_microchip_raw_job_target(row.identifier)
        for other in ("STM32F103C8T6", "ATSAML10E16A-MZTVAO", None):
            _reject_unmapped_microchip_raw_job_target(other)

    def test_microchip_official_saml1x_route_is_l1_visible_but_never_executable(self) -> None:
        catalog = get_default_device_catalog()
        registry = get_default_programming_qualification_registry()
        rows = [r for r in catalog.records if r.vendor == "Microchip" and r.family == "SAML1X"]
        self.assertEqual(len(rows), 122)
        self.assertEqual(len({r.identifier for r in rows}), 122)
        self.assertTrue(all(r.family == "SAML1X" and
                            r.mapping_status == "no_mapping" and
                            r.target_config == "" for r in rows))
        for record in rows:
            with self.subTest(icpn=record.identifier):
                qualification = registry.describe(record.vendor, record.identifier)
                self.assertEqual(qualification["identity_state"], "IDENTIFIED")
                self.assertEqual(qualification["catalog_level"], 1)
                self.assertEqual(qualification["catalog_level_state"], "PROGRAMMING_CANDIDATE")
                self.assertEqual(qualification["state"], "CANDIDATE")
                self.assertEqual(qualification["route_evidence"], "backend_candidate_registry")
                self.assertTrue(qualification["selector_visible"])
                self.assertFalse(qualification["job_selectable"])
                self.assertFalse(qualification["execution_authorized"])

                status, payload = self.request(
                    f"/api/devices/search?q={record.identifier}&limit=20")
                self.assertEqual(status, 200)
                self.assertEqual(payload["scope"], "customer_ic_selector")
                self.assertEqual(payload["levels"], [1, 2, 3])
                self.assertEqual(payload["catalog_size"], EXPECTED_CUSTOMER_SELECTOR_SIZE)
                found = [x for x in payload["results"] if x["icpn"] == record.identifier]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["catalog_level"], 1)
                self.assertFalse(found[0]["job_selectable"])
                self.assertEqual(found[0]["backend"]["mapping_status"], "no_mapping")

                status, excluded = self.request(
                    f"/api/devices/search?q={record.identifier}&levels=2&limit=20")
                self.assertEqual(status, 200)
                self.assertEqual(excluded["total_count"], 0)

        status, payload = self.request("/api/devices/search?q=ATSAML10E16A-MU&levels=0")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["error_type"], "INVALID_DEVICE_SEARCH")
        self.assertIn("Level 0 is internal-only", payload["error"]["message"])

        for blocked in (
            "ATSAML10D16A-MZTVAO", "ATSAML10E16A-MZTVAO",
            "ATSAML10E16A-MZVAO", "ATSAML11E16A-MZTVAO",
        ):
            with self.subTest(excluded=blocked):
                status, payload = self.request(f"/api/devices/search?q={blocked}&limit=5")
                self.assertEqual(status, 200)
                self.assertEqual(payload["total_count"], 0)

    def test_pic32mx_admitted_l1_candidate_visible_but_not_job_selectable(self) -> None:
        catalog = get_default_device_catalog()
        registry = get_default_programming_qualification_registry()
        rows = [r for r in catalog.records
                if r.vendor == "Microchip" and r.family == "PIC32MX"]
        self.assertEqual(len(rows), 893)
        self.assertEqual(len({r.identifier for r in rows}), 893)
        for record in rows:
            with self.subTest(icpn=record.identifier):
                self.assertEqual(record.mapping_status, "no_mapping")
                self.assertFalse(record.target_config)
                q = registry.describe("Microchip", record.identifier)
                self.assertEqual(q["catalog_level"], 1)
                self.assertEqual(q["state"], "CANDIDATE")
                self.assertTrue(q["selector_visible"])
                self.assertFalse(q["job_selectable"])
                self.assertFalse(q["execution_authorized"])
                self.assertFalse(q["physical_programming_qualified"])
        # Verify actual customer-facing gateway and L2 isolation for a bounded
        # sample. Job rejection of all 1015 Microchip codes is a separate test.
        for code in (rows[0].identifier, rows[len(rows) // 2].identifier,
                     rows[-1].identifier):
            status, payload = self.request(
                f"/api/devices/search?q={quote(code, safe='')}&limit=100")
            self.assertEqual(status, 200)
            found = [r for r in payload["results"] if r["icpn"] == code]
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["catalog_level"], 1)
            self.assertFalse(found[0]["job_selectable"])
            status, l2 = self.request(
                f"/api/devices/search?q={quote(code, safe='')}&levels=2&limit=100")
            self.assertEqual(status, 200)
            self.assertEqual(l2["total_count"], 0)

    def test_customer_selector_filters_l1_and_l2_server_side(self) -> None:
        status, l1 = self.request("/api/devices/search?q=STM32F103T8U6&levels=1&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(l1["levels"], [1])
        self.assertGreaterEqual(l1["count"], 1)
        self.assertEqual(l1["results"][0]["icpn"], "STM32F103T8U6")
        self.assertEqual(l1["results"][0]["catalog_level"], 1)
        self.assertEqual(l1["results"][0]["catalog_level_state"], "PROGRAMMING_CANDIDATE")
        self.assertFalse(l1["results"][0]["job_selectable"])
        self.assertTrue(l1["results"][0]["programming_qualification"]["selector_visible"])

        status, l1_as_l2 = self.request("/api/devices/search?q=STM32F103T8U6&levels=2&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(l1_as_l2["count"], 0)
        self.assertEqual(l1_as_l2["total_count"], 0)

        status, l2 = self.request("/api/devices/search?q=STM32F103C8T6&levels=2&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(l2["levels"], [2])
        self.assertGreaterEqual(l2["count"], 1)
        self.assertEqual(l2["results"][0]["icpn"], "STM32F103C8T6")
        self.assertEqual(l2["results"][0]["catalog_level"], 2)
        self.assertEqual(l2["results"][0]["catalog_level_state"], "PROGRAMMABLE")
        self.assertTrue(l2["results"][0]["job_selectable"])

        status, l2_as_l1 = self.request("/api/devices/search?q=STM32F103C8T6&levels=1&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(l2_as_l1["count"], 0)
        self.assertEqual(l2_as_l1["total_count"], 0)

    def test_search_is_case_insensitive(self) -> None:
        status, payload = self.request("/api/devices/search?q=stm32f103c8t6")
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"][0]["identifier"], "STM32F103C8T6")

    def test_search_total_count_is_independent_of_return_limit(self) -> None:
        status, limited = self.request("/api/devices/search?q=STM32&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(limited["count"], 5)
        self.assertGreater(limited["total_count"], limited["count"])

        status, wider = self.request("/api/devices/search?q=STM32&limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(wider["count"], 10)
        self.assertEqual(wider["total_count"], limited["total_count"])

    def test_search_offset_pages_are_deterministic_and_preserve_total_count(self) -> None:
        status, first = self.request("/api/devices/search?q=STM32F&limit=5&offset=0")
        self.assertEqual(status, 200)
        self.assertEqual(first["limit"], 5)
        self.assertEqual(first["offset"], 0)
        self.assertEqual(first["count"], 5)
        self.assertGreater(first["total_count"], 5)

        status, second = self.request("/api/devices/search?q=STM32F&limit=5&offset=5")
        self.assertEqual(status, 200)
        self.assertEqual(second["limit"], 5)
        self.assertEqual(second["offset"], 5)
        self.assertEqual(second["count"], 5)
        self.assertEqual(second["total_count"], first["total_count"])
        self.assertTrue(
            {item["identifier"] for item in first["results"]}.isdisjoint(
                {item["identifier"] for item in second["results"]}
            )
        )

        status, repeated = self.request("/api/devices/search?q=STM32F&limit=5&offset=5")
        self.assertEqual(status, 200)
        self.assertEqual(
            [item["identifier"] for item in repeated["results"]],
            [item["identifier"] for item in second["results"]],
        )

    def test_search_offset_beyond_end_returns_empty_page_with_total(self) -> None:
        status, first = self.request("/api/devices/search?q=STM32F&limit=5&offset=0")
        self.assertEqual(status, 200)
        status, beyond = self.request(
            f"/api/devices/search?q=STM32F&limit=5&offset={first['total_count'] + 10}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(beyond["count"], 0)
        self.assertEqual(beyond["total_count"], first["total_count"])
        self.assertEqual(beyond["results"], [])

    def test_family_and_vendor_queries_return_only_admitted_rows(self) -> None:
        status, payload = self.request("/api/devices/search?q=STMicroelectronics%20STM32F4&limit=100")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 100)
        self.assertEqual(payload["catalog_size"], EXPECTED_CUSTOMER_SELECTOR_SIZE)
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

    def test_phase40_foundation_batch6_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F413ZGJ6TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F413ZGJ6TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "UFBGA")
        self.assertEqual(result["pin_count"], "144")
        self.assertEqual(result["flash_size"], "1024 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_foundation_batch7_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F439ZGT7TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F439ZGT7TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "144")
        self.assertEqual(result["flash_size"], "1024 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_foundation_batch8_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F417VET6TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F417VET6TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "100")
        self.assertEqual(result["flash_size"], "512 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_foundation_batch9_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F469VIT6TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F469VIT6TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "100")
        self.assertEqual(result["flash_size"], "2048 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_foundation_batch10_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F479VIT6&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F479VIT6")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "100")
        self.assertEqual(result["flash_size"], "2048 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase40_foundation_batch11_icpn_is_exposed_only_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F479ZIT6&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F479ZIT6")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "144")
        self.assertEqual(result["flash_size"], "2048 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase41_rt_batch2_icpn_is_exposed_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F405RGT7TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["catalog_size"], EXPECTED_CUSTOMER_SELECTOR_SIZE)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F405RGT7TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase41_rt_batch3_icpn_is_exposed_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F413RGT6TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["catalog_size"], EXPECTED_CUSTOMER_SELECTOR_SIZE)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F413RGT6TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase41_rt_batch4_icpn_is_exposed_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F446RET7TR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["catalog_size"], EXPECTED_CUSTOMER_SELECTOR_SIZE)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F446RET7TR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "64")
        self.assertEqual(result["flash_size"], "512 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase42b_stm32f410cb_icpn_is_exposed_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F410CBT6&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["catalog_size"], EXPECTED_CUSTOMER_SELECTOR_SIZE)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F410CBT6")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "LQFP")
        self.assertEqual(result["pin_count"], "48")
        self.assertEqual(result["flash_size"], "128 KiB")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_phase42f_stm32f412rg_ptr_icpn_is_exposed_after_admission(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32F412RGY6PTR&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(payload["catalog_size"], EXPECTED_CUSTOMER_SELECTOR_SIZE)
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["icpn"], "STM32F412RGY6PTR")
        self.assertEqual(result["family"], "STM32F4")
        self.assertEqual(result["package"], "WLCSP")
        self.assertEqual(result["pin_count"], "64")
        self.assertEqual(result["flash_size"], "1024 KiB")
        self.assertEqual(result["option_suffix"], "PTR")
        self.assertEqual(result["backend"]["target_config"], "tcl/target/stm32f4x.cfg")

    def test_research_only_identifier_is_not_exposed_by_production_search(self) -> None:
        status, payload = self.request("/api/devices/search?q=ADUC7019BCPZ62I")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["total_count"], 0)
        self.assertEqual(payload["results"], [])

    def test_empty_query_is_valid_for_catalog_metadata_idle_state(self) -> None:
        status, payload = self.request("/api/devices/search?q=")
        self.assertEqual(status, 200)
        self.assertEqual(payload["catalog_size"], EXPECTED_CUSTOMER_SELECTOR_SIZE)
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["total_count"], 0)
        self.assertEqual(payload["results"], [])

    def test_invalid_limit_fails_closed(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32&limit=101")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["error_type"], "INVALID_DEVICE_SEARCH")

    def test_invalid_offset_fails_closed(self) -> None:
        status, payload = self.request("/api/devices/search?q=STM32&limit=30&offset=-1")
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
