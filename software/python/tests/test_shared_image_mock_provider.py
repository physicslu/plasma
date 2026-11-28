from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from plasma_core.enums import Operation
from plasma_core.errors import PlasmaError
from plasma_core.models import JobRequest
from plasma_web.shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


class SharedImageMockProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.provider = SharedImageMockEngineeringPPUProvider(
            self.root,
            flash_size_bytes=64 * 1024,
        )
        self.provider.start()
        session = self.provider.begin_session()
        self.session_id = session["session"]["session_id"]
        self.facility_id = "mock-facility-01"
        self.ppu_id = "mock-facility-01-ppu-01"

    async def asyncTearDown(self) -> None:
        self.provider.close()
        self.temporary.cleanup()

    async def test_program_job_is_refused_by_the_mock_ppu_without_a_reservation(self) -> None:
        image = b"shared-provider-image" * 128
        digest = hashlib.sha256(image).hexdigest()
        self.provider.cache_asset(
            self.session_id,
            self.facility_id,
            self.ppu_id,
            "application.bin",
            "image",
            "binary",
            digest,
            image,
        )
        request = JobRequest(
            site_id=1,
            operation=Operation.PROGRAM,
            job_id="shared-provider-program",
            timeout_s=10.0,
        )
        # U7: the Mock PPU refuses a Programming Job outside an ACTIVE
        # Resource Reservation; nothing is registered or queued.
        with self.assertRaisesRegex(PlasmaError, "Reservation required"):
            await self.provider.start_job(
                self.facility_id,
                self.ppu_id,
                request,
                session_id=self.session_id,
                asset_sha256=digest,
            )
        server = self.provider._servers[(self.facility_id, self.ppu_id)]
        self.assertEqual(server.manager.registry.all(), [])
        self.assertFalse(server.manager.execution_lease_snapshot()["busy"])


if __name__ == "__main__":
    unittest.main()
