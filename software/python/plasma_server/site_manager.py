from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from plasma_core.config import PlasmaConfig, SiteConfig
from plasma_core.enums import Operation, SiteState
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ICSupportResolver, get_default_ic_support_resolver
from plasma_core.job_logging import OutputManager, ServerEventLogger
from plasma_core.models import JobRequest, JobResult, iso_now
from plasma_core.protocol import PROTOCOL_VERSION
from plasma_interfaces.base import BaseInterface
from plasma_interfaces.fpga import FPGAInterface
from plasma_interfaces.mock import MockActivityTracker, MockInterface
from plasma_interfaces.openocd import OpenOCDInterface

from .execution_router import RoutedProgrammingHandler, SiteExecutionRouter
from .job_manager import JobRegistry, JobRuntime
from .site_worker import SiteWorker

InterfaceFactory = Callable[[SiteConfig], BaseInterface]


@dataclass(slots=True)
class PPUExecutionLease:
    """Active execution ownership for one physical PPU.

    A logical owner may run multiple Site Jobs concurrently. A different owner
    is rejected until every Job currently owned by the lease is terminal.
    """

    owner_kind: str
    owner_id: str
    job_ids: set[str] = field(default_factory=set)

    def snapshot(self) -> dict[str, Any]:
        return {
            "busy": True,
            "owner_kind": self.owner_kind,
            "owner_id": self.owner_id,
            "active_job_count": len(self.job_ids),
        }


