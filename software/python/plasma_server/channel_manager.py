from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from plasma_core.config import ChannelConfig, PlasmaConfig
from plasma_core.enums import ChannelState, Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.job_logging import OutputManager, ServerEventLogger
from plasma_core.models import JobRequest, JobResult, iso_now
from plasma_handlers.stm32 import STM32F103Handler
from plasma_interfaces.base import BaseInterface
from plasma_interfaces.fpga import FPGAInterface
from plasma_interfaces.mock import MockActivityTracker, MockInterface
from plasma_interfaces.openocd import OpenOCDInterface

from .channel_worker import ChannelWorker
from .job_manager import JobRegistry, JobRuntime

InterfaceFactory = Callable[[ChannelConfig], BaseInterface]


class ChannelManager:
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
        self._channel_configs = {channel.id: channel for channel in config.channels}
        self.interfaces: dict[int, BaseInterface] = {}
        self.workers: dict[int, ChannelWorker] = {}
        self._started = False

        for channel in config.channels:
            if not channel.enabled:
                continue
            interface = (
                interface_factory(channel)
                if interface_factory
                else self._default_interface(channel, mock_tracker)
            )
            self.interfaces[channel.id] = interface
            handler = STM32F103Handler(interface)
            self.workers[channel.id] = ChannelWorker(
                channel,
                handler,
                self.output,
                config.server.log_root,
                self._semaphore,
                config.server.max_queue_depth_per_channel,
            )

    @staticmethod
    def _default_interface(
        channel: ChannelConfig,
        tracker: MockActivityTracker | None,
    ) -> BaseInterface:
        if channel.interface == "mock":
            return MockInterface.from_options(channel.mock, tracker=tracker)
        if channel.interface == "openocd":
            return OpenOCDInterface(channel.openocd)
        if channel.interface == "fpga":
            return FPGAInterface(channel.id, channel.register_base)
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"unsupported interface: {channel.interface}")

    async def start(self) -> list[str]:
        if self._started:
            return []
        recovered = self.output.recover_incomplete()
        for worker in self.workers.values():
            worker.start()
        self._started = True
        self.server_log.event(
            "INFO",
            "channel_manager_started",
            enabled_channels=sorted(self.workers),
            recovered_jobs=recovered,
        )
        return recovered

    async def shutdown(self) -> None:
        if not self._started:
            return
        for runtime in self.registry.all():
            if not runtime.state.terminal:
                worker = self.workers.get(runtime.request.channel_id)
                if worker:
                    worker.cancel(runtime)
        await asyncio.gather(*(worker.stop() for worker in self.workers.values()))
        self._started = False
        self.server_log.event("INFO", "channel_manager_stopped")

    def _resolve_channel(self, channel_id: int) -> ChannelWorker:
        config = self._channel_configs.get(channel_id)
        if config is None:
            raise PlasmaError(ErrorCode.CHANNEL_INVALID, f"channel does not exist: CH{channel_id}")
        if not config.enabled:
            raise PlasmaError(ErrorCode.CHANNEL_DISABLED, f"channel is disabled: CH{channel_id}")
        return self.workers[channel_id]

    def enqueue(self, request: JobRequest) -> asyncio.Future[JobResult]:
        if not self._started:
            raise PlasmaError(ErrorCode.INTERNAL_ERROR, "channel manager is not started")
        request.validate()
        if request.operation in {Operation.STATUS, Operation.CANCEL}:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "status/cancel are control operations")
        worker = self._resolve_channel(request.channel_id)
        if worker.queue.full():
            raise PlasmaError(
                ErrorCode.CHANNEL_BUSY,
                f"CH{request.channel_id} queue is full",
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
            job_id=request.job_id,
            channel_id=request.channel_id,
            operation=request.operation.value,
        )
        return runtime.future

    async def submit(self, request: JobRequest) -> JobResult:
        return await self.enqueue(request)

    def cancel(self, job_id: str) -> dict[str, Any]:
        runtime = self.registry.get(job_id)
        worker = self._resolve_channel(runtime.request.channel_id)
        already_terminal = runtime.state.terminal
        worker.cancel(runtime)
        runtime.updated_at = iso_now()
        self.server_log.event(
            "INFO",
            "job_cancel_requested",
            job_id=job_id,
            channel_id=runtime.request.channel_id,
            already_terminal=already_terminal,
        )
        return {
            "job_id": job_id,
            "accepted": not already_terminal,
            "state": runtime.state.value,
            "cancel_requested": runtime.cancel_requested,
        }

    def status(self, *, channel_id: int | None = None, job_id: str | None = None) -> dict[str, Any]:
        if job_id:
            return {"job": self.registry.get(job_id).snapshot()}
        channel_ids = [channel_id] if channel_id is not None else sorted(self._channel_configs)
        channels: list[dict[str, Any]] = []
        for current_id in channel_ids:
            config = self._channel_configs.get(current_id)
            if config is None:
                raise PlasmaError(ErrorCode.CHANNEL_INVALID, f"channel does not exist: CH{current_id}")
            worker = self.workers.get(current_id)
            channels.append(
                {
                    "channel_id": current_id,
                    "enabled": config.enabled,
                    "state": worker.state.value if worker else ChannelState.DISABLED.value,
                    "current_job_id": (
                        worker.current.request.job_id if worker and worker.current else None
                    ),
                    "queued_jobs": worker.queue.qsize() if worker else 0,
                    "interface": config.interface if config.enabled else None,
                    "target": config.target if config.enabled else None,
                }
            )
        return {"channels": channels}
