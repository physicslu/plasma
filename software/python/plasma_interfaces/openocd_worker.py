from __future__ import annotations

import asyncio
import math
import os
import socket
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from plasma_core.errors import ErrorCode, PlasmaError

from .openocd_rpc import OpenOCDRpcClient


ProcessLauncher = Callable[..., Awaitable[asyncio.subprocess.Process]]
PortAllocator = Callable[[], int]


def allocate_loopback_port() -> int:
    """Reserve an ephemeral loopback port long enough to learn its number.

    OpenOCD does not accept a pre-bound socket from Plasma, so there is an
    unavoidable close-to-bind race. OpenOCDWorker contains that race with
    bounded start retries and never falls back to a non-loopback bind.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass(frozen=True, slots=True)
class OpenOCDWorkerStatus:
    site_id: int
    running: bool
    pid: int | None
    rpc_host: str
    rpc_port: int | None
    generation: int
    hardware_runtime_ready: bool = False


class OpenOCDWorker:
    """Supervise one isolated OpenOCD process and its Tcl RPC connection.

    This worker qualifies only the OpenOCD process-control plane. It does not
    claim a validated SWD/JTAG adapter, target power/reset path, FPGA PL path, or
    real-IC programming capability.
    """

    RECOVERABLE_RPC_CODES = {
        ErrorCode.CONNECTION_FAILED,
        ErrorCode.CONNECTION_TIMEOUT,
        ErrorCode.INTERFACE_FAILURE,
        ErrorCode.OPERATION_TIMEOUT,
        ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE,
    }

    def __init__(
        self,
        *,
        site_id: int,
        executable: str | Path,
        scripts_root: str | Path,
        work_dir: str | Path | None = None,
        startup_commands: Sequence[str] = ("adapter driver dummy",),
        config_files: Sequence[str | Path] = (),
        rpc_host: str = "127.0.0.1",
        rpc_connect_timeout_s: float = 0.5,
        command_timeout_s: float = 30.0,
        startup_timeout_s: float = 5.0,
        stop_timeout_s: float = 2.0,
        max_start_attempts: int = 4,
        log_tail_lines: int = 100,
        process_launcher: ProcessLauncher = asyncio.create_subprocess_exec,
        port_allocator: PortAllocator = allocate_loopback_port,
    ) -> None:
        if not isinstance(site_id, int) or isinstance(site_id, bool) or site_id < 1:
            raise ValueError("site_id must be a one-based positive integer")
        if rpc_host != "127.0.0.1":
            raise ValueError("OpenOCDWorker currently requires explicit IPv4 loopback")
        for label, value in (
            ("rpc_connect_timeout_s", rpc_connect_timeout_s),
            ("command_timeout_s", command_timeout_s),
            ("startup_timeout_s", startup_timeout_s),
            ("stop_timeout_s", stop_timeout_s),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label} must be a positive finite number")
        if not isinstance(max_start_attempts, int) or max_start_attempts < 1:
            raise ValueError("max_start_attempts must be a positive integer")
        if not isinstance(log_tail_lines, int) or log_tail_lines < 1:
            raise ValueError("log_tail_lines must be a positive integer")

        self.site_id = site_id
        self.executable = Path(executable).expanduser().resolve()
        self.scripts_root = Path(scripts_root).expanduser().resolve()
        self.work_dir = (
            Path(work_dir).expanduser().resolve()
            if work_dir is not None
            else self.executable.parent
        )
        self.startup_commands = tuple(self._validate_startup_command(item) for item in startup_commands)
        self.config_files = tuple(Path(item).expanduser().resolve() for item in config_files)
        self.rpc_host = rpc_host
        self.rpc_connect_timeout_s = float(rpc_connect_timeout_s)
        self.command_timeout_s = float(command_timeout_s)
        self.startup_timeout_s = float(startup_timeout_s)
        self.stop_timeout_s = float(stop_timeout_s)
        self.max_start_attempts = max_start_attempts
        self._process_launcher = process_launcher
        self._port_allocator = port_allocator

        self._process: asyncio.subprocess.Process | None = None
        self._rpc: OpenOCDRpcClient | None = None
        self._rpc_port: int | None = None
        self._log_task: asyncio.Task[None] | None = None
        self._log_tail: deque[str] = deque(maxlen=log_tail_lines)
        self._generation = 0
        self._last_argv: tuple[str, ...] = ()
        self._lifecycle_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()

    @staticmethod
    def _validate_startup_command(command: str) -> str:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("OpenOCD startup command must be a non-empty string")
        if any(ch in command for ch in ("\x00", "\x1a", "\n", "\r")):
            raise ValueError("OpenOCD startup command contains forbidden control characters")
        return command

    def _validate_runtime(self) -> None:
        if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD worker executable is missing or not executable",
                context={"executable": str(self.executable), "site_id": self.site_id},
            )
        if not self.scripts_root.is_dir():
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD worker scripts_root is missing",
                context={"scripts_root": str(self.scripts_root), "site_id": self.site_id},
            )
        if not self.work_dir.is_dir():
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "OpenOCD worker work_dir is missing",
                context={"work_dir": str(self.work_dir), "site_id": self.site_id},
            )
        for path in self.config_files:
            if not path.is_file():
                raise PlasmaError(
                    ErrorCode.INTERFACE_NOT_CONFIGURED,
                    "OpenOCD worker config file is missing",
                    context={"config_file": str(path), "site_id": self.site_id},
                )

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None and self._rpc is not None

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def rpc_port(self) -> int | None:
        return self._rpc_port

    @property
    def last_argv(self) -> tuple[str, ...]:
        return self._last_argv

    @property
    def log_tail(self) -> tuple[str, ...]:
        return tuple(self._log_tail)

    def status(self) -> OpenOCDWorkerStatus:
        process = self._process
        return OpenOCDWorkerStatus(
            site_id=self.site_id,
            running=self.running,
            pid=process.pid if process is not None and process.returncode is None else None,
            rpc_host=self.rpc_host,
            rpc_port=self._rpc_port,
            generation=self._generation,
        )

    def _arguments(self, port: int) -> list[str]:
        argv = [
            str(self.executable),
            "-s",
            str(self.scripts_root),
            "-c",
            f"bindto {self.rpc_host}",
            "-c",
            "gdb_port disabled",
            "-c",
            "telnet_port disabled",
            "-c",
            f"tcl_port {port}",
        ]
        for command in self.startup_commands:
            argv.extend(["-c", command])
        for path in self.config_files:
            argv.extend(["-f", str(path)])
        return argv

    async def _drain_output(self, process: asyncio.subprocess.Process) -> None:
        reader = process.stdout
        if reader is None:
            return
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                self._log_tail.append(line.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            raise
        except (ConnectionError, OSError, ValueError):
            return

    async def _wait_ready(
        self,
        process: asyncio.subprocess.Process,
        rpc: OpenOCDRpcClient,
    ) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.startup_timeout_s
        last_error: PlasmaError | None = None

        while loop.time() < deadline:
            if process.returncode is not None:
                raise PlasmaError(
                    ErrorCode.INTERFACE_FAILURE,
                    "OpenOCD worker exited before Tcl RPC became ready",
                    recoverable=True,
                    context={
                        "site_id": self.site_id,
                        "return_code": process.returncode,
                        "log_tail": list(self._log_tail),
                    },
                )
            remaining = deadline - loop.time()
            try:
                response = await rpc.command(
                    "version",
                    timeout_s=min(max(remaining, 0.05), 0.5),
                )
                if response.strip():
                    return response
                last_error = PlasmaError(
                    ErrorCode.INTERFACE_FAILURE,
                    "OpenOCD Tcl RPC readiness probe returned an empty version",
                    recoverable=True,
                )
            except PlasmaError as exc:
                last_error = exc
                await rpc.close()
            await asyncio.sleep(min(0.05, max(deadline - loop.time(), 0)))

        raise PlasmaError(
            ErrorCode.CONNECTION_TIMEOUT,
            "OpenOCD worker Tcl RPC readiness timed out",
            recoverable=True,
            original_exception=last_error,
            context={"site_id": self.site_id, "log_tail": list(self._log_tail)},
        )

    async def _stop_locked(self) -> None:
        rpc = self._rpc
        process = self._process
        log_task = self._log_task

        self._rpc = None
        self._rpc_port = None
        self._process = None
        self._log_task = None

        if process is not None and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=self.stop_timeout_s)
            except TimeoutError:
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()

        if rpc is not None:
            await rpc.close()

        if log_task is not None:
            if not log_task.done():
                try:
                    await asyncio.wait_for(log_task, timeout=0.5)
                except TimeoutError:
                    log_task.cancel()
                    try:
                        await log_task
                    except asyncio.CancelledError:
                        pass
            else:
                try:
                    log_task.result()
                except (asyncio.CancelledError, ConnectionError, OSError, ValueError):
                    pass

    async def start(self) -> OpenOCDWorkerStatus:
        async with self._lifecycle_lock:
            if self.running:
                return self.status()
            await self._stop_locked()
            self._validate_runtime()
            last_error: BaseException | None = None

            for attempt in range(1, self.max_start_attempts + 1):
                port = int(self._port_allocator())
                if not 1 <= port <= 65535:
                    raise PlasmaError(
                        ErrorCode.CONFIG_INVALID,
                        "OpenOCD worker port allocator returned an invalid port",
                        context={"port": port, "site_id": self.site_id},
                    )
                argv = self._arguments(port)
                self._last_argv = tuple(argv)
                self._log_tail.clear()

                try:
                    process = await self._process_launcher(
                        *argv,
                        cwd=self.work_dir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                except (FileNotFoundError, OSError) as exc:
                    last_error = exc
                    continue

                rpc = OpenOCDRpcClient(
                    self.rpc_host,
                    port,
                    connect_timeout_s=self.rpc_connect_timeout_s,
                    command_timeout_s=self.command_timeout_s,
                )
                self._process = process
                self._rpc = rpc
                self._rpc_port = port
                self._log_task = asyncio.create_task(
                    self._drain_output(process),
                    name=f"openocd-site-{self.site_id}-log",
                )

                try:
                    await self._wait_ready(process, rpc)
                except PlasmaError as exc:
                    last_error = exc
                    await self._stop_locked()
                    if attempt < self.max_start_attempts:
                        continue
                    break

                self._generation += 1
                return self.status()

            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                "OpenOCD worker could not start after bounded retries",
                recoverable=True,
                original_exception=last_error,
                context={
                    "site_id": self.site_id,
                    "attempts": self.max_start_attempts,
                    "last_argv": list(self._last_argv),
                    "log_tail": list(self._log_tail),
                },
            )

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            await self._stop_locked()

    async def kill(self) -> None:
        async with self._lifecycle_lock:
            rpc = self._rpc
            process = self._process
            log_task = self._log_task
            self._rpc = None
            self._rpc_port = None
            self._process = None
            self._log_task = None
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            if rpc is not None:
                await rpc.close()
            if log_task is not None and not log_task.done():
                try:
                    await asyncio.wait_for(log_task, timeout=0.5)
                except TimeoutError:
                    log_task.cancel()
                    try:
                        await log_task
                    except asyncio.CancelledError:
                        pass

    async def restart(self) -> OpenOCDWorkerStatus:
        await self.stop()
        return await self.start()

    async def _recover_after_fault(self) -> str:
        try:
            status = await self.restart()
        except PlasmaError as exc:
            return f"failed:{exc.code}"
        return f"restarted:generation={status.generation}"

    async def command(self, command: str, *, timeout_s: float | None = None) -> str:
        async with self._command_lock:
            process = self._process
            rpc = self._rpc
            if process is None or process.returncode is not None or rpc is None:
                fault = PlasmaError(
                    ErrorCode.INTERFACE_FAILURE,
                    "OpenOCD worker is not running",
                    recoverable=True,
                    context={"site_id": self.site_id},
                )
                recovery = await self._recover_after_fault()
                fault.with_context(worker_recovery=recovery)
                raise fault

            try:
                return await rpc.command(command, timeout_s=timeout_s)
            except asyncio.CancelledError:
                await asyncio.shield(self._recover_after_fault())
                raise
            except PlasmaError as exc:
                if exc.code in self.RECOVERABLE_RPC_CODES:
                    recovery = await self._recover_after_fault()
                    exc.with_context(site_id=self.site_id, worker_recovery=recovery)
                raise

    async def __aenter__(self) -> "OpenOCDWorker":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()
