from __future__ import annotations

from dataclasses import replace
from typing import Any

from plasma_core.config import SiteConfig
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ICSupportResolver
from plasma_core.models import ExecutionOutput, JobRequest
from plasma_handlers.base import BaseHandler, StageCallback
from plasma_handlers.programming import ProgrammingOperationHandler
from plasma_interfaces.base import BaseInterface


RESOLVED_IC_SUPPORT_METADATA_KEY = "resolved_ic_support"
MOCK_ROUTE = "mock_workflow"
OPENOCD_ROUTE = "openocd"
SUPPORTED_PROGRAMMING_PROFILES = frozenset({"stm32f1-medium-density-flash-v0"})


def normalize_openocd_target_config(value: object) -> str | None:
    """Normalize OpenOCD target paths to the canonical target/<file>.cfg form."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("\\", "/")
    lowered = normalized.casefold()
    marker = "/target/"
    index = lowered.rfind(marker)
    if index >= 0:
        return "target/" + normalized[index + len(marker) :]
    if lowered.startswith("tcl/target/"):
        return normalized[4:]
    if lowered.startswith("target/"):
        return normalized
    return normalized


class SiteExecutionRouter:
    """Admit one Job onto one Site and select a handler from IC Support truth.

    Mock remains a workflow simulator and does not create hardware-support
    evidence. Non-Mock execution must resolve an exact ICPN before queueing.
    """

    def __init__(
        self,
        site: SiteConfig,
        interface: BaseInterface,
        resolver: ICSupportResolver | None,
    ) -> None:
        self.site = site
        self.interface = interface
        self.resolver = resolver
        self._generic_handler = ProgrammingOperationHandler(interface)
        self._profile_handlers: dict[str, BaseHandler] = {
            profile_id: ProgrammingOperationHandler(interface)
            for profile_id in SUPPORTED_PROGRAMMING_PROFILES
        }

    @staticmethod
    def _server_owned_metadata(request: JobRequest) -> None:
        if RESOLVED_IC_SUPPORT_METADATA_KEY in request.metadata:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"metadata.{RESOLVED_IC_SUPPORT_METADATA_KEY} is server-owned",
            )

    def _decorate(
        self,
        request: JobRequest,
        *,
        route: dict[str, Any],
    ) -> JobRequest:
        return replace(
            request,
            metadata={
                **request.metadata,
                RESOLVED_IC_SUPPORT_METADATA_KEY: route,
            },
        )

    def _admit_mock(self, request: JobRequest) -> JobRequest:
        return self._decorate(
            request,
            route={
                "mode": MOCK_ROUTE,
                "target": request.target,
                "hardware_support_claimed": False,
                "runtime_ready": True,
            },
        )

    def _resolved_route(self, request: JobRequest) -> tuple[str, dict[str, Any]]:
        if self.resolver is None:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "non-Mock Site has no IC Support resolver",
                context={"site_id": self.site.id, "site_interface": self.site.interface},
            )
        support = self.resolver.resolve_exact(request.target)
        if support is None:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"no evidence-backed IC Support binding for target {request.target!r}",
                context={
                    "site_id": self.site.id,
                    "site_interface": self.site.interface,
                    "target": request.target,
                    "ic_support_state": "unresolved",
                },
            )

        programming_profile_id = support.programming_profile.profile_id
        if programming_profile_id not in SUPPORTED_PROGRAMMING_PROFILES:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"Programming Profile is not execution-routed: {programming_profile_id}",
                context={
                    "site_id": self.site.id,
                    "site_interface": self.site.interface,
                    "target": support.icpn,
                    "programming_profile_id": programming_profile_id,
                },
            )

        return programming_profile_id, support.to_runtime_payload()

    def _admit_openocd(self, request: JobRequest) -> JobRequest:
        programming_profile_id, support_payload = self._resolved_route(request)
        expected_target = normalize_openocd_target_config(
            support_payload["backends"]["openocd"]["target_config"]
        )
        configured_target = normalize_openocd_target_config(self.site.openocd.get("target_cfg"))
        if configured_target is None:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                f"SITE{self.site.id} OpenOCD target_cfg is required",
                context={
                    "site_id": self.site.id,
                    "target": request.target,
                    "expected_target_config": expected_target,
                },
            )
        if expected_target is None or configured_target.casefold() != expected_target.casefold():
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "OpenOCD target_cfg conflicts with resolved IC Support",
                context={
                    "site_id": self.site.id,
                    "target": request.target,
                    "configured_target_config": configured_target,
                    "expected_target_config": expected_target,
                    "programming_profile_id": programming_profile_id,
                },
            )
        return self._decorate(
            request,
            route={
                **support_payload,
                "mode": OPENOCD_ROUTE,
                "selected_programming_profile_id": programming_profile_id,
                "selected_openocd_target_config": configured_target,
                # Phase 3.6 proves deterministic admission/routing only. The
                # current OpenOCD Program/Verify/Read implementation remains
                # hardware-specific and is not promoted to full runtime-ready.
                "runtime_ready": False,
            },
        )

    def _admit_fpga(self, request: JobRequest) -> JobRequest:
        programming_profile_id, support_payload = self._resolved_route(request)
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            "Plasma Native PPU execution is not implemented for the resolved Programming Profile",
            context={
                "site_id": self.site.id,
                "target": request.target,
                "programming_profile_id": programming_profile_id,
                "native_backend_state": support_payload["backends"]["plasma_native"]["state"],
            },
        )

    def admit(self, request: JobRequest) -> JobRequest:
        self._server_owned_metadata(request)
        if self.site.interface == "mock":
            return self._admit_mock(request)
        if self.site.interface == "openocd":
            return self._admit_openocd(request)
        if self.site.interface == "fpga":
            return self._admit_fpga(request)
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            f"unsupported interface for execution routing: {self.site.interface}",
        )

    def handler_for(self, request: JobRequest) -> BaseHandler:
        route = request.metadata.get(RESOLVED_IC_SUPPORT_METADATA_KEY)
        if not isinstance(route, dict):
            raise PlasmaError(
                ErrorCode.INTERNAL_ERROR,
                "Job reached SiteWorker without resolved execution route",
                context={"site_id": self.site.id, "job_id": request.job_id},
            )
        mode = route.get("mode")
        if mode == MOCK_ROUTE:
            return self._generic_handler
        if mode != OPENOCD_ROUTE:
            raise PlasmaError(
                ErrorCode.INTERNAL_ERROR,
                f"unsupported resolved execution route: {mode!r}",
                context={"site_id": self.site.id, "job_id": request.job_id},
            )
        profile_id = route.get("selected_programming_profile_id")
        try:
            return self._profile_handlers[str(profile_id)]
        except KeyError as exc:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"no handler is registered for Programming Profile {profile_id!r}",
                context={"site_id": self.site.id, "job_id": request.job_id},
            ) from exc


class RoutedProgrammingHandler(BaseHandler):
    """Preserve SiteWorker's one-handler contract while routing per Job."""

    def __init__(self, interface: BaseInterface, router: SiteExecutionRouter) -> None:
        super().__init__(interface)
        self.router = router

    async def execute(self, request: JobRequest, stage_callback: StageCallback) -> ExecutionOutput:
        return await self.router.handler_for(request).execute(request, stage_callback)
