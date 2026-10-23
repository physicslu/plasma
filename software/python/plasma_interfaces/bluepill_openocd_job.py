"""One-Site Blue Pill OpenOCD Job adapter; inert without trusted injection.

This is *not* a hardware admission implementation. The production server
constructs OpenOCDInterface, never this class. An approved hardware supervisor
in Path 2 must inject both an already admitted OpenOCDPlanExecutor (including
a real process launcher) and an owner/electrical/rollback admission predicate.
Without both the canonical SiteExecutionRouter will refuse every Job.
"""
from __future__ import annotations

from dataclasses import replace
from collections.abc import Awaitable, Callable
from typing import Any

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ICSupportResolver
from plasma_core.models import JobRequest
from .base import ProgressCallback
from .openocd import OpenOCDInterface
from .openocd_executor import OpenOCDPlanExecutor
from .openocd_plan import OpenOCDPlanCompiler


AdmissionCheck = Callable[[JobRequest, dict[str, Any]], bool]
Shutdown = Callable[[], Awaitable[None]]


class BluepillPoCOpenOCDInterface(OpenOCDInterface):
    """Explicit opt-in candidate for *one* canonical STM32F103C8T6 Site.

    The only current positive host test may use a synthetic injected executor;
    such a test never qualifies physical SWD, the bitstream or a real IC.
    """

    TARGET = "STM32F103C8T6"
    SITE_ID = 1
    PROFILE = "stm32f1-medium-density-flash-v0"

    def __init__(
        self,
        options: dict[str, Any],
        resolver: ICSupportResolver,
        *,
        executor: OpenOCDPlanExecutor | None = None,
        admission_check: AdmissionCheck | None = None,
        shutdown: Shutdown | None = None,
    ) -> None:
        super().__init__(options)
        self._resolver = resolver
        self._executor = executor
        self._admission_check = admission_check
        self._shutdown = shutdown
        self._active: JobRequest | None = None
        self._compiler = OpenOCDPlanCompiler()

    def runtime_admitted(self, request: JobRequest, route: dict[str, Any]) -> bool:
        """Check exact Site/ICPN/profile/route and injected physical ownership.

        No environment variable, REST request, YAML bool or Host CI artifact
        alone can activate this callback. It must be supplied by a trusted
        external hardware owner *after* real Path 2 electrical checks.
        """
        if (request.site_id != self.SITE_ID
                or request.target != self.TARGET
                or route.get("mode") != "openocd"
                or route.get("selected_programming_profile_id") != self.PROFILE
                or route.get("selected_openocd_target_config") != "target/stm32f1x.cfg"
                or self._executor is None
                or self._admission_check is None
                or self._shutdown is None):
            return False
        try:
            return self._admission_check(request, route) is True
        except Exception:
            return False

    def prepare_request(self, request: JobRequest) -> None:
        route = request.metadata.get("resolved_ic_support")
        if not isinstance(route, dict) or route.get("hardware_runtime_ready") is not True:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "Blue Pill PoC execution route has not been admitted",
            )
        if not self.runtime_admitted(request, route):
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "Blue Pill PoC admission expired before target access",
            )
        self._active = request

    async def _execute(self, operation: Operation, *, image: bytes | None = None,
                       section: dict[str, Any] | None = None) -> dict[str, bytes]:
        request = self._active
        if request is None or request.operation != operation:
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "No matching prepared PoC Job")
        route = request.metadata.get("resolved_ic_support")
        if not isinstance(route, dict) or not self.runtime_admitted(request, route):
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "PoC hardware ownership was revoked")
        if image is not None and (request.image_ref is not None or image != request.image):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Programming Image changed after Job admission")
        if section is not None:
            request = replace(request, map_data={"sections": [section]})
        support = self._resolver.require_exact(self.TARGET)
        plan = self._compiler.compile(
            support,
            request,
            configured_target_config=self.target_cfg,
        )
        assert self._executor is not None
        result = await self._executor.execute(plan, support, request)
        return result.read_sections

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        await self._execute(Operation.ERASE)
        if progress:
            await progress(1, 1)

    async def program(self, image: bytes, address: int = 0,
                      progress: ProgressCallback | None = None) -> None:
        if address != 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PoC programming requires main Flash offset zero")
        await self._execute(Operation.PROGRAM, image=image)
        if progress:
            await progress(len(image), len(image))

    async def verify(self, image: bytes, address: int = 0,
                     progress: ProgressCallback | None = None) -> None:
        if address != 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PoC verification requires main Flash offset zero")
        await self._execute(Operation.VERIFY, image=image)
        if progress:
            await progress(len(image), len(image))

    async def read(self, address: int, length: int,
                   progress: ProgressCallback | None = None) -> bytes:
        if type(address) is not int or type(length) is not int or address < 0 or length <= 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PoC read range invalid")
        sections = await self._execute(
            Operation.READ,
            section={"name": "flash", "address": address, "length": length},
        )
        if len(sections) != 1 or "flash" not in sections or len(sections["flash"]) != length:
            raise PlasmaError(ErrorCode.INTERFACE_FAILURE, "PoC OpenOCD returned wrong read section")
        if progress:
            await progress(length, length)
        return sections["flash"]

    async def safe_shutdown(self) -> None:
        self._active = None
        if self._shutdown is not None:
            await self._shutdown()
