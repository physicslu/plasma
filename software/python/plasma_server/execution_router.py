from __future__ import annotations

from dataclasses import replace
from typing import Any

from plasma_core.config import SiteConfig
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ICSupportResolver, ResolvedICSupport
from plasma_core.models import ExecutionOutput, JobRequest
from plasma_handlers.base import BaseHandler, StageCallback
from plasma_handlers.programming import ProgrammingOperationHandler
from plasma_interfaces.base import BaseInterface
from plasma_interfaces.openocd_plan import (
    OPENOCD_PLAN_PROGRAMMING_PROFILES,
    OpenOCDPlanCompiler,
    normalize_openocd_target_config,
)


RESOLVED_IC_SUPPORT_METADATA_KEY = "resolved_ic_support"
MOCK_ROUTE = "mock_workflow"
OPENOCD_ROUTE = "openocd"
PLASMA_NATIVE_ROUTE = "plasma_native"
ROUTABLE_PROGRAMMING_PROFILES = OPENOCD_PLAN_PROGRAMMING_PROFILES


class SiteExecutionRouter:
    """Resolve one Job route, compile backend plans, then gate real execution.

    Mock is a workflow simulator and does not create hardware-support evidence.
    Non-Mock routing must resolve an exact ICPN and backend identity before the
    Job can be considered for queue admission. Phase 3.7 adds deterministic
    OpenOCD dry-run plan compilation while keeping real hardware execution
    closed until an executor is independently proven runtime-ready.
    """

    def __init__(
        self,
        site: SiteConfig,
        interface: BaseInterface,
        resolver: ICSupportResolver | None,
        openocd_plan_compiler: OpenOCDPlanCompiler | None = None,
    ) -> None:
        self.site = site
        self.interface = interface
        self.resolver = resolver
        self.openocd_plan_compiler = openocd_plan_compiler or OpenOCDPlanCompiler()
        self._generic_handler = ProgrammingOperationHandler(interface)
        self._profile_handlers: dict[str, BaseHandler] = {
            profile_id: ProgrammingOperationHandler(interface)
            for profile_id in ROUTABLE_PROGRAMMING_PROFILES
        }

    @staticmethod
    def _server_owned_metadata(request: JobRequest) -> None:
        if RESOLVED_IC_SUPPORT_METADATA_KEY in request.metadata:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"metadata.{RESOLVED_IC_SUPPORT_METADATA_KEY} is server-owned",
            )

    @staticmethod
    def _route_payload(request: JobRequest) -> dict[str, Any]:
        route = request.metadata.get(RESOLVED_IC_SUPPORT_METADATA_KEY)
        if not isinstance(route, dict):
            raise PlasmaError(
                ErrorCode.INTERNAL_ERROR,
                "request does not contain a server-resolved IC Support route",
                context={"job_id": request.job_id, "site_id": request.site_id},
            )
        return route

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

    def _resolve_mock(self, request: JobRequest) -> JobRequest:
        return self._decorate(
            request,
            route={
                "mode": MOCK_ROUTE,
                "target": request.target,
                "hardware_support_claimed": False,
                "workflow_runtime_ready": True,
                "hardware_runtime_ready": False,
            },
        )

    def _resolved_support(
        self,
        request: JobRequest,
    ) -> tuple[str, ResolvedICSupport, dict[str, Any]]:
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
        if programming_profile_id not in ROUTABLE_PROGRAMMING_PROFILES:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"Programming Profile has no execution route: {programming_profile_id}",
                context={
                    "site_id": self.site.id,
                    "site_interface": self.site.interface,
                    "target": support.icpn,
                    "programming_profile_id": programming_profile_id,
                },
            )

        return programming_profile_id, support, support.to_runtime_payload()

    def _resolve_openocd(self, request: JobRequest) -> JobRequest:
        programming_profile_id, support, support_payload = self._resolved_support(request)
        plan = self.openocd_plan_compiler.compile(
            support,
            request,
            configured_target_config=self.site.openocd.get("target_cfg"),
        )
        return self._decorate(
            request,
            route={
                **support_payload,
                "mode": OPENOCD_ROUTE,
                "selected_programming_profile_id": programming_profile_id,
                "selected_openocd_target_config": plan.target_config,
                "backend_implementation_state": "plan_compiled_not_executable",
                "openocd_execution_plan": plan.to_dict(),
                "hardware_runtime_ready": False,
            },
        )

    def _resolve_fpga(self, request: JobRequest) -> JobRequest:
        programming_profile_id, _support, support_payload = self._resolved_support(request)
        return self._decorate(
            request,
            route={
                **support_payload,
                "mode": PLASMA_NATIVE_ROUTE,
                "selected_programming_profile_id": programming_profile_id,
                "backend_implementation_state": "not_implemented",
                "hardware_runtime_ready": False,
            },
        )

    def resolve_route(self, request: JobRequest) -> JobRequest:
        """Resolve server-owned target/profile/backend identity without execution."""
        self._server_owned_metadata(request)
        if self.site.interface == "mock":
            return self._resolve_mock(request)
        if self.site.interface == "openocd":
            return self._resolve_openocd(request)
        if self.site.interface == "fpga":
            return self._resolve_fpga(request)
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            f"unsupported interface for execution routing: {self.site.interface}",
        )

    def admit(self, request: JobRequest) -> JobRequest:
        """Admit only routes whose selected execution implementation is ready."""
        resolved = self.resolve_route(request)
        route = self._route_payload(resolved)
        if route.get("mode") == MOCK_ROUTE:
            return resolved
        if route.get("hardware_runtime_ready") is not True:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "resolved hardware backend is not runtime-ready",
                context={
                    "site_id": self.site.id,
                    "site_interface": self.site.interface,
                    "target": request.target,
                    "route_mode": route.get("mode"),
                    "programming_profile_id": route.get("selected_programming_profile_id"),
                    "backend_implementation_state": route.get("backend_implementation_state"),
                },
            )
        return resolved

    def handler_for(self, request: JobRequest) -> BaseHandler:
        route = self._route_payload(request)
        mode = route.get("mode")
        if mode == MOCK_ROUTE:
            return self._generic_handler
        if route.get("hardware_runtime_ready") is not True:
            raise PlasmaError(
                ErrorCode.INTERNAL_ERROR,
                "non-ready hardware route reached SiteWorker",
                context={"site_id": self.site.id, "job_id": request.job_id, "route_mode": mode},
            )
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
