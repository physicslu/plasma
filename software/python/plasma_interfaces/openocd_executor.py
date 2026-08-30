from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ResolvedICSupport
from plasma_core.models import JobRequest

from .openocd_plan import OpenOCDExecutionPlan, OpenOCDPlanCompiler


ProcessLauncher = Callable[..., Awaitable[asyncio.subprocess.Process]]
_PLAN_TOKEN_PATTERN = re.compile(r"\$\{PLASMA_[A-Z0-9_]+\}")
_SAFE_ADAPTER_SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9._:+/-]+$")


@dataclass(frozen=True, slots=True)
class OpenOCDExecutionResult:
    stdout: str
    stderr: str
    read_sections: dict[str, bytes]


class OpenOCDPlanExecutor:
    """Materialize and execute one canonical OpenOCD plan in an isolated workspace.

    Phase 3.8 deliberately has no default process launcher. Production runtime
    therefore cannot execute OpenOCD merely because this class exists. Tests
    explicitly inject ``asyncio.create_subprocess_exec`` and point ``executable``
    at a fake OpenOCD process to validate argv, staging, timeout and cleanup.
    """

    def __init__(
        self,
        options: dict[str, Any],
        *,
        process_launcher: ProcessLauncher | None = None,
        compiler: OpenOCDPlanCompiler | None = None,
    ) -> None:
        self.executable = str(options.get("executable", "openocd"))
        self.interface_cfg = options.get("interface_cfg")
        self.target_cfg = options.get("target_cfg")
        self.adapter_serial = options.get("adapter_serial")
        self.work_dir = Path(options.get("work_dir", ".")).resolve()
        self.command_timeout_s = float(options.get("command_timeout_s", 30.0))
        self._process_launcher = process_launcher
        self._compiler = compiler or OpenOCDPlanCompiler()

    def _require_software_validation_launcher(self) -> ProcessLauncher:
        if self._process_launcher is None:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD compiled-plan executor has no software-validation process launcher",
                context={"hardware_runtime_ready": False},
            )
        return self._process_launcher

    @staticmethod
    def _validate_argv_text(value: object, *, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, f"OpenOCD {field} is required")
        if "\x00" in value or "\n" in value or "\r" in value:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"OpenOCD {field} contains invalid characters")
        return value

    def _validate_runtime_options(self) -> None:
        self._validate_argv_text(self.executable, field="executable")
        self._validate_argv_text(self.interface_cfg, field="interface_cfg")
        self._validate_argv_text(self.target_cfg, field="target_cfg")
        if not self.work_dir.is_dir():
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "OpenOCD work_dir must exist and be a directory",
                context={"work_dir": str(self.work_dir)},
            )
        if not math.isfinite(self.command_timeout_s) or self.command_timeout_s <= 0:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "OpenOCD command_timeout_s must be a positive finite number",
            )
        if self.adapter_serial is not None:
            serial = str(self.adapter_serial)
            if not serial or _SAFE_ADAPTER_SERIAL_PATTERN.fullmatch(serial) is None:
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    "OpenOCD adapter_serial contains unsupported command characters",
                )

    def _canonical_plan(
        self,
        support: ResolvedICSupport,
        request: JobRequest,
    ) -> OpenOCDExecutionPlan:
        return self._compiler.compile(
            support,
            request,
            configured_target_config=self.target_cfg,
        )

    @staticmethod
    def _validate_plan_identity(
        supplied: OpenOCDExecutionPlan,
        canonical: OpenOCDExecutionPlan,
    ) -> None:
        if supplied != canonical:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "OpenOCD execution plan does not match canonical profile-derived plan",
                context={
                    "target": canonical.icpn,
                    "operation": canonical.operation.value,
                    "programming_profile_id": canonical.programming_profile_id,
                    "memory_geometry_profile_id": canonical.memory_geometry_profile_id,
                },
            )

    @staticmethod
    def _tcl_path(path: Path) -> str:
        normalized = path.resolve().as_posix()
        if "{" in normalized or "}" in normalized or "\x00" in normalized or "\n" in normalized or "\r" in normalized:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD staging path cannot be represented safely")
        return "{" + normalized + "}"

    @staticmethod
    def _render_commands(
        plan: OpenOCDExecutionPlan,
        substitutions: dict[str, str],
    ) -> list[str]:
        rendered: list[str] = []
        for command in plan.commands:
            if not isinstance(command, str) or not command or "\x00" in command or "\n" in command or "\r" in command:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD plan contains an invalid command")
            resolved = command
            for token, replacement in substitutions.items():
                resolved = resolved.replace(token, replacement)
            unresolved = _PLAN_TOKEN_PATTERN.findall(resolved)
            if unresolved:
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    "OpenOCD plan contains unresolved artifact tokens",
                    context={"tokens": sorted(set(unresolved))},
                )
            rendered.append(resolved)
        return rendered

    @staticmethod
    def _stage_artifacts(
        workspace: Path,
        plan: OpenOCDExecutionPlan,
        request: JobRequest,
    ) -> tuple[dict[str, str], list[tuple[Path, str, int]]]:
        substitutions: dict[str, str] = {}
        outputs: list[tuple[Path, str, int]] = []
        seen_sections: set[str] = set()

        for index, artifact in enumerate(plan.artifacts):
            if artifact.token in substitutions:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD plan reuses an artifact token")
            if _PLAN_TOKEN_PATTERN.fullmatch(artifact.token) is None:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD plan contains an invalid artifact token")
            if artifact.size_bytes <= 0:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD plan artifact size must be positive")

            if artifact.direction == "input":
                if artifact.role != "programming_image":
                    raise PlasmaError(ErrorCode.CONFIG_INVALID, "unsupported OpenOCD input artifact role")
                if request.image_ref is not None or not request.image:
                    raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "OpenOCD input artifact requires inline image bytes")
                if artifact.size_bytes != len(request.image):
                    raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD input artifact size does not match Job image")
                digest = hashlib.sha256(request.image).hexdigest()
                if artifact.sha256 != digest:
                    raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD input artifact SHA-256 does not match Job image")
                path = workspace / f"input-{index:03d}.bin"
                path.write_bytes(request.image)
                if os.name != "nt":
                    path.chmod(0o600)
            elif artifact.direction == "output":
                if artifact.role != "read_output":
                    raise PlasmaError(ErrorCode.CONFIG_INVALID, "unsupported OpenOCD output artifact role")
                if not isinstance(artifact.section_name, str) or not artifact.section_name:
                    raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD read artifact requires section_name")
                if artifact.section_name in seen_sections:
                    raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD plan contains duplicate read section names")
                seen_sections.add(artifact.section_name)
                path = workspace / f"output-{index:03d}.bin"
                outputs.append((path, artifact.section_name, artifact.size_bytes))
            else:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "unsupported OpenOCD artifact direction")

            substitutions[artifact.token] = OpenOCDPlanExecutor._tcl_path(path)

        return substitutions, outputs

    def _arguments(self, commands: list[str]) -> list[str]:
        arguments = [
            self.executable,
            "-f",
            str(self.interface_cfg),
            "-f",
            str(self.target_cfg),
        ]
        if self.adapter_serial is not None:
            arguments.extend(["-c", f"adapter serial {self.adapter_serial}"])
        for command in commands:
            arguments.extend(["-c", command])
        return arguments

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.kill()
        except ProcessLookupError:
            return
        await process.wait()

    async def execute(
        self,
        plan: OpenOCDExecutionPlan,
        support: ResolvedICSupport,
        request: JobRequest,
    ) -> OpenOCDExecutionResult:
        """Execute only a canonical plan through an explicitly injected launcher."""
        launcher = self._require_software_validation_launcher()
        self._validate_runtime_options()
        canonical = self._canonical_plan(support, request)
        self._validate_plan_identity(plan, canonical)

        with tempfile.TemporaryDirectory(prefix="plasma-openocd-plan-") as temp_root:
            workspace = Path(temp_root)
            substitutions, outputs = self._stage_artifacts(workspace, plan, request)
            commands = self._render_commands(plan, substitutions)
            arguments = self._arguments(commands)

            try:
                process = await launcher(
                    *arguments,
                    cwd=self.work_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.command_timeout_s,
                )
            except asyncio.CancelledError:
                if "process" in locals():
                    await self._terminate_process(process)
                raise
            except TimeoutError as exc:
                if "process" in locals():
                    await self._terminate_process(process)
                raise PlasmaError(
                    ErrorCode.OPERATION_TIMEOUT,
                    "OpenOCD compiled plan timed out",
                    recoverable=True,
                    original_exception=exc,
                ) from exc
            except FileNotFoundError as exc:
                raise PlasmaError(
                    ErrorCode.INTERFACE_FAILURE,
                    f"OpenOCD executable not found: {self.executable}",
                    original_exception=exc,
                ) from exc
            except OSError as exc:
                raise PlasmaError(
                    ErrorCode.INTERFACE_FAILURE,
                    "OpenOCD compiled-plan process could not be launched",
                    original_exception=exc,
                ) from exc

            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            if process.returncode != 0:
                raise PlasmaError(
                    ErrorCode.INTERFACE_FAILURE,
                    f"OpenOCD compiled plan exited with code {process.returncode}",
                    recoverable=True,
                    context={
                        "return_code": process.returncode,
                        "stdout": stdout[-4000:],
                        "stderr": stderr[-4000:],
                    },
                )

            read_sections: dict[str, bytes] = {}
            for path, section_name, expected_size in outputs:
                if not path.is_file():
                    raise PlasmaError(
                        ErrorCode.INTERFACE_FAILURE,
                        "OpenOCD did not produce an expected read artifact",
                        context={"section_name": section_name, "expected_size_bytes": expected_size},
                    )
                payload = path.read_bytes()
                if len(payload) != expected_size:
                    raise PlasmaError(
                        ErrorCode.INTERFACE_FAILURE,
                        "OpenOCD read artifact size does not match compiled plan",
                        context={
                            "section_name": section_name,
                            "expected_size_bytes": expected_size,
                            "actual_size_bytes": len(payload),
                        },
                    )
                read_sections[section_name] = payload

            return OpenOCDExecutionResult(
                stdout=stdout,
                stderr=stderr,
                read_sections=read_sections,
            )
