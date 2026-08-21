from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from plasma_core.enums import Operation
from plasma_core.models import LOCAL_MOCK_BLOB_SCHEME, JobRequest
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

    async def test_program_job_enters_mock_server_as_shared_reference(self) -> None:
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
        accepted = await self.provider.start_job(
            self.facility_id,
            self.ppu_id,
            request,
            session_id=self.session_id,
            asset_sha256=digest,
        )
        self.assertTrue(accepted["ok"])

        server = self.provider._servers[(self.facility_id, self.ppu_id)]
        runtime = server.manager.registry.get(request.job_id)
        self.assertEqual(runtime.request.image, b"")
        self.assertIsNotNone(runtime.request.image_ref)
        assert runtime.request.image_ref is not None
        self.assertEqual(runtime.request.image_ref.scheme, LOCAL_MOCK_BLOB_SCHEME)
        self.assertEqual(runtime.request.image_ref.sha256, digest)
        self.assertEqual(runtime.request.image_ref.size_bytes, len(image))


if __name__ == "__main__":
    unittest.main()
