from __future__ import annotations

import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path

from plasma_core.enums import JobState, Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
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

    async def wait_terminal(self, facility_id: str, ppu_id: str, job_id: str) -> dict:
        for _ in range(1000):
            payload = await self.provider.status(facility_id, ppu_id, job_id=job_id)
            job = payload["job"]
            if JobState(job["state"]).terminal:
                return job
            await asyncio.sleep(0.01)
        self.fail(f"job did not become terminal: {job_id}")

    def cache_image_asset(
        self,
        facility_id: str,
        ppu_id: str,
        image: bytes,
        name: str = "test.bin",
    ) -> tuple[str, str]:
        session_id = self.provider.begin_session()["session"]["session_id"]
        sha256 = hashlib.sha256(image).hexdigest()
        self.provider.cache_asset(
            session_id,
            facility_id,
            ppu_id,
            name,
            "image",
            "binary",
            sha256,
            image,
        )
        return session_id, sha256

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

    def test_session_can_cache_multiple_assets_and_reconnect_clears_session(self) -> None:
        facility_id = "mock-facility-02"
        ppu_id = "mock-facility-02-ppu-03"
        other_ppu_id = "mock-facility-02-ppu-04"
        image_a = b"A" * 4096
        image_b = b"B" * 4096
        sha_a = hashlib.sha256(image_a).hexdigest()
        sha_b = hashlib.sha256(image_b).hexdigest()

        first_session = self.provider.begin_session()["session"]["session_id"]
        miss = self.provider.asset_cache_status(
            first_session, facility_id, ppu_id, "A.bin", "image", "binary", len(image_a), sha_a
        )
        self.assertFalse(miss["programming_asset"]["cache_hit"])

        uploaded = self.provider.cache_asset(
            first_session, facility_id, ppu_id, "A.bin", "image", "binary", sha_a, image_a
        )
        self.assertTrue(uploaded["programming_asset"]["uploaded"])
        hit = self.provider.asset_cache_status(
            first_session, facility_id, ppu_id, "A.bin", "image", "binary", len(image_a), sha_a
        )
        self.assertTrue(hit["programming_asset"]["cache_hit"])

        other_ppu_miss = self.provider.asset_cache_status(
            first_session, facility_id, other_ppu_id, "A.bin", "image", "binary", len(image_a), sha_a
        )
        self.assertFalse(other_ppu_miss["programming_asset"]["cache_hit"])

        self.provider.cache_asset(
            first_session, facility_id, ppu_id, "B.bin", "image", "binary", sha_b, image_b
        )
        old_asset_still_present = self.provider.asset_cache_status(
            first_session, facility_id, ppu_id, "A.bin", "image", "binary", len(image_a), sha_a
        )
        new_asset_present = self.provider.asset_cache_status(
            first_session, facility_id, ppu_id, "B.bin", "image", "binary", len(image_b), sha_b
        )
        self.assertTrue(old_asset_still_present["programming_asset"]["cache_hit"])
        self.assertTrue(new_asset_present["programming_asset"]["cache_hit"])

        serial = b"SN-000001"
        serial_sha = hashlib.sha256(serial).hexdigest()
        self.provider.cache_asset(
            first_session,
            facility_id,
            ppu_id,
            "serial.txt",
            "serial_number",
            "text",
            serial_sha,
            serial,
        )
        serial_hit = self.provider.asset_cache_status(
            first_session,
            facility_id,
            ppu_id,
            "serial.txt",
            "serial_number",
            "text",
            len(serial),
            serial_sha,
        )
        self.assertTrue(serial_hit["programming_asset"]["cache_hit"])

        second_session_payload = self.provider.begin_session(first_session)["session"]
        self.assertTrue(second_session_payload["previous_session_cleared"])
        second_session = second_session_payload["session_id"]
        reconnect_miss = self.provider.asset_cache_status(
            second_session, facility_id, ppu_id, "B.bin", "image", "binary", len(image_b), sha_b
        )
        self.assertFalse(reconnect_miss["programming_asset"]["cache_hit"])
        with self.assertRaises(PlasmaError):
            self.provider.asset_cache_status(
                first_session, facility_id, ppu_id, "B.bin", "image", "binary", len(image_b), sha_b
            )

    def test_upload_rejects_fingerprint_mismatch(self) -> None:
        facility_id = "mock-facility-01"
        ppu_id = "mock-facility-01-ppu-01"
        session_id = self.provider.begin_session()["session"]["session_id"]
        data = b"payload"
        wrong_sha = hashlib.sha256(b"other").hexdigest()
        with self.assertRaises(PlasmaError):
            self.provider.cache_asset(
                session_id, facility_id, ppu_id, "bad.bin", "image", "binary", wrong_sha, data
            )

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

    async def test_job_is_executed_by_selected_ppu_using_cached_image_asset(self) -> None:
        facility_id = "mock-facility-02"
        ppu_id = "mock-facility-02-ppu-03"
        image = b"\x11\x22\x33\x44" * 64
        session_id, asset_sha256 = self.cache_image_asset(facility_id, ppu_id, image)
        accepted = await self.provider.start_job(
            facility_id,
            ppu_id,
            JobRequest(site_id=6, operation=Operation.PROGRAM),
            session_id=session_id,
            asset_sha256=asset_sha256,
        )
        job = await self.wait_terminal(facility_id, ppu_id, accepted["job"]["job_id"])
        self.assertEqual(job["site_id"], 6)
        self.assertEqual(job["operation"], "program")
        self.assertEqual(job["state"], "success")
        selected = await self.provider.status(facility_id, ppu_id)
        self.assertEqual(selected["sites"][5]["latest_job"]["job_id"], job["job_id"])
        other = await self.provider.status("mock-facility-02", "mock-facility-02-ppu-02")
        self.assertTrue(all(site["latest_job"] is None for site in other["sites"]))

    async def test_non_image_asset_cannot_drive_program_job(self) -> None:
        facility_id = "mock-facility-01"
        ppu_id = "mock-facility-01-ppu-01"
        session_id = self.provider.begin_session()["session"]["session_id"]
        serial = b"SN-000002"
        asset_sha256 = hashlib.sha256(serial).hexdigest()
        self.provider.cache_asset(
            session_id,
            facility_id,
            ppu_id,
            "serial.txt",
            "serial_number",
            "text",
            asset_sha256,
            serial,
        )
        with self.assertRaises(PlasmaError) as caught:
            await self.provider.start_job(
                facility_id,
                ppu_id,
                JobRequest(site_id=1, operation=Operation.PROGRAM),
                session_id=session_id,
                asset_sha256=asset_sha256,
            )
        self.assertEqual(caught.exception.code, ErrorCode.OPERATION_UNSUPPORTED)

    async def test_size_aware_program_has_real_cancellation_window(self) -> None:
        facility_id = "mock-facility-01"
        ppu_id = "mock-facility-01-ppu-01"
        image = bytes((index % 251 for index in range(100 * 1024)))
        session_id, asset_sha256 = self.cache_image_asset(facility_id, ppu_id, image, "100k.bin")
        accepted = await self.provider.start_job(
            facility_id,
            ppu_id,
            JobRequest(site_id=1, operation=Operation.PROGRAM),
            session_id=session_id,
            asset_sha256=asset_sha256,
        )
        job_id = accepted["job"]["job_id"]
        await asyncio.sleep(0.2)
        cancellation = await self.provider.cancel_job(facility_id, ppu_id, job_id)
        self.assertTrue(cancellation["accepted"])
        job = await self.wait_terminal(facility_id, ppu_id, job_id)
        self.assertEqual(job["state"], "cancelled")
        self.assertTrue(job["cancel_requested"])

    async def test_two_sites_can_reuse_one_normalized_image(self) -> None:
        facility_id = "mock-facility-03"
        ppu_id = "mock-facility-03-ppu-02"
        image = b"shared" * 128
        session_id, asset_sha256 = self.cache_image_asset(facility_id, ppu_id, image, "shared.bin")
        accepted = await asyncio.gather(
            self.provider.start_job(
                facility_id, ppu_id, JobRequest(site_id=1, operation=Operation.PROGRAM),
                session_id=session_id, asset_sha256=asset_sha256,
            ),
            self.provider.start_job(
                facility_id, ppu_id, JobRequest(site_id=2, operation=Operation.PROGRAM),
                session_id=session_id, asset_sha256=asset_sha256,
            ),
        )
        jobs = await asyncio.gather(*(
            self.wait_terminal(facility_id, ppu_id, item["job"]["job_id"])
            for item in accepted
        ))
        self.assertEqual([job["state"] for job in jobs], ["success", "success"])

    async def test_ppu_rejects_different_active_images_across_sessions(self) -> None:
        facility_id = "mock-facility-03"
        ppu_id = "mock-facility-03-ppu-04"
        image_a = b"A" * 1024
        image_b = b"B" * 1024
        sha_a = hashlib.sha256(image_a).hexdigest()
        sha_b = hashlib.sha256(image_b).hexdigest()

        session_a = self.provider.begin_session()["session"]["session_id"]
        self.provider.cache_asset(session_a, facility_id, ppu_id, "A.bin", "image", "binary", sha_a, image_a)
        first = await self.provider.start_job(
            facility_id, ppu_id, JobRequest(site_id=1, operation=Operation.PROGRAM),
            session_id=session_a, asset_sha256=sha_a,
        )

        session_same = self.provider.begin_session()["session"]["session_id"]
        self.provider.cache_asset(session_same, facility_id, ppu_id, "A-again.bin", "image", "binary", sha_a, image_a)
        second = await self.provider.start_job(
            facility_id, ppu_id, JobRequest(site_id=2, operation=Operation.PROGRAM),
            session_id=session_same, asset_sha256=sha_a,
        )

        session_b = self.provider.begin_session()["session"]["session_id"]
        self.provider.cache_asset(session_b, facility_id, ppu_id, "B.bin", "image", "binary", sha_b, image_b)
        with self.assertRaises(PlasmaError) as blocked:
            await self.provider.start_job(
                facility_id, ppu_id, JobRequest(site_id=3, operation=Operation.PROGRAM),
                session_id=session_b, asset_sha256=sha_b,
            )
        self.assertEqual(blocked.exception.code, ErrorCode.SITE_BUSY)
        self.assertTrue(blocked.exception.recoverable)

        for accepted in (first, second):
            await self.provider.cancel_job(facility_id, ppu_id, accepted["job"]["job_id"])
        await asyncio.gather(*(
            self.wait_terminal(facility_id, ppu_id, accepted["job"]["job_id"])
            for accepted in (first, second)
        ))

        third = None
        for _ in range(100):
            try:
                third = await self.provider.start_job(
                    facility_id, ppu_id, JobRequest(site_id=3, operation=Operation.PROGRAM),
                    session_id=session_b, asset_sha256=sha_b,
                )
                break
            except PlasmaError as exc:
                if exc.code is not ErrorCode.SITE_BUSY:
                    raise
                await asyncio.sleep(0.02)
        self.assertIsNotNone(third, "PPU Image lease was not released after terminal Jobs")
        assert third is not None
        await self.provider.cancel_job(facility_id, ppu_id, third["job"]["job_id"])
        await self.wait_terminal(facility_id, ppu_id, third["job"]["job_id"])

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