class SiteManager:
    """Own the Programming Sites local to exactly one physical PPU."""

    def __init__(
        self,
        config: PlasmaConfig,
        interface_factory: InterfaceFactory | None = None,
        mock_tracker: MockActivityTracker | None = None,
        ic_support_resolver: ICSupportResolver | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.output = OutputManager(config.server.output_root)
        self.server_log = ServerEventLogger(config.server.log_root)
        self.registry = JobRegistry()
        self._semaphore = asyncio.Semaphore(config.server.max_concurrent_jobs)
        self._site_configs = {site.id: site for site in config.sites}
        requires_ic_support = any(
            site.enabled and site.interface != "mock" for site in config.sites
        )
        self.ic_support_resolver = (
            ic_support_resolver
            if ic_support_resolver is not None
            else get_default_ic_support_resolver() if requires_ic_support else None
        )
        self.interfaces: dict[int, BaseInterface] = {}
        self.execution_routers: dict[int, SiteExecutionRouter] = {}
        self.workers: dict[int, SiteWorker] = {}
        self._execution_lock = threading.RLock()
        self._execution_lease: PPUExecutionLease | None = None
        self._started = False

        for site in config.sites:
            if not site.enabled:
                continue
            interface = (
                interface_factory(site)
                if interface_factory
                else self._default_interface(site, mock_tracker)
            )
            self.interfaces[site.id] = interface
            router = SiteExecutionRouter(site, interface, self.ic_support_resolver)
            self.execution_routers[site.id] = router
            handler = RoutedProgrammingHandler(interface, router)
            self.workers[site.id] = SiteWorker(
                site,
                handler,
                self.output,
                config.server.log_root,
                self._semaphore,
                config.server.max_queue_depth_per_site,
            )

    @staticmethod
    def _default_interface(
        site: SiteConfig,
        tracker: MockActivityTracker | None,
    ) -> BaseInterface:
        if site.interface == "mock":
            return MockInterface.from_options(site.mock, tracker=tracker)
        if site.interface == "openocd":
            return OpenOCDInterface(site.openocd)
        if site.interface == "fpga":
            return FPGAInterface(site.id, site.register_base)
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"unsupported interface: {site.interface}")

    async def start(self) -> list[str]:
        if self._started:
            return []
        recovered = self.output.recover_incomplete()
        for worker in self.workers.values():
            worker.start()
        self._started = True
        self.server_log.event(
            "INFO",
            "site_manager_started",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
            enabled_sites=sorted(self.workers),
            recovered_jobs=recovered,
        )
        return recovered

    async def shutdown(self) -> None:
        if not self._started:
            return
        for runtime in self.registry.all():
            if not runtime.state.terminal:
                worker = self.workers.get(runtime.request.site_id)
                if worker:
                    worker.cancel(runtime)
        await asyncio.gather(*(worker.stop() for worker in self.workers.values()))
        self._started = False
        self.server_log.event(
            "INFO",
            "site_manager_stopped",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
        )

    def _resolve_site(self, site_id: int) -> SiteWorker:
        config = self._site_configs.get(site_id)
        if config is None:
            raise PlasmaError(ErrorCode.SITE_INVALID, f"site does not exist: SITE{site_id}")
        if not config.enabled:
            raise PlasmaError(ErrorCode.SITE_DISABLED, f"site is disabled: SITE{site_id}")
        return self.workers[site_id]

    @staticmethod
    def _validate_execution_owner(value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 256:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"{field_name} must be a non-empty string of at most 256 characters",
            )
        return value

    @classmethod
    def _execution_owner(cls, request: JobRequest) -> tuple[str, str]:
        explicit_kind = request.metadata.get("execution_owner_kind")
        explicit_id = request.metadata.get("execution_owner_id")
        if (explicit_kind is None) != (explicit_id is None):
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "execution_owner_kind and execution_owner_id must be supplied together",
            )
        if explicit_kind is not None and explicit_id is not None:
            return (
                cls._validate_execution_owner(explicit_kind, "execution_owner_kind"),
                cls._validate_execution_owner(explicit_id, "execution_owner_id"),
            )

        batch_id = request.metadata.get("batch_id")
        if batch_id is not None:
            return "batch", cls._validate_execution_owner(batch_id, "batch_id")

        # REST gateway client IDs are process-global labels, not authenticated
        # client identities. Treat an unscoped REST Job as its own execution so
        # two browser tabs/PCs cannot bypass PPU ownership merely because both
        # requests carry the same fixed gateway client_id. Multi-Site Web work
        # that needs one shared owner must use the server-side Batch contract.
        if request.client_id in {"plasma-web", "plasma-web-engineering"}:
            return "rest_job", cls._validate_execution_owner(request.job_id, "job_id")

        return "client", cls._validate_execution_owner(request.client_id, "client_id")

    def _reserve_execution_job(self, request: JobRequest) -> tuple[str, str]:
        owner_kind, owner_id = self._execution_owner(request)
        acquired = False
        conflict: PPUExecutionLease | None = None
        with self._execution_lock:
            lease = self._execution_lease
            if lease is not None and (lease.owner_kind, lease.owner_id) != (owner_kind, owner_id):
                conflict = PPUExecutionLease(
                    owner_kind=lease.owner_kind,
                    owner_id=lease.owner_id,
                    job_ids=set(lease.job_ids),
                )
            else:
                if lease is None:
                    lease = PPUExecutionLease(owner_kind=owner_kind, owner_id=owner_id)
                    self._execution_lease = lease
                    acquired = True
                lease.job_ids.add(request.job_id)

        if conflict is not None:
            self.server_log.event(
                "WARNING",
                "ppu_execution_lease_conflict",
                ppu_id=self.config.ppu.id,
                facility_id=self.config.ppu.facility_id,
                active_owner_kind=conflict.owner_kind,
                active_owner_id=conflict.owner_id,
                requested_owner_kind=owner_kind,
                requested_owner_id=owner_id,
                requested_job_id=request.job_id,
            )
            raise PlasmaError(
                ErrorCode.PPU_BUSY,
                "PPU is owned by another active execution",
                recoverable=True,
                context={
                    "ppu_id": self.config.ppu.id,
                    "facility_id": self.config.ppu.facility_id,
                    "active_owner_kind": conflict.owner_kind,
                    "active_owner_id": conflict.owner_id,
                    "requested_owner_kind": owner_kind,
                    "requested_owner_id": owner_id,
                },
            )

        if acquired:
            self.server_log.event(
                "INFO",
                "ppu_execution_lease_acquired",
                ppu_id=self.config.ppu.id,
                facility_id=self.config.ppu.facility_id,
                owner_kind=owner_kind,
                owner_id=owner_id,
            )
        return owner_kind, owner_id

    def _release_execution_job(self, job_id: str) -> None:
        released: tuple[str, str] | None = None
        with self._execution_lock:
            lease = self._execution_lease
            if lease is None or job_id not in lease.job_ids:
                return
            lease.job_ids.discard(job_id)
            if not lease.job_ids:
                released = (lease.owner_kind, lease.owner_id)
                self._execution_lease = None
        if released is not None:
            self.server_log.event(
                "INFO",
                "ppu_execution_lease_released",
                ppu_id=self.config.ppu.id,
                facility_id=self.config.ppu.facility_id,
                owner_kind=released[0],
                owner_id=released[1],
            )

    def execution_lease_snapshot(self) -> dict[str, Any]:
        with self._execution_lock:
            lease = self._execution_lease
            if lease is None:
                return {
                    "busy": False,
                    "owner_kind": None,
                    "owner_id": None,
                    "active_job_count": 0,
                }
            return lease.snapshot()

    def enqueue(self, request: JobRequest) -> asyncio.Future[JobResult]:
        if not self._started:
            raise PlasmaError(ErrorCode.INTERNAL_ERROR, "site manager is not started")
        request.validate()
        if request.operation in {Operation.STATUS, Operation.CANCEL}:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "status/cancel are control operations")
        worker = self._resolve_site(request.site_id)
        request = self.execution_routers[request.site_id].admit(request)
        if worker.queue.full():
            raise PlasmaError(
                ErrorCode.SITE_BUSY,
                f"SITE{request.site_id} queue is full",
                recoverable=True,
            )

        # Registry insertion happens before lease reservation, but still before
        # any worker dispatch. This makes duplicate job IDs fail without
        # touching the active execution lease or an existing JobRuntime.
        runtime = self.registry.create(request)
        try:
            owner_kind, owner_id = self._reserve_execution_job(request)
            self.output.write_state(request.job_id, worker._state_payload(runtime))
            worker.enqueue(runtime)
        except Exception:
            self.registry.discard(request.job_id)
            self._release_execution_job(request.job_id)
            raise
        runtime.future.add_done_callback(
            lambda _future, job_id=request.job_id: self._release_execution_job(job_id)
        )
        self.server_log.event(
            "INFO",
            "job_queued",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
            job_id=request.job_id,
            site_id=request.site_id,
            operation=request.operation.value,
            execution_owner_kind=owner_kind,
            execution_owner_id=owner_id,
        )
        return runtime.future

    async def submit(self, request: JobRequest) -> JobResult:
        return await self.enqueue(request)

    def cancel(self, job_id: str) -> dict[str, Any]:
        runtime = self.registry.get(job_id)
        worker = self._resolve_site(runtime.request.site_id)
        already_terminal = runtime.state.terminal
        worker.cancel(runtime)
        runtime.updated_at = iso_now()
        self.server_log.event(
            "INFO",
            "job_cancel_requested",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
            job_id=job_id,
            site_id=runtime.request.site_id,
            already_terminal=already_terminal,
        )
        return {
            "job_id": job_id,
            "accepted": not already_terminal,
            "state": runtime.state.value,
            "cancel_requested": runtime.cancel_requested,
        }

    def ppu_snapshot(self) -> dict[str, Any]:
        ppu = self.config.ppu
        return {
            "ppu_id": ppu.id,
            "facility_id": ppu.facility_id,
            "model": ppu.model,
            "display_name": ppu.display_name,
            "site_count": self.config.site_count,
            "enabled_site_count": self.config.enabled_site_count,
            "execution": self.execution_lease_snapshot(),
            "capabilities": {
                "max_supported_sites": self.config.server.max_supported_sites,
                "operations": [
                    Operation.ERASE.value,
                    Operation.PROGRAM.value,
                    Operation.VERIFY.value,
                    Operation.READ.value,
                ],
            },
        }

    def _latest_job_summary(self, site_id: int) -> dict[str, Any] | None:
        """Return a browser-safe latest-job summary without result files or raw metadata."""
        for runtime in reversed(self.registry.all()):
            if runtime.request.site_id != site_id:
                continue
            return {
                "job_id": runtime.request.job_id,
                "operation": runtime.request.operation.value,
                "state": runtime.state.value,
                "stage": runtime.stage,
                "stage_state": runtime.stage_state,
                "progress_percent": runtime.progress_percent,
                "created_at": runtime.created_at,
                "started_at": runtime.started_at,
                "updated_at": runtime.updated_at,
                "cancel_requested": runtime.cancel_requested,
            }
        return None

    def status(
        self,
        *,
        site_id: int | None = None,
        job_id: str | None = None,
        protocol_version: str = PROTOCOL_VERSION,
    ) -> dict[str, Any]:
        if protocol_version != PROTOCOL_VERSION:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported protocol version: {protocol_version!r}",
            )
        if job_id:
            return {"job": self.registry.get(job_id).snapshot(protocol_version)}
        site_ids = [site_id] if site_id is not None else sorted(self._site_configs)
        sites: list[dict[str, Any]] = []
        for current_id in site_ids:
            config = self._site_configs.get(current_id)
            if config is None:
                raise PlasmaError(ErrorCode.SITE_INVALID, f"site does not exist: SITE{current_id}")
            worker = self.workers.get(current_id)
            sites.append(
                {
                    "site_id": current_id,
                    "enabled": config.enabled,
                    "state": worker.state.value if worker else SiteState.DISABLED.value,
                    "current_job_id": (
                        worker.current.request.job_id if worker and worker.current else None
                    ),
                    "latest_job": self._latest_job_summary(current_id),
                    "queued_jobs": worker.queue.qsize() if worker else 0,
                    "interface": config.interface if config.enabled else None,
                    "target": config.target if config.enabled else None,
                }
            )
        return {
            "ppu": self.ppu_snapshot(),
            "sites": sites,
        }
