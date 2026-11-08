"""Select one PPU Programming Job execution route with existing SiteWorker/lease.

The legacy exact-ICPN CompilerRegistry admission route is retired.
OpenOCD Plan Compiler, Flash Geometry and qualification remain independent.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from plasma_core.config import SiteConfig
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import ExecutionOutput, JobRequest
from plasma_handlers.base import BaseHandler, StageCallback
from plasma_handlers.programming import ProgrammingOperationHandler
from plasma_interfaces.base import BaseInterface
from plasma_interfaces.openocd import OpenOCDInterface
from plasma_interfaces.package_provider import PackageProviderInterface, TrustedProviderAction


ROUTE_METADATA_KEY = "execution_route"
MOCK_ROUTE = "mock_workflow"
OPENOCD_ROUTE = "openocd"
PACKAGE_PROVIDER_ROUTE = "opf_package"


class SiteExecutionRouter:
    """Choose an already qualified PPU execution capability per authorized Job.

    No Runtime compiler registry, Catalog allowlist, or fallback. Package selection
    originates from the trusted root-only Package Action, not SiteConfig.
    """

    def __init__(self, site: SiteConfig, interface: BaseInterface,
                 package_interface: PackageProviderInterface | None = None) -> None:
        self.site = site
        self.interface = interface
        self.package_interface = package_interface

    @staticmethod
    def _server_owned_metadata(request: JobRequest) -> None:
        if ROUTE_METADATA_KEY in request.metadata or "resolved_ic_support" in request.metadata:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT,
                              "programming execution route metadata is server-owned")

    @staticmethod
    def _route_payload(request: JobRequest) -> dict[str, Any]:
        route = request.metadata.get(ROUTE_METADATA_KEY)
        if not isinstance(route, dict):
            raise PlasmaError(ErrorCode.INTERNAL_ERROR,
                              "Job has no server-selected execution route",
                              context={"job_id": request.job_id, "site_id": request.site_id})
        return route

    @staticmethod
    def _decorate(request: JobRequest, *, route: dict[str, Any]) -> JobRequest:
        return replace(request, metadata={**request.metadata, ROUTE_METADATA_KEY: route})

    def resolve_route(self, request: JobRequest, *,
                      trusted_provider: TrustedProviderAction | None = None) -> JobRequest:
        self._server_owned_metadata(request)
        if trusted_provider is not None:
            if (not isinstance(trusted_provider, TrustedProviderAction)
                    or self.site.interface == "mock"
                    or self.package_interface is None
                    or not self.package_interface.runtime_wired
                    or request.operation is not Operation.FLASH_CYCLE):
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PACKAGE_PROVIDER_NOT_READY")
            return self._decorate(request, route={
                "mode": PACKAGE_PROVIDER_ROUTE,
                "backend_implementation_state": "opf_package_c2",
                "hardware_runtime_ready": True,
            })
        if self.site.interface == "mock":
            return self._decorate(request, route={
                "mode": MOCK_ROUTE, "target": request.target,
                "hardware_support_claimed": False,
                "workflow_runtime_ready": True,
                "hardware_runtime_ready": False,
            })
        if (self.site.interface == "openocd"
                and isinstance(self.interface, OpenOCDInterface)
                and self.interface.site_worker_ready):
            if request.operation is not Operation.FLASH_CYCLE:
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                                  "C-3 OpenOCD permits only flash_cycle")
            return self._decorate(request, route={
                "mode": OPENOCD_ROUTE, "target": request.target,
                "backend_implementation_state": "opf_bundle_c3_site_worker",
                "hardware_runtime_ready": True,
            })
        raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                          "NO_QUALIFIED_JOB_PROVIDER",
                          context={"site_id": self.site.id, "site_interface": self.site.interface})

    def admit(self, request: JobRequest, *,
              trusted_provider: TrustedProviderAction | None = None) -> JobRequest:
        return self.resolve_route(request, trusted_provider=trusted_provider)

    def interface_for(self, request: JobRequest) -> BaseInterface:
        mode = self._route_payload(request).get("mode")
        if mode == MOCK_ROUTE and self.site.interface == "mock":
            return self.interface
        if (mode == OPENOCD_ROUTE and self.site.interface == "openocd"
                and isinstance(self.interface, OpenOCDInterface)
                and self.interface.site_worker_ready):
            return self.interface
        if mode == PACKAGE_PROVIDER_ROUTE and self.package_interface is not None:
            return self.package_interface
        raise PlasmaError(ErrorCode.INTERNAL_ERROR, "invalid server-selected Job route",
                          context={"job_id": request.job_id, "site_id": request.site_id})

    def handler_for(self, request: JobRequest) -> BaseHandler:
        return ProgrammingOperationHandler(self.interface_for(request))


class RoutedProgrammingHandler(BaseHandler):
    """Preserve SiteWorker's one-handler contract; select the interface per Job."""

    def __init__(self, interface: BaseInterface, router: SiteExecutionRouter) -> None:
        super().__init__(interface)
        self.router = router

    def interface_for(self, request: JobRequest) -> BaseInterface:
        return self.router.interface_for(request)

    async def execute(self, request: JobRequest, stage_callback: StageCallback) -> ExecutionOutput:
        return await self.router.handler_for(request).execute(request, stage_callback)
