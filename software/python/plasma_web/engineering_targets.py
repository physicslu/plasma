from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from plasma_client.client import PlasmaClient
from plasma_core.assets import ProgrammingAssetFormat, ProgrammingAssetType
from plasma_core.config import PPUConfig, PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import validate_job_id
from plasma_server.server import PlasmaServer


MOCK_FACILITY_COUNT = 8
MOCK_SITE_COUNTS = (2, 4, 6, 8)
MOCK_FLASH_SIZE_BYTES = 4 * 1024 * 1024
MOCK_OPERATION_TIMEOUT_S = 90.0
MOCK_THROUGHPUT_BYTES_PER_S = {
    "erase": 2 * 1024 * 1024,
    "program": 96 * 1024,
    "verify": 192 * 1024,
    "read": 192 * 1024,
}
MOCK_OPERATION_OVERHEADS_S = {
    "erase": 1.0,
    "program": 4.0,
    "verify": 1.0,
    "read": 1.0,
}
MOCK_PROGRESS_STEPS = 20


class EngineeringPPUProvider(Protocol):
    """Execution boundary consumed by the Engineering Web API."""

    def catalog(self) -> dict[str, Any]: ...

    async def status(
        self,
        facility_id: str,
        ppu_id: str,
        *,
        site_id: int | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]: ...

    def read_output_file(
        self,
        facility_id: str,
        ppu_id: str,
        job_id: str,
        filename: str,
    ) -> bytes: ...


@dataclass(frozen=True, slots=True)
class MockPPUSpec:
    facility_id: str
    facility_name: str
    ppu_id: str
    display_name: str
    site_count: int


