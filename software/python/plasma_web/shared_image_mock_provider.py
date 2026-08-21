from __future__ import annotations

from dataclasses import replace

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_image_store import default_mock_image_store
from plasma_core.models import LOCAL_MOCK_BLOB_SCHEME, ExecutionImageRef, JobRequest

from .engineering_targets import MockEngineeringPPUProvider


class SharedImageMockEngineeringPPUProvider(MockEngineeringPPUProvider):
    """Mock multi-PPU provider that keeps normalized Images content-addressed.

    The historical Engineering provider caches the Programming Asset but sends
    normalized Image bytes through localhost for every Program/Verify Job. The
    Execution Contract from PR #89 allows a local Mock runtime to consume a
    content-addressed `execution_image_ref` instead. This adapter preserves the
    existing Engineering Provider API while removing the repeated per-Site
    binary transport.
    """

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
    ) -> dict[str, object]:
        result = super().cache_asset(
            session_id,
            facility_id,
            ppu_id,
            asset_name,
            asset_type,
            asset_format,
            asset_sha256,
            data,
        )
        asset = self._cached_asset(session_id, facility_id, ppu_id, asset_sha256)
        image = asset.normalize_image()
        default_mock_image_store().put(image.data)
        return result

    async def start_job(
        self,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
        *,
        session_id: str | None = None,
        asset_sha256: str | None = None,
    ) -> dict[str, object]:
        lease_key: tuple[str, str] | None = None
        if request.operation in {Operation.PROGRAM, Operation.VERIFY}:
            if request.image or request.image_ref is not None:
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
            shared = default_mock_image_store().resolve(image.sha256, expected_size=image.size)
            lease_key = self._key(facility_id, ppu_id)
            self._reserve_ppu_image(lease_key, image.sha256, request.job_id)
            request = replace(
                request,
                image_ref=ExecutionImageRef(
                    scheme=LOCAL_MOCK_BLOB_SCHEME,
                    sha256=shared.sha256,
                    size_bytes=shared.size_bytes,
                ),
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

        request = replace(request, timeout_s=self.job_timeout_s(facility_id, ppu_id))
        try:
            accepted = await self._client(facility_id, ppu_id).start(request)
        except Exception:
            if lease_key is not None:
                self._release_ppu_image(lease_key, request.job_id)
            raise
        if lease_key is not None:
            self._schedule_image_watch(lease_key, request.job_id)
        return accepted
