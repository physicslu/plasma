from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import Any

import pytest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_interfaces.openocd_rpc import OpenOCDRpcClient, TCL_RPC_TERMINATOR
from plasma_interfaces.openocd_worker import OpenOCDWorker


async def _server_port(handler) -> tuple[asyncio.AbstractServer, int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    socket_info = server.sockets[0].getsockname()
    return server, int(socket_info[1])


@pytest.mark.asyncio
async def test_rpc_client_frames_commands_and_reuses_connection() -> None:
    received: list[str] = []
    connections = 0

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal connections
        connections += 1
        try:
            while True:
                framed = await reader.readuntil(TCL_RPC_TERMINATOR)
                command = framed[:-1].decode()
                received.append(command)
                writer.write(command.upper().encode() + TCL_RPC_TERMINATOR)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server, port = await _server_port(handler)
    try:
        client = OpenOCDRpcClient("127.0.0.1", port)
        assert await client.command("version") == "VERSION"
        assert await client.command("services") == "SERVICES"
        assert received == ["version", "services"]
        assert connections == 1
        await client.close()
    finally:
        server.close()
        await server.wait_closed()


def test_rpc_client_rejects_non_loopback_and_framing_injection() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OpenOCDRpcClient("0.0.0.0", 6666)

    client = OpenOCDRpcClient("127.0.0.1", 6666)
    with pytest.raises(PlasmaError) as caught:
        asyncio.run(client.command("version\x1ashutdown"))
    assert caught.value.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_rpc_timeout_invalidates_connection() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(TCL_RPC_TERMINATOR)
            await asyncio.sleep(1)
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server, port = await _server_port(handler)
    try:
        client = OpenOCDRpcClient("127.0.0.1", port, command_timeout_s=0.05)
        with pytest.raises(PlasmaError) as caught:
            await client.command("sleep 1000")
        assert caught.value.code == ErrorCode.OPERATION_TIMEOUT
        assert client.connected is False
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_rpc_incomplete_response_fails_closed() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(TCL_RPC_TERMINATOR)
        writer.write(b"partial")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server, port = await _server_port(handler)
    try:
        client = OpenOCDRpcClient("127.0.0.1", port)
        with pytest.raises(PlasmaError) as caught:
            await client.command("version")
        assert caught.value.code == ErrorCode.INTERFACE_FAILURE
        assert client.connected is False
    finally:
        server.close()
        await server.wait_closed()


class _FakeProcess:
    _next_pid = 10000

    def __init__(self, server: asyncio.AbstractServer) -> None:
        type(self)._next_pid += 1
        self.pid = type(self)._next_pid
        self.returncode: int | None = None
        self.stdout = None
        self._server = server
        self._done = asyncio.Event()
        self._writers: set[asyncio.StreamWriter] = set()

    def add_writer(self, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)

    def remove_writer(self, writer: asyncio.StreamWriter) -> None:
        self._writers.discard(writer)

    def _finish(self, returncode: int) -> None:
        if self.returncode is not None:
            return
        self.returncode = returncode
        self._server.close()
        for writer in tuple(self._writers):
            writer.close()
        self._done.set()

    def terminate(self) -> None:
        self._finish(-15)

    def kill(self) -> None:
        self._finish(-9)

    def crash(self) -> None:
        self._finish(23)

    async def wait(self) -> int:
        await self._done.wait()
        await self._server.wait_closed()
        return int(self.returncode)


class _FakeOpenOCDLauncher:
    def __init__(self) -> None:
        self.processes: list[_FakeProcess] = []

    async def __call__(self, *argv: str, **_: Any) -> _FakeProcess:
        commands = [
            argv[index + 1]
            for index, value in enumerate(argv[:-1])
            if value == "-c"
        ]
        host = next(
            command.split(maxsplit=1)[1]
            for command in commands
            if command.startswith("bindto ")
        )
        port = int(
            next(
                command.split(maxsplit=1)[1]
                for command in commands
                if command.startswith("tcl_port ")
            )
        )

        process_box: dict[str, _FakeProcess] = {}

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            process = process_box["process"]
            process.add_writer(writer)
            try:
                while True:
                    framed = await reader.readuntil(TCL_RPC_TERMINATOR)
                    command = framed[:-1].decode("utf-8")
                    if command == "version":
                        response = "Open On-Chip Debugger 0.12.0"
                    elif command.startswith("sleep "):
                        await asyncio.sleep(int(command.split()[1]) / 1000)
                        response = ""
                    elif command == "crash":
                        process.crash()
                        return
                    else:
                        response = f'invalid command name "{command}"'
                    writer.write(response.encode("utf-8") + TCL_RPC_TERMINATOR)
                    await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionError, OSError):
                pass
            finally:
                process.remove_writer(writer)
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionError, OSError):
                    pass

        server = await asyncio.start_server(handler, host, port)
        process = _FakeProcess(server)
        process_box["process"] = process
        self.processes.append(process)
        return process


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _runtime_paths(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "fake-openocd"
    executable.write_text("unit-test launcher injection\n", encoding="utf-8")
    executable.chmod(0o755)
    scripts = tmp_path / "scripts"
    (scripts / "target").mkdir(parents=True)
    (scripts / "interface").mkdir()
    return executable, scripts


@pytest.mark.asyncio
async def test_worker_security_flags_timeout_and_restart(tmp_path: Path) -> None:
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _FakeOpenOCDLauncher()
    worker = OpenOCDWorker(
        site_id=1,
        executable=executable,
        scripts_root=scripts,
        command_timeout_s=0.05,
        startup_timeout_s=1,
        process_launcher=launcher,
    )
    try:
        first = await worker.start()
        assert first.running
        assert first.hardware_runtime_ready is False
        assert "bindto 127.0.0.1" in worker.last_argv
        assert "gdb_port disabled" in worker.last_argv
        assert "telnet_port disabled" in worker.last_argv
        assert any(item.startswith("tcl_port ") for item in worker.last_argv)

        assert "Open On-Chip Debugger" in await worker.command("version")
        invalid = await worker.command("definitely_not_a_command")
        assert "invalid command name" in invalid

        with pytest.raises(PlasmaError) as caught:
            await worker.command("sleep 1000")
        assert caught.value.code == ErrorCode.OPERATION_TIMEOUT
        assert caught.value.context["worker_recovery"].startswith("restarted:")
        assert worker.generation == first.generation + 1
        assert "Open On-Chip Debugger" in await worker.command("version")
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_cancellation_restarts_before_propagating(tmp_path: Path) -> None:
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _FakeOpenOCDLauncher()
    worker = OpenOCDWorker(
        site_id=2,
        executable=executable,
        scripts_root=scripts,
        command_timeout_s=5,
        startup_timeout_s=1,
        process_launcher=launcher,
    )
    try:
        first = await worker.start()
        task = asyncio.create_task(worker.command("sleep 1000"))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert worker.generation == first.generation + 1
        assert "Open On-Chip Debugger" in await worker.command("version")
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_process_crash_recovers_for_next_command(tmp_path: Path) -> None:
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _FakeOpenOCDLauncher()
    worker = OpenOCDWorker(
        site_id=3,
        executable=executable,
        scripts_root=scripts,
        startup_timeout_s=1,
        process_launcher=launcher,
    )
    try:
        first = await worker.start()
        with pytest.raises(PlasmaError) as caught:
            await worker.command("crash")
        assert caught.value.code == ErrorCode.INTERFACE_FAILURE
        assert caught.value.context["worker_recovery"].startswith("restarted:")
        assert worker.generation == first.generation + 1
        assert "Open On-Chip Debugger" in await worker.command("version")
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_retries_port_collision(tmp_path: Path) -> None:
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _FakeOpenOCDLauncher()
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen(1)
    occupied_port = int(occupied.getsockname()[1])
    second_port = _free_port()
    ports = iter((occupied_port, second_port))
    worker = OpenOCDWorker(
        site_id=4,
        executable=executable,
        scripts_root=scripts,
        startup_timeout_s=0.2,
        max_start_attempts=2,
        port_allocator=lambda: next(ports),
        process_launcher=launcher,
    )
    try:
        status = await worker.start()
        assert status.running
        assert status.rpc_port == second_port
        assert "Open On-Chip Debugger" in await worker.command("version")
    finally:
        occupied.close()
        await worker.stop()


@pytest.mark.asyncio
async def test_eight_workers_isolate_single_site_failure(tmp_path: Path) -> None:
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _FakeOpenOCDLauncher()
    workers = [
        OpenOCDWorker(
            site_id=site_id,
            executable=executable,
            scripts_root=scripts,
            startup_timeout_s=1,
            process_launcher=launcher,
        )
        for site_id in range(1, 9)
    ]
    try:
        statuses = await asyncio.gather(*(worker.start() for worker in workers))
        assert len({status.rpc_port for status in statuses}) == 8

        await workers[3].kill()
        assert workers[3].running is False

        responses = await asyncio.gather(
            *(worker.command("version") for index, worker in enumerate(workers) if index != 3)
        )
        assert all("Open On-Chip Debugger" in response for response in responses)

        restarted = await workers[3].start()
        assert restarted.running
        assert "Open On-Chip Debugger" in await workers[3].command("version")
    finally:
        await asyncio.gather(*(worker.stop() for worker in workers), return_exceptions=True)


class _PortLaunchRecorder(_FakeOpenOCDLauncher):
    def __init__(self) -> None:
        super().__init__()
        self.launch_ports: list[int] = []

    async def __call__(self, *argv: str, **kwargs: Any) -> _FakeProcess:
        commands = [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == "-c"]
        port = int(next(x.split()[1] for x in commands if x.startswith("tcl_port ")))
        self.launch_ports.append(port)
        return await super().__call__(*argv, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("cycle", range(12))
async def test_concurrent_workers_lease_distinct_ports_before_launch(
    tmp_path: Path, cycle: int,
) -> None:
    """Deterministic duplicate-first-choice under eight simultaneous starts."""
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _PortLaunchRecorder()
    ports: set[int] = set()
    while len(ports) < 9:
        ports.add(_free_port())
    shared, *alternates = sorted(ports)
    workers: list[OpenOCDWorker] = []
    for site_id in range(1, 9):
        choices = iter((shared, alternates[site_id - 1]))
        workers.append(
            OpenOCDWorker(
                site_id=site_id,
                executable=executable,
                scripts_root=scripts,
                startup_timeout_s=1,
                process_launcher=launcher,
                port_allocator=lambda choices=choices: next(choices),
            )
        )
    try:
        statuses = await asyncio.gather(*(w.start() for w in workers))
        assert len({s.rpc_port for s in statuses}) == 8
        assert len({s.pid for s in statuses}) == 8
        # Crucial assertion: no launch attempt may reuse another live
        # worker's port (not merely eventual retry after a bind collision).
        assert len(launcher.launch_ports) == 8
        assert len(set(launcher.launch_ports)) == 8
        assert all("Open On-Chip Debugger" in response for response in
                   await asyncio.gather(*(w.command("version") for w in workers)))
        await workers[4].kill()
        assert len(await asyncio.gather(
            *(w.command("version") for i, w in enumerate(workers) if i != 4)
        )) == 7
    finally:
        await asyncio.gather(*(w.stop() for w in workers), return_exceptions=True)


@pytest.mark.asyncio
async def test_port_lease_released_on_stop_and_kill(tmp_path: Path) -> None:
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _FakeOpenOCDLauncher()
    port = _free_port()
    one = OpenOCDWorker(site_id=1, executable=executable, scripts_root=scripts,
                        port_allocator=lambda: port, process_launcher=launcher)
    two = OpenOCDWorker(site_id=2, executable=executable, scripts_root=scripts,
                        port_allocator=lambda: port, process_launcher=launcher)
    try:
        assert (await one.start()).rpc_port == port
        await one.stop()
        assert (await two.start()).rpc_port == port
        await two.kill()
        assert (await one.start()).rpc_port == port
    finally:
        await asyncio.gather(one.stop(), two.stop(), return_exceptions=True)


@pytest.mark.asyncio
async def test_port_lease_fails_closed_and_survives_other_worker_stop(tmp_path: Path) -> None:
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _PortLaunchRecorder()
    port = _free_port()
    one = OpenOCDWorker(site_id=1, executable=executable, scripts_root=scripts,
                        port_allocator=lambda: port, process_launcher=launcher)
    two = OpenOCDWorker(site_id=2, executable=executable, scripts_root=scripts,
                        port_allocator=lambda: port, max_start_attempts=2,
                        process_launcher=launcher)
    try:
        await one.start()
        with pytest.raises(PlasmaError) as caught:
            await two.start()
        assert caught.value.code == ErrorCode.INTERFACE_FAILURE
        assert launcher.launch_ports == [port]
        assert "Open On-Chip Debugger" in await one.command("version")
        await one.stop()
        assert (await two.start()).rpc_port == port
    finally:
        await asyncio.gather(one.stop(), two.stop(), return_exceptions=True)


@pytest.mark.asyncio
async def test_port_lease_released_when_launcher_raises(tmp_path: Path) -> None:
    executable, scripts = _runtime_paths(tmp_path)
    port = _free_port()

    async def failed_launcher(*_argv: str, **_kwargs: Any) -> _FakeProcess:
        raise OSError("injected launcher failure")

    failed = OpenOCDWorker(site_id=1, executable=executable, scripts_root=scripts,
                           max_start_attempts=1, port_allocator=lambda: port,
                           process_launcher=failed_launcher)
    good = OpenOCDWorker(site_id=2, executable=executable, scripts_root=scripts,
                         port_allocator=lambda: port,
                         process_launcher=_FakeOpenOCDLauncher())
    try:
        with pytest.raises(PlasmaError) as caught:
            await failed.start()
        assert caught.value.code == ErrorCode.INTERFACE_FAILURE
        assert (await good.start()).rpc_port == port
    finally:
        await asyncio.gather(failed.stop(), good.stop(), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("stop", "kill"))
async def test_cancelled_teardown_retains_port_until_child_exits(
    tmp_path: Path, method: str,
) -> None:
    """Cancellation must not free a still-listening child's RPC port."""
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _PortLaunchRecorder()
    port = _free_port()
    one = OpenOCDWorker(
        site_id=1, executable=executable, scripts_root=scripts,
        port_allocator=lambda: port, process_launcher=launcher,
    )
    two = OpenOCDWorker(
        site_id=2, executable=executable, scripts_root=scripts,
        port_allocator=lambda: port, max_start_attempts=1,
        process_launcher=launcher,
    )
    process = None
    task = None
    original = None
    try:
        await one.start()
        process = one._process
        assert process is not None
        entered = asyncio.Event()
        original = getattr(process, "terminate" if method == "stop" else "kill")
        setattr(process, "terminate" if method == "stop" else "kill",
                lambda: entered.set())
        task = asyncio.create_task(getattr(one, method)())
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        with pytest.raises(PlasmaError) as caught:
            await two.start()
        assert caught.value.code == ErrorCode.INTERFACE_FAILURE
        # A second launch would be a false ownership attempt even if bind fails.
        assert launcher.launch_ports == [port]
        original()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        assert (await two.start()).rpc_port == port
    finally:
        if process is not None and original is not None:
            setattr(process, "terminate" if method == "stop" else "kill", original)
            if process.returncode is None:
                original()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await asyncio.gather(one.stop(), two.stop(), return_exceptions=True)


@pytest.mark.asyncio
async def test_kill_queued_during_start_releases_actual_new_lease(
    tmp_path: Path,
) -> None:
    """Kill must acquire lifecycle ownership before reading the lease."""
    executable, scripts = _runtime_paths(tmp_path)
    launcher = _PortLaunchRecorder()
    port = _free_port()
    launch_entered, allow_launch = asyncio.Event(), asyncio.Event()

    async def controlled_launcher(*argv: str, **kwargs: Any) -> _FakeProcess:
        launch_entered.set()
        await allow_launch.wait()
        return await launcher(*argv, **kwargs)

    one = OpenOCDWorker(
        site_id=1, executable=executable, scripts_root=scripts,
        port_allocator=lambda: port, process_launcher=controlled_launcher,
    )
    two = OpenOCDWorker(
        site_id=2, executable=executable, scripts_root=scripts,
        port_allocator=lambda: port, max_start_attempts=1,
        process_launcher=launcher,
    )
    start_task = asyncio.create_task(one.start())
    kill_task = None
    try:
        await asyncio.wait_for(launch_entered.wait(), timeout=1)
        kill_task = asyncio.create_task(one.kill())
        await asyncio.sleep(0)  # allow kill() to block on the lifecycle lock
        allow_launch.set()
        await asyncio.wait_for(asyncio.gather(start_task, kill_task), timeout=3)
        assert not one.running
        assert (await two.start()).rpc_port == port
        assert launcher.launch_ports == [port, port]
    finally:
        allow_launch.set()
        await asyncio.gather(start_task, return_exceptions=True)
        if kill_task is not None:
            await asyncio.gather(kill_task, return_exceptions=True)
        await asyncio.gather(one.stop(), two.stop(), return_exceptions=True)
