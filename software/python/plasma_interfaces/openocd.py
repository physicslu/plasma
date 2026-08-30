from __future__ import annotations

from pathlib import Path
from typing import Any

from plasma_core.errors import ErrorCode, PlasmaError

from .base import BaseInterface, ProgressCallback


class OpenOCDInterface(BaseInterface):
    """OpenOCD Site configuration boundary.

    Phase 3.8 intentionally keeps this interface non-executable. OpenOCD
    process execution is isolated in ``OpenOCDPlanExecutor`` and that executor
    has no default process launcher. Production routing therefore remains
    fail-closed until a later hardware-validation phase explicitly promotes the
    compiled-plan executor into the real runtime.
    """

    def __init__(self, options: dict[str, Any]) -> None:
        self.executable = str(options.get("executable", "openocd"))
        self.interface_cfg = options.get("interface_cfg")
        self.target_cfg = options.get("target_cfg")
        self.adapter_serial = options.get("adapter_serial")
        self.work_dir = Path(options.get("work_dir", ".")).resolve()
        self.command_timeout_s = float(options.get("command_timeout_s", 30.0))
        self._configured = bool(self.interface_cfg and self.target_cfg)

    def _require_configured(self) -> None:
        if not self._configured:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD interface_cfg and target_cfg are required",
            )

    @staticmethod
    def _raise_hardware_runtime_not_ready() -> None:
        raise PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "OpenOCD hardware runtime is not enabled; use the software-validation compiled-plan executor only",
        )

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        self._raise_hardware_runtime_not_ready()

    async def program(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._raise_hardware_runtime_not_ready()

    async def verify(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._raise_hardware_runtime_not_ready()

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        self._raise_hardware_runtime_not_ready()

    async def safe_shutdown(self) -> None:
        # No subprocess is allowed through this interface in Phase 3.8.
        # A real hardware shutdown/reset policy belongs to the later validated
        # runtime executor, not to a latent direct-process escape hatch.
        return None
