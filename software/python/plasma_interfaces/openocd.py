from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ICSupportResolver, get_default_ic_support_resolver
from plasma_core.models import JobRequest

from .base import BaseInterface, ProgressCallback
from .openocd_executor import OpenOCDPlanExecutor, ProcessLauncher
from .openocd_plan import OpenOCDPlanCompiler


class OpenOCDInterface(BaseInterface):
    """Per-Site OpenOCD interface; only an explicit injected launcher may execute.

    Host-only integration exercises actual Job/Handler/Executor plumbing using
    fake processes. The default runtime has no process launcher and remains
    incapable of launching OpenOCD on the device.
    """

    def __init__(
        self,
        options: dict[str, Any],
        *,
        process_launcher: ProcessLauncher | None = None,
        resolver: ICSupportResolver | None = None,
    ) -> None:
        self.executable = str(options.get("executable", "openocd"))
        self.interface_cfg = options.get("interface_cfg")
        self.target_cfg = options.get("target_cfg")
        self.adapter_serial = options.get("adapter_serial")
        self.work_dir = Path(options.get("work_dir", ".")).resolve()
        self.command_timeout_s = float(options.get("command_timeout_s", 30.0))
        self._configured = bool(self.interface_cfg and self.target_cfg)
        self._process_launcher = process_launcher
        self._resolver = resolver
        self._compiler = OpenOCDPlanCompiler()
        self._executor = OpenOCDPlanExecutor(
            options, process_launcher=process_launcher, compiler=self._compiler
        )
        self._request: JobRequest | None = None

    @property
    def software_validation_ready(self) -> bool:
        """Readiness is an internal injected capability, never a config key."""
        return self._configured and self._process_launcher is not None

    def _require_ready(self) -> None:
        if not self.software_validation_ready:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD hardware runtime is not enabled; use the software-validation compiled-plan executor only",
            )

    def _support(self, target: str):
        resolver = self._resolver or get_default_ic_support_resolver()
        return resolver.require_exact(target)

    def prepare_request(self, request: JobRequest) -> None:
        self._require_ready()
        # The Job is already resolved by SiteExecutionRouter, but recompile
        # from the canonical support before any injected fake process executes.
        support = self._support(request.target)
        self._compiler.compile(support, request, configured_target_config=self.target_cfg)
        self._request = request

    def _prepared(self, operation: Operation) -> JobRequest:
        self._require_ready()
        request = self._request
        if request is None or request.operation is not operation:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD operation has no matching prepared Job",
            )
        return request

    async def _execute(self, request: JobRequest):
        support = self._support(request.target)
        plan = self._compiler.compile(
            support, request, configured_target_config=self.target_cfg
        )
        return await self._executor.execute(plan, support, request)

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        request = self._prepared(Operation.ERASE)
        await self._execute(request)
        if progress:
            await progress(1, 1)

    async def program(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        request = self._prepared(Operation.PROGRAM)
        if address != 0 or image != request.image:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "OpenOCD Job image or address mismatch")
        await self._execute(request)
        if progress:
            await progress(len(image), len(image))

    async def verify(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        request = self._prepared(Operation.VERIFY)
        if address != 0 or image != request.image:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "OpenOCD Job image or address mismatch")
        await self._execute(request)
        if progress:
            await progress(len(image), len(image))

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        request = self._prepared(Operation.READ)
        # The generic handler uses (0, 256) for an omitted section. Map that
        # default to the target's real main-Flash base; explicit map sections
        # continue to be compiled and range-checked against the IC geometry.
        if address == 0 and not request.map_data:
            support = self._support(request.target)
            address = int(support.memory_geometry_profile.data["main_flash_start"], 0)
        section_request = replace(
            request,
            map_data={"sections": [{"name": "readback", "address": address, "length": length}]},
        )
        result = await self._execute(section_request)
        payload = result.read_sections["readback"]
        if progress:
            await progress(len(payload), len(payload))
        return payload

    async def safe_shutdown(self) -> None:
        # OpenOCDPlanExecutor owns its subprocess and awaits its exit/kill.
        self._request = None
