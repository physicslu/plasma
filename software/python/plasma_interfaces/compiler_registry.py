from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ResolvedICSupport
from plasma_core.models import JobRequest

from .openocd_plan import OpenOCDExecutionPlan


HEX64 = re.compile(r"^[0-9a-f]{64}$")


class PlanCompiler(Protocol):
    def compile(
        self,
        support: ResolvedICSupport,
        request: JobRequest,
        *,
        configured_target_config: object,
    ) -> OpenOCDExecutionPlan: ...


@dataclass(frozen=True, slots=True)
class CompilerBinding:
    compiler_id: str
    backend_id: str
    backend_lock_digest: str
    compiler: PlanCompiler


@dataclass(frozen=True, slots=True)
class OperationAdmission:
    target_icpn: str
    request_operation: str
    state: str
    operation_admission_id: str
    operation_admission_digest: str
    operation_contract_id: str
    operation_contract_digest: str
    canonical_admission_digest: str
    backend_id: str
    backend_lock_digest: str
    compiler_id: str
    hardware_runtime_ready: bool


@dataclass(frozen=True, slots=True)
class CompilerSelection:
    compiler: PlanCompiler
    admission: OperationAdmission


class CompilerRegistry:
    """Select a plan compiler only through an admitted operation binding."""

    def __init__(
        self,
        bindings: tuple[CompilerBinding, ...] = (),
        admissions: tuple[OperationAdmission, ...] = (),
    ) -> None:
        self._bindings: dict[str, CompilerBinding] = {}
        self._admissions: dict[tuple[str, str], OperationAdmission] = {}
        for binding in bindings:
            self.register(binding)
        for admission in admissions:
            self.admit(admission)

    def register(self, binding: CompilerBinding) -> None:
        self._validate_binding(binding)
        if binding.compiler_id in self._bindings:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"duplicate compiler_id: {binding.compiler_id}")
        self._bindings[binding.compiler_id] = binding

    def admit(self, admission: OperationAdmission) -> None:
        self._validate_admission(admission)
        key = (admission.target_icpn.casefold(), admission.request_operation)
        if key in self._admissions:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "duplicate operation admission",
                context={"target": admission.target_icpn, "operation": admission.request_operation},
            )
        self._admissions[key] = admission

    def select(self, target_icpn: str, operation: Operation) -> CompilerSelection:
        admission = self._admissions.get((target_icpn.casefold(), operation.name))
        if admission is None or admission.state != "ADMITTED":
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                "operation has no admitted compiler binding",
                context={"target": target_icpn, "operation": operation.name},
            )
        binding = self._bindings.get(admission.compiler_id)
        if binding is None:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "admitted operation references an unregistered compiler",
                context={"compiler_id": admission.compiler_id},
            )
        if (
            binding.backend_id != admission.backend_id
            or binding.backend_lock_digest != admission.backend_lock_digest
        ):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "admitted operation does not match the registered backend lock",
                context={
                    "compiler_id": admission.compiler_id,
                    "backend_id": admission.backend_id,
                    "backend_lock_digest": admission.backend_lock_digest,
                },
            )
        return CompilerSelection(binding.compiler, admission)

    @staticmethod
    def _validate_binding(binding: CompilerBinding) -> None:
        if not binding.compiler_id or not binding.backend_id:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler and backend IDs are required")
        if HEX64.fullmatch(binding.backend_lock_digest) is None:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "backend lock digest must be lowercase SHA-256")
        if not callable(getattr(binding.compiler, "compile", None)):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "registered compiler must provide compile()")

    @staticmethod
    def _validate_admission(admission: OperationAdmission) -> None:
        text_fields = (
            admission.target_icpn,
            admission.request_operation,
            admission.operation_admission_id,
            admission.operation_contract_id,
            admission.backend_id,
            admission.compiler_id,
        )
        if not all(isinstance(value, str) and value for value in text_fields):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "operation admission identity is incomplete")
        digest_fields = (
            admission.operation_admission_digest,
            admission.operation_contract_digest,
            admission.canonical_admission_digest,
            admission.backend_lock_digest,
        )
        if not all(HEX64.fullmatch(value) is not None for value in digest_fields):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "operation admission digest is invalid")
        if admission.state not in {"ADMITTED", "BLOCKED", "INCOMPLETE"}:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "operation admission state is invalid")
        if type(admission.hardware_runtime_ready) is not bool:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "hardware_runtime_ready must be boolean")
