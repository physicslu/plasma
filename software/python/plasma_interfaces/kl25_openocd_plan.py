from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest

from .openocd_plan import (
    IMAGE_ARTIFACT_TOKEN,
    OpenOCDExecutionPlan,
    OpenOCDPlanArtifact,
    OpenOCDPlanCompiler,
    _hex32,
    _require,
)


KL25_PROGRAMMING_PROFILE_ID = "nxp-kl25-ftfa-programming-v0"
KL25_MEMORY_GEOMETRY_PROFILE_ID = "nxp-mkl25z128-128k-v0"
KL25_TARGET_CONFIG = "target/kl25.cfg"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_backend_lock() -> dict[str, Any]:
    path = _repo_root() / "data/ic-support/benchmarks/nxp-kl25/backend-implementation-lock.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    digest = value.get("lock_digest")
    payload = {k: v for k, v in value.items() if k != "lock_digest"}
    actual = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    _require(digest == actual, "KL25 backend implementation lock digest mismatch")
    return value


class KL25OpenOCDPlanCompiler(OpenOCDPlanCompiler):
    """Software-only compiler for the explicitly admitted KL25 operation subset."""

    def compile(self, support: Any, request: JobRequest, *, configured_target_config: object) -> OpenOCDExecutionPlan:
        lock = load_backend_lock()
        _require(support.programming_profile.profile_id == KL25_PROGRAMMING_PROFILE_ID, "unsupported KL25 Programming Profile")
        _require(support.memory_geometry_profile.profile_id == KL25_MEMORY_GEOMETRY_PROFILE_ID, "unsupported KL25 Memory Geometry Profile")
        _require(support.openocd_target_config == KL25_TARGET_CONFIG, "KL25 target config binding mismatch")
        _require(configured_target_config == KL25_TARGET_CONFIG, "configured KL25 target config mismatch")
        if request.target.casefold() != support.icpn.casefold():
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Job target does not match KL25 support")
        geometry = self._geometry(support)
        constraints = lock["admitted_constraints"]
        commands: list[str] = ["init", "reset init"]
        artifacts: list[OpenOCDPlanArtifact] = []
        if request.operation is Operation.READ:
            for index, section in enumerate(self._read_sections(request, geometry)):
                token = f"${{PLASMA_READ_{index:03d}_BIN}}"
                commands.append(f"dump_image {token} {_hex32(int(section['address']))} {_hex32(int(section['length']))}")
                artifacts.append(OpenOCDPlanArtifact("read_output", token, "output", int(section["length"]), section_name=str(section["name"])))
        elif request.operation is Operation.VERIFY:
            start = self._image_start(request, geometry)
            artifact = self._image_artifact(request, geometry.end - start + 1)
            commands.append(f"flash verify_image {IMAGE_ARTIFACT_TOKEN} {_hex32(start)} bin")
            artifacts.append(artifact)
        elif request.operation is Operation.PROGRAM:
            start = self._image_start(request, geometry)
            artifact = self._image_artifact(request, geometry.end - start + 1)
            _require(start % int(constraints["program_start_alignment_bytes"]) == 0, "PROGRAM start violates backend alignment")
            self._reject_fcf_intersection(start, request.image_size, constraints)
            commands.append(f"flash write_image {IMAGE_ARTIFACT_TOKEN} {_hex32(start)} bin")
            artifacts.append(artifact)
        elif request.operation is Operation.ERASE:
            address = request.map_data.get("address")
            length = request.map_data.get("length")
            _require(type(address) is int and type(length) is int, "ERASE_SECTOR requires integer address and length")
            _require(length == geometry.erase_granularity_bytes and address % length == 0, "ERASE_SECTOR must name one exact aligned sector")
            _require(geometry.start <= address and address + length - 1 <= geometry.end, "ERASE_SECTOR outside main Flash")
            fcf_sector = int(constraints["flash_configuration_field_sector_start"], 0)
            _require(address != fcf_sector, "erase of Flash Configuration Field sector is not admitted")
            commands.append(f"flash erase_address {_hex32(address)} {_hex32(length)}")
        else:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "operation is outside frozen KL25 Software Executor scope")
        commands.append("shutdown")
        return OpenOCDExecutionPlan(support.icpn, request.operation, KL25_PROGRAMMING_PROFILE_ID, KL25_MEMORY_GEOMETRY_PROFILE_ID, KL25_TARGET_CONFIG, geometry.start, geometry.size_bytes, geometry.erase_granularity_bytes, geometry.program_granularity_bytes, tuple(commands), tuple(artifacts))

    @staticmethod
    def _image_artifact(request: JobRequest, capacity: int) -> OpenOCDPlanArtifact:
        _require(request.has_image and request.image_ref is None, f"{request.operation.value} requires inline Programming Image")
        _require(request.image_size <= capacity, "Programming Image exceeds KL25 main Flash")
        return OpenOCDPlanArtifact("programming_image", IMAGE_ARTIFACT_TOKEN, "input", request.image_size, sha256=request.image_sha256)

    @staticmethod
    def _image_start(request: JobRequest, geometry: Any) -> int:
        start = request.map_data.get("address", geometry.start)
        _require(type(start) is int, f"{request.operation.value} address must be an integer")
        _require(geometry.start <= start <= geometry.end, f"{request.operation.value} address outside main Flash")
        return start

    @staticmethod
    def _reject_fcf_intersection(start: int, size: int, constraints: dict[str, Any]) -> None:
        fcf_start = int(constraints["flash_configuration_field_start"], 0)
        fcf_end = fcf_start + int(constraints["flash_configuration_field_size_bytes"])
        _require(start + size <= fcf_start or start >= fcf_end, "Flash Configuration Field programming is not admitted")
