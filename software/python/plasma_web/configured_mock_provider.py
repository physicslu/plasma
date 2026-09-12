from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import replace
from pathlib import Path
from typing import Any

from plasma_core.assets import ProgrammingAssetFormat, ProgrammingAssetType
from plasma_core.config import PlasmaConfig, load_config
from plasma_core.enums import JobState, Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest

from .engineering_targets import MockEngineeringPPUProvider, MockPPUSpec


DEFAULT_MOCK_FLASH_SIZE_BYTES = 256 * 1024


class ConfiguredMockEngineeringPPUProvider(MockEngineeringPPUProvider):
    """Bind Engineering Programming to one already-running configured Mock PPU.

    This provider does not create the legacy 8-Facility / 32-PPU demo topology
    and does not own the local ``PlasmaServer`` lifecycle.  It reads the
    canonical PPU YAML, exposes exactly that Facility/PPU/Site identity, and
    sends normal Plasma Protocol Jobs to the independent local Server process.

    Activation is deliberately fail-closed: every configured Site must use the
    ``mock`` execution interface.  A later OpenOCD/FPGA Site therefore cannot be
    made remotely programmable merely by leaving this Z2-like mock capability
    enabled.
    """

    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path).resolve()
        initial = self._load_config()
        self._identity = (
            initial.ppu.facility_id,
            initial.ppu.id,
            initial.server.host,
            initial.server.port,
            initial.server.output_root.resolve(),
        )
        self._initial_config = initial
        flash_sizes = self._flash_sizes(initial)
        root = initial.server.output_root.resolve().parent / "engineering-configured-mock"
        super().__init__(
            root,
            flash_size_bytes=max(flash_sizes.values(), default=DEFAULT_MOCK_FLASH_SIZE_BYTES),
        )

    @staticmethod
    def _require_loopback_server(config: PlasmaConfig) -> None:
        try:
            address = ipaddress.ip_address(config.server.host)
        except ValueError as exc:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "configured Engineering mock provider requires an explicit loopback Plasma Server address",
                original_exception=exc,
            ) from exc
        if not address.is_loopback:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "configured Engineering mock provider may bind only to the local Plasma Server",
                context={"server_host": config.server.host},
            )

    @staticmethod
    def _require_mock_sites(config: PlasmaConfig) -> None:
        unsupported = [site.id for site in config.sites if site.interface != "mock"]
        if unsupported:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "configured Engineering mock provider refuses non-mock Sites",
                context={"site_ids": unsupported},
            )

    def _load_config(self) -> PlasmaConfig:
        config = load_config(self.config_path)
        self._require_loopback_server(config)
        self._require_mock_sites(config)
        return config

    def _current_config(self) -> PlasmaConfig:
        config = self._load_config()
        identity = (
            config.ppu.facility_id,
            config.ppu.id,
            config.server.host,
            config.server.port,
            config.server.output_root.resolve(),
        )
        if identity != self._identity:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "configured Engineering mock PPU identity changed while Gateway is running",
                context={
                    "expected_facility_id": self._identity[0],
                    "expected_ppu_id": self._identity[1],
                    "actual_facility_id": config.ppu.facility_id,
                    "actual_ppu_id": config.ppu.id,
                },
            )
        return config

    @staticmethod
    def _mock_flash_size(site: Any) -> int:
        value = site.mock.get("flash_size", DEFAULT_MOCK_FLASH_SIZE_BYTES)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"SITE{site.id} mock.flash_size must be a positive integer",
            )
        return value

    @classmethod
    def _flash_sizes(cls, config: PlasmaConfig) -> dict[int, int]:
        return {site.id: cls._mock_flash_size(site) for site in config.sites}

    def _build_specs(self) -> tuple[MockPPUSpec, ...]:
        config = self._initial_config
        return (
            MockPPUSpec(
                facility_id=config.ppu.facility_id,
                facility_name=config.ppu.facility_id,
                ppu_id=config.ppu.id,
                display_name=config.ppu.display_name,
                site_count=len(config.sites),
            ),
        )

    async def _start_servers(self) -> None:
        config = self._current_config()
        key = (config.ppu.facility_id, config.ppu.id)
        self._ports[key] = config.server.port
        self._output_roots[key] = config.server.output_root.resolve()
        try:
            snapshot = await self._client(*key).status()
        except Exception:
            self._ports.clear()
            self._output_roots.clear()
            raise
        ppu = snapshot.get("ppu") if isinstance(snapshot, dict) else None
        runtime_ppu_id = ppu.get("ppu_id") if isinstance(ppu, dict) else None
        if runtime_ppu_id != config.ppu.id:
            self._ports.clear()
            self._output_roots.clear()
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "configured Engineering mock provider reached the wrong local Plasma Server",
                context={"expected_ppu_id": config.ppu.id, "actual_ppu_id": runtime_ppu_id},
            )

    async def _close_servers(self) -> None:
        # The configured provider never owns the local Plasma Server lifecycle.
        return None

    async def _shutdown_servers_and_watchers(self) -> None:
        # Gateway shutdown must not stop or mutate the independently owned Server.
        with self._asset_lock:
            self._ppu_image_leases.clear()
        self._ports.clear()
        self._output_roots.clear()
        await asyncio.sleep(0)

    async def _watch_image_job(self, key: tuple[str, str], job_id: str) -> None:
        try:
            timeout_s = max(1.0, self.job_timeout_s(*key)) + 15.0
            deadline = asyncio.get_running_loop().time() + timeout_s
            while asyncio.get_running_loop().time() < deadline:
                try:
                    snapshot = await self._client(*key).status(job_id=job_id)
                    job = snapshot.get("job") if isinstance(snapshot, dict) else None
                    if isinstance(job, dict):
                        try:
                            if JobState(str(job.get("state"))).terminal:
                                return
                        except ValueError:
                            pass
                except PlasmaError:
                    # Do not fail-open the PPU-wide Image lease while the local
                    # Server may still own the accepted Job.
                    pass
                await asyncio.sleep(0.05)
        finally:
            self._release_ppu_image(key, job_id)

    def _site_config(self, site_id: int) -> Any:
        config = self._current_config()
        for site in config.sites:
            if site.id == site_id:
                return site
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            f"unknown configured Engineering Site: {site_id}",
        )

    def job_timeout_s(self, facility_id: str, ppu_id: str) -> float:
        self._key(facility_id, ppu_id)
        config = self._current_config()
        return max((float(site.operation_timeout_s) for site in config.sites), default=30.0)

    def catalog(self) -> dict[str, Any]:
        config = self._current_config()
        flash_sizes = self._flash_sizes(config)
        facility = {
            "facility_id": config.ppu.facility_id,
            "display_name": config.ppu.facility_id,
            "ppus": [
                {
                    "ppu_id": config.ppu.id,
                    "display_name": config.ppu.display_name,
                    "model": config.ppu.model,
                    "site_count": len(config.sites),
                    "provider": "configured_mock",
                }
            ],
        }
        return {
            "ok": True,
            "provider": "configured_mock",
            "facility_count": 1,
            "ppu_count": 1,
            "site_count": len(config.sites),
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
                "model": "configured-local-mock",
                "site_flash_size_bytes": {str(site_id): size for site_id, size in flash_sizes.items()},
                "operation_timeout_s": self.job_timeout_s(config.ppu.facility_id, config.ppu.id),
            },
            "facilities": [facility],
        }

    def _resolve_main_flash_read(self, request: JobRequest) -> JobRequest:
        if request.operation is not Operation.READ:
            return request
        site = self._site_config(request.site_id)
        flash_size = self._mock_flash_size(site)
        return replace(
            request,
            map_data={
                "scope": "main_flash",
                "sections": [
                    {
                        "name": "main_flash",
                        "address": 0,
                        "length": flash_size,
                    }
                ],
            },
            metadata={
                **request.metadata,
                "read_scope": "main_flash",
                "read_size_bytes": flash_size,
            },
        )

    async def start_job(
        self,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
        *,
        session_id: str | None = None,
        asset_sha256: str | None = None,
    ) -> dict[str, Any]:
        request = self._resolve_main_flash_read(request)
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
                    "configured Engineering program/verify requires session_id and asset_sha256",
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
                    "source_asset_origin": "user",
                },
            )
        elif session_id is not None or asset_sha256 is not None:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "session Programming Asset reference is only valid for program or verify",
            )

        site = self._site_config(request.site_id)
        request = replace(request, timeout_s=float(site.operation_timeout_s))
        try:
            accepted = await self._client(facility_id, ppu_id).start(request)
        except Exception:
            if lease_key is not None:
                self._release_ppu_image(lease_key, request.job_id)
            raise
        if lease_key is not None:
            self._schedule_image_watch(lease_key, request.job_id)
        return accepted
