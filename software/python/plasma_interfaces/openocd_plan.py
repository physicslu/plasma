from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ResolvedICSupport
from plasma_core.models import JobRequest


OPENOCD_PLAN_SCHEMA_VERSION = "0.1.0"
OPENOCD_PLAN_PROGRAMMING_PROFILES = frozenset({"stm32f1-medium-density-flash-v0"})
IMAGE_ARTIFACT_TOKEN = "${PLASMA_IMAGE_BIN}"
READ_ARTIFACT_TOKEN_TEMPLATE = "${PLASMA_READ_%03d_BIN}"


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


def _hex32(value: int) -> str:
    return f"0x{value:08X}"


def _require(condition: bool, message: str, *, context: dict[str, Any] | None = None) -> None:
    if not condition:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, message, context=context or {})


def _parse_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError as exc:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"{field} must be an integer or base-prefixed integer string",
                original_exception=exc,
            ) from exc
    raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{field} must be an integer")


@dataclass(frozen=True, slots=True)
class OpenOCDPlanArtifact:
    role: str
    token: str
    direction: str
    size_bytes: int
    sha256: str | None = None
    section_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": self.role,
            "token": self.token,
            "direction": self.direction,
            "size_bytes": self.size_bytes,
        }
        if self.sha256 is not None:
            payload["sha256"] = self.sha256
        if self.section_name is not None:
            payload["section_name"] = self.section_name
        return payload


@dataclass(frozen=True, slots=True)
class OpenOCDExecutionPlan:
    icpn: str
    operation: Operation
    programming_profile_id: str
    memory_geometry_profile_id: str
    target_config: str
    main_flash_start: int
    main_flash_size_bytes: int
    erase_granularity_bytes: int
    program_granularity_bytes: int
    commands: tuple[str, ...]
    artifacts: tuple[OpenOCDPlanArtifact, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OPENOCD_PLAN_SCHEMA_VERSION,
            "plan_kind": "openocd_dry_run",
            "icpn": self.icpn,
            "operation": self.operation.value,
            "programming_profile_id": self.programming_profile_id,
            "memory_geometry_profile_id": self.memory_geometry_profile_id,
            "target_config": self.target_config,
            "memory": {
                "main_flash_start": _hex32(self.main_flash_start),
                "main_flash_size_bytes": self.main_flash_size_bytes,
                "main_flash_end": _hex32(self.main_flash_start + self.main_flash_size_bytes - 1),
                "erase_granularity_bytes": self.erase_granularity_bytes,
                "program_granularity_bytes": self.program_granularity_bytes,
            },
            "commands": list(self.commands),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "plan_only": True,
            "hardware_runtime_ready": False,
        }


@dataclass(frozen=True, slots=True)
class _MainFlashGeometry:
    start: int
    size_bytes: int
    end: int
    page_size_bytes: int
    page_count: int
    erase_granularity_bytes: int
    program_granularity_bytes: int


