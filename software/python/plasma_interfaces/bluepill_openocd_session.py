"""Explicit one-Site OpenOCD/remote-bitbang session wrapper, off by default.

This is a scoped subprocess/socket *transport* for the canonical plan executor;
it does not decide electrical admission, configure Linux MMIO, create a Site,
install a bitstream or promote a backend. Only a trusted external Site owner
may inject an already qualified WordPort and an independent admission hook.

Host-only use with VirtualSWDTarget can prove a *real process* was launched
and then correctly failed to program unsupported virtual Flash.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import tempfile
from typing import Callable

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import ResolvedICSupport
from plasma_core.models import JobRequest

from .bluepill_remote_bitbang import RemoteBitbangSWD, WordPort, serve_local_unix_once
from .openocd_executor import OpenOCDExecutionResult, OpenOCDPlanExecutor
from .openocd_plan import OpenOCDExecutionPlan


class BluepillOpenOCDSessionExecutor:
    """Job-scoped UNIX socket, ordered SWD WordPort and real OpenOCD process.

    No default constructor or Production interface factory creates this object.
    Requires explicit path, port factory and single fixed Site base.
    """

    BASE = 0x40008000

    def __init__(
        self,
        *,
        executable: str | Path,
        scripts_root: str | Path,
        adapter_config: str | Path,
        work_dir: str | Path,
        word_port_factory: Callable[[], WordPort],
        command_timeout_s: float = 12.0,
        socket_timeout_s: float = 8.0,
    ) -> None:
        if not callable(word_port_factory):
            raise ValueError("Explicit qualified WordPort factory required")
        if not 0 < socket_timeout_s <= 120:
            raise ValueError("Socket timeout must be bounded")
        if not 0 < command_timeout_s <= 120:
            raise ValueError("Process timeout must be bounded")
        self.executable = Path(executable).resolve()
        self.scripts_root = Path(scripts_root).resolve()
        self.adapter_config = Path(adapter_config).resolve()
        self.work_dir = Path(work_dir).resolve()
        self.word_port_factory = word_port_factory
        self.command_timeout_s = float(command_timeout_s)
        self.socket_timeout_s = float(socket_timeout_s)
        self.last_command_count = 0
        self.last_socket_path: Path | None = None
        self.last_process_argv: tuple[str, ...] = ()
        self._busy = False

    def _validate_files(self) -> None:
        if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "Pinned OpenOCD executable not available")
        if not self.scripts_root.is_dir() or not self.adapter_config.is_file():
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "OpenOCD script/config missing")
        if not self.work_dir.is_dir():
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "OpenOCD working directory missing")

    async def execute(
        self, plan: OpenOCDExecutionPlan, support: ResolvedICSupport, request: JobRequest
    ) -> OpenOCDExecutionResult:
        if self._busy:
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "Site 1 OpenOCD session already active")
        if request.site_id != 1 or support.icpn != "STM32F103C8T6":
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "Unexpected Blue Pill session target/Site")
        self._validate_files()
        self._busy = True
        self.last_command_count = 0
        try:
            with tempfile.TemporaryDirectory(prefix="plasma-bluepill-rbb-") as root:
                private = Path(root)
                private.chmod(0o700)
                socket_path = private / "swd.sock"
                self.last_socket_path = socket_path
                bridge = RemoteBitbangSWD(self.word_port_factory(), base=self.BASE)
                serving = asyncio.create_task(asyncio.to_thread(
                    serve_local_unix_once, socket_path, bridge,
                    idle_timeout_s=self.socket_timeout_s,
                ))
                try:
                    loop = asyncio.get_running_loop()
                    deadline = loop.time() + min(self.socket_timeout_s, 5.0)
                    while not socket_path.is_socket():
                        if serving.done():
                            await serving
                            raise PlasmaError(ErrorCode.INTERFACE_FAILURE, "SWD bridge terminated before listening")
                        if loop.time() >= deadline:
                            raise PlasmaError(ErrorCode.CONNECTION_TIMEOUT, "SWD bridge socket startup timed out")
                        await asyncio.sleep(0.01)

                    async def launch(*argv, **kwargs):
                        # OpenOCD must select/register remote_bitbang through
                        # its adapter -f BEFORE the 'remote_bitbang host'
                        # subcommand is interpreted. Keep the canonical
                        # target -f after that, and do not accept alternative
                        # adapter/target commands from a plan or caller.
                        if (len(argv) < 5
                                or tuple(argv[1:3]) != ("-f", str(self.adapter_config))
                                or tuple(argv[3:5]) != ("-f", "target/stm32f1x.cfg")
                                or argv[0] != str(self.executable)):
                            raise PlasmaError(
                                ErrorCode.CONFIG_INVALID,
                                "Blue Pill OpenOCD argv violates pinned adapter/target order",
                            )
                        args = (
                            str(self.executable),
                            "-s", str(self.scripts_root),
                            *argv[1:3],
                            "-c", f"remote_bitbang host {socket_path}",
                            *argv[3:],
                        )
                        self.last_process_argv = tuple(args)
                        return await asyncio.create_subprocess_exec(*args, **kwargs)

                    executor = OpenOCDPlanExecutor(
                        {
                            "executable": str(self.executable),
                            "interface_cfg": str(self.adapter_config),
                            "target_cfg": "target/stm32f1x.cfg",
                            "work_dir": str(self.work_dir),
                            "command_timeout_s": self.command_timeout_s,
                        },
                        process_launcher=launch,
                    )
                    return await executor.execute(plan, support, request)
                finally:
                    # Completion/Q, EOF/error, and non-start all converge on a
                    # bounded close. With real hardware, owner supervision
                    # remains responsible for physical safe-off/recovery.
                    try:
                        self.last_command_count = await asyncio.wait_for(
                            asyncio.shield(serving),
                            timeout=self.socket_timeout_s + 1.0,
                        )
                    except asyncio.CancelledError:
                        # Preserve Job cancellation; never turn it into a
                        # success or an unrelated transport exception.
                        if not serving.done():
                            serving.cancel()
                        raise
                    except Exception as exc:
                        if not serving.done():
                            serving.cancel()
                        # Even if bridge.close() ran after EOF/timeout, that
                        # does not prove a valid OpenOCD 'Q' handshake.
                        # A failed transport must never yield Job success.
                        raise PlasmaError(
                            ErrorCode.INTERFACE_FAILURE,
                            "SWD bridge ended without a confirmed clean session; "
                            "external recovery may be required",
                        ) from exc
        finally:
            self._busy = False
