from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_client.client import PlasmaClient
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager

from tests.helpers import make_config


class PPUExecutionOwnershipTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.server: PlasmaServer | None = None

    async def asyncTearDown(self) -> None:
        if self.server is not None:
            await self.server.close()

    async def start_server(self) -> PlasmaClient:
        config = make_config(
            self.root,
            enabled_sites=2,
            max_concurrent_jobs=2,
            site_options={
                1: {"mock": {"default_delay_s": 0.2}},
                2: {"mock": {"default_delay_s": 0.2}},
            },
        )
        self.server = PlasmaServer(config, SiteManager(config))
        await self.server.start()
        return PlasmaClient(*self.server.address, response_timeout_s=2.0)

    @staticmethod
    def owned_request(
        site_id: int,
        job_id: str,
        owner_id: str,
    ) -> JobRequest:
        return JobRequest(
            site_id=site_id,
            operation=Operation.ERASE,
            job_id=job_id,
            client_id="ownership-test-client",
            metadata={
                "execution_owner_kind": "test",
                "execution_owner_id": owner_id,
            },
        )

    async def test_same_owner_can_run_multiple_sites_and_other_owner_is_rejected(self) -> None:
        client = await self.start_server()
        first = self.owned_request(1, "owner-a-site-1", "owner-a")
        second = self.owned_request(2, "owner-a-site-2", "owner-a")

        await client.start(first)
        await client.start(second)

        status = await client.status()
        self.assertTrue(status["ppu"]["execution"]["busy"])
        self.assertEqual(status["ppu"]["execution"]["owner_kind"], "test")
        self.assertEqual(status["ppu"]["execution"]["owner_id"], "owner-a")
        self.assertEqual(status["ppu"]["execution"]["active_job_count"], 2)

        with self.assertRaises(PlasmaError) as caught:
            await client.start(self.owned_request(1, "owner-b-site-1", "owner-b"))
        self.assertEqual(caught.exception.code, ErrorCode.PPU_BUSY)
        self.assertTrue(caught.exception.recoverable)
        self.assertEqual(caught.exception.context["active_owner_id"], "owner-a")
        self.assertEqual(caught.exception.context["requested_owner_id"], "owner-b")

        await client.wait_for_job(first.job_id)
        await client.wait_for_job(second.job_id)

        released = await client.status()
        self.assertFalse(released["ppu"]["execution"]["busy"])
        self.assertIsNone(released["ppu"]["execution"]["owner_id"])
        self.assertEqual(released["ppu"]["execution"]["active_job_count"], 0)

        third = self.owned_request(1, "owner-b-after-release", "owner-b")
        await client.start(third)
        await client.wait_for_job(third.job_id)

    async def test_batch_id_is_the_execution_owner_not_shared_batch_client_id(self) -> None:
        client = await self.start_server()
        first = JobRequest(
            site_id=1,
            operation=Operation.ERASE,
            job_id="batch-a-site-1",
            client_id="plasma-batch-runtime",
            metadata={"batch_id": "batch-a", "batch_round": 1},
        )
        same_batch = JobRequest(
            site_id=2,
            operation=Operation.ERASE,
            job_id="batch-a-site-2",
            client_id="plasma-batch-runtime",
            metadata={"batch_id": "batch-a", "batch_round": 1},
        )
        different_batch = JobRequest(
            site_id=2,
            operation=Operation.ERASE,
            job_id="batch-b-site-2",
            client_id="plasma-batch-runtime",
            metadata={"batch_id": "batch-b", "batch_round": 1},
        )

        await client.start(first)
        await client.start(same_batch)
        with self.assertRaises(PlasmaError) as caught:
            await client.start(different_batch)
        self.assertEqual(caught.exception.code, ErrorCode.PPU_BUSY)
        self.assertEqual(caught.exception.context["active_owner_kind"], "batch")
        self.assertEqual(caught.exception.context["active_owner_id"], "batch-a")
        self.assertEqual(caught.exception.context["requested_owner_id"], "batch-b")

        await client.wait_for_job(first.job_id)
        await client.wait_for_job(same_batch.job_id)

    async def test_unscoped_rest_jobs_do_not_share_fixed_gateway_client_identity(self) -> None:
        client = await self.start_server()
        first = JobRequest(
            site_id=1,
            operation=Operation.ERASE,
            job_id="rest-job-a",
            client_id="plasma-web-engineering",
        )
        second = JobRequest(
            site_id=2,
            operation=Operation.ERASE,
            job_id="rest-job-b",
            client_id="plasma-web-engineering",
        )

        await client.start(first)
        status = await client.status()
        self.assertEqual(status["ppu"]["execution"]["owner_kind"], "rest_job")
        self.assertEqual(status["ppu"]["execution"]["owner_id"], first.job_id)

        with self.assertRaises(PlasmaError) as caught:
            await client.start(second)
        self.assertEqual(caught.exception.code, ErrorCode.PPU_BUSY)
        self.assertEqual(caught.exception.context["active_owner_id"], first.job_id)
        self.assertEqual(caught.exception.context["requested_owner_id"], second.job_id)

        await client.wait_for_job(first.job_id)
        await client.start(second)
        await client.wait_for_job(second.job_id)

    async def test_execution_owner_metadata_requires_kind_and_id_together(self) -> None:
        client = await self.start_server()
        invalid = JobRequest(
            site_id=1,
            operation=Operation.ERASE,
            job_id="invalid-owner",
            metadata={"execution_owner_id": "owner-a"},
        )
        with self.assertRaises(PlasmaError) as caught:
            await client.start(invalid)
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)