class OpenOCDPlanCompiler:
    """Compile evidence-backed IC Support knowledge into a non-executable OpenOCD plan.

    The compiler produces deterministic command text and artifact requirements
    only. It never starts OpenOCD, creates staging files, or changes hardware
    runtime readiness.
    """

    def compile(
        self,
        support: ResolvedICSupport,
        request: JobRequest,
        *,
        configured_target_config: object,
    ) -> OpenOCDExecutionPlan:
        if request.target.casefold() != support.icpn.casefold():
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "Job target does not match ResolvedICSupport ICPN",
                context={"request_target": request.target, "resolved_icpn": support.icpn},
            )

        programming_profile_id = support.programming_profile.profile_id
        if programming_profile_id not in OPENOCD_PLAN_PROGRAMMING_PROFILES:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"Programming Profile has no OpenOCD plan compiler: {programming_profile_id}",
                context={"programming_profile_id": programming_profile_id, "target": support.icpn},
            )

        expected_target = normalize_openocd_target_config(support.openocd_target_config)
        configured_target = normalize_openocd_target_config(configured_target_config)
        if configured_target is None:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD target_cfg is required for plan compilation",
                context={"target": support.icpn, "expected_target_config": expected_target},
            )
        if expected_target is None or configured_target.casefold() != expected_target.casefold():
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "OpenOCD target_cfg conflicts with resolved IC Support",
                context={
                    "target": support.icpn,
                    "configured_target_config": configured_target,
                    "expected_target_config": expected_target,
                    "programming_profile_id": programming_profile_id,
                },
            )

        geometry = self._geometry(support)
        commands, artifacts = self._operation_plan(support, request, geometry)
        return OpenOCDExecutionPlan(
            icpn=support.icpn,
            operation=request.operation,
            programming_profile_id=programming_profile_id,
            memory_geometry_profile_id=support.memory_geometry_profile.profile_id,
            target_config=configured_target,
            main_flash_start=geometry.start,
            main_flash_size_bytes=geometry.size_bytes,
            erase_granularity_bytes=geometry.erase_granularity_bytes,
            program_granularity_bytes=geometry.program_granularity_bytes,
            commands=tuple(commands),
            artifacts=tuple(artifacts),
        )

    @staticmethod
    def _geometry(support: ResolvedICSupport) -> _MainFlashGeometry:
        data = support.memory_geometry_profile.data
        start = _parse_int(data.get("main_flash_start"), field="memory.main_flash_start")
        size = _parse_int(data.get("main_flash_size_bytes"), field="memory.main_flash_size_bytes")
        end = _parse_int(data.get("main_flash_end"), field="memory.main_flash_end")
        page_size = _parse_int(data.get("page_size_bytes"), field="memory.page_size_bytes")
        page_count = _parse_int(data.get("page_count"), field="memory.page_count")
        erase_granularity = _parse_int(
            data.get("erase_granularity_bytes"), field="memory.erase_granularity_bytes"
        )
        geometry_program_granularity = _parse_int(
            data.get("program_granularity_bytes"), field="memory.program_granularity_bytes"
        )
        profile_program_granularity = _parse_int(
            support.programming_profile.data.get("program_granularity_bytes"),
            field="programming.program_granularity_bytes",
        )

        _require(start >= 0, "main Flash start must be non-negative")
        _require(size > 0, "main Flash size must be positive")
        _require(page_size > 0 and page_count > 0, "page geometry must be positive")
        _require(erase_granularity > 0, "erase granularity must be positive")
        _require(geometry_program_granularity > 0, "program granularity must be positive")
        _require(
            end == start + size - 1,
            "main Flash end does not match start + size - 1",
            context={"start": _hex32(start), "size_bytes": size, "end": _hex32(end)},
        )
        _require(
            page_size * page_count == size,
            "page geometry does not cover the declared main Flash size",
            context={"page_size_bytes": page_size, "page_count": page_count, "size_bytes": size},
        )
        _require(
            size % erase_granularity == 0,
            "main Flash size is not aligned to erase granularity",
            context={"size_bytes": size, "erase_granularity_bytes": erase_granularity},
        )
        _require(
            geometry_program_granularity == profile_program_granularity,
            "Programming Profile and Memory Geometry disagree on program granularity",
            context={
                "programming_profile_bytes": profile_program_granularity,
                "memory_geometry_bytes": geometry_program_granularity,
            },
        )
        return _MainFlashGeometry(
            start=start,
            size_bytes=size,
            end=end,
            page_size_bytes=page_size,
            page_count=page_count,
            erase_granularity_bytes=erase_granularity,
            program_granularity_bytes=geometry_program_granularity,
        )

    def _operation_plan(
        self,
        support: ResolvedICSupport,
        request: JobRequest,
        geometry: _MainFlashGeometry,
    ) -> tuple[list[str], list[OpenOCDPlanArtifact]]:
        prefix = ["init", "reset init"]
        suffix = ["shutdown"]

        if request.operation is Operation.ERASE:
            return (
                prefix
                + [f"flash erase_address {_hex32(geometry.start)} {_hex32(geometry.size_bytes)}"]
                + suffix,
                [],
            )

        if request.operation in {Operation.PROGRAM, Operation.VERIFY}:
            if not request.has_image:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"{request.operation.value} requires a non-empty Programming Image",
                )
            if request.image_ref is not None:
                raise PlasmaError(
                    ErrorCode.OPERATION_UNSUPPORTED,
                    "OpenOCD dry-run planning does not accept execution image references",
                    context={"scheme": request.image_ref.scheme},
                )
            if request.image_size > geometry.size_bytes:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Programming Image exceeds resolved main Flash capacity",
                    context={
                        "image_size_bytes": request.image_size,
                        "main_flash_size_bytes": geometry.size_bytes,
                        "target": support.icpn,
                    },
                )
            artifact = OpenOCDPlanArtifact(
                role="programming_image",
                token=IMAGE_ARTIFACT_TOKEN,
                direction="input",
                size_bytes=request.image_size,
                sha256=request.image_sha256,
            )
            verb = "flash write_image" if request.operation is Operation.PROGRAM else "flash verify_image"
            command = f"{verb} {IMAGE_ARTIFACT_TOKEN} {_hex32(geometry.start)} bin"
            return prefix + [command] + suffix, [artifact]

        if request.operation is Operation.READ:
            sections = self._read_sections(request, geometry)
            commands = list(prefix)
            artifacts: list[OpenOCDPlanArtifact] = []
            for index, section in enumerate(sections):
                token = READ_ARTIFACT_TOKEN_TEMPLATE % index
                commands.append(
                    f"dump_image {token} {_hex32(section['address'])} {_hex32(section['length'])}"
                )
                artifacts.append(
                    OpenOCDPlanArtifact(
                        role="read_output",
                        token=token,
                        direction="output",
                        size_bytes=section["length"],
                        section_name=section["name"],
                    )
                )
            return commands + suffix, artifacts

        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            f"operation {request.operation.value!r} has no OpenOCD execution-plan compiler",
        )

    @staticmethod
    def _read_sections(
        request: JobRequest,
        geometry: _MainFlashGeometry,
    ) -> list[dict[str, int | str]]:
        raw_sections = request.map_data.get("sections") if request.map_data else None
        if raw_sections is None:
            raw_sections = [
                {
                    "name": "main_flash_head",
                    "address": geometry.start,
                    "length": min(256, geometry.size_bytes),
                }
            ]
        if not isinstance(raw_sections, list) or not raw_sections:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "map.sections must be a non-empty array")

        sections: list[dict[str, int | str]] = []
        for index, item in enumerate(raw_sections):
            if not isinstance(item, dict):
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"map section {index} must be an object")
            try:
                name = str(item.get("name", f"section{index}"))
                address = int(item["address"])
                length = int(item["length"])
            except (KeyError, TypeError, ValueError) as exc:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"map section {index} has invalid address or length",
                    original_exception=exc,
                ) from exc
            if not name:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"map section {index} name must not be empty")
            if address < geometry.start or length <= 0:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"map section {index} is outside resolved main Flash",
                    context={"address": _hex32(max(address, 0)), "length": length},
                )
            section_end = address + length - 1
            if section_end > geometry.end:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"map section {index} exceeds resolved main Flash",
                    context={
                        "address": _hex32(address),
                        "length": length,
                        "main_flash_end": _hex32(geometry.end),
                    },
                )
            sections.append({"name": name, "address": address, "length": length})
        return sections
