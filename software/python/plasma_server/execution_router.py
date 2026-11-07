from __future__ import annotations

from dataclasses import replace
from typing import Any

from plasma_core.config import SiteConfig
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ICSupportResolver, ResolvedICSupport
from plasma_core.models import ExecutionOutput, JobRequest
from plasma_handlers.base import BaseHandler, StageCallback
from plasma_handlers.programming import ProgrammingOperationHandler
from plasma_interfaces.base import BaseInterface
from plasma_interfaces.openocd import OpenOCDInterface, as_program_request
from plasma_interfaces.package_provider import PackageProviderInterface
from plasma_interfaces.openocd_executor import compile_flash_cycle
from plasma_interfaces.compiler_registry import (
    CompilerBinding,
    CompilerRegistry,
    load_operation_admission_projection,
)
from plasma_interfaces.kl25_openocd_plan import KL25OpenOCDPlanCompiler
from plasma_interfaces.openocd_plan import (
    OPENOCD_PLAN_PROGRAMMING_PROFILES,
    OpenOCDPlanCompiler,
    normalize_openocd_target_config,
)


RESOLVED_IC_SUPPORT_METADATA_KEY = "resolved_ic_support"
MOCK_ROUTE = "mock_workflow"
OPENOCD_ROUTE = "openocd"
PLASMA_NATIVE_ROUTE = "plasma_native"
PACKAGE_PROVIDER_ROUTE = "opf_package"
ROUTABLE_PROGRAMMING_PROFILES = OPENOCD_PLAN_PROGRAMMING_PROFILES
STM32_COMPILER_ID = "plasma_interfaces.openocd_plan.OpenOCDPlanCompiler"
KL25_COMPILER_ID = "plasma_interfaces.kl25_openocd_plan.KL25OpenOCDPlanCompiler"
KL25_BACKEND_ID = "nxp-kl25-openocd-backend-v1"
KL25_BACKEND_LOCK_DIGEST = "7628554b4b34a3587688824e95f861bcd95c792699f023e2ae5ad7880196e1c5"


