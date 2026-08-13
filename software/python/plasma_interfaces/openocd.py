from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from plasma_core.errors import ErrorCode, PlasmaError

from .base import BaseInterface, ProgressCallback


class OpenOCDInterface(BaseInterface):
    """OpenOCD process boundary.

    This v0.1 class validates per-channel configuration and process/error
    handling. Target-specific command templates require hardware validation.
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

    async def _run(self, commands: list[str]) -> tuple[str, str]:
        self._require_configured()
        arguments = [self.executable, "-f", str(self.interface_cfg), "-f", str(self.target_cfg)]
        if self.adapter_serial:
            arguments.extend(["-c", f"adapter serial {self.adapter_serial}"])
        for command in commands:
            arguments.extend(["-c", command])
        arguments.extend(["-c", "shutdown"])
        try:
            process = await asyncio.create_subprocess_exec(
                *arguments,
                cwd=self.work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.command_timeout_s)
        except FileNotFoundError as exc:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                f"OpenOCD executable not found: {self.executable}",
                original_exception=exc,
            ) from exc
        except TimeoutError as exc:
            if "process" in locals() and process.returncode is None:
                process.kill()
                await process.wait()
            raise PlasmaError(
                ErrorCode.OPERATION_TIMEOUT,
                "OpenOCD command timed out",
                recoverable=True,
                original_exception=exc,
            ) from exc
        decoded_stdout = stdout.decode(errors="replace")
        decoded_stderr = stderr.decode(errors="replace")
        if process.returncode != 0:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                f"OpenOCD exited with code {process.returncode}",
                recoverable=True,
                context={
                    "return_code": process.returncode,
                    "stdout": decoded_stdout[-4000:],
                    "stderr": decoded_stderr[-4000:],
                },
            )
        return decoded_stdout, decoded_stderr

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        if progress:
            await progress(0, 100)
        await self._run(["init", "reset halt", "flash erase_address 0x08000000 0x10000"])
        if progress:
            await progress(100, 100)

    async def program(
        self,
        firmware: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        raise PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "binary staging for OpenOCD requires hardware-specific configuration",
        )

    async def verify(
        self,
        firmware: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        raise PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "binary staging for OpenOCD requires hardware-specific configuration",
        )

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        raise PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "OpenOCD read-back requires hardware-specific configuration",
        )

    async def safe_shutdown(self) -> None:
        if self._configured:
            try:
                await self._run(["init", "reset run"])
            except PlasmaError:
                pass
