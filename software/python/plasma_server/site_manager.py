from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from plasma_core.config import PlasmaConfig, SiteConfig
from plasma_core.enums import Operation, SiteState
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.job_logging import OutputManager, ServerEventLogger
from plasma_core.models import JobRequest, JobResult, iso_now
from plasma_core.protocol import PROTOCOL_VERSION
from plasma_handlers.stm32 import STM32F103Handler
from plasma_interfaces.base import BaseInterface
from plasma_interfaces.fpga import FPGAInterface
from plasma_interfaces.mock import MockActivityTracker, MockInterface
from plasma_interfaces.openocd import OpenOCDInterface

from .job_manager import JobRegistry, JobRuntime
from .site_worker import SiteWorker

InterfaceFactory = Callable[[SiteConfig], BaseInterface]


class SiteManager:
    """Own the Programming Sites local to exactly one physical PPU."""

    def __init__(
        self,
        config: PlasmaConfig,
        interface_factory: InterfaceFactory | None = None,
        mock_tracker: MockActivityTracker | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.output = OutputManager(config.server.output_root)
        self.server_log = ServerEventLogger(config.server.log_root)
        self.registry = JobRegistry()
        self._semaphore = asyncio.Semaphore(config.server.max_concurrent_jobs)
        self._site_configs = {site.id: site for site in config.sites}
        self.interfaces: dict[int, BaseInterface] = {}
        self.workers: dict[int, SiteWorker] = {}
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
            handler = STM32F103Handler(interface)
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

    def enqueue(self, request: JobRequest) -> asyncio.Future[JobResult]:
        if not self._started:
            raise PlasmaError(ErrorCode.INTERNAL_ERROR, "site manager is not started")
        request.validate()
        if request.operation in {Operation.STATUS, Operation.CANCEL}:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "status/cancel are control operations")
        worker = self._resolve_site(request.site_id)
        if worker.queue.full():
            raise PlasmaError(
                ErrorCode.SITE_BUSY,
                f"SITE{request.site_id} queue is full",
                recoverable=True,
            )
        runtime = self.registry.create(request)
        try:
            self.output.write_state(request.job_id, worker._state_payload(runtime))
            worker.enqueue(runtime)
        except Exception:
            self.registry._jobs.pop(request.job_id, None)
            raise
        self.server_log.event(
            "INFO",
            "job_queued",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
            job_id=request.job_id,
            site_id=request.site_id,
            operation=request.operation.value,
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