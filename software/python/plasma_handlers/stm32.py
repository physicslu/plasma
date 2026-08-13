from __future__ import annotations

import time
from typing import Any

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import ExecutionOutput, JobRequest

from .base import BaseHandler, StageCallback


class STM32F103Handler(BaseHandler):
    TARGET_NAME = "STM32F103C8T6"

    async def _stage(
        self,
        name: str,
        callback: StageCallback,
        operation: Any,
        *,
        stage_index: int,
        stage_count: int,
        byte_progress: bool = False,
    ) -> Any:
        common = {"stage_index": stage_index, "stage_count": stage_count}
        await callback(name, "started", {**common, "stage_progress_percent": 0.0})
        started = time.monotonic()

        async def report(done: int, total: int) -> None:
            stage_percent = 100.0 if total <= 0 else min(100.0, max(0.0, done * 100.0 / total))
            fields: dict[str, Any] = {
                **common,
                "stage_progress_percent": round(stage_percent, 1),
                "progress_percent": round((stage_index + stage_percent / 100.0) * 100.0 / stage_count, 1),
            }
            if byte_progress:
                fields.update(bytes_done=done, bytes_total=total)
            await callback(name, "progress", fields)

        try:
            result = await operation(report)
        except BaseException as exc:
            await callback(
                name,
                "failed",
                {
                    **common,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "error": str(exc),
                },
            )
            raise
        await callback(
            name,
            "completed",
            {
                **common,
                "stage_progress_percent": 100.0,
                "progress_percent": round((stage_index + 1) * 100.0 / stage_count, 1),
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return result

    async def execute(self, request: JobRequest, stage_callback: StageCallback) -> ExecutionOutput:
        operation = request.operation
        if operation is Operation.ERASE:
            await self._stage(
                "erase",
                stage_callback,
                lambda progress: self.interface.erase(progress),
                stage_index=0,
                stage_count=1,
            )
            return ExecutionOutput(details={"stages": ["erase"]})

        if operation is Operation.PROGRAM:
            if not request.firmware:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "program requires non-empty firmware")
            await self._stage(
                "erase",
                stage_callback,
                lambda progress: self.interface.erase(progress),
                stage_index=0,
                stage_count=3,
            )
            await self._stage(
                "program",
                stage_callback,
                lambda progress: self.interface.program(request.firmware, 0, progress),
                stage_index=1,
                stage_count=3,
                byte_progress=True,
            )
            await self._stage(
                "verify",
                stage_callback,
                lambda progress: self.interface.verify(request.firmware, 0, progress),
                stage_index=2,
                stage_count=3,
                byte_progress=True,
            )
            return ExecutionOutput(
                details={"stages": ["erase", "program", "verify"], "bytes_programmed": len(request.firmware)}
            )

        if operation is Operation.VERIFY:
            if not request.firmware:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "verify requires non-empty reference firmware")
            await self._stage(
                "verify",
                stage_callback,
                lambda progress: self.interface.verify(request.firmware, 0, progress),
                stage_index=0,
                stage_count=1,
                byte_progress=True,
            )
            return ExecutionOutput(details={"stages": ["verify"], "bytes_verified": len(request.firmware)})

        if operation is Operation.READ:
            sections = self._read_sections(request.map_data)
            output: dict[str, bytes] = {}
            for index, section in enumerate(sections):
                name = str(section["name"])
                address = int(section["address"])
                length = int(section["length"])
                output[name] = await self._stage(
                    f"read_{name}",
                    stage_callback,
                    lambda progress, address=address, length=length: self.interface.read(
                        address, length, progress
                    ),
                    stage_index=index,
                    stage_count=len(sections),
                    byte_progress=True,
                )
            return ExecutionOutput(
                read_sections=output,
                details={"stages": [f"read_{item['name']}" for item in sections]},
            )

        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            f"operation '{operation.value}' is not handled by STM32F103Handler",
        )

    @staticmethod
    def _read_sections(map_data: dict[str, Any]) -> list[dict[str, Any]]:
        sections = map_data.get("sections") if map_data else None
        if sections is None:
            sections = [{"name": "section0", "address": 0, "length": 256}]
        if not isinstance(sections, list) or not sections:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "map.sections must be a non-empty array")
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(sections):
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
            if address < 0 or length <= 0:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"map section {index} range is invalid")
            normalized.append({"name": name, "address": address, "length": length})
        return normalized
