from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ICSupportResolver, get_default_ic_support_resolver
from plasma_core.models import JobRequest

from .base import BaseInterface, ProgressCallback
from .openocd_executor import OpenOCDPlanExecutor, ProcessLauncher, compile_flash_cycle
from .openocd_plan import OpenOCDPlanCompiler, normalize_openocd_target_config
from .site_worker_c3 import (
    DEFAULT_IMAGE_ROOT,
    C3FlashProfile,
    SiteWorkerControlClient,
)


class OpenOCDInterface(BaseInterface):
    """Per-Site OpenOCD interface with two explicit execution backends.

    * ``site_worker_socket`` (Z2 product path): the complete Flash cycle runs
      through the local Stage C-3 Site Worker, which owns Site admission and
      the PS-local OpenOCD. Only ``flash_cycle`` is offered; the target config
      and Flash geometry come from the selected verified Bundle Profile.
    * an injected ``process_launcher`` (Host-only software validation with
      fake processes).

    Without either, the interface cannot execute anything.
    """

    def __init__(
        self,
        options: dict[str, Any],
        *,
        process_launcher: ProcessLauncher | None = None,
        resolver: ICSupportResolver | None = None,
    ) -> None:
        self.executable = str(options.get("executable", "openocd"))
        self.interface_cfg = options.get("interface_cfg")
        self.target_cfg = options.get("target_cfg")
        self.adapter_serial = options.get("adapter_serial")
        self.work_dir = Path(options.get("work_dir", ".")).resolve()
        self.command_timeout_s = float(options.get("command_timeout_s", 30.0))
        self._configured = bool(self.interface_cfg and self.target_cfg)
        socket_path = options.get("site_worker_socket")
        self._site_worker = (
            SiteWorkerControlClient(Path(str(socket_path))) if socket_path else None
        )
        self.normalized_image_root = Path(
            str(options.get("normalized_image_root", DEFAULT_IMAGE_ROOT))
        )
        self._process_launcher = process_launcher
        self._resolver = resolver
        self._compiler = OpenOCDPlanCompiler()
        self._executor = OpenOCDPlanExecutor(
            options, process_launcher=process_launcher, compiler=self._compiler
        )
        self._request: JobRequest | None = None
        # Installed by the trusted Runtime composition, never by Job metadata.
        self.opf_flash_executor: Callable[..., Awaitable[dict[str, Any]]] | None = None
        self.opf_flash_preflight: Callable[..., dict[str, Any]] | None = None
        self._runtime_job: tuple[str, dict[str, Any] | None, float] | None = None

    def bind_runtime_job(self, job_id: str, active_asset_set: dict[str, Any] | None,
                         deadline_monotonic: float) -> None:
        self._runtime_job = (job_id, deepcopy(active_asset_set), deadline_monotonic)

    @property
    def software_validation_ready(self) -> bool:
        """Readiness is an internal injected capability, never a config key."""
        return self._configured and self._process_launcher is not None

    @property
    def site_worker_ready(self) -> bool:
        """Configured for the C-3 Site Worker product path (no fake launcher)."""
        return self._site_worker is not None and self._process_launcher is None

    def _require_ready(self) -> None:
        if not (self.software_validation_ready or self.site_worker_ready):
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD hardware runtime is not enabled; use the software-validation compiled-plan executor only",
            )

    def _support(self, target: str):
        resolver = self._resolver or get_default_ic_support_resolver()
        return resolver.require_exact(target)

    def target_config_for(self, support) -> object:
        """Site-configured target cfg (cross-checked by the compiler) or, on
        the C-3 path, the exact-ICPN IC Support selection itself."""
        if self.target_cfg:
            return self.target_cfg
        return support.openocd_target_config if self.site_worker_ready else None

    def prepare_request(self, request: JobRequest) -> None:
        self._require_ready()
        if self.site_worker_ready and request.operation is not Operation.FLASH_CYCLE:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                "the C-3 Site Worker path offers only the complete flash_cycle operation",
                context={"operation": request.operation.value},
            )
        if self.site_worker_ready:
            if self.opf_flash_preflight is None or self._runtime_job is None:
                raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "OPF_RUNTIME_NOT_WIRED")
            try:
                self.opf_flash_preflight(
                    active_asset_set=self._runtime_job[1], target=request.target,
                    site_id=request.site_id, image_size=request.image_size,
                    provider=request.metadata.get("provider"), profile=request.metadata.get("profile"))
            except (ValueError, OSError, KeyError, TypeError) as exc:
                raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                                  "OPF_FLASH_DENIED:" + str(exc)) from exc
            self._request = request
            return
        # Non-C3 software validation keeps its separate compiled-plan contract.
        support = self._support(request.target)
        if request.operation is Operation.FLASH_CYCLE:
            compile_flash_cycle(
                self._compiler, support, as_program_request(request),
                configured_target_config=self.target_config_for(support),
            )
        else:
            self._compiler.compile(
                support, request, configured_target_config=self.target_config_for(support)
            )
        self._request = request

    def _prepared(self, operation: Operation) -> JobRequest:
        self._require_ready()
        request = self._request
        if request is None or request.operation is not operation:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD operation has no matching prepared Job",
            )
        return request

    async def _execute(self, request: JobRequest):
        support = self._support(request.target)
        plan = self._compiler.compile(
            support, request, configured_target_config=self.target_cfg
        )
        return await self._executor.execute(plan, support, request)

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        request = self._prepared(Operation.ERASE)
        await self._execute(request)
        if progress:
            await progress(1, 1)

    async def program(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        request = self._prepared(Operation.PROGRAM)
        if address != 0 or image != request.image:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "OpenOCD Job image or address mismatch")
        await self._execute(request)
        if progress:
            await progress(len(image), len(image))

    async def verify(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        request = self._prepared(Operation.VERIFY)
        if address != 0 or image != request.image:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "OpenOCD Job image or address mismatch")
        await self._execute(request)
        if progress:
            await progress(len(image), len(image))

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        request = self._prepared(Operation.READ)
        # The generic handler uses (0, 256) for an omitted section. Map that
        # default to the target's real main-Flash base; explicit map sections
        # continue to be compiled and range-checked against the IC geometry.
        if address == 0 and not request.map_data:
            support = self._support(request.target)
            address = int(support.memory_geometry_profile.data["main_flash_start"], 0)
        section_request = replace(
            request,
            map_data={"sections": [{"name": "readback", "address": address, "length": length}]},
        )
        result = await self._execute(section_request)
        payload = result.read_sections["readback"]
        if progress:
            await progress(len(payload), len(payload))
        return payload

    async def flash_cycle(
        self,
        image: bytes,
        progress: ProgressCallback | None = None,
    ) -> dict[str, object]:
        request = self._prepared(Operation.FLASH_CYCLE)
        if image != request.image or not image:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "OpenOCD Job image mismatch")
        if self.site_worker_ready:
            assert self._site_worker is not None
            if (self.opf_flash_executor is None or self._runtime_job is None
                    or self._runtime_job[0] != request.job_id):
                raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED,
                                  "OPF_RUNTIME_NOT_WIRED")
            evidence = await self.opf_flash_executor(
                self._site_worker, request=request,
                active_asset_set=self._runtime_job[1],
                job_deadline_monotonic=self._runtime_job[2],
                image_root=self.normalized_image_root,
            )
        else:
            support = self._support(request.target)
            program = as_program_request(request)
            plan = compile_flash_cycle(
                self._compiler, support, program,
                configured_target_config=self.target_config_for(support),
            )
            result = await self._executor.execute(plan, support, program, flash_cycle=True)
            readback = result.read_sections["flash_readback"]
            evidence = {
                "result": "PASS",
                "backend": "host_only_injected_process",
                "bytes_verified": len(readback),
                "readback_sha256": hashlib.sha256(readback).hexdigest(),
            }
        if progress:
            await progress(len(image), len(image))
        return evidence

    async def safe_shutdown(self) -> None:
        # OpenOCDPlanExecutor owns its subprocess and awaits its exit/kill.
        self._request = None
        self._runtime_job = None


def as_program_request(request: JobRequest) -> JobRequest:
    """The Flash cycle is compiled from the canonical PROGRAM plan (the
    source-locked compiler has no FLASH_CYCLE operation)."""
    return replace(request, operation=Operation.PROGRAM)


def c3_flash_profile(support) -> C3FlashProfile:
    """Exact-ICPN Flash profile for the C-3 Site Worker, from IC Support only."""
    target = normalize_openocd_target_config(support.openocd_target_config)
    data = support.memory_geometry_profile.data
    try:
        profile = C3FlashProfile(
            icpn=support.icpn,
            target_config=str(target),
            flash_base=int(str(data["main_flash_start"]), 0),
            flash_size=int(data["main_flash_size_bytes"]),
            erase_granularity=int(data["erase_granularity_bytes"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            "IC Support has no complete Flash geometry for the C-3 Flash cycle",
            context={"target": support.icpn},
        ) from exc
    if target is None or not target.startswith("target/"):
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            "IC Support has no OpenOCD target config for the C-3 Flash cycle",
            context={"target": support.icpn},
        )
    return profile
