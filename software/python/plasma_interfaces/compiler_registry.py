from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Protocol

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ResolvedICSupport
from plasma_core.models import JobRequest

from .openocd_plan import OpenOCDExecutionPlan


HEX64 = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_ADMISSION_PROJECTION_RESOURCE = "stm32f103c-compiler-admission-projection-v1.json"


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


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_operation_admission_projection(value: Mapping[str, Any]) -> tuple[OperationAdmission, ...]:
    """Parse a content-addressed projection produced from generic-valid admission packages.

    Runtime deliberately consumes this small compiled projection rather than
    importing benchmark/migration code. CI is responsible for rebuilding the
    source admission packages, running the generic validator, and proving that
    this projection is an exact projection of their admitted operation rows.
    """

    root = dict(value)
    expected_keys = {
        "schema_version",
        "artifact_type",
        "artifact_id",
        "source_governance",
        "targets",
        "artifact_digest",
    }
    if set(root) != expected_keys:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission projection shape is invalid")
    if root.get("schema_version") != "1.0.0":
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission projection schema is unsupported")
    if root.get("artifact_type") != "compiler_admission_projection":
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission projection type is invalid")
    if root.get("source_governance") != "vendor-neutral-admission-v1":
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission projection governance is invalid")

    digest = root.get("artifact_digest")
    unsigned = {key: item for key, item in root.items() if key != "artifact_digest"}
    if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission projection digest is invalid")
    if _canonical_digest(unsigned) != digest:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission projection digest mismatch")

    targets = root.get("targets")
    if not isinstance(targets, list) or not targets:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission projection has no targets")

    admissions: list[OperationAdmission] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission target projection must be an object")
        if set(target) != {
            "target_icpn",
            "operation_admission_id",
            "operation_admission_digest",
            "operations",
        }:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission target projection shape is invalid")
        target_icpn = target.get("target_icpn")
        admission_id = target.get("operation_admission_id")
        admission_digest = target.get("operation_admission_digest")
        operations = target.get("operations")
        if not isinstance(target_icpn, str) or not target_icpn:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission target ICPN is invalid")
        if not isinstance(admission_id, str) or not admission_id:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission artifact ID is invalid")
        if not isinstance(admission_digest, str) or HEX64.fullmatch(admission_digest) is None:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission artifact digest is invalid")
        if not isinstance(operations, list) or not operations:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission target has no operations")

        for row in operations:
            if not isinstance(row, dict):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission operation must be an object")
            if set(row) != {
                "request_operation",
                "state",
                "operation_contract_id",
                "operation_contract_digest",
                "canonical_admission_digest",
                "backend_id",
                "backend_lock_digest",
                "compiler_id",
                "hardware_runtime_ready",
            }:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission operation shape is invalid")
            admission = OperationAdmission(
                target_icpn=target_icpn,
                request_operation=row.get("request_operation"),
                state=row.get("state"),
                operation_admission_id=admission_id,
                operation_admission_digest=admission_digest,
                operation_contract_id=row.get("operation_contract_id"),
                operation_contract_digest=row.get("operation_contract_digest"),
                canonical_admission_digest=row.get("canonical_admission_digest"),
                backend_id=row.get("backend_id"),
                backend_lock_digest=row.get("backend_lock_digest"),
                compiler_id=row.get("compiler_id"),
                hardware_runtime_ready=row.get("hardware_runtime_ready"),
            )
            CompilerRegistry._validate_admission(admission)
            if admission.state != "ADMITTED":
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    "runtime compiler projection may contain only ADMITTED operations",
                )
            if admission.hardware_runtime_ready is not False:
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    "runtime compiler projection must remain hardware-runtime blocked",
                )
            key = (admission.target_icpn.casefold(), admission.request_operation)
            if key in seen:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "duplicate projected operation admission")
            seen.add(key)
            admissions.append(admission)

    return tuple(admissions)


def load_operation_admission_projection(
    resource_name: str = DEFAULT_ADMISSION_PROJECTION_RESOURCE,
) -> tuple[OperationAdmission, ...]:
    try:
        raw = files("plasma_interfaces").joinpath(resource_name).read_text(encoding="utf-8")
        value = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "compiler admission projection could not be loaded",
            original_exception=exc,
        ) from exc
    if not isinstance(value, dict):
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "compiler admission projection root must be an object")
    return parse_operation_admission_projection(value)


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
        if not all(isinstance(value, str) and HEX64.fullmatch(value) is not None for value in digest_fields):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "operation admission digest is invalid")
        if admission.state not in {"ADMITTED", "BLOCKED", "INCOMPLETE"}:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "operation admission state is invalid")
        if type(admission.hardware_runtime_ready) is not bool:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "hardware_runtime_ready must be boolean")
