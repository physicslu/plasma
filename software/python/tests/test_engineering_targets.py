from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_web.engineering_targets import MockEngineeringPPUProvider


class EngineeringMockPPUProviderTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.provider = MockEngineeringPPUProvider(cls.root)
        cls.provider.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.provider.close()
        cls.temporary.cleanup()

    def test_catalog_is_eight_facilities_four_ppus_each_and_one_hundred_sixty_sites(self) -> None:
        catalog = self.provider.catalog()
        self.assertTrue(catalog["ok"])
        self.assertEqual(catalog["provider"], "mock")
        self.assertEqual(catalog["facility_count"], 8)
        self.assertEqual(catalog["ppu_count"], 32)
        self.assertEqual(catalog["site_count"], 160)
        self.assertEqual(catalog["programming_asset_scope"], "connection-session-and-ppu")
        self.assertIn("serial_number", catalog["supported_asset_types"])
        self.assertIn("intel_hex", catalog["supported_asset_formats"])
        self.assertEqual(
            catalog["implemented_normalizers"],
            [{"asset_type": "image", "asset_format": "binary", "output": "normalized_image"}],
        )
        self.assertEqual(len(catalog["facilities"]), 8)
        for facility in catalog["facilities"]:
            self.assertEqual(len(facility["ppus"]), 4)
            self.assertEqual([ppu["site_count"] for ppu in facility["ppus"]], [2, 4, 6, 8])

    def test_catalog_reports_size_aware_timing_profile(self) -> None:
        profile = self.provider.catalog()["timing_profile"]
        self.assertEqual(profile["model"], "fixed-overhead-plus-bytes-over-throughput")
        self.assertEqual(profile["flash_size_bytes"], 4 * 1024 * 1024)
        self.assertEqual(profile["operation_timeout_s"], 90.0)
        program_100k_s = (
            profile["operation_overheads_s"]["program"]
            + (100 * 1024) / profile["throughput_bytes_per_s"]["program"]
        )
        self.assertGreaterEqual(program_100k_s, 5.0)
        self.assertLess(program_100k_s, 5.2)
        erase_s = (
            profile["operation_overheads_s"]["erase"]
            + profile["flash_size_bytes"] / profile["throughput_bytes_per_s"]["erase"]
        )
        self.assertAlmostEqual(erase_s, 3.0)

    async def test_each_mock_ppu_reports_its_own_canonical_topology(self) -> None:
        catalog = self.provider.catalog()
        for facility in catalog["facilities"]:
            for ppu in facility["ppus"]:
                with self.subTest(facility=facility["facility_id"], ppu=ppu["ppu_id"]):
                    status = await self.provider.status(facility["facility_id"], ppu["ppu_id"])
                    self.assertEqual(status["ppu"]["facility_id"], facility["facility_id"])
                    self.assertEqual(status["ppu"]["ppu_id"], ppu["ppu_id"])
                    self.assertEqual(status["ppu"]["site_count"], ppu["site_count"])
                    self.assertEqual(
                        [site["site_id"] for site in status["sites"]],
                        list(range(1, ppu["site_count"] + 1)),
                    )



if __name__ == "__main__":
    unittest.main()