def _default_compiler_registry() -> CompilerRegistry:
    admissions = load_operation_admission_projection()
    stm32_bindings = {
        (row.compiler_id, row.backend_id, row.backend_lock_digest)
        for row in admissions
    }
    if len(stm32_bindings) != 1:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "STM32 compiler admission projection must resolve to one compiler/backend lock",
        )
    compiler_id, backend_id, backend_lock_digest = next(iter(stm32_bindings))
    if compiler_id != STM32_COMPILER_ID:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "STM32 compiler admission projection references an unsupported compiler",
            context={"compiler_id": compiler_id},
        )

    return CompilerRegistry(
        bindings=(
            CompilerBinding(
                compiler_id,
                backend_id,
                backend_lock_digest,
                OpenOCDPlanCompiler(),
            ),
            # Candidate availability only. There is intentionally no KL25
            # Production operation admission in the default runtime registry.
            CompilerBinding(
                KL25_COMPILER_ID,
                KL25_BACKEND_ID,
                KL25_BACKEND_LOCK_DIGEST,
                KL25OpenOCDPlanCompiler(),
            ),
        ),
        admissions=admissions,
    )


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
        compiler_registry: CompilerRegistry | None = None,
    ) -> None:
        self.site = site
        self.interface = interface
        self.resolver = resolver
        self.compiler_registry = (compiler_registry if compiler_registry is not None else
                                  None if isinstance(interface, OpenOCDInterface)
                                  and interface.site_worker_ready else _default_compiler_registry())
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
        # The C-3 OPF flash_cycle uses the selected Active Bundle, not the
        # repository exact-ICPN list or static compiler admission projection.
        if isinstance(self.interface, OpenOCDInterface) and self.interface.site_worker_ready:
            if request.operation is not Operation.FLASH_CYCLE:
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                                  "C-3 supports only flash_cycle")
            return self._decorate(request, route={
                "mode": OPENOCD_ROUTE, "target": request.target,
                "backend_implementation_state": "opf_bundle_c3_site_worker",
                "software_validation_runtime_ready": False,
                "hardware_runtime_ready": True})
        programming_profile_id, support, support_payload = self._resolved_support(request)
        # REST read offsets are relative to main Flash; the canonical compiler
        # only accepts absolute target addresses. Normalize before admission.
        if request.operation is Operation.READ and request.map_data:
            sections = request.map_data.get("sections")
            if isinstance(sections, list):
                flash_start = int(str(support.memory_geometry_profile.data["main_flash_start"]), 0)
                normalized = [
                    {**entry, "address": flash_start + entry["address"]}
                    if isinstance(entry, dict)
                    and type(entry.get("address")) is int
                    and 0 <= entry["address"] < flash_start
                    else entry
                    for entry in sections
                ]
                request = replace(
                    request,
                    map_data={**request.map_data, "sections": normalized},
                )
        openocd = self.interface if isinstance(self.interface, OpenOCDInterface) else None
        target_config = (
            openocd.target_config_for(support)
            if openocd is not None
            else self.site.openocd.get("target_cfg")
        )
        if request.operation is Operation.FLASH_CYCLE:
            # One complete cycle = every component operation must be admitted
            # for this exact ICPN; the plan is composed from the PROGRAM plan.
            selections = {
                operation: self.compiler_registry.select(support.icpn, operation)
                for operation in (
                    Operation.ERASE, Operation.PROGRAM, Operation.VERIFY, Operation.READ
                )
            }
            selection = selections[Operation.PROGRAM]
            plan = compile_flash_cycle(
                selection.compiler,
                support,
                as_program_request(request),
                configured_target_config=target_config,
            )
        else:
            selection = self.compiler_registry.select(support.icpn, request.operation)
            plan = selection.compiler.compile(
                support,
                request,
                configured_target_config=target_config,
            )
        software_validation = openocd is not None and openocd.software_validation_ready
        site_worker = (
            openocd is not None
            and openocd.site_worker_ready
            and request.operation is Operation.FLASH_CYCLE
        )
        return self._decorate(
            request,
            route={
                **support_payload,
                "mode": OPENOCD_ROUTE,
                "selected_programming_profile_id": programming_profile_id,
                "selected_openocd_target_config": plan.target_config,
                "operation_admission_id": selection.admission.operation_admission_id,
                "operation_admission_digest": selection.admission.operation_admission_digest,
                "operation_contract_id": selection.admission.operation_contract_id,
                "operation_contract_digest": selection.admission.operation_contract_digest,
                "compiler_id": selection.admission.compiler_id,
                "backend_id": selection.admission.backend_id,
                "backend_lock_digest": selection.admission.backend_lock_digest,
                "backend_implementation_state": (
                    "c3_site_worker"
                    if site_worker
                    else "host_only_process_injected"
                    if software_validation
                    else "plan_compiled_not_executable"
                ),
                "openocd_execution_plan": plan.to_dict(),
                "software_validation_runtime_ready": software_validation,
                # C-3 owns admission/OpenOCD/SAFE_OFF; it refuses explicitly
                # (ENGINE_NOT_READY, Site sealed, lease) at execution time.
                "hardware_runtime_ready": site_worker,
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
        if self.site.interface == "provider":
            if (not isinstance(self.interface, PackageProviderInterface)
                    or not self.interface.runtime_wired
                    or request.operation is not Operation.FLASH_CYCLE):
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PACKAGE_PROVIDER_NOT_READY")
            return self._decorate(request, route={
                "mode": PACKAGE_PROVIDER_ROUTE,
                "backend_implementation_state": "opf_package_c2",
                "software_validation_runtime_ready": False,
                "hardware_runtime_ready": True,
            })
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
        host_only = (
            route.get("mode") == OPENOCD_ROUTE
            and route.get("software_validation_runtime_ready") is True
        )
        if route.get("hardware_runtime_ready") is not True and not host_only:
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
        if mode in (MOCK_ROUTE, PACKAGE_PROVIDER_ROUTE):
            return self._generic_handler
        host_only = (
            mode == OPENOCD_ROUTE
            and route.get("software_validation_runtime_ready") is True
        )
        if route.get("hardware_runtime_ready") is not True and not host_only:
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
        if isinstance(self.interface, OpenOCDInterface) and self.interface.site_worker_ready:
            return self._generic_handler
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