class MockEngineeringPPUProvider:
    """Twelve in-process PlasmaServer runtimes backed by MockInterface.

    Read-only Engineering provider: catalog, Site status and Job output files.
    Programming Jobs are submitted only through the Manager-owned Batch with an
    ACTIVE Resource Reservation (U7); the Gateway has no Job write path here.
    """

    def __init__(self, root: Path, *, flash_size_bytes: int = MOCK_FLASH_SIZE_BYTES) -> None:
        if isinstance(flash_size_bytes, bool) or not isinstance(flash_size_bytes, int) or flash_size_bytes <= 0:
            raise ValueError("Engineering mock flash_size_bytes must be a positive integer")
        self.root = root.resolve()
        self.flash_size_bytes = flash_size_bytes
        self._specs = self._build_specs()
        self._servers: dict[tuple[str, str], PlasmaServer] = {}
        self._ports: dict[tuple[str, str], int] = {}
        self._output_roots: dict[tuple[str, str], Path] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None

    @staticmethod
    def _build_specs() -> tuple[MockPPUSpec, ...]:
        specs: list[MockPPUSpec] = []
        for facility_number in range(1, MOCK_FACILITY_COUNT + 1):
            facility_id = f"mock-facility-{facility_number:02d}"
            facility_name = f"Mock Facility {facility_number:02d}"
            for ppu_number, site_count in enumerate(MOCK_SITE_COUNTS, start=1):
                specs.append(
                    MockPPUSpec(
                        facility_id=facility_id,
                        facility_name=facility_name,
                        ppu_id=f"{facility_id}-ppu-{ppu_number:02d}",
                        display_name=f"Mock PPU {ppu_number:02d}",
                        site_count=site_count,
                    )
                )
        return tuple(specs)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._ready.is_set())

    def start(self, timeout_s: float = 10.0) -> None:
        if self.running:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        self._startup_error = None
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="plasma-engineering-mock-ppu-provider",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout_s):
            raise RuntimeError("Engineering mock PPU provider startup timed out")
        if self._startup_error is not None:
            raise RuntimeError("Engineering mock PPU provider startup failed") from self._startup_error

    def close(self, timeout_s: float = 10.0) -> None:
        loop = self._loop
        thread = self._thread
        if loop is None or thread is None:
            return
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._shutdown_servers_and_watchers(),
                loop,
            )
            future.result(timeout=timeout_s)
            loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=timeout_s)
        self._thread = None
        self._loop = None
        self._ready.clear()

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._start_servers())
        except BaseException as exc:
            self._startup_error = exc
            if self._servers:
                loop.run_until_complete(self._close_servers())
            self._ready.set()
            loop.close()
            return
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            if self._servers:
                loop.run_until_complete(self._shutdown_servers_and_watchers())
            loop.close()

    async def _start_servers(self) -> None:
        for spec in self._specs:
            config = self._config_for(spec)
            server = PlasmaServer(config)
            await server.start()
            key = (spec.facility_id, spec.ppu_id)
            self._servers[key] = server
            self._ports[key] = server.address[1]
            self._output_roots[key] = config.server.output_root.resolve()

    async def _close_servers(self) -> None:
        servers = tuple(self._servers.values())
        self._servers.clear()
        self._ports.clear()
        self._output_roots.clear()
        if servers:
            await asyncio.gather(*(server.close() for server in servers))

    async def _shutdown_servers_and_watchers(self) -> None:
        await self._close_servers()

    def _config_for(self, spec: MockPPUSpec) -> PlasmaConfig:
        ppu_root = self.root / spec.ppu_id
        return PlasmaConfig(
            ppu=PPUConfig(
                id=spec.ppu_id,
                facility_id=spec.facility_id,
                model="MOCK-PPU",
                display_name=spec.display_name,
            ),
            server=ServerConfig(
                host="127.0.0.1",
                port=0,
                max_supported_sites=spec.site_count,
                max_concurrent_jobs=spec.site_count,
                max_queue_depth_per_site=4,
                output_root=ppu_root / "output",
                log_root=ppu_root / "logs",
            ),
            sites=[
                SiteConfig(
                    id=site_id,
                    enabled=True,
                    interface="mock",
                    target="MOCK-IC",
                    operation_timeout_s=MOCK_OPERATION_TIMEOUT_S,
                    max_retries=0,
                    retry_backoff_s=0.01,
                    mock={
                        "flash_size": self.flash_size_bytes,
                        "throughput_bytes_per_s": dict(MOCK_THROUGHPUT_BYTES_PER_S),
                        "operation_overheads_s": dict(MOCK_OPERATION_OVERHEADS_S),
                        "progress_steps": MOCK_PROGRESS_STEPS,
                    },
                )
                for site_id in range(1, spec.site_count + 1)
            ],
        )

    def _key(self, facility_id: str, ppu_id: str) -> tuple[str, str]:
        key = (facility_id, ppu_id)
        if key not in self._ports:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"unknown Engineering PPU: {facility_id}/{ppu_id}",
            )
        return key

    def _client(self, facility_id: str, ppu_id: str) -> PlasmaClient:
        key = self._key(facility_id, ppu_id)
        return PlasmaClient("127.0.0.1", self._ports[key])

    def catalog(self) -> dict[str, Any]:
        facilities: list[dict[str, Any]] = []
        for facility_number in range(1, MOCK_FACILITY_COUNT + 1):
            facility_id = f"mock-facility-{facility_number:02d}"
            specs = [spec for spec in self._specs if spec.facility_id == facility_id]
            facilities.append(
                {
                    "facility_id": facility_id,
                    "display_name": specs[0].facility_name,
                    "ppus": [
                        {
                            "ppu_id": spec.ppu_id,
                            "display_name": spec.display_name,
                            "model": "MOCK-PPU",
                            "site_count": spec.site_count,
                            "provider": "mock",
                        }
                        for spec in specs
                    ],
                }
            )
        return {
            "ok": True,
            "provider": "mock",
            "facility_count": len(facilities),
            "ppu_count": len(self._specs),
            "site_count": sum(spec.site_count for spec in self._specs),
            "programming_asset_scope": "connection-session-and-ppu",
            "supported_asset_types": [item.value for item in ProgrammingAssetType],
            "supported_asset_formats": [item.value for item in ProgrammingAssetFormat],
            "implemented_normalizers": [
                {
                    "asset_type": ProgrammingAssetType.IMAGE.value,
                    "asset_format": ProgrammingAssetFormat.BINARY.value,
                    "output": "normalized_image",
                }
            ],
            "timing_profile": {
                "model": "fixed-overhead-plus-bytes-over-throughput",
                "flash_size_bytes": self.flash_size_bytes,
                "throughput_bytes_per_s": dict(MOCK_THROUGHPUT_BYTES_PER_S),
                "operation_overheads_s": dict(MOCK_OPERATION_OVERHEADS_S),
                "operation_timeout_s": MOCK_OPERATION_TIMEOUT_S,
            },
            "facilities": facilities,
        }

    async def status(
        self,
        facility_id: str,
        ppu_id: str,
        *,
        site_id: int | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._client(facility_id, ppu_id).status(site_id=site_id, job_id=job_id)

    def read_output_file(
        self,
        facility_id: str,
        ppu_id: str,
        job_id: str,
        filename: str,
    ) -> bytes:
        validate_job_id(job_id)
        if not filename or Path(filename).name != filename or filename in {".", ".."}:
            raise ValueError("invalid output filename")
        output_root = self._output_roots[self._key(facility_id, ppu_id)]
        job_directory = (output_root / job_id).resolve()
        result_path = job_directory / "result.json"
        if not result_path.is_file():
            raise ValueError("job output is not available")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        allowed: set[str] = set()
        for raw_path in result.get("output_files", []):
            output_path = Path(str(raw_path))
            if output_path.resolve().parent == job_directory:
                allowed.add(output_path.name)
        requested = (job_directory / filename).resolve()
        if requested.parent != job_directory or filename not in allowed or not requested.is_file():
            raise ValueError("output file does not belong to this job")
        return requested.read_bytes()
