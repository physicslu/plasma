from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from plasma_core.enums import JobState, Operation
from plasma_core.models import JobRequest
from plasma_web.engineering_targets import MockEngineeringPPUProvider


class EngineeringMockPPUProviderTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.provider = MockEngineeringPPUProvider(Path(cls.temporary.name))
        cls.provider.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.provider.close()
        cls.temporary.cleanup()

    async def wait_terminal(self, facility_id: str, ppu_id: str, job_id: str) -> dict:
        for _ in range(1000):
            payload = await self.provider.status(facility_id, ppu_id, job_id=job_id)
            job = payload["job"]
            if JobState(job["state"]).terminal:
                return job
            await asyncio.sleep(0.01)
        self.fail(f"job did not become terminal: {job_id}")

    def test_catalog_is_three_facilities_four_ppus_each_and_sixty_sites(self) -> None:
        catalog = self.provider.catalog()
        self.assertTrue(catalog["ok"])
        self.assertEqual(catalog["provider"], "mock")
        self.assertEqual(catalog["facility_count"], 3)
        self.assertEqual(catalog["ppu_count"], 12)
        self.assertEqual(catalog["site_count"], 60)
        self.assertEqual(len(catalog["facilities"]), 3)
        for facility in catalog["facilities"]:
            self.assertEqual(len(facility["ppus"]), 4)
            self.assertEqual([ppu["site_count"] for ppu in facility["ppus"]], [2, 4, 6, 8])

    def test_catalog_reports_size_aware_timing_profile(self) -> None:
        profile = self.provider.catalog()["timing_profile"]
        self.assertEqual(profile["model"], "fixed-overhead-plus-bytes-over-throughput")
        self.assertEqual(profile["flash_size_bytes"], 4 * 1024 * 1024)

        program_bytes_per_s = profile["throughput_bytes_per_s"]["program"]
        program_overhead_s = profile["operation_overheads_s"]["program"]
        program_100k_s = program_overhead_s + (100 * 1024) / program_bytes_per_s
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

    async def test_job_is_executed_by_the_selected_mock_ppu(self) -> None:
        facility_id = "mock-facility-02"
        ppu_id = "mock-facility-02-ppu-03"  # six-Site PPU
        firmware = b"\x11\x22\x33\x44" * 64

        accepted = await self.provider.start_job(
            facility_id,
            ppu_id,
            JobRequest(site_id=6, operation=Operation.PROGRAM, firmware=firmware),
        )
        job = await self.wait_terminal(facility_id, ppu_id, accepted["job"]["job_id"])
        self.assertEqual(job["site_id"], 6)
        self.assertEqual(job["operation"], "program")
        self.assertEqual(job["state"], "success")

        selected = await self.provider.status(facility_id, ppu_id)
        self.assertEqual(selected["sites"][5]["latest_job"]["job_id"], job["job_id"])

        other = await self.provider.status("mock-facility-02", "mock-facility-02-ppu-02")
        self.assertTrue(all(site["latest_job"] is None for site in other["sites"]))

    async def test_size_aware_program_has_a_real_cancellation_window(self) -> None:
        facility_id = "mock-facility-01"
        ppu_id = "mock-facility-01-ppu-01"
        firmware = bytes((index % 251 for index in range(100 * 1024)))
        accepted = await self.provider.start_job(
            facility_id,
            ppu_id,
            JobRequest(site_id=1, operation=Operation.PROGRAM, firmware=firmware),
        )
        job_id = accepted["job"]["job_id"]

        await asyncio.sleep(0.2)
        cancellation = await self.provider.cancel_job(facility_id, ppu_id, job_id)
        self.assertTrue(cancellation["accepted"])
        job = await self.wait_terminal(facility_id, ppu_id, job_id)
        self.assertEqual(job["state"], "cancelled")
        self.assertTrue(job["cancel_requested"])

    async def test_read_result_can_be_retrieved_from_selected_mock_ppu(self) -> None:
        facility_id = "mock-facility-03"
        ppu_id = "mock-facility-03-ppu-01"
        accepted = await self.provider.start_job(
            facility_id,
            ppu_id,
            JobRequest(
                site_id=1,
                operation=Operation.READ,
                map_data={"sections": [{"name": "flash", "address": 0, "length": 16}]},
            ),
        )
        job = await self.wait_terminal(facility_id, ppu_id, accepted["job"]["job_id"])
        self.assertEqual(job["state"], "success")
        output_file = Path(job["result"]["output_files"][0]).name
        data = self.provider.read_output_file(facility_id, ppu_id, job["job_id"], output_file)
        self.assertEqual(len(data), 16)


if __name__ == "__main__":
    unittest.main()
