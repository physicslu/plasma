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
from plasma_interfaces.compiler_registry import (
    CompilerBinding,
    CompilerRegistry,
    OperationAdmission,
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
ROUTABLE_PROGRAMMING_PROFILES = OPENOCD_PLAN_PROGRAMMING_PROFILES
STM32_COMPILER_ID = "plasma_interfaces.openocd_plan.OpenOCDPlanCompiler"
STM32_BACKEND_ID = "stm32f103c-openocd-backend-v1"
STM32_BACKEND_LOCK_DIGEST = "041644e5e7203c0d1b679d0799d2136b1ce89c398cb5686395753e73998f4411"
KL25_COMPILER_ID = "plasma_interfaces.kl25_openocd_plan.KL25OpenOCDPlanCompiler"
KL25_BACKEND_ID = "nxp-kl25-openocd-backend-v1"
KL25_BACKEND_LOCK_DIGEST = "7628554b4b34a3587688824e95f861bcd95c792699f023e2ae5ad7880196e1c5"


def _default_compiler_registry() -> CompilerRegistry:
    contract_digests = {
        "READ": "0a073d9c5ec716cc77c6b5f25c1e8af972866124ca747758d4cf96cc2ebbed55",
        "VERIFY": "bce2403bc5132c6d7c0ccbd23fcbdda7098b8d99a1286739ddce03452c17675c",
        "PROGRAM": "124d2ceb2eefc249cb79a40f5435082d1688845e4479f1412beb05505a721d4c",
        "ERASE": "4754a708c498fbf0e2972f77589122746cbd27a71371320517ee4ec4d50f1730",
    }
    targets = {
        "STM32F103C8T6": (
            "stm32f103c-stm32f103c8t6-operation-admission-v1",
            "6d8a4df4d16fdac95d15274b1215f2f70ca576e7511e952e8348797190e05e28",
            "186e24dd768343e9e924a661573ae6fc2da6c86028c37ed876b7fdab3244ef56",
        ),
        "STM32F103CBT6": (
            "stm32f103c-stm32f103cbt6-operation-admission-v1",
            "5499d74d2c7ba1246a473ce40f66590d92743797f0d3358f190669d0768b4f13",
            "24bb3fa0e4245186d92b02b93bc2bd49f9eea9d8a0e3bb787d0bbb78e38d7b01",
        ),
    }
    admissions = tuple(
        OperationAdmission(
            target_icpn=target,
            request_operation=operation,
            state="ADMITTED",
            operation_admission_id=admission_id,
            operation_admission_digest=admission_digest,
            operation_contract_id=f"stm32f103c-operation-contract-{operation.lower()}-v1",
            operation_contract_digest=contract_digests[operation],
            canonical_admission_digest=canonical_digest,
            backend_id=STM32_BACKEND_ID,
            backend_lock_digest=STM32_BACKEND_LOCK_DIGEST,
            compiler_id=STM32_COMPILER_ID,
            hardware_runtime_ready=False,
        )
        for target, (admission_id, admission_digest, canonical_digest) in targets.items()
        for operation in contract_digests
    )
    return CompilerRegistry(
        bindings=(
            CompilerBinding(STM32_COMPILER_ID, STM32_BACKEND_ID, STM32_BACKEND_LOCK_DIGEST, OpenOCDPlanCompiler()),
            CompilerBinding(KL25_COMPILER_ID, KL25_BACKEND_ID, KL25_BACKEND_LOCK_DIGEST, KL25OpenOCDPlanCompiler()),
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
        self.compiler_registry = compiler_registry or _default_compiler_registry()
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
        selection = self.compiler_registry.select(support.icpn, request.operation)
        plan = selection.compiler.compile(
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
                "operation_admission_id": selection.admission.operation_admission_id,
                "operation_admission_digest": selection.admission.operation_admission_digest,
                "operation_contract_id": selection.admission.operation_contract_id,
                "operation_contract_digest": selection.admission.operation_contract_digest,
                "compiler_id": selection.admission.compiler_id,
                "backend_id": selection.admission.backend_id,
                "backend_lock_digest": selection.admission.backend_lock_digest,
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
