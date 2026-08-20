from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from plasma_client.client import PlasmaClient
from plasma_core.assets import ProgrammingAsset, ProgrammingAssetFormat, ProgrammingAssetType
from plasma_core.config import PPUConfig, PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest, validate_job_id
from plasma_server.server import PlasmaServer


MOCK_FACILITY_COUNT = 3
MOCK_SITE_COUNTS = (2, 4, 6, 8)
MOCK_FLASH_SIZE_BYTES = 4 * 1024 * 1024
MOCK_MAX_CACHED_ASSET_BYTES = 16 * 1024 * 1024
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
SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(slots=True)
class PPUImageLease:
    image_sha256: str
    job_ids: set[str]


class EngineeringPPUProvider(Protocol):
    """Execution boundary consumed by the Engineering Web API."""

    def catalog(self) -> dict[str, Any]: ...

    def begin_session(self, previous_session_id: str | None = None) -> dict[str, Any]: ...

    def asset_cache_status(
        self,
        session_id: str,
        facility_id: str,
        ppu_id: str,
        asset_name: str,
        asset_type: str,
        asset_format: str,
        asset_size: int,
        asset_sha256: str,
    ) -> dict[str, Any]: ...

    def cache_asset(
        self,
        session_id: str,
        facility_id: str,
        ppu_id: str,
        asset_name: str,
        asset_type: str,
        asset_format: str,
        asset_sha256: str,
        data: bytes,
    ) -> dict[str, Any]: ...

    def job_timeout_s(self, facility_id: str, ppu_id: str) -> float: ...

    async def status(
        self,
        facility_id: str,
        ppu_id: str,
        *,
        site_id: int | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def start_job(
        self,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
        *,
        session_id: str | None = None,
        asset_sha256: str | None = None,
    ) -> dict[str, Any]: ...

    async def cancel_job(self, facility_id: str, ppu_id: str, job_id: str) -> dict[str, Any]: ...

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

    Programming Asset cache scope is one browser connection session and one
    selected PPU. A session/PPU can hold multiple Assets simultaneously so a
    future workflow may reference an Image, Option, Key, Serial Number and other
    inputs without replacing unrelated entries.

    Program/Verify currently require an Image Asset that can be normalized to a
    target execution Image. Only image+binary normalization is implemented.

    The PPU-wide execution invariant is enforced on the normalized Image SHA,
    not the source Asset SHA. This matters once HEX/SREC/ELF parsers exist:
    different source files that normalize to the same target bytes represent
    the same programming resource from the PPU's concurrency perspective.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._specs = self._build_specs()
        self._servers: dict[tuple[str, str], PlasmaServer] = {}
        self._ports: dict[tuple[str, str], int] = {}
        self._output_roots: dict[tuple[str, str], Path] = {}
        self._asset_sessions: dict[
            str,
            dict[tuple[str, str], dict[str, ProgrammingAsset]],
        ] = {}
        self._ppu_image_leases: dict[tuple[str, str], PPUImageLease] = {}
        self._asset_lock = threading.Lock()
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
        with self._asset_lock:
            self._asset_sessions.clear()
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
        for _ in range(100):
            with self._asset_lock:
                if not self._ppu_image_leases:
                    break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0)
        with self._asset_lock:
            self._ppu_image_leases.clear()

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
                        "flash_size": MOCK_FLASH_SIZE_BYTES,
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

    @staticmethod
    def _validate_session_id(session_id: str) -> str:
        if not isinstance(session_id, str) or SESSION_ID_PATTERN.fullmatch(session_id) is None:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid Engineering session_id")
        return session_id

    @staticmethod
    def _validate_sha256(value: str, field: str = "asset_sha256") -> str:
        if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"invalid {field}")
        return value

    def _client(self, facility_id: str, ppu_id: str) -> PlasmaClient:
        key = self._key(facility_id, ppu_id)
        return PlasmaClient("127.0.0.1", self._ports[key])

    def begin_session(self, previous_session_id: str | None = None) -> dict[str, Any]:
        with self._asset_lock:
            if previous_session_id is not None:
                self._validate_session_id(previous_session_id)
                self._asset_sessions.pop(previous_session_id, None)
            session_id = uuid.uuid4().hex
            self._asset_sessions[session_id] = {}
        return {
            "ok": True,
            "session": {
                "session_id": session_id,
                "programming_asset_cache_scope": "connection-session-and-ppu",
                "previous_session_cleared": previous_session_id is not None,
            },
        }

    def _session(
        self,
        session_id: str,
    ) -> dict[tuple[str, str], dict[str, ProgrammingAsset]]:
        self._validate_session_id(session_id)
        with self._asset_lock:
            session = self._asset_sessions.get(session_id)
        if session is None:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Engineering session is not active")
        return session

    @staticmethod
    def _asset_payload(
        asset: ProgrammingAsset | None,
        *,
        asset_name: str,
        asset_type: str,
        asset_format: str,
        asset_size: int,
        asset_sha256: str,
        cache_hit: bool,
        uploaded: bool = False,
        session_id: str,
        facility_id: str,
        ppu_id: str,
    ) -> dict[str, Any]:
        return {
            "cache_hit": cache_hit,
            "uploaded": uploaded,
            "asset_name": asset.name if asset else asset_name,
            "asset_type": asset.asset_type.value if asset else asset_type,
            "asset_format": asset.asset_format.value if asset else asset_format,
            "asset_size": asset.size if asset else asset_size,
            "asset_sha256": asset.sha256 if asset else asset_sha256,
            "scope": {
                "session_id": session_id,
                "facility_id": facility_id,
                "ppu_id": ppu_id,
            },
        }

    def asset_cache_status(
        self,
        session_id: str,
        facility_id: str,
        ppu_id: str,
        asset_name: str,
        asset_type: str,
        asset_format: str,
        asset_size: int,
        asset_sha256: str,
    ) -> dict[str, Any]:
        key = self._key(facility_id, ppu_id)
        self._validate_sha256(asset_sha256)
        if isinstance(asset_size, bool) or not isinstance(asset_size, int) or asset_size <= 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "asset_size must be a positive integer")
        try:
            parsed_type = ProgrammingAssetType(asset_type)
            parsed_format = ProgrammingAssetFormat(asset_format)
        except ValueError as exc:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid Programming Asset type or format") from exc
        session = self._session(session_id)
        with self._asset_lock:
            entry = session.get(key, {}).get(asset_sha256)
            hit = bool(
                entry
                and entry.name == asset_name
                and entry.asset_type is parsed_type
                and entry.asset_format is parsed_format
                and entry.size == asset_size
            )
        return {
            "ok": True,
            "programming_asset": self._asset_payload(
                entry if hit else None,
                asset_name=asset_name,
                asset_type=parsed_type.value,
                asset_format=parsed_format.value,
                asset_size=asset_size,
                asset_sha256=asset_sha256,
                cache_hit=hit,
                session_id=session_id,
                facility_id=facility_id,
                ppu_id=ppu_id,
            ),
        }

    def cache_asset(
        self,
        session_id: str,
        facility_id: str,
        ppu_id: str,
        asset_name: str,
        asset_type: str,
        asset_format: str,
        asset_sha256: str,
        data: bytes,
    ) -> dict[str, Any]:
        key = self._key(facility_id, ppu_id)
        self._validate_sha256(asset_sha256)
        if len(data) > MOCK_MAX_CACHED_ASSET_BYTES:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "Engineering Programming Asset upload exceeds the mock cache limit",
                context={"size": len(data), "limit": MOCK_MAX_CACHED_ASSET_BYTES},
            )
        asset = ProgrammingAsset.from_upload(
            name=asset_name,
            asset_type=asset_type,
            asset_format=asset_format,
            data=data,
            sha256=asset_sha256,
        )
        session = self._session(session_id)
        with self._asset_lock:
            bucket = session.setdefault(key, {})
            bucket[asset.sha256] = asset
        return {
            "ok": True,
            "programming_asset": self._asset_payload(
                asset,
                asset_name=asset.name,
                asset_type=asset.asset_type.value,
                asset_format=asset.asset_format.value,
                asset_size=asset.size,
                asset_sha256=asset.sha256,
                cache_hit=True,
                uploaded=True,
                session_id=session_id,
                facility_id=facility_id,
                ppu_id=ppu_id,
            ),
        }

    def _cached_asset(
        self,
        session_id: str,
        facility_id: str,
        ppu_id: str,
        asset_sha256: str,
    ) -> ProgrammingAsset:
        key = self._key(facility_id, ppu_id)
        self._validate_sha256(asset_sha256)
        session = self._session(session_id)
        with self._asset_lock:
            entry = session.get(key, {}).get(asset_sha256)
        if entry is None:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "Engineering Programming Asset cache miss",
                context={
                    "session_id": session_id,
                    "facility_id": facility_id,
                    "ppu_id": ppu_id,
                    "asset_sha256": asset_sha256,
                },
            )
        return entry

    def _reserve_ppu_image(
        self,
        key: tuple[str, str],
        image_sha256: str,
        job_id: str,
    ) -> None:
        self._validate_sha256(image_sha256, "image_sha256")
        with self._asset_lock:
            lease = self._ppu_image_leases.get(key)
            if lease is not None and lease.image_sha256 != image_sha256:
                raise PlasmaError(
                    ErrorCode.SITE_BUSY,
                    "PPU is busy with a different normalized Image",
                    recoverable=True,
                    context={
                        "facility_id": key[0],
                        "ppu_id": key[1],
                        "active_image_sha256": lease.image_sha256,
                        "requested_image_sha256": image_sha256,
                    },
                )
            if lease is None:
                lease = PPUImageLease(image_sha256=image_sha256, job_ids=set())
                self._ppu_image_leases[key] = lease
            lease.job_ids.add(job_id)

    def _release_ppu_image(self, key: tuple[str, str], job_id: str) -> None:
        with self._asset_lock:
            lease = self._ppu_image_leases.get(key)
            if lease is None:
                return
            lease.job_ids.discard(job_id)
            if not lease.job_ids:
                self._ppu_image_leases.pop(key, None)

    async def _watch_image_job(self, key: tuple[str, str], job_id: str) -> None:
        try:
            while True:
                server = self._servers.get(key)
                if server is None:
                    return
                try:
                    runtime = server.manager.registry.get(job_id)
                except PlasmaError as exc:
                    if exc.code is not ErrorCode.JOB_NOT_FOUND:
                        return
                    await asyncio.sleep(0.05)
                    continue
                if runtime.state.terminal:
                    return
                await asyncio.sleep(0.05)
        finally:
            self._release_ppu_image(key, job_id)

    def _schedule_image_watch(self, key: tuple[str, str], job_id: str) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            self._release_ppu_image(key, job_id)
            return
        try:
            asyncio.run_coroutine_threadsafe(self._watch_image_job(key, job_id), loop)
        except RuntimeError:
            self._release_ppu_image(key, job_id)
            raise

    def job_timeout_s(self, facility_id: str, ppu_id: str) -> float:
        self._key(facility_id, ppu_id)
        return MOCK_OPERATION_TIMEOUT_S

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
                "flash_size_bytes": MOCK_FLASH_SIZE_BYTES,
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

    async def start_job(
        self,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
        *,
        session_id: str | None = None,
        asset_sha256: str | None = None,
    ) -> dict[str, Any]:
        lease_key: tuple[str, str] | None = None
        if request.operation in {Operation.PROGRAM, Operation.VERIFY}:
            if request.image:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Engineering program/verify must use a session-cached Programming Asset",
                )
            if not session_id or not asset_sha256:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Engineering program/verify requires session_id and asset_sha256",
                )
            asset = self._cached_asset(session_id, facility_id, ppu_id, asset_sha256)
            image = asset.normalize_image()
            lease_key = self._key(facility_id, ppu_id)
            self._reserve_ppu_image(lease_key, image.sha256, request.job_id)
            request = replace(
                request,
                image=image.data,
                metadata={
                    **request.metadata,
                    "image_name": image.name,
                    "source_asset_name": asset.name,
                    "source_asset_sha256": asset.sha256,
                    "source_asset_type": asset.asset_type.value,
                    "source_asset_format": asset.asset_format.value,
                },
            )
        elif session_id is not None or asset_sha256 is not None:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "session Programming Asset reference is only valid for program or verify",
            )
        request = replace(request, timeout_s=MOCK_OPERATION_TIMEOUT_S)
        try:
            accepted = await self._client(facility_id, ppu_id).start(request)
        except Exception:
            if lease_key is not None:
                self._release_ppu_image(lease_key, request.job_id)
            raise
        if lease_key is not None:
            self._schedule_image_watch(lease_key, request.job_id)
        return accepted

    async def cancel_job(self, facility_id: str, ppu_id: str, job_id: str) -> dict[str, Any]:
        return await self._client(facility_id, ppu_id).cancel(job_id)

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
