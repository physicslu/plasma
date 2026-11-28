from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from plasma_client.client import PlasmaClient
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_interfaces.mock import MockInterface
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager

from tests.helpers import make_config
from tests.test_mock_programming_operations import reserved_request


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
        self.manager = SiteManager(config)
        self.server = PlasmaServer(config, self.manager)
        await self.server.start()
        return PlasmaClient(*self.server.address, response_timeout_s=2.0)

    def owned_request(self, site_id: int, job_id: str, owner_id: str) -> JobRequest:
        """A Job of ``owner_id``'s Batch under its Resource Reservation (U7)."""
        return reserved_request(self.manager, JobRequest(
            site_id=site_id,
            operation=Operation.ERASE,
            job_id=job_id,
            client_id="ownership-test-client",
        ), owner_id)

    def foreign_request(self, site_id: int, job_id: str, owner_id: str) -> JobRequest:
        """Another Batch's Job while ``owner-a`` holds the Reservation."""
        return JobRequest(
            site_id=site_id, operation=Operation.ERASE, job_id=job_id,
            client_id="ownership-test-client",
            metadata={"execution_owner_kind": "rest_client", "execution_owner_id": owner_id,
                      "resource_reservation_token": "0" * 32})

    async def test_same_owner_can_run_multiple_sites_and_other_owner_is_rejected(self) -> None:
        client = await self.start_server()
        first = self.owned_request(1, "owner-a-site-1", "owner-a")
        second = self.owned_request(2, "owner-a-site-2", "owner-a")

        await client.start(first)
        await client.start(second)

        status = await client.status()
        self.assertTrue(status["ppu"]["execution"]["busy"])
        self.assertEqual(status["ppu"]["execution"]["owner_kind"], "rest_client")
        self.assertEqual(status["ppu"]["execution"]["owner_id"], "owner-a")
        self.assertEqual(status["ppu"]["execution"]["active_job_count"], 2)

        with self.assertRaises(PlasmaError) as caught:
            await client.start(self.foreign_request(1, "owner-b-site-1", "owner-b"))
        self.assertEqual(caught.exception.code, ErrorCode.PPU_BUSY)
        self.assertIn("another execution", caught.exception.message)

        await client.wait_for_job(first.job_id)
        await client.wait_for_job(second.job_id)

        released = await client.status()
        self.assertFalse(released["ppu"]["execution"]["busy"])
        self.assertIsNone(released["ppu"]["execution"]["owner_id"])
        self.assertEqual(released["ppu"]["execution"]["active_job_count"], 0)

        # owner-a's Batch ends; its Reservation settles (Mock ERASE proves no
        # SAFE_OFF, so through the explicit local recovery), then owner-b reserves.
        with self.assertRaises(PlasmaError):
            self.manager.resource_reservation(
                "release", owner_id="owner-a",
                token=first.metadata["resource_reservation_token"])
        self.manager.recover_resource_reservation(
            self.manager.resource_reservation_snapshot()["recovery_id"])
        third = self.owned_request(1, "owner-b-after-release", "owner-b")
        await client.start(third)
        await client.wait_for_job(third.job_id)

    async def test_duplicate_job_id_does_not_remove_existing_job_or_lease(self) -> None:
        client = await self.start_server()
        original = self.owned_request(1, "duplicate-active-job", "owner-a")
        await client.start(original)

        with self.assertRaises(PlasmaError) as caught:
            await client.start(original)
        self.assertEqual(caught.exception.code, ErrorCode.DUPLICATE_JOB)

        status = await client.status()
        self.assertTrue(status["ppu"]["execution"]["busy"])
        self.assertEqual(status["ppu"]["execution"]["owner_kind"], "rest_client")
        self.assertEqual(status["ppu"]["execution"]["owner_id"], "owner-a")
        self.assertEqual(status["ppu"]["execution"]["active_job_count"], 1)

        observed = await client.status(job_id=original.job_id)
        self.assertEqual(observed["job"]["job_id"], original.job_id)
        await client.wait_for_job(original.job_id)

        released = await client.status()
        self.assertFalse(released["ppu"]["execution"]["busy"])

    async def test_owner_labels_without_a_reservation_never_program(self) -> None:
        # U7: a batch_id, a fixed Gateway client label or an explicit owner of
        # any kind is only an owner identity; without the ACTIVE Reservation's
        # token no Programming Job is admitted and nothing is left behind.
        client = await self.start_server()
        for request in (
            JobRequest(site_id=1, operation=Operation.ERASE, job_id="batch-a-site-1",
                       client_id="plasma-batch-runtime", metadata={"batch_id": "batch-a"}),
            JobRequest(site_id=1, operation=Operation.ERASE, job_id="rest-job-a",
                       client_id="plasma-web-engineering"),
            JobRequest(site_id=1, operation=Operation.ERASE, job_id="labelled",
                       metadata={"execution_owner_kind": "diagnostic",
                                 "execution_owner_id": "mock"}),
        ):
            with self.subTest(job=request.job_id):
                with self.assertRaises(PlasmaError) as caught:
                    await client.start(request)
                self.assertEqual(caught.exception.code, ErrorCode.PPU_BUSY)
                self.assertIn("Reservation required", caught.exception.message)
        status = await client.status()
        self.assertFalse(status["ppu"]["execution"]["busy"])
        self.assertEqual(status["ppu"]["execution"]["active_job_count"], 0)

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


class _HeldEraseMock(MockInterface):
    """Erase blocks on a shared event, recording the Site that reached hardware."""

    def __init__(self, site_id: int, arrived: dict[int, asyncio.Event],
                 release: asyncio.Event) -> None:
        super().__init__()
        self._site_id = site_id
        self._arrived = arrived
        self._release = release

    async def erase(self, progress=None) -> None:
        self._arrived[self._site_id].set()
        await self._release.wait()


class PPUSiteConcurrencyOracleTests(unittest.IsolatedAsyncioTestCase):
    """PPU-side oracle: ``server.max_concurrent_jobs`` alone decides overlap.

    One Batch owner holds the PPU lease for both Sites. Each Site's interface
    is held on an event, so a serial PPU cannot let the second Site reach the
    interface while the first is still held, and a two-slot PPU must.
    """

    async def _manager(self, max_jobs: int):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config = make_config(Path(temporary.name), enabled_sites=2, max_concurrent_jobs=max_jobs,
                             site_options={1: {"operation_timeout_s": 10.0},
                                           2: {"operation_timeout_s": 10.0}})
        arrived = {1: asyncio.Event(), 2: asyncio.Event()}
        release = asyncio.Event()
        manager = SiteManager(config, interface_factory=lambda site: _HeldEraseMock(
            site.id, arrived, release))
        await manager.start()
        self.addAsyncCleanup(manager.shutdown)
        futures = [manager.enqueue(reserved_request(manager, JobRequest(
            site_id=site, operation=Operation.ERASE, job_id=f"batch-a-site-{site}",
            client_id="plasma-batch-runtime"), "batch-a"))
            for site in (1, 2)]
        return manager, arrived, release, futures

    async def test_two_slots_overlap_both_sites_under_one_batch_lease(self) -> None:
        manager, arrived, release, futures = await self._manager(2)
        await asyncio.wait_for(asyncio.gather(arrived[1].wait(), arrived[2].wait()), 5)
        lease = manager.execution_lease_snapshot()
        self.assertEqual((lease["owner_kind"], lease["owner_id"], lease["active_job_count"]),
                         ("rest_client", "batch-a", 2))
        states = {site: manager.registry.get(f"batch-a-site-{site}").state.value for site in (1, 2)}
        self.assertEqual(states, {1: "running", 2: "running"})
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*futures), 5)
        self.assertEqual([r.state.value for r in results], ["success", "success"])

    async def test_one_slot_serializes_sites_even_under_one_batch_lease(self) -> None:
        manager, arrived, release, futures = await self._manager(1)
        first = await asyncio.wait_for(asyncio.wait(
            [asyncio.ensure_future(arrived[s].wait()) for s in (1, 2)],
            return_when=asyncio.FIRST_COMPLETED), 5)
        self.assertTrue(first[0])
        held = 1 if arrived[1].is_set() else 2
        other = 3 - held
        for _ in range(50):  # the peer is admitted and queued, never on hardware
            await asyncio.sleep(0.01)
            self.assertFalse(arrived[other].is_set(), "max_concurrent_jobs=1 let a peer overlap")
        self.assertEqual(manager.registry.get(f"batch-a-site-{other}").state.value, "queued")
        self.assertEqual(manager.execution_lease_snapshot()["active_job_count"], 2)
        release.set()
        await asyncio.wait_for(arrived[other].wait(), 5)
        results = await asyncio.wait_for(asyncio.gather(*futures), 5)
        self.assertEqual([r.state.value for r in results], ["success", "success"])
